"""Drive panel — keyboard teleop with continuous publish loop."""

from __future__ import annotations

import contextlib
import math
import re
import time
from typing import TYPE_CHECKING, ClassVar, cast

from textual.containers import Container, Horizontal
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    # Only imported for typing — runtime would create a circular import
    # (app.py imports DrivePanel).
    from command_center.app import RovacCommandCenter

# Strips Rich markup tags so we can compute the *visible* width of a
# styled cell for column alignment (markup chars don't take space on
# screen but len() counts them).
_MARKUP_RE = re.compile(r'\[/?[^\]]*\]')

# Speed presets — must match keyboard_teleop.py SPEED_STEPS/TURN_STEPS exactly
# so the two teleops have identical feel.
SPEED_PRESETS = [
    (0.05, 1.0),
    (0.10, 1.5),
    (0.15, 2.0),
    (0.20, 3.0),
    (0.30, 4.0),
    (0.40, 5.0),
    (0.50, 6.5),
]

# Publish rate for sustained driving (matches keyboard_teleop.py)
PUBLISH_HZ = 20
PUBLISH_INTERVAL = 1.0 / PUBLISH_HZ

# Arc-turn (Q/E) angular = lin_speed * ARC_ANG_SCALE. Same scale as
# keyboard_teleop.py — keeps the curve radius gear-independent.
ARC_ANG_SCALE = 2.0

# Adaptive hold window — long for the first key event, short once
# auto-repeats start streaming in. macOS Terminal.app DOES auto-repeat
# even in Textual raw mode, so this adaptive model works here too.
#   HOLD_INITIAL bridges the ~300ms gap before terminal repeat kicks in.
#   HOLD_REPEATING gives a tight stop once repeats flow.
# To force a stop earlier, press SPACE.
HOLD_INITIAL = 0.35      # seconds — single-tap hold window
HOLD_REPEATING = 0.08    # seconds — once auto-repeat is streaming
REPEAT_THRESHOLD = 2     # consecutive events to count as "repeating"

# Angular tap-ramp — fine turns on first tap, full speed once held.
# A single tap commands ANGULAR_RAMP_MIN * target; each successive event
# multiplies by repeat_count/ANGULAR_RAMP_REPEATS until it hits 1.0.
ANGULAR_RAMP_REPEATS = 6
ANGULAR_RAMP_MIN = 0.25

# If True, the tap-ramp also applies to turn-in-place (←/→) taps for even
# finer control (~10° per tap at gear 2 vs ~33° with the ramp off).
#
# keyboard_teleop.py's original analysis worried that nerfing the first tap
# to 25% angular would leave the motors below stiction break-out. Empirically
# that doesn't happen on ROVAC — the ESP32 PID's integral term ramps PWM up
# fast enough to break stiction even at 0.25 * commanded angular. Default
# True after live testing confirmed finer control feels better.
#
# Runtime toggle: press 't' on the Drive tab to flip this for the session.
# Edit this constant to change the default that the panel starts with.
DEFAULT_TAP_RAMP_TURN_IN_PLACE = True

# Output velocity smoothing — acceleration-limited ramping. Step changes
# in target velocity (e.g. 0 → 2.0 rad/s on a tap) become smooth ramps
# at these rates, which (a) cuts the integrated angle/distance of a tap
# dramatically and (b) is gentler on the drivetrain.
LINEAR_ACCEL = 1.5       # m/s² — linear ramp rate
ANGULAR_ACCEL = 10.0     # rad/s² — angular ramp rate
DECEL_SCALE = 2.5        # multiplier on accel when braking — faster stops


def _range_color(distance: float) -> str:
    if distance == float("inf") or distance <= 0:
        return "[dim]---  [/]"
    if distance < 0.2:
        return f"[red]{distance:4.2f}m[/]"
    elif distance < 0.5:
        return f"[yellow]{distance:4.2f}m[/]"
    else:
        return f"[green]{distance:4.2f}m[/]"


class DrivePanel(Widget):
    """Teleop driving panel with continuous cmd_vel publishing."""

    def __init__(self) -> None:
        super().__init__()
        self.gear = 2  # Default gear index
        # Target velocity (set by keys, with tap-ramp applied)
        self._target_linear = 0.0
        self._target_angular = 0.0
        # Smoothed output velocity (what we actually publish — ramps toward
        # target at LINEAR_ACCEL/ANGULAR_ACCEL).
        self._smooth_linear = 0.0
        self._smooth_angular = 0.0
        self._last_pub_time = 0.0
        # Tap-ramp state — count consecutive events for the same key so a
        # held key ramps to full angular over ANGULAR_RAMP_REPEATS events,
        # and a tap stays at ANGULAR_RAMP_MIN.
        self._repeat_count = 0
        self._last_key: str | None = None
        # Whether to apply the tap-ramp to turn-in-place (←/→) taps too.
        # Toggle live with 't' on the Drive tab; default lives at module top.
        self._tap_ramp_turn_in_place = DEFAULT_TAP_RAMP_TURN_IN_PLACE
        self._publish_timer: Timer | None = None
        self._hold_timer: Timer | None = None
        self._driving = False
        # Sustained-condition tracker for pipeline health (used by stuck-motor
        # rule etc.). Keyed by check name → monotonic timestamp when the
        # condition first became True, or None when it's currently False.
        self._sustained_state: dict[str, float | None] = {}

    @property
    def _app(self) -> RovacCommandCenter:
        """Typed accessor for the host App.

        Widget.app returns App[Any] (Textual's base class), but our app is
        RovacCommandCenter which exposes .ros and .log_message. Casting via
        a single accessor centralises the cost and lets mypy verify those
        attribute accesses across drive.py.
        """
        return cast("RovacCommandCenter", self.app)

    @staticmethod
    def _step_toward(current: float, target: float,
                     accel: float, dt: float) -> float:
        """Move `current` toward `target` at acceleration-limited rate.

        Brakes faster (DECEL_SCALE * accel) when reducing magnitude or
        reversing direction, so stops are crisp. Ported verbatim from
        keyboard_teleop.py — keep them in sync if you tune one.
        """
        diff = target - current
        if abs(target) < abs(current) or target * current < 0:
            rate = accel * DECEL_SCALE
        else:
            rate = accel
        max_step = rate * dt
        if abs(diff) <= max_step:
            return target
        return current + math.copysign(max_step, diff)

    def compose(self):
        with Container(classes="panel-box-green") as c:
            c.border_title = "Controls"
            yield Static("[dim]Loading...[/]", id="drive-controls")

        with Horizontal(id="drive-lower"):
            with Container(classes="panel-box-cyan") as c:
                c.border_title = "Odometry"
                yield Static(
                    "(+0.00, +0.00)  yaw +0.0\u00b0\n"
                    "v=+0.00 m/s  \u03c9=+0.00 r/s\n"
                    "dist 0.0m  odom 0.0Hz",
                    id="drive-odom",
                )

            with Container(classes="panel-box-yellow") as c:
                c.border_title = "Proximity"
                yield Static(
                    "        Top: [dim]---  [/]\n [dim]---  [/]   [bold]\u25fc[/]   [dim]---  [/]\n"
                    "        Bot: [dim]---  [/]\n\n Status: [green]CLEAR[/]",
                    id="drive-proximity",
                )

        # Pipeline Health \u2014 at-a-glance diagnosis of the 5-hop chain from
        # this panel's keypress to motor PWM. See _compute_pipeline_status
        # for the cell logic and _update_pipeline_health for the rendering.
        with Container(classes="panel-box-magenta") as c:
            c.border_title = "Pipeline Health"
            yield Static(
                "[dim]waiting for ROS bridge\u2026[/]\n\n\n",
                id="drive-pipeline",
            )

    def on_mount(self) -> None:
        self._refresh_controls_display()

    def process_key(self, key: str) -> bool:
        """Handle drive key presses. Called by App dispatcher.

        Computes a target velocity from the key + current gear, applies the
        angular tap-ramp (so the first tap commands a fraction of full
        angular speed), then hands off to _set_drive which manages the
        publish timer and hold timeout.
        """
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]

        # ── Decode key → raw target velocities ────────────────────────────
        if key in ("w", "up"):
            new_lin, new_ang = lin_speed, 0.0
        elif key in ("s", "down"):
            new_lin, new_ang = -lin_speed, 0.0
        elif key in ("a", "left"):
            new_lin, new_ang = 0.0, ang_speed
        elif key in ("d", "right"):
            new_lin, new_ang = 0.0, -ang_speed
        elif key == "q":
            new_lin, new_ang = lin_speed, lin_speed * ARC_ANG_SCALE
        elif key == "e":
            new_lin, new_ang = lin_speed, -lin_speed * ARC_ANG_SCALE
        elif key == "space":
            self._stop_immediately()
            return True
        elif key in ("equal", "plus"):
            self.gear = min(self.gear + 1, len(SPEED_PRESETS) - 1)
            if self._driving:
                self._rescale_targets_for_new_gear()
            self._refresh_controls_display()
            return True
        elif key in ("minus", "underscore"):
            self.gear = max(self.gear - 1, 0)
            if self._driving:
                self._rescale_targets_for_new_gear()
            self._refresh_controls_display()
            return True
        elif key == "t":
            # Toggle whether turn-in-place taps get the angular tap-ramp.
            # ON  (default) → tap-in-place commands ANGULAR_RAMP_MIN fraction
            #                 (~10° at gear 2 — finer control)
            # OFF           → tap-in-place commands full angular speed,
            #                 smoothed only by accel/decel limits (~26° at
            #                 gear 2). Flip to OFF if you want bigger nudges.
            self._tap_ramp_turn_in_place = not self._tap_ramp_turn_in_place
            state = "ON" if self._tap_ramp_turn_in_place else "OFF"
            with contextlib.suppress(Exception):
                self._app.log_message(
                    f"Drive: turn-in-place tap-ramp -> {state}"
                )
            self._refresh_controls_display()
            return True
        else:
            return False

        # ── Track repeat count for the same key ───────────────────────────
        # Same key → growing repeat_count (drives both adaptive hold AND
        # the angular ramp). Different key → reset to 1.
        if key == self._last_key:
            self._repeat_count += 1
        else:
            self._repeat_count = 1
            self._last_key = key

        # ── Apply angular tap-ramp ────────────────────────────────────────
        # Turn-in-place (pure rotation): skip the ramp by default — kb_teleop
        # comment notes that 25% angular at low gears can't break stiction.
        # Press 't' to toggle live; edit DEFAULT_TAP_RAMP_TURN_IN_PLACE at
        # module top to change the panel's startup default.
        is_turn_in_place = abs(new_lin) < 1e-3
        apply_ramp = (new_ang != 0.0
                      and (not is_turn_in_place
                           or self._tap_ramp_turn_in_place))
        if apply_ramp:
            ramp = max(ANGULAR_RAMP_MIN,
                       min(1.0, self._repeat_count / ANGULAR_RAMP_REPEATS))
            new_ang *= ramp

        self._set_drive(new_lin, new_ang)
        return True

    def _set_drive(self, linear: float, angular: float) -> None:
        """Latch a new target and (re)arm the publish timer + hold timeout."""
        self._target_linear = linear
        self._target_angular = angular
        self._driving = True

        # Start the smoothing/publish loop if it's not already running.
        if self._publish_timer is None:
            self._last_pub_time = 0.0  # reset so the first dt is sane
            self._publish_timer = self.set_interval(
                PUBLISH_INTERVAL, self._publish_tick
            )

        # Adaptive hold: long window on the first event, short once terminal
        # auto-repeat is streaming in.
        hold_window = (HOLD_REPEATING
                       if self._repeat_count >= REPEAT_THRESHOLD
                       else HOLD_INITIAL)
        self._reset_hold_timer(hold_window)

        # Publish the first smoothed value immediately (otherwise we wait
        # PUBLISH_INTERVAL = 50ms for the timer's first tick, adding noticeable
        # latency to a key press).
        self._publish_tick()
        self._refresh_controls_display()

    def _publish_tick(self) -> None:
        """Smooth output velocity toward target, publish, self-cancel on idle.

        The smoother turns a step change (e.g. 0 → 2.0 rad/s on a tap) into
        a ramp at ANGULAR_ACCEL rad/s². On the trailing edge (hold timer
        expires → target = 0), output decays at DECEL_SCALE * accel and the
        timer self-cancels once both target and smoothed values are ~zero.

        SELF-CANCELING: only cancels when target AND smoothed are both at
        rest. This is critical — if we cancelled the moment _driving went
        False, we'd leave the last non-zero velocity published and the ESP32
        watchdog would have to time it out abruptly.
        """
        now = time.monotonic()
        dt = (now - self._last_pub_time
              if self._last_pub_time > 0 else PUBLISH_INTERVAL)
        self._last_pub_time = now
        dt = min(dt, 0.1)  # cap to prevent jumps after pauses (tab switch)

        self._smooth_linear = self._step_toward(
            self._smooth_linear, self._target_linear, LINEAR_ACCEL, dt)
        self._smooth_angular = self._step_toward(
            self._smooth_angular, self._target_angular, ANGULAR_ACCEL, dt)

        fully_stopped = (
            not self._driving
            and abs(self._smooth_linear) < 1e-3
            and abs(self._smooth_angular) < 1e-3
            and abs(self._target_linear) < 1e-4
            and abs(self._target_angular) < 1e-4
        )
        if fully_stopped:
            # One final zero so the mux sees an explicit stop (otherwise the
            # last published value just stops being refreshed, and mux would
            # treat the connection as 'TELEOP still active' until its 0.5s
            # timeout — which then drops priority to /cmd_vel_joy or /nav).
            if self._app.ros:
                self._app.ros.publish_cmd_vel(0.0, 0.0)
            if self._publish_timer is not None:
                self._publish_timer.stop()
                self._publish_timer = None
            self._last_pub_time = 0.0
            return

        if self._app.ros:
            self._app.ros.publish_cmd_vel(
                self._smooth_linear, self._smooth_angular)

    def _reset_hold_timer(self, duration: float) -> None:
        """Restart the hold timeout — fires _hold_timer_expired after `duration`
        seconds of no key events. Duration is supplied by caller so the
        adaptive HOLD_INITIAL vs HOLD_REPEATING decision lives in process_key.
        """
        if self._hold_timer is not None:
            self._hold_timer.stop()
        self._hold_timer = self.set_timer(duration, self._hold_timer_expired)

    def _hold_timer_expired(self) -> None:
        """No key events arrived within the hold window — release the throttle
        but let the smoother decelerate gracefully. Resets the tap-ramp state
        so the next press starts fresh.
        """
        self._target_linear = 0.0
        self._target_angular = 0.0
        self._driving = False
        self._repeat_count = 0
        self._last_key = None
        # DON'T stop the publish timer — it'll self-cancel from _publish_tick
        # once smoothed values decay to zero. That's what makes the stop
        # smooth instead of an abrupt cut.
        self._refresh_controls_display()

    def _stop_immediately(self) -> None:
        """Hard stop — for SPACE (E-stop). Zero everything, kill timers,
        publish one final zero. No deceleration ramp.
        """
        self._target_linear = 0.0
        self._target_angular = 0.0
        self._smooth_linear = 0.0
        self._smooth_angular = 0.0
        self._driving = False
        self._repeat_count = 0
        self._last_key = None

        if self._app.ros:
            self._app.ros.publish_cmd_vel(0.0, 0.0)

        if self._publish_timer is not None:
            self._publish_timer.stop()
            self._publish_timer = None
        if self._hold_timer is not None:
            self._hold_timer.stop()
            self._hold_timer = None
        self._last_pub_time = 0.0
        self._refresh_controls_display()

    def _rescale_targets_for_new_gear(self) -> None:
        """When the user changes gear mid-drive, scale current target velocities
        to match the new preset, preserving direction.
        """
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]
        if abs(self._target_linear) > 0.001:
            sign = 1.0 if self._target_linear > 0 else -1.0
            self._target_linear = sign * lin_speed
        if abs(self._target_angular) > 0.001:
            sign = 1.0 if self._target_angular > 0 else -1.0
            # Arc turns (linear != 0) use lin_speed * ARC_ANG_SCALE so the
            # curve radius stays consistent; pure rotation uses full angular.
            if abs(self._target_linear) > 0.001:
                self._target_angular = sign * lin_speed * ARC_ANG_SCALE
            else:
                self._target_angular = sign * ang_speed

    def _refresh_controls_display(self) -> None:
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]
        gear_num = self.gear + 1
        total_gears = len(SPEED_PRESETS)

        # Show the smoothed output (what we're actually publishing) so the
        # display tracks reality during the accel/decel ramps. kb_teleop
        # shows this same value as 'Out:'.
        lin_out = self._smooth_linear
        ang_out = self._smooth_angular
        moving = abs(lin_out) > 0.005 or abs(ang_out) > 0.005
        out_color = "green" if (self._driving or moving) else "dim"

        # Tap-ramp toggle indicator — green when ON (finer ←/→ taps),
        # dim when OFF (full angular on tap, smoothed only by accel limit).
        if self._tap_ramp_turn_in_place:
            tap_state = "[green bold]ON [/]"
        else:
            tap_state = "[dim]OFF[/]"

        text = (
            "        [bold]W/Up[/] Fwd     [bold]Q[/] Arc-L     "
            f"Gear [bold]{gear_num}[/]/{total_gears}  "
            f"[bold]{lin_speed:.2f}[/] m/s  [bold]{ang_speed:.1f}[/] rad/s\n"
            "  [bold]A/Left[/] [bold]SPACE[/] [bold]D/Right[/]   [bold]E[/] Arc-R     "
            f"[{out_color}]Out: lin={lin_out:+.2f} ang={ang_out:+.2f}[/]\n"
            f"        [bold]S/Down[/] Rev    [bold]+/-[/] Speed     "
            f"[bold]T[/] Tap-ramp ←/→: {tap_state}"
        )
        with contextlib.suppress(Exception):
            self.query_one("#drive-controls", Static).update(text)

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        self._update_odom(state)
        self._update_proximity(state)
        self._update_pipeline_health(state)

    def _update_odom(self, state: dict) -> None:
        x = state.get("odom_x", 0)
        y = state.get("odom_y", 0)
        yaw_deg = math.degrees(state.get("odom_yaw", 0))
        vx = state.get("odom_vx", 0)
        wz = state.get("odom_wz", 0)
        dist = state.get("odom_total_dist", 0)
        hz = state.get("odom_hz", 0)

        lines = [
            f"({x:+.2f}, {y:+.2f})  yaw {yaw_deg:+.1f}\u00b0",
            f"v={vx:+.2f} m/s  \u03c9={wz:+.2f} r/s",
            f"dist {dist:.1f}m  odom {hz:.1f}Hz",
        ]
        with contextlib.suppress(Exception):
            self.query_one("#drive-odom", Static).update("\n".join(lines))

    def _update_proximity(self, state: dict) -> None:
        ft = state.get("ultra_front_top", float("inf"))
        fb = state.get("ultra_front_bottom", float("inf"))
        left = state.get("ultra_left", float("inf"))
        right = state.get("ultra_right", float("inf"))
        obstacle = state.get("obstacle_detected", False)

        text = (
            f"        Top: {_range_color(ft)}\n"
            f" {_range_color(left)}   [bold]\u25fc[/]   {_range_color(right)}\n"
            f"        Bot: {_range_color(fb)}\n"
            "\n"
            f" Status: {'[red bold]OBSTACLE[/]' if obstacle else '[green]CLEAR[/]'}"
        )
        with contextlib.suppress(Exception):
            self.query_one("#drive-proximity", Static).update(text)

    # \u2500\u2500\u2500 Pipeline Health \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    # Diagnoses the 5-hop chain from a keypress in this panel to a motor
    # PWM pulse:  MAC pub \u2192 DDS+MUX \u2192 MUX active source \u2192 ESP32 alive \u2192
    # motors actually responding. Each cell is a traffic light.

    _PIPELINE_LABELS = ("MAC", "DDS", "MUX", "ESP32", "MTR")

    # Visible column width for each cell on rows 1 and 2. Wide enough to
    # fit the longest metric ("0.15\u21920.13 87%") plus a label, so rows
    # column-align cleanly.
    _PIPELINE_COL_WIDTH = 14

    # Status -> Rich color name. 'red' is also bolded by callers so the
    # severity hierarchy reads correctly even on monochrome terminals.
    # ClassVar so static analyzers know we never reassign this on an
    # instance \u2014 it's an immutable lookup table.
    _STATUS_COLORS: ClassVar[dict[str, str]] = {
        "green": "green",
        "yellow": "yellow",
        "red": "red",
        "grey": "dim",
    }

    @staticmethod
    def _strip_markup(s: str) -> str:
        """Return `s` with all Rich markup removed \u2014 used for visible-width
        computation when right-padding a styled cell to a fixed column."""
        return _MARKUP_RE.sub('', s)

    @classmethod
    def _pad_visible(cls, text: str, width: int) -> str:
        """Right-pad `text` to `width` *visible* columns (markup-aware)."""
        visible_len = len(cls._strip_markup(text))
        return text + ' ' * max(0, width - visible_len)

    @classmethod
    def _glyph(cls, color: str, leftmost_red: bool = False) -> str:
        """Traffic-light cell glyph. `leftmost_red=True` adds reverse-video
        emphasis so the eye snaps to the actual root cause among multiple
        red cells (downstream reds are usually consequences)."""
        if color == "green":
            return "[green]\u25cf[/]"
        if color == "yellow":
            return "[yellow]\u25cf[/]"
        if color == "red":
            return "[red bold reverse]\u25cf[/]" if leftmost_red else "[red bold]\u25cf[/]"
        return "[dim]\u25cb[/]"  # grey / idle / not-applicable

    @classmethod
    def _color_label(cls, label: str, color: str,
                     leftmost_red: bool = False) -> str:
        """Wrap a cell label in its status color (polish item: color-coded
        labels). Leftmost-red gets reverse video to match its glyph."""
        rich_color = cls._STATUS_COLORS.get(color, "dim")
        if color == "red" and leftmost_red:
            return f"[red bold reverse]{label}[/]"
        if color == "red":
            return f"[red bold]{label}[/]"
        return f"[{rich_color}]{label}[/]"

    def _check_sustained(self, condition: bool, key: str,
                         duration: float) -> bool:
        """Return True only if `condition` has been continuously True for
        `duration` seconds across calls. Resets when condition goes False.

        Use a unique `key` per check site \u2014 this is how we distinguish e.g.
        the stuck-motor timer from a future stuck-mux timer.
        """
        import time
        now = time.monotonic()
        if condition:
            start = self._sustained_state.get(key)
            if start is None:
                self._sustained_state[key] = now
                return False
            return (now - start) >= duration
        else:
            self._sustained_state[key] = None
            return False

    def _sustained_elapsed(self, key: str) -> float:
        """Seconds since `key`'s sustained condition first became True, or
        0.0 if the timer is currently reset. Used to render the countdown
        on yellow cells (polish item: yellow shows '(1.2s/2.0s)')."""
        import time
        start = self._sustained_state.get(key)
        return (time.monotonic() - start) if start is not None else 0.0

    def _compute_pipeline_status(
        self, sig: dict
    ) -> tuple[list[str], str]:
        """Decide the 5 traffic-light colors + hint for the pipeline strip.

        Cells (left \u2192 right follow the signal chain):
          [0] MAC publishing       Mac \u2192 /cmd_vel_teleop
          [1] DDS + MUX            /cmd_vel ticking on Pi (mux output)
          [2] MUX active           mux choosing 'teleop' (vs joy/nav)
          [3] ESP32 alive          firmware/USB/driver chain (always-on)
          [4] Motors responding    odom effort tracks commanded effort

        4-state colors (green/yellow/red/grey). Yellow = "warming up or
        degraded but functional." Hint surfaces the leftmost red because
        downstream cells are usually consequences, not causes.
        """
        # Foundational gate: bridge dead \u2192 no other signal is meaningful.
        if not sig['ros_connected']:
            return (["grey"] * 5, "ROS bridge not connected")

        driving = sig['driving']

        # \u2500\u2500 Cell 0: MAC publishing \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Drive panel publishes at 20 Hz while a key is held.
        if not driving:
            mac = "grey"
        elif sig['teleop_hz'] >= 5:
            mac = "green"
        elif sig['teleop_hz'] >= 1:
            mac = "yellow"
        else:
            mac = "red"

        # \u2500\u2500 Cell 1: DDS round trip + MUX forwarding \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # /cmd_vel is Pi-published; Mac receiving it proves DDS works
        # AND the mux is converting teleop \u2192 /cmd_vel.
        if not driving:
            dds = "grey"
        elif sig['cmd_vel_hz'] >= 5:
            dds = "green"
        elif sig['cmd_vel_hz'] >= 1:
            dds = "yellow"
        else:
            dds = "red"

        # \u2500\u2500 Cell 2: MUX choosing 'TELEOP' \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # cmd_vel_mux.py publishes uppercase labels: 'TELEOP', 'JOYSTICK',
        # 'OBSTACLE', 'NAV', 'IDLE'. ('' means we haven't received any
        # value yet \u2014 mux service down OR transient_local cache empty.)
        # Sustained-checked because mux switches sources on its 0.5 s
        # teleop timeout \u2014 yellow during the handoff window, red once
        # persistent.
        mux_silent = sig['mux_active'] in ('', 'IDLE')
        mux_wrong = sig['mux_active'] not in ('', 'IDLE', 'TELEOP')
        silent_sustained = self._check_sustained(
            driving and mux_silent,
            key='mux_silent', duration=2.0)
        wrong_sustained = self._check_sustained(
            driving and mux_wrong,
            key='mux_wrong', duration=0.5)

        if not driving:
            mux = "grey"
        elif sig['mux_active'] == 'TELEOP':
            mux = "green"
        elif mux_silent:
            # IDLE while driving = our messages aren't reaching the mux
            # (QoS mismatch / topic name typo / DDS dropped us).
            mux = "red" if silent_sustained else "yellow"
        else:
            mux = "red" if wrong_sustained else "yellow"

        # \u2500\u2500 Cell 3: ESP32 alive (always-on) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # /odom target is ~20 Hz. <10 = degraded; <2 = effectively dead.
        if sig['odom_hz'] >= 10:
            esp32 = "green"
        elif sig['odom_hz'] >= 2:
            esp32 = "yellow"
        else:
            esp32 = "red"

        # \u2500\u2500 Cell 4: motors actually responding \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # Effort = |linear| + 0.5\u00b7|angular|. Angular weighted lower
        # because rad/s and m/s scales differ (max 6.5 vs 0.57). 0.3
        # ratio floor covers PID rise time; 0.8 s sustained avoids
        # false-flagging the first frames of acceleration. Always
        # evaluate so the timer auto-resets when state changes.
        cmd_effort = abs(sig['cmd_lin']) + 0.5 * abs(sig['cmd_ang'])
        actual_effort = abs(sig['odom_vx']) + 0.5 * abs(sig['odom_wz'])
        stuck_now = (
            driving
            and esp32 != "red"
            and cmd_effort > 0.04
            and actual_effort < 0.3 * cmd_effort
        )
        stuck_sustained = self._check_sustained(
            stuck_now, key='motor_stuck', duration=0.8)

        if not driving:
            mtr = "grey"
        elif esp32 == "red":
            # No odometry \u2192 can't verify motor response; don't
            # double-flag the same root cause.
            mtr = "yellow"
        elif stuck_sustained:
            mtr = "red"
        else:
            mtr = "green"

        statuses = [mac, dds, mux, esp32, mtr]

        # \u2500\u2500 Hint: leftmost red wins \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if mac == "red":
            hint = "MAC not publishing \u2014 ROS bridge dead or DDS broken"
        elif dds == "red":
            hint = ("/cmd_vel silent on Pi \u2014 re-source ros2_env.sh "
                    "or check rovac-edge-mux")
        elif mux == "red":
            if sig['mux_active'] == 'IDLE':
                hint = ("MUX shows IDLE while driving \u2014 teleop msgs not "
                        "reaching mux (QoS mismatch?)")
            elif sig['mux_active'] == '':
                hint = "MUX silent \u2014 rovac-edge-mux service likely down"
            else:
                # Map mux's display label \u2192 actual /cmd_vel_* topic suffix.
                topic_suffix = {
                    'JOYSTICK': 'joy',
                    'OBSTACLE': 'obstacle',
                    'NAV': 'smoothed',
                }.get(sig['mux_active'], sig['mux_active'].lower())
                hint = (f"MUX active='{sig['mux_active']}' \u2014 kill stale "
                        f"publisher on /cmd_vel_{topic_suffix}")
        elif esp32 == "red":
            hint = ("ESP32 odom silent \u2014 check /dev/esp32_motor and "
                    "rovac-edge-motor-driver")
        elif mtr == "red":
            hint = ("Motors commanded but not moving \u2014 12V power switch? "
                    "mechanical jam? motor driver IC?")
        else:
            hint = ""

        return statuses, hint

    def _update_pipeline_health(self, state: dict) -> None:
        """Build the signal dict, run diagnostics, render the 4-row panel.

        Row 1 \u2014 pipeline cells with traffic-light glyphs (colored labels,
                leftmost-red emphasized in reverse video).
        Row 2 \u2014 per-cell metrics (Hz / mux source / cmd\u2192actual ratio,
                with countdown for yellow MUX cell).
        Row 3 \u2014 safety/context (cliff, closest obstacle, edge services).
        Row 4 \u2014 diagnostic hint (red on problems, dim when idle/nominal).
        """
        # Pull Hz values from the bridge's private trackers \u2014 they live
        # on _hz, not in state, because state stores cached scalars and
        # these are derived metrics. Tolerant of missing keys for the
        # window between bridge thread start and first subscription.
        bridge = self._app.ros
        teleop_hz = 0.0
        cmd_vel_hz = 0.0
        ros_connected = False
        if bridge is not None:
            ros_connected = bool(state.get("ros_connected", False))
            try:
                teleop_hz = bridge._hz["cmd_vel_teleop"].hz()
                cmd_vel_hz = bridge._hz["cmd_vel"].hz()
            except (KeyError, AttributeError):
                pass

        cmd_lin = float(state.get("cmd_vel_linear", 0.0))
        cmd_ang = float(state.get("cmd_vel_angular", 0.0))
        driving = abs(cmd_lin) > 0.01 or abs(cmd_ang) > 0.01

        sig = {
            "driving": driving,
            "cmd_lin": cmd_lin,
            "cmd_ang": cmd_ang,
            "odom_vx": float(state.get("odom_vx", 0.0)),
            "odom_wz": float(state.get("odom_wz", 0.0)),
            "teleop_hz": teleop_hz,
            "cmd_vel_hz": cmd_vel_hz,
            "mux_active": state.get("mux_active", "") or "",
            "odom_hz": float(state.get("odom_hz", 0.0)),
            "ros_connected": ros_connected,
        }

        try:
            statuses, hint = self._compute_pipeline_status(sig)
        except Exception as e:
            statuses = ["red"] * 5
            hint = f"pipeline diagnostic error: {e}"

        # Defensive shape guard \u2014 a typo in compute() must never crash
        # the whole Drive panel. Pad/truncate to exactly 5 statuses.
        statuses = (list(statuses) + ["grey"] * 5)[:5]

        # Find the leftmost red so it can be visually distinguished \u2014
        # downstream reds are usually consequences of an upstream cause.
        try:
            leftmost_red = statuses.index("red")
        except ValueError:
            leftmost_red = -1

        # \u2500\u2500 Row 1: cells (label + glyph), column-aligned \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        row1_cells = []
        # strict=True: defensive — we just padded `statuses` to length 5 to
        # match the 5-label tuple, so a mismatch here would be a real bug.
        for i, (label, status) in enumerate(
                zip(self._PIPELINE_LABELS, statuses, strict=True)):
            is_lr = (i == leftmost_red)
            cell = (f"{self._color_label(label, status, is_lr)} "
                    f"{self._glyph(status, is_lr)}")
            row1_cells.append(self._pad_visible(cell, self._PIPELINE_COL_WIDTH))
        row1 = " \u2500\u2192 ".join(row1_cells)

        # \u2500\u2500 Row 2: per-cell metrics \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        metrics = self._build_pipeline_metrics(sig, statuses)
        row2_cells = [
            self._pad_visible(m, self._PIPELINE_COL_WIDTH) for m in metrics
        ]
        # Use 4-space connector to match " \u2500\u2192 " width on row 1 (4 visible
        # cols), so columns line up directly under their cells.
        row2 = "    ".join(row2_cells)

        # \u2500\u2500 Row 3: safety / context \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        row3 = self._build_pipeline_safety_row(state)

        # \u2500\u2500 Row 4: hint \u2014 leftmost-red text, idle text, or nominal \u2500\u2500\u2500
        if hint:
            hint_line = f"[red bold]{hint}[/]"
        elif driving:
            hint_line = "[green dim]all checkpoints nominal[/]"
        else:
            hint_line = (
                "[dim]idle \u2014 press a drive key to test the full pipeline[/]"
            )

        with contextlib.suppress(Exception):
            self.query_one("#drive-pipeline", Static).update(
                f"{row1}\n{row2}\n{row3}\n{hint_line}"
            )

    def _build_pipeline_metrics(
        self, sig: dict, statuses: list
    ) -> list[str]:
        """Per-cell metric strings for row 2. Uses Rich markup for color.

        - MAC/DDS: publish rate (e.g. '20Hz'). Yellow shows countdown if
                   we ever wire a sustained timer there (currently no).
        - MUX:     active source name; if yellow, append elapsed/limit
                   (e.g. 'JOYSTICK 0.3/.5s') so user can predict the flip.
        - ESP32:   /odom rate.
        - MTR:     command vs actual on the dominant axis with percent
                   tracking (e.g. '0.15\u21920.13 87%'). 'STUCK' when red.
        """
        mac, dds, mux, esp32, mtr = statuses
        mux_active = sig['mux_active']

        # MAC \u2014 show our outgoing publish rate
        mac_metric = self._color_metric(f"{sig['teleop_hz']:.0f}Hz", mac)

        # DDS \u2014 show /cmd_vel rate (mux output, proves Pi side alive)
        dds_metric = self._color_metric(f"{sig['cmd_vel_hz']:.0f}Hz", dds)

        # MUX \u2014 show source label, plus countdown when yellow
        if mux == "yellow":
            if mux_active in ('', 'IDLE'):
                elapsed = self._sustained_elapsed('mux_silent')
                label = mux_active or 'IDLE'
                mux_metric = f"[yellow]{label} {elapsed:.1f}/2.0s[/]"
            else:
                elapsed = self._sustained_elapsed('mux_wrong')
                # Truncate long labels to keep column width
                short = mux_active[:8]
                mux_metric = f"[yellow]{short} {elapsed:.1f}/.5s[/]"
        else:
            display = mux_active if mux_active else "\u2014"
            mux_metric = self._color_metric(display, mux)

        # ESP32 \u2014 show /odom rate (always-on)
        esp32_metric = self._color_metric(f"{sig['odom_hz']:.0f}Hz", esp32)

        # MTR \u2014 cmd vs actual on the dominant axis. We show whichever
        # axis we're commanding harder so a pure rotation reads sensibly.
        mtr_metric = self._build_motor_metric(sig, mtr)

        return [mac_metric, dds_metric, mux_metric, esp32_metric, mtr_metric]

    @classmethod
    def _color_metric(cls, text: str, status: str) -> str:
        """Wrap a metric value in its status color."""
        rich = cls._STATUS_COLORS.get(status, "dim")
        return f"[{rich}]{text}[/]"

    def _build_motor_metric(self, sig: dict, mtr_status: str) -> str:
        """Format the MTR cell metric: cmd\u2192actual on the dominant axis,
        with a percentage when we have meaningful command magnitude."""
        if not sig['driving']:
            return "[dim]\u2014[/]"
        if mtr_status == "yellow":
            # ESP32 dead \u2192 no odometry to compare against
            return "[yellow]?[/]"

        # Pick the axis with the larger commanded magnitude (with a
        # 0.5 weight on angular to compensate for unit-scale mismatch).
        lin_mag = abs(sig['cmd_lin'])
        ang_mag = abs(sig['cmd_ang']) * 0.5
        if lin_mag >= ang_mag and lin_mag > 0.001:
            cmd_v = sig['cmd_lin']
            act_v = sig['odom_vx']
        elif ang_mag > 0.001:
            cmd_v = sig['cmd_ang']
            act_v = sig['odom_wz']
        else:
            return self._color_metric("\u2014", mtr_status)

        pct = abs(act_v) / abs(cmd_v) * 100 if abs(cmd_v) > 0.001 else 0
        body = f"{cmd_v:+.2f}\u2192{act_v:+.2f} {pct:.0f}%"
        if mtr_status == "red":
            return f"[red bold]{body} STUCK[/]"
        return self._color_metric(body, mtr_status)

    def _build_pipeline_safety_row(self, state: dict) -> str:
        """Row 3 \u2014 context that explains *why* the pipeline might be wedged
        even when the upstream cells look healthy:

        - Cliff sensor: a triggered cliff causes the obstacle node to
          send zero cmd_vel, which mux forwards (mux=OBSTACLE). Without
          this row the user sees green\u2192green\u2192OBSTACLE and wonders why.
        - Closest obstacle: same logic \u2014 explains MUX=OBSTACLE.
        - Critical edge services (motor-driver, mux, obstacle): a dead
          service produces the same symptom as a dead ESP32 / dead mux,
          but requires a different fix. Showing service status separates
          'firmware crashed' from 'driver process crashed'.
        """
        parts = []

        # Cliff
        if state.get('cliff_detected', False):
            parts.append("[red bold]Cliff: DETECTED[/]")
        else:
            parts.append("[dim]Cliff:[/] [green]clear[/]")

        # Closest obstacle (min of 4 ultrasonic, with direction)
        sensors = {
            'front': state.get('ultra_front', float('inf')),
            'rear': state.get('ultra_rear', float('inf')),
            'left': state.get('ultra_left', float('inf')),
            'right': state.get('ultra_right', float('inf')),
        }
        valid = {k: v for k, v in sensors.items()
                 if isinstance(v, (int, float))
                 and v != float('inf') and v > 0}
        if valid:
            direction, distance = min(valid.items(), key=lambda kv: kv[1])
            if distance < 0.3:
                color = "red bold"
            elif distance < 0.5:
                color = "yellow"
            else:
                color = "green"
            parts.append(
                f"[dim]Closest:[/] [{color}]{distance:.2f}m {direction}[/]")
        else:
            parts.append("[dim]Closest:[/] [dim]\u2014 (sensor hub silent)[/]")

        # Critical edge services
        health = state.get('edge_health', {}) or {}
        services = health.get('services', {}) or {}
        critical_map = {
            'motor': 'rovac-edge-motor-driver',
            'mux': 'rovac-edge-mux',
            'obstacle': 'rovac-edge-obstacle',
        }
        if services:
            svc_glyphs = []
            for short, full in critical_map.items():
                svc = services.get(full, {})
                active = svc.get('active') if isinstance(svc, dict) else None
                if active is True:
                    svc_glyphs.append(f"[dim]{short}[/] [green]\u25cf[/]")
                elif active is False:
                    svc_glyphs.append(f"[red bold]{short}[/] [red bold]\u25cf[/]")
                else:
                    svc_glyphs.append(f"[dim]{short} \u25cb[/]")
            parts.append("[dim]Edge:[/] " + "  ".join(svc_glyphs))
        else:
            parts.append("[dim]Edge:[/] [dim](no health data yet)[/]")

        return "  \u2022  ".join(parts)
