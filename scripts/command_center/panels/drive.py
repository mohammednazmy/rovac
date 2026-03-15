"""Drive panel — keyboard teleop with live odometry and proximity display."""

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

# Hold timeout — if no key press within this window, stop.
HOLD_TIMEOUT = 0.4  # seconds


def _range_color(distance: float) -> str:
    """Color-code a distance value."""
    if distance == float("inf") or distance <= 0:
        return "[dim]---  [/]"
    if distance < 0.2:
        return f"[red]{distance:4.2f}m[/]"
    elif distance < 0.5:
        return f"[yellow]{distance:4.2f}m[/]"
    else:
        return f"[green]{distance:4.2f}m[/]"


class DrivePanel(Widget):
    """Teleop driving panel with keyboard controls."""

    def __init__(self) -> None:
        super().__init__()
        self.gear = 2  # Default gear index
        self._hold_timer: Timer | None = None
        self._current_linear = 0.0
        self._current_angular = 0.0

    def compose(self):
        # -- Controls section --
        with Container(classes="panel-box-green") as c:
            c.border_title = "Controls"
            yield Static("[dim]Loading...[/]", id="drive-controls")

        # -- Bottom row: Odometry + Proximity --
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
        """Handle drive key presses. Called by App dispatcher. Returns True if handled."""
        linear = 0.0
        angular = 0.0
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]

        if key in ("w", "up"):
            linear = lin_speed
        elif key in ("s", "down"):
            linear = -lin_speed
        elif key in ("a", "left"):
            angular = ang_speed
        elif key in ("d", "right"):
            angular = -ang_speed
        elif key == "q":
            # Arc left — forward + turn left
            linear = lin_speed
            angular = ang_speed * 0.5
        elif key == "e":
            # Arc right — forward + turn right
            linear = lin_speed
            angular = -ang_speed * 0.5
        elif key == "space":
            linear = 0.0
            angular = 0.0
        elif key in ("equal", "plus"):
            self.gear = min(self.gear + 1, len(SPEED_PRESETS) - 1)
            self._refresh_controls_display()
            return True
        elif key in ("minus", "underscore"):
            self.gear = max(self.gear - 1, 0)
            self._refresh_controls_display()
            return True
        elif key == "h":
            # Toggle headlights (phone flashlight)
            if self.app.ros:
                current = self.app.ros.get_state().get('phone_flashlight_on', False)
                self.app.ros.publish_flashlight(not current)
            return True
        else:
            return False

        # Publish velocity
        self._current_linear = linear
        self._current_angular = angular
        if self.app.ros:
            self.app.ros.publish_cmd_vel(linear, angular)

        # Reset hold timer — will send zero if no key pressed within timeout
        self._reset_hold_timer()
        self._refresh_controls_display()
        return True

    def _reset_hold_timer(self) -> None:
        """Cancel previous hold timer and start a new one."""
        if self._hold_timer is not None:
            self._hold_timer.stop()
        self._hold_timer = self.set_timer(HOLD_TIMEOUT, self._release_timeout)

    def _release_timeout(self) -> None:
        """No key press received within hold window — stop the robot."""
        self._current_linear = 0.0
        self._current_angular = 0.0
        if self.app.ros:
            self.app.ros.publish_cmd_vel(0.0, 0.0)
        self._refresh_controls_display()

    def _refresh_controls_display(self) -> None:
        """Update the controls help text."""
        lin_speed, ang_speed = SPEED_PRESETS[self.gear]
        gear_num = self.gear + 1
        total_gears = len(SPEED_PRESETS)

        # Current output indicator
        lin_out = self._current_linear
        ang_out = self._current_angular
        if abs(lin_out) > 0.001 or abs(ang_out) > 0.001:
            out_color = "green"
        else:
            out_color = "dim"

        # Flashlight state
        if self.app.ros:
            flash_on = self.app.ros.get_state().get('phone_flashlight_on', False)
        else:
            flash_on = False
        flash_text = "[yellow]● ON[/]" if flash_on else "[dim]○ OFF[/]"

        text = (
            "        [bold]W/Up[/] Fwd     [bold]Q[/] Arc-L     "
            f"Gear [bold]{gear_num}[/]/{total_gears}  "
            f"[bold]{lin_speed:.2f}[/] m/s  [bold]{ang_speed:.1f}[/] rad/s\n"
            "  [bold]A/Left[/] [bold]SPACE[/] [bold]D/Right[/]   [bold]E[/] Arc-R     "
            f"[{out_color}]Out: lin={lin_out:+.2f} ang={ang_out:+.2f}[/]\n"
            f"        [bold]S/Down[/] Rev    [bold]+/-[/] Speed    "
            f"[bold]H[/] Headlight {flash_text}"
        )
        try:
            self.query_one("#drive-controls", Static).update(text)
        except Exception:
            pass

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        """Called by the app at 1 Hz."""
        self._update_odom(state)
        self._update_proximity(state)

    def _update_odom(self, state: dict) -> None:
        x = state.get("odom_x", 0)
        y = state.get("odom_y", 0)
        yaw_rad = state.get("odom_yaw", 0)
        yaw_deg = math.degrees(yaw_rad)
        vx = state.get("odom_vx", 0)
        wz = state.get("odom_wz", 0)
        dist = state.get("odom_total_dist", 0)
        hz = state.get("odom_hz", 0)
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

        ft_s = _range_color(ft)
        fb_s = _range_color(fb)
        left_s = _range_color(left)
        right_s = _range_color(right)

        if obstacle:
            status = "[red bold]OBSTACLE[/]"
        else:
            status = "[green]CLEAR[/]"

        text = (
            f"        Top: {ft_s}\n"
            f" {left_s}   [bold]◼[/]   {right_s}\n"
            f"        Bot: {fb_s}\n"
            "\n"
            f" Status: {status}"
        )
        try:
            self.query_one("#drive-proximity", Static).update(text)
        except Exception:
            pass
