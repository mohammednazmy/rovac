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
            yield Static("", id="sens-odom")

        # LIDAR
        with Container(classes="panel-box-blue") as c:
            c.border_title = "LIDAR"
            yield Static("", id="sens-lidar")

        # Ultrasonic
        with Container(classes="panel-box-cyan") as c:
            c.border_title = "Ultrasonic"
            yield Static("", id="sens-ultra")

        # ESP32 diagnostics — side by side
        with Horizontal(id="sensors-diag-row"):
            with Container(classes="panel-box-magenta") as c:
                c.border_title = "ESP32 Motor"
                yield Static("", id="sens-diag-motor")

            with Container(classes="panel-box-magenta") as c:
                c.border_title = "ESP32 LIDAR"
                yield Static("", id="sens-diag-lidar")

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        self._update_odom(state)
        self._update_lidar(state)
        self._update_ultra(state)
        self._update_diag_motor(state)
        self._update_diag_lidar(state)

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
        ft = state.get("ultra_front_top", float("inf"))
        fb = state.get("ultra_front_bottom", float("inf"))
        left = state.get("ultra_left", float("inf"))
        right = state.get("ultra_right", float("inf"))
        obstacle = state.get("obstacle_detected", False)

        def _f(v: float) -> str:
            if v == float("inf") or v <= 0:
                return "[dim]  --- [/]"
            return f"{v:5.2f} m"

        obs_text = "[red bold]DETECTED[/]" if obstacle else "[green]CLEAR[/]"

        lines = [
            f"Front Top:    {_f(ft)}    Front Bottom: {_f(fb)}",
            f"Left:         {_f(left)}    Right:        {_f(right)}",
            f"Obstacle:     {obs_text}",
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

    def _update_diag_lidar(self, state: dict) -> None:
        diag = state.get("diag_lidar", {})
        if not diag:
            try:
                self.query_one("#sens-diag-lidar", Static).update(
                    "[dim]No LIDAR diagnostics[/]"
                )
            except Exception:
                pass
            return

        rssi = diag.get("wifi_rssi", "---")
        heap = _fmt_heap(diag.get("heap_free", "0"))
        rpm = diag.get("rpm", "---")
        chk_err = diag.get("checksum_errors", "0")

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

        lines = [
            f"WiFi RSSI: {rssi_text}    Heap: {heap}",
            f"RPM: {rpm}    Checksum Errors: {chk_err}",
        ]
        try:
            self.query_one("#sens-diag-lidar", Static).update("\n".join(lines))
        except Exception:
            pass
