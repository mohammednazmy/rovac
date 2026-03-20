"""Dashboard panel — system-wide overview of robot health and connectivity."""

from __future__ import annotations

import math
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Static

from ..process_manager import PI_SERVICES


def _dot(ok: bool | None) -> str:
    if ok is None:
        return "[dim]○[/]"
    return "[green]●[/]" if ok else "[red]●[/]"


def _bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, int(pct / 100 * width)))
    empty = width - filled
    if pct >= 80:
        colour = "red"
    elif pct >= 60:
        colour = "yellow"
    else:
        colour = "green"
    return f"[{colour}]{'█' * filled}{'░' * empty}[/]{pct:4.0f}%"


def _hz(val: float) -> str:
    if val <= 0:
        return "[dim]0.0[/]"
    return f"[green]{val:.1f}[/]"


class DashboardPanel(Widget):
    """Compact system overview dashboard."""

    def compose(self):
        # Row 1: Connectivity + Pi System side by side
        with Horizontal(id="dashboard-top-row"):
            with Container(classes="panel-box-green") as c:
                c.border_title = "Connectivity"
                yield Static(
                    "[dim]ROS2[/] ○  [dim]Pi[/] ○  [dim]Motor[/] ○  [dim]LIDAR[/] ○\n"
                    "[dim]Foxglove[/] ○ OFF",
                    id="dash-connectivity",
                )

            with Container(classes="panel-box-blue") as c:
                c.border_title = "Pi System"
                yield Static("[dim]Waiting for health data...[/]", id="dash-pi-system")

        # Row 2: Topic Rates + Robot side by side
        with Horizontal(id="dashboard-mid-row"):
            with Container(classes="panel-box-cyan") as c:
                c.border_title = "Topics & Robot"
                yield Static(
                    "/odom [dim]0.0[/] Hz   /scan [dim]0.0[/] Hz   /map [dim]0.0[/] Hz\n"
                    "Pos (0.00, 0.00)  Yaw 0.0\u00b0  Vel 0.00 m/s  Dist 0.0 m",
                    id="dash-topics-robot",
                )

        # Row 3: Edge Services
        with Container(classes="panel-box-green") as c:
            c.border_title = "Edge Services"
            yield Static("[dim]Waiting for service data...[/]", id="dash-edge-services")

        # Row 4: Log
        with Container(classes="panel-box-magenta", id="dash-log-box") as c:
            c.border_title = "Log"
            yield Static("[dim]No log entries[/]", id="dash-log")

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        self._update_connectivity(state, proc_status)
        self._update_pi_system(state)
        self._update_topics_robot(state)
        self._update_edge_services(state)
        self._update_log(logs)

    def _update_connectivity(self, state: dict, proc_status: dict) -> None:
        ros_ok = state.get("ros_connected", False)
        edge = state.get("edge_health", {})
        net = edge.get("network", {})

        esp_motor_ok = net.get("esp32_motor", {}).get("reachable")
        pi_ok = bool(edge)
        fox_ok = proc_status.get("foxglove") == "running"

        # RPLIDAR C1 is USB — check service status instead of network ping
        services = edge.get("services", {})
        rplidar_info = services.get("rovac-edge-rplidar-c1", {})
        rplidar_ok = rplidar_info.get("active", False) if isinstance(rplidar_info, dict) else False

        line1 = (
            f"[dim]ROS2[/] {_dot(ros_ok)}  "
            f"[dim]Pi[/] {_dot(pi_ok)}  "
            f"[dim]Motor[/] {_dot(esp_motor_ok)}  "
            f"[dim]LIDAR[/] {_dot(rplidar_ok if pi_ok else None)}"
        )
        if fox_ok:
            line2 = f"[dim]Foxglove[/] [green]● ws://localhost:8765[/]"
        else:
            line2 = f"[dim]Foxglove[/] [dim]○ OFF[/]"

        # BNO055 IMU status
        bno055_hz = state.get("bno055_imu_hz", 0)
        if bno055_hz > 0:
            bno055_line = f"[dim]BNO055[/] [green]● {bno055_hz:.0f}Hz[/]"
        else:
            bno055_line = f"[dim]BNO055[/] [dim]○ ---[/]"

        # Phone sensor status
        phone_imu_hz = state.get("phone_imu_hz", 0)
        phone_gps_hz = state.get("phone_gps_hz", 0)
        phone_cam_hz = state.get("phone_camera_hz", 0)
        if phone_imu_hz > 0 or phone_gps_hz > 0 or phone_cam_hz > 0:
            phone_parts = []
            if phone_imu_hz > 0:
                phone_parts.append(f"IMU {phone_imu_hz:.0f}Hz")
            if phone_gps_hz > 0:
                phone_parts.append(f"GPS {phone_gps_hz:.0f}Hz")
            if phone_cam_hz > 0:
                phone_parts.append(f"Cam {phone_cam_hz:.0f}FPS")
            phone_line = f"[dim]Phone[/] [green]● {' '.join(phone_parts)}[/]"
        else:
            phone_line = f"[dim]Phone[/] [dim]○ ---[/]"

        lines = [line1, line2, bno055_line, phone_line]
        self.query_one("#dash-connectivity", Static).update("\n".join(lines))

    def _update_pi_system(self, state: dict) -> None:
        edge = state.get("edge_health", {})
        sys_info = edge.get("system", {})
        agent = edge.get("agent", {})

        if not sys_info:
            self.query_one("#dash-pi-system", Static).update(
                "[dim]Waiting for health data...[/]"
            )
            return

        cpu = sys_info.get("cpu_percent") or 0
        ram = sys_info.get("memory_percent") or 0
        temp = sys_info.get("cpu_temp") or 0
        disk = sys_info.get("disk_percent") or 0
        rss = agent.get("rss_mb") or 0

        text = (
            f"CPU {_bar(cpu)}  RAM {_bar(ram)}\n"
            f"Temp {temp:.0f}°C  Disk {_bar(disk)}\n"
            f"Agent {rss:.0f} MB RSS"
        )
        self.query_one("#dash-pi-system", Static).update(text)

    def _update_topics_robot(self, state: dict) -> None:
        odom_hz = state.get("odom_hz", 0)
        scan_hz = state.get("scan_hz", 0)
        map_hz = state.get("map_hz", 0)

        x = state.get("odom_x", 0)
        y = state.get("odom_y", 0)
        yaw_deg = math.degrees(state.get("odom_yaw", 0))
        vx = state.get("odom_vx", 0)
        wz = state.get("odom_wz", 0)
        dist = state.get("odom_total_dist", 0)

        line1 = (
            f"/odom {_hz(odom_hz)} Hz   "
            f"/scan {_hz(scan_hz)} Hz   "
            f"/map {_hz(map_hz)} Hz"
        )
        line2 = (
            f"Pos ({x:+.2f}, {y:+.2f})  "
            f"Yaw {yaw_deg:+.1f}\u00b0  "
            f"v={vx:+.2f} m/s  "
            f"\u03c9={wz:+.2f} r/s  "
            f"Dist {dist:.1f}m"
        )
        self.query_one("#dash-topics-robot", Static).update(f"{line1}\n{line2}")

    def _update_edge_services(self, state: dict) -> None:
        edge = state.get("edge_health", {})
        services = edge.get("services", {})

        if not services:
            self.query_one("#dash-edge-services", Static).update(
                "[dim]Waiting for service data...[/]"
            )
            return

        # Compact 5-column grid
        items = []
        for svc in PI_SERVICES:
            svc_info = services.get(svc, {})
            is_active = svc_info.get("active", False) if isinstance(svc_info, dict) else False
            short = svc.replace("rovac-edge-", "")
            dot = "[green]●[/]" if is_active else "[dim]○[/]"
            items.append(f"{dot} {short:<13}")

        rows = []
        for i in range(0, len(items), 5):
            rows.append(" ".join(items[i : i + 5]))
        self.query_one("#dash-edge-services", Static).update("\n".join(rows))

    def _update_log(self, logs: list) -> None:
        if not logs:
            self.query_one("#dash-log", Static).update("[dim]No log entries[/]")
            return
        recent = logs[-6:]
        lines = [f"[dim]{ts}[/] {msg}" for ts, msg in recent]
        self.query_one("#dash-log", Static).update("\n".join(lines))
