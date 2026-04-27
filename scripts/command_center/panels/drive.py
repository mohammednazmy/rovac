"""Drive panel — keyboard teleop with continuous publish loop."""

from __future__ import annotations

import math
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Static
from textual.timer import Timer

# Same speed presets as keyboard_teleop.py (7 gears)
SPEED_PRESETS = [
    (0.05, 1.0),
    (0.10, 1.5),
    (0.15, 2.0),
    (0.20, 3.0),
    (0.25, 4.0),
    (0.35, 5.0),
    (0.50, 6.5),
]

# Publish rate for sustained driving (matches keyboard_teleop.py)
PUBLISH_HZ = 20
PUBLISH_INTERVAL = 1.0 / PUBLISH_HZ

# How long after last key press to stop. Was 0.4s — too short for
# users who TAP rather than hold, and for terminals that don't auto-
# repeat in TUI mode (most macOS terminals don't, since Textual puts
# stdin in raw mode and disables OS key-repeat). 1.5s gives a single
# tap a meaningful drive distance (~22cm at 0.15 m/s gear 2).
# To stop sooner, press SPACE.
HOLD_TIMEOUT = 1.5  # seconds


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
        self._target_linear = 0.0
        self._target_angular = 0.0
        self._publish_timer: Timer | None = None
        self._hold_timer: Timer | None = None
        self._driving = False

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

    def on_mount(self) -> None:
        self._refresh_controls_display()

    def process_key(self, key: str) -> bool:
        """Handle drive key presses. Called by App dispatcher."""
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]

        if key in ("w", "up"):
            self._set_drive(lin_speed, 0.0)
        elif key in ("s", "down"):
            self._set_drive(-lin_speed, 0.0)
        elif key in ("a", "left"):
            self._set_drive(0.0, ang_speed)
        elif key in ("d", "right"):
            self._set_drive(0.0, -ang_speed)
        elif key == "q":
            self._set_drive(lin_speed, ang_speed * 0.5)
        elif key == "e":
            self._set_drive(lin_speed, -ang_speed * 0.5)
        elif key == "space":
            self._stop_driving()
        elif key in ("equal", "plus"):
            self.gear = min(self.gear + 1, len(SPEED_PRESETS) - 1)
            # Update target if currently driving
            if self._driving:
                self._update_speed_while_driving()
            self._refresh_controls_display()
        elif key in ("minus", "underscore"):
            self.gear = max(self.gear - 1, 0)
            if self._driving:
                self._update_speed_while_driving()
            self._refresh_controls_display()
        else:
            return False
        return True

    def _set_drive(self, linear: float, angular: float) -> None:
        """Set drive target and start continuous publishing."""
        self._target_linear = linear
        self._target_angular = angular
        self._driving = True

        # Publish immediately
        if self.app.ros:
            self.app.ros.publish_cmd_vel(linear, angular)

        # Start continuous publish timer (if not already running)
        if self._publish_timer is None:
            self._publish_timer = self.set_interval(
                PUBLISH_INTERVAL, self._publish_tick
            )

        # Reset the hold timeout (stop after no key press)
        self._reset_hold_timer()
        self._refresh_controls_display()

    def _publish_tick(self) -> None:
        """Continuous publish at 20Hz while driving.

        SELF-CANCELING: if both targets are zero OR _driving became False
        by any path (tab switch, hold-timer, panel hide), this tick
        stops the timer entirely. Without this safety, the timer kept
        firing publish_cmd_vel(0,0) at 20Hz forever, which the mux
        treats as 'TELEOP active' (priority 1) and silently overrode
        Nav2 — the failure mode that caused 'A pressed but robot won't
        move' in the live test.
        """
        zero_velocity = (abs(self._target_linear) < 1e-4
                         and abs(self._target_angular) < 1e-4)
        if not self._driving or zero_velocity:
            # Self-destruct: stop the timer and don't publish.
            if self._publish_timer is not None:
                self._publish_timer.stop()
                self._publish_timer = None
            self._driving = False
            return
        if self.app.ros:
            self.app.ros.publish_cmd_vel(
                self._target_linear, self._target_angular)

    def _reset_hold_timer(self) -> None:
        """Reset the hold timeout — stops driving if no key arrives within window."""
        if self._hold_timer is not None:
            self._hold_timer.stop()
        self._hold_timer = self.set_timer(HOLD_TIMEOUT, self._stop_driving)

    def _stop_driving(self) -> None:
        """Stop the robot and cancel continuous publishing."""
        self._target_linear = 0.0
        self._target_angular = 0.0
        self._driving = False

        # Send zero cmd_vel
        if self.app.ros:
            self.app.ros.publish_cmd_vel(0.0, 0.0)

        # Stop the continuous publish timer
        if self._publish_timer is not None:
            self._publish_timer.stop()
            self._publish_timer = None

        if self._hold_timer is not None:
            self._hold_timer.stop()
            self._hold_timer = None

        self._refresh_controls_display()

    def _update_speed_while_driving(self) -> None:
        """Update target speed when gear changes during active driving."""
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]
        # Scale the current direction to the new speed
        if abs(self._target_linear) > 0.001:
            sign = 1.0 if self._target_linear > 0 else -1.0
            self._target_linear = sign * lin_speed
        if abs(self._target_angular) > 0.001:
            sign = 1.0 if self._target_angular > 0 else -1.0
            # For pure turns, use full angular speed
            # For arcs, use half angular speed
            if abs(self._target_linear) > 0.001:
                self._target_angular = sign * ang_speed * 0.5
            else:
                self._target_angular = sign * ang_speed

    def _refresh_controls_display(self) -> None:
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]
        gear_num = self.gear + 1
        total_gears = len(SPEED_PRESETS)

        lin_out = self._target_linear
        ang_out = self._target_angular
        if self._driving:
            out_color = "green"
        else:
            out_color = "dim"

        text = (
            "        [bold]W/Up[/] Fwd     [bold]Q[/] Arc-L     "
            f"Gear [bold]{gear_num}[/]/{total_gears}  "
            f"[bold]{lin_speed:.2f}[/] m/s  [bold]{ang_speed:.1f}[/] rad/s\n"
            "  [bold]A/Left[/] [bold]SPACE[/] [bold]D/Right[/]   [bold]E[/] Arc-R     "
            f"[{out_color}]Out: lin={lin_out:+.2f} ang={ang_out:+.2f}[/]\n"
            f"        [bold]S/Down[/] Rev    [bold]+/-[/] Speed"
        )
        try:
            self.query_one("#drive-controls", Static).update(text)
        except Exception:
            pass

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        self._update_odom(state)
        self._update_proximity(state)

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
        try:
            self.query_one("#drive-odom", Static).update("\n".join(lines))
        except Exception:
            pass

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
        try:
            self.query_one("#drive-proximity", Static).update(text)
        except Exception:
            pass
