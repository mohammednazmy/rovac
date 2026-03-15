"""Phone panel — dedicated view for Android phone sensor node status."""

from __future__ import annotations

import math
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Static


class PhonePanel(Widget):
    """Phone sensor node — IMU, GPS, camera, flashlight, connection status."""

    def compose(self):
        # Connection status
        with Container(classes="panel-box-green") as c:
            c.border_title = "Connection"
            yield Static("[dim]Waiting for phone data...[/]", id="phone-conn")

        # IMU — accel + gyro + orientation
        with Horizontal(id="phone-imu-row"):
            with Container(classes="panel-box-blue") as c:
                c.border_title = "Accelerometer (m/s\u00b2)"
                yield Static("[dim]No data[/]", id="phone-accel")

            with Container(classes="panel-box-blue") as c:
                c.border_title = "Gyroscope (rad/s)"
                yield Static("[dim]No data[/]", id="phone-gyro")

            with Container(classes="panel-box-cyan") as c:
                c.border_title = "Orientation (RPY\u00b0)"
                yield Static("[dim]No data[/]", id="phone-orient")

        # GPS + Camera side by side
        with Horizontal(id="phone-lower-row"):
            with Container(classes="panel-box-green") as c:
                c.border_title = "GPS"
                yield Static("[dim]No GPS fix[/]", id="phone-gps")

            with Container(classes="panel-box-magenta") as c:
                c.border_title = "Camera"
                yield Static("[dim]No camera data[/]", id="phone-camera")

        # Controls
        with Container(classes="panel-box-yellow") as c:
            c.border_title = "Controls"
            yield Static(
                "[bold]H[/] Toggle Flashlight    "
                "[bold]Status:[/] [dim]Unknown[/]",
                id="phone-controls",
            )

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        self._update_connection(state)
        self._update_accel(state)
        self._update_gyro(state)
        self._update_orient(state)
        self._update_gps(state)
        self._update_camera(state)
        self._update_controls(state)

    def process_key(self, key: str) -> bool:
        """Handle key presses — returns True if handled."""
        if key == "h":
            # Toggle flashlight via ROS bridge (set by app.py)
            if hasattr(self, '_toggle_flashlight') and self._toggle_flashlight:
                self._toggle_flashlight()
            return True
        return False

    def _update_connection(self, state: dict) -> None:
        imu_hz = state.get("phone_imu_hz", 0)
        gps_hz = state.get("phone_gps_hz", 0)
        cam_hz = state.get("phone_camera_hz", 0)

        parts = []
        if imu_hz > 0:
            parts.append(f"[green]\u25cf IMU[/] {imu_hz:.0f} Hz")
        else:
            parts.append("[red]\u25cb IMU[/] offline")

        if gps_hz > 0:
            parts.append(f"[green]\u25cf GPS[/] {gps_hz:.1f} Hz")
        else:
            parts.append("[yellow]\u25cb GPS[/] no fix")

        if cam_hz > 0:
            parts.append(f"[green]\u25cf Camera[/] {cam_hz:.1f} FPS")
        else:
            parts.append("[red]\u25cb Camera[/] off")

        connected = imu_hz > 0
        status = "[green bold]CONNECTED[/]" if connected else "[red bold]DISCONNECTED[/]"
        line = f"{status}    " + "    ".join(parts)

        try:
            self.query_one("#phone-conn", Static).update(line)
        except Exception:
            pass

    def _update_accel(self, state: dict) -> None:
        ax = state.get("phone_accel_x", 0)
        ay = state.get("phone_accel_y", 0)
        az = state.get("phone_accel_z", 0)
        norm = math.sqrt(ax*ax + ay*ay + az*az)
        text = (
            f"X: [bold]{ax:+8.3f}[/]\n"
            f"Y: [bold]{ay:+8.3f}[/]\n"
            f"Z: [bold]{az:+8.3f}[/]\n"
            f"Norm: {norm:.2f}"
        )
        try:
            self.query_one("#phone-accel", Static).update(text)
        except Exception:
            pass

    def _update_gyro(self, state: dict) -> None:
        gx = state.get("phone_gyro_x", 0)
        gy = state.get("phone_gyro_y", 0)
        gz = state.get("phone_gyro_z", 0)
        norm = math.sqrt(gx*gx + gy*gy + gz*gz)
        text = (
            f"X: [bold]{gx:+8.4f}[/]\n"
            f"Y: [bold]{gy:+8.4f}[/]\n"
            f"Z: [bold]{gz:+8.4f}[/]\n"
            f"Norm: {norm:.4f}"
        )
        try:
            self.query_one("#phone-gyro", Static).update(text)
        except Exception:
            pass

    def _update_orient(self, state: dict) -> None:
        roll = state.get("phone_orient_roll", 0)
        pitch = state.get("phone_orient_pitch", 0)
        yaw = state.get("phone_orient_yaw", 0)
        text = (
            f"Roll:  [bold]{math.degrees(roll):+7.2f}\u00b0[/]\n"
            f"Pitch: [bold]{math.degrees(pitch):+7.2f}\u00b0[/]\n"
            f"Yaw:   [bold]{math.degrees(yaw):+7.2f}\u00b0[/]"
        )
        try:
            self.query_one("#phone-orient", Static).update(text)
        except Exception:
            pass

    def _update_gps(self, state: dict) -> None:
        lat = state.get("phone_lat", 0)
        lon = state.get("phone_lon", 0)
        alt = state.get("phone_alt", 0)
        hz = state.get("phone_gps_hz", 0)
        status = state.get("phone_gps_status", -1)

        if hz > 0:
            fix = "[green]Fix[/]" if status >= 0 else "[yellow]No Fix[/]"
            text = (
                f"Lat:  [bold]{lat:.7f}[/]\n"
                f"Lon:  [bold]{lon:.7f}[/]\n"
                f"Alt:  [bold]{alt:.1f} m[/]\n"
                f"Status: {fix}    Rate: {hz:.1f} Hz"
            )
        else:
            text = "[dim]No GPS data — ensure phone is outdoors[/]"

        try:
            self.query_one("#phone-gps", Static).update(text)
        except Exception:
            pass

    def _update_camera(self, state: dict) -> None:
        hz = state.get("phone_camera_hz", 0)
        size = state.get("phone_camera_bytes", 0)

        if hz > 0:
            text = (
                f"FPS:   [bold]{hz:.1f}[/]\n"
                f"Frame: [bold]{size:,} bytes[/]\n"
                f"Stream: [green]Active[/]"
            )
        else:
            text = "[dim]Camera not streaming[/]\n[dim]Enable in phone Settings[/]"

        try:
            self.query_one("#phone-camera", Static).update(text)
        except Exception:
            pass

    def _update_controls(self, state: dict) -> None:
        torch = state.get("phone_flashlight_on", False)
        torch_str = "[yellow bold]ON \u2600[/]" if torch else "[dim]OFF \u25cf[/]"
        text = f"[bold]H[/] Toggle Flashlight    Status: {torch_str}"
        try:
            self.query_one("#phone-controls", Static).update(text)
        except Exception:
            pass
