"""Sensors panel — detailed view of all sensor data streams."""

from __future__ import annotations

import math
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Static


def _fmt_uptime(seconds_str: str) -> str:
    """Format uptime seconds into human-readable string."""
    try:
        secs = int(float(seconds_str))
    except (ValueError, TypeError):
        return "---"
    hours, remainder = divmod(secs, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    elif minutes > 0:
        return f"{minutes}m {seconds:02d}s"
    else:
        return f"{seconds}s"


def _fmt_heap(heap_str: str) -> str:
    """Format heap bytes to KB."""
    try:
        val = int(heap_str)
        return f"{val / 1024:.0f} KB"
    except (ValueError, TypeError):
        return "---"


class SensorsPanel(Widget):
    """Sensor data viewer — odometry, LIDAR, ultrasonic, ESP32 diagnostics."""

    def compose(self):
        # Odometry
        with Container(classes="panel-box-green") as c:
            c.border_title = "Odometry"
            yield Static(
                "Position    x:   0.000 m    y:   0.000 m\n"
                "Heading     yaw:    0.0\u00b0 (+0.000 rad)\n"
                "Velocity    linear:  0.000 m/s    angular: +0.000 rad/s\n"
                "Distance    total:   0.00 m\n"
                "Rate          0.0 Hz",
                id="sens-odom",
            )

        # LIDAR
        with Container(classes="panel-box-blue") as c:
            c.border_title = "LIDAR"
            yield Static(
                "Rate:      0.0 Hz     Points: 0 / 360\n"
                "Range:   0.00 - 0.00 m\n"
                "Status:  [dim]\u25cb No data[/]",
                id="sens-lidar",
            )

        # Ultrasonic + cliff (ESP32 sensor hub: 4x HC-SR04 + 2x IR cliff)
        with Container(classes="panel-box-cyan") as c:
            c.border_title = "Ultrasonic + Cliff (ESP32 sensor hub)"
            yield Static(
                "Front:  [dim]  --- [/]    Rear:   [dim]  --- [/]\n"
                "Left:   [dim]  --- [/]    Right:  [dim]  --- [/]\n"
                "Cliff:  [green]CLEAR[/]",
                id="sens-ultra",
            )

        # ESP32 Motor diagnostics (only motor ESP32 publishes /diagnostics)
        with Container(classes="panel-box-magenta") as c:
            c.border_title = "ESP32 Motor"
            yield Static("[dim]No motor diagnostics[/]", id="sens-diag-motor")

        # BNO055 IMU
        with Container(classes="panel-box-green") as c:
            c.border_title = "BNO055 IMU"
            yield Static("[dim]No BNO055 IMU data[/]", id="sens-bno055-imu")

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        self._update_odom(state)
        self._update_lidar(state)
        self._update_ultra(state)
        self._update_diag_motor(state)
        self._update_bno055_imu(state)

    def _update_odom(self, state: dict) -> None:
        x = state.get("odom_x", 0)
        y = state.get("odom_y", 0)
        yaw_rad = state.get("odom_yaw", 0)
        yaw_deg = math.degrees(yaw_rad)
        vx = state.get("odom_vx", 0)
        wz = state.get("odom_wz", 0)
        dist = state.get("odom_total_dist", 0)
        hz = state.get("odom_hz", 0)

        lines = [
            f"Position    x: {x:7.3f} m    y: {y:7.3f} m",
            f"Heading     yaw: {yaw_deg:6.1f}° ({yaw_rad:+.3f} rad)",
            f"Velocity    linear: {vx:6.3f} m/s    angular: {wz:+6.3f} rad/s",
            f"Distance    total: {dist:6.2f} m",
            f"Rate        {hz:5.1f} Hz",
        ]
        try:
            self.query_one("#sens-odom", Static).update("\n".join(lines))
        except Exception:
            pass

    def _update_lidar(self, state: dict) -> None:
        hz = state.get("scan_hz", 0)
        count = state.get("scan_count", 0)
        scan_min = state.get("scan_min", 0)
        scan_max = state.get("scan_max", 0)

        if hz > 0:
            status = "[green]● Active[/]"
        else:
            status = "[dim]○ No data[/]"

        lines = [
            f"Rate:    {hz:5.1f} Hz     Points: {count} / 360",
            f"Range:   {scan_min:.2f} - {scan_max:.2f} m",
            f"Status:  {status}",
        ]
        try:
            self.query_one("#sens-lidar", Static).update("\n".join(lines))
        except Exception:
            pass

    def _update_ultra(self, state: dict) -> None:
        front = state.get("ultra_front", float("inf"))
        rear = state.get("ultra_rear", float("inf"))
        left = state.get("ultra_left", float("inf"))
        right = state.get("ultra_right", float("inf"))
        cliff = state.get("cliff_detected", False)

        def _f(v: float) -> str:
            if v == float("inf") or v <= 0:
                return "[dim]  --- [/]"
            return f"{v:5.2f} m"

        cliff_text = "[red bold]CLIFF![/]" if cliff else "[green]CLEAR[/]"

        lines = [
            f"Front:  {_f(front)}    Rear:   {_f(rear)}",
            f"Left:   {_f(left)}    Right:  {_f(right)}",
            f"Cliff:  {cliff_text}",
        ]
        try:
            self.query_one("#sens-ultra", Static).update("\n".join(lines))
        except Exception:
            pass

    def _update_diag_motor(self, state: dict) -> None:
        diag = state.get("diag_motor", {})
        if not diag:
            try:
                self.query_one("#sens-diag-motor", Static).update(
                    "[dim]No motor diagnostics[/]"
                )
            except Exception:
                pass
            return

        rssi = diag.get("wifi_rssi", "---")
        heap = _fmt_heap(diag.get("heap_free", "0"))
        uptime = _fmt_uptime(diag.get("uptime_s", "0"))

        # Color-code RSSI
        try:
            rssi_val = int(rssi)
            if rssi_val > -50:
                rssi_text = f"[green]{rssi} dBm[/]"
            elif rssi_val > -70:
                rssi_text = f"[yellow]{rssi} dBm[/]"
            else:
                rssi_text = f"[red]{rssi} dBm[/]"
        except (ValueError, TypeError):
            rssi_text = f"[dim]{rssi}[/]"

        text = f"WiFi RSSI: {rssi_text}    Heap: {heap}    Up: {uptime}"
        try:
            self.query_one("#sens-diag-motor", Static).update(text)
        except Exception:
            pass

    def _update_bno055_imu(self, state: dict) -> None:
        hz = state.get("bno055_imu_hz", 0)
        if hz <= 0:
            try:
                self.query_one("#sens-bno055-imu", Static).update("[dim]No BNO055 IMU data[/]")
            except Exception:
                pass
            return

        ax = state.get("bno055_accel_x", 0)
        ay = state.get("bno055_accel_y", 0)
        az = state.get("bno055_accel_z", 0)
        gx = state.get("bno055_gyro_x", 0)
        gy = state.get("bno055_gyro_y", 0)
        gz = state.get("bno055_gyro_z", 0)
        roll = state.get("bno055_orient_roll", 0)
        pitch = state.get("bno055_orient_pitch", 0)
        yaw = state.get("bno055_orient_yaw", 0)

        text = (
            f"Accel   x:{ax:+7.2f}  y:{ay:+7.2f}  z:{az:+7.2f} m/s²    Rate: {hz:.0f} Hz\n"
            f"Gyro    x:{gx:+7.2f}  y:{gy:+7.2f}  z:{gz:+7.2f} rad/s\n"
            f"Orient  R:{roll:+6.1f}°  P:{pitch:+6.1f}°  Y:{yaw:+6.1f}°"
        )
        try:
            self.query_one("#sens-bno055-imu", Static).update(text)
        except Exception:
            pass

