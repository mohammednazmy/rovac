"""Dashboard panel — system-wide overview of robot health and connectivity."""

from __future__ import annotations

import math
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static

from ..process_manager import PI_SERVICES


def _indicator(ok: bool | None, label_ok: str = "OK", label_fail: str = "FAIL") -> str:
    """Return a coloured status indicator."""
    if ok is None:
        return f"[dim]○ ---[/]"
    return f"[green]● {label_ok}[/]" if ok else f"[red]● {label_fail}[/]"


def _bar(pct: float, width: int = 12) -> str:
    """Render a simple ASCII progress bar with colour."""
    filled = max(0, min(width, int(pct / 100 * width)))
    empty = width - filled
    if pct >= 80:
        colour = "red"
    elif pct >= 60:
        colour = "yellow"
    else:
        colour = "green"
    return f"[{colour}]{'█' * filled}{'░' * empty}[/] {pct:4.0f}%"


def _hz_fmt(hz: float) -> str:
    if hz <= 0:
        return "[dim]  0.0 Hz[/]"
    return f"{hz:5.1f} Hz"


def _service_indicator(status: str) -> str:
    """Render a service status dot."""
    if status == "active":
        return "[green]●[/]"
    elif status == "failed":
        return "[red]●[/]"
    elif status == "inactive":
        return "[dim]○[/]"
    else:
        return "[yellow]?[/]"


class DashboardPanel(Widget):
    """System overview dashboard."""

    def compose(self):
        # -- Top row: Connectivity + Pi System --
        with Horizontal(id="dashboard-top-row"):
            with Container(classes="panel-box-green") as c:
                c.border_title = "Connectivity"
                yield Static("", id="dash-connectivity")

            with Container(classes="panel-box-blue") as c:
                c.border_title = "Pi System"
                yield Static("", id="dash-pi-system")

        # -- Topic rates --
        with Container(classes="panel-box-cyan") as c:
            c.border_title = "Topic Rates"
            yield Static("", id="dash-topic-rates")

        # -- Edge services --
        with Container(classes="panel-box-green") as c:
            c.border_title = "Edge Services"
            yield Static("", id="dash-edge-services")

        # -- Bottom row: Robot + Log --
        with Horizontal(id="dashboard-bottom-row"):
            with Container(classes="panel-box-cyan") as c:
                c.border_title = "Robot"
                yield Static("", id="dash-robot")

            with Container(classes="panel-box-magenta", id="dash-log-box") as c:
                c.border_title = "Log"
                yield Static("", id="dash-log")

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        """Called by the app at 1 Hz with fresh data."""
        self._update_connectivity(state, proc_status)
        self._update_pi_system(state)
        self._update_topic_rates(state)
        self._update_edge_services(state)
        self._update_robot(state)
        self._update_log(logs)

    # ── Section updaters ──────────────────────────────

    def _update_connectivity(self, state: dict, proc_status: dict) -> None:
        ros_ok = state.get("ros_connected", False)
        edge = state.get("edge_health", {})
        net = edge.get("network", {})

        esp_motor_ok = net.get("esp32_motor", {}).get("reachable")
        esp_lidar_ok = net.get("esp32_lidar", {}).get("reachable")

        # Pi SSH — if we have edge_health, the Pi health node is running
        pi_ok = bool(edge)

        foxglove_running = proc_status.get("foxglove") == "running"

        lines = [
            f"ROS2:          {_indicator(ros_ok, 'CONNECTED', 'DISCONNECTED')}",
            f"Pi SSH:        {_indicator(pi_ok)}",
            f"ESP32 Motor:   {_indicator(esp_motor_ok)}",
            f"ESP32 LIDAR:   {_indicator(esp_lidar_ok)}",
            f"Foxglove:      {_indicator(foxglove_running if foxglove_running else None, 'RUNNING', 'STOPPED') if foxglove_running else '[dim]○ OFF[/]'}",
        ]
        self.query_one("#dash-connectivity", Static).update("\n".join(lines))

    def _update_pi_system(self, state: dict) -> None:
        edge = state.get("edge_health", {})
        sys_info = edge.get("system", {})
        agent = edge.get("agent", {})

        if not sys_info:
            self.query_one("#dash-pi-system", Static).update(
                "[dim]Waiting for Pi health data...[/]"
            )
            return

        cpu = sys_info.get("cpu_percent", 0)
        ram = sys_info.get("memory_percent", 0)
        temp = sys_info.get("cpu_temp", 0)
        disk = sys_info.get("disk_percent", 0)
        rss = agent.get("rss_mb", 0)

        lines = [
            f"CPU:   {_bar(cpu)}",
            f"RAM:   {_bar(ram)}",
            f"Temp:  {temp:4.0f}°C",
            f"Disk:  {_bar(disk)}",
            f"Agent: {rss:.0f} MB RSS",
        ]
        self.query_one("#dash-pi-system", Static).update("\n".join(lines))

    def _update_topic_rates(self, state: dict) -> None:
        odom_hz = state.get("odom_hz", 0)
        scan_hz = state.get("scan_hz", 0)
        map_hz = state.get("map_hz", 0)

        line = (
            f"/odom  {_hz_fmt(odom_hz)}    "
            f"/scan  {_hz_fmt(scan_hz)}    "
            f"/map   {_hz_fmt(map_hz)}"
        )
        self.query_one("#dash-topic-rates", Static).update(line)

    def _update_edge_services(self, state: dict) -> None:
        edge = state.get("edge_health", {})
        services = edge.get("services", {})

        if not services:
            self.query_one("#dash-edge-services", Static).update(
                "[dim]Waiting for service data...[/]"
            )
            return

        # Build a compact 3-column grid
        items = []
        for svc in PI_SERVICES:
            svc_info = services.get(svc, {})
            status = svc_info.get("sub_state", "unknown") if isinstance(svc_info, dict) else "unknown"
            is_active = svc_info.get("active", False) if isinstance(svc_info, dict) else False
            short = svc.replace("rovac-edge-", "")
            dot = "[green]●[/]" if is_active else "[dim]○[/]"
            items.append(f"{dot} {short:<16}")

        # Arrange in rows of 3
        rows = []
        for i in range(0, len(items), 3):
            rows.append("  ".join(items[i : i + 3]))
        self.query_one("#dash-edge-services", Static).update("\n".join(rows))

    def _update_robot(self, state: dict) -> None:
        x = state.get("odom_x", 0)
        y = state.get("odom_y", 0)
        yaw_rad = state.get("odom_yaw", 0)
        yaw_deg = math.degrees(yaw_rad)
        vx = state.get("odom_vx", 0)
        dist = state.get("odom_total_dist", 0)

        lines = [
            f"Pos:  ({x:6.2f}, {y:6.2f})",
            f"Yaw:  {yaw_deg:6.1f}°",
            f"Vel:  {vx:5.2f} m/s",
            f"Dist: {dist:5.1f} m",
        ]
        self.query_one("#dash-robot", Static).update("\n".join(lines))

    def _update_log(self, logs: list) -> None:
        if not logs:
            self.query_one("#dash-log", Static).update("[dim]No log entries[/]")
            return
        # Show last 8 entries
        recent = logs[-8:]
        lines = [f"[dim]{ts}[/] {msg}" for ts, msg in recent]
        self.query_one("#dash-log", Static).update("\n".join(lines))
