"""Edge panel — Pi service management and system health."""

from __future__ import annotations

import threading
from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import Static, DataTable

from ..process_manager import PI_SERVICES


def _svc_indicator(status: str) -> str:
    """Status dot for a systemd service."""
    if status == "active":
        return "[green]● active[/]"
    elif status == "failed":
        return "[red]● failed[/]"
    elif status == "inactive":
        return "[dim]○ inactive[/]"
    else:
        return "[yellow]? unknown[/]"


class EdgePanel(Widget):
    """Pi edge service management and system monitoring."""

    def __init__(self) -> None:
        super().__init__()
        self._service_statuses: dict[str, str] = {}
        self._refreshing = False

    def compose(self):
        # Services table
        with Container(classes="panel-box-green", id="edge-services-box") as c:
            c.border_title = "Pi Edge Services"
            yield DataTable(id="edge-services-table")

        # Bottom row
        with Horizontal(id="edge-lower"):
            # Pi system stats
            with Container(classes="panel-box-blue") as c:
                c.border_title = "Pi System"
                yield Static("", id="edge-pi-stats")

            # Actions
            with Container(classes="panel-box-yellow") as c:
                c.border_title = "Actions"
                yield Static(
                    " [bold]R[/]  Refresh service status\n"
                    " [bold]A[/]  Restart all (rovac-edge.target)\n"
                    " [bold]Enter[/]  Restart selected service\n"
                    " [bold]Up/Down[/]  Select service",
                    id="edge-actions-help",
                )
                yield Static("", id="edge-action-result")

    def on_mount(self) -> None:
        table = self.query_one("#edge-services-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Service", "Status")

        # Populate initial rows
        for svc in PI_SERVICES:
            short = svc.replace("rovac-edge-", "")
            table.add_row(short, "[dim]---[/]", key=svc)

        # Trigger an initial SSH refresh in the background
        self._trigger_refresh()

    def process_key(self, key: str) -> bool:
        """Handle Edge tab key bindings. Called by App dispatcher. Returns True if handled."""
        if key == "r":
            self._trigger_refresh()
        elif key == "a":
            self._restart_all()
        elif key == "enter":
            self._restart_selected()
        else:
            return False
        return True

    def _trigger_refresh(self) -> None:
        """Refresh service statuses via SSH (background thread)."""
        if self._refreshing:
            return
        self._refreshing = True
        self._show_result("[dim]Refreshing...[/]")

        def _do_refresh():
            try:
                statuses = self.app.pm.pi_all_service_status()
                self._service_statuses = statuses
                # Schedule UI update on main thread
                try:
                    self.app.call_from_thread(self._apply_service_statuses)
                    self.app.call_from_thread(
                        self._show_result, "[green]Refreshed[/]"
                    )
                except Exception:
                    pass  # App may have shut down
            except Exception:
                try:
                    self.app.call_from_thread(
                        self._show_result, "[red]SSH refresh failed[/]"
                    )
                except Exception:
                    pass
            finally:
                self._refreshing = False

        threading.Thread(target=_do_refresh, daemon=True).start()

    def _apply_service_statuses(self) -> None:
        """Update the DataTable with fresh service statuses."""
        try:
            table = self.query_one("#edge-services-table", DataTable)
            for svc in PI_SERVICES:
                status = self._service_statuses.get(svc, "unknown")
                short = svc.replace("rovac-edge-", "")
                indicator = _svc_indicator(status)
                try:
                    table.update_cell(svc, "Service", short)
                    table.update_cell(svc, "Status", indicator)
                except Exception:
                    pass
        except Exception:
            pass

    def _restart_all(self) -> None:
        """Restart rovac-edge.target."""
        self._show_result("[dim]Restarting all services...[/]")

        def _do_restart():
            ok = self.app.pm.pi_service_action("rovac-edge.target", "restart")
            if ok:
                self.app.call_from_thread(
                    self._show_result,
                    "[green]All services restarted[/]",
                )
            else:
                self.app.call_from_thread(
                    self._show_result,
                    "[red]Failed to restart services[/]",
                )
            # Refresh after a moment
            import time
            time.sleep(2)
            self._refreshing = False
            self.app.call_from_thread(self._trigger_refresh)

        self._refreshing = True
        threading.Thread(target=_do_restart, daemon=True).start()

    def _restart_selected(self) -> None:
        """Restart the currently selected service in the DataTable."""
        try:
            table = self.query_one("#edge-services-table", DataTable)
            row_key = table.cursor_row
            if row_key < 0 or row_key >= len(PI_SERVICES):
                return
            svc = PI_SERVICES[row_key]
        except Exception:
            return

        short = svc.replace("rovac-edge-", "")
        self._show_result(f"[dim]Restarting {short}...[/]")

        def _do_restart():
            ok = self.app.pm.pi_service_action(svc, "restart")
            if ok:
                self.app.call_from_thread(
                    self._show_result,
                    f"[green]{short} restarted[/]",
                )
            else:
                self.app.call_from_thread(
                    self._show_result,
                    f"[red]Failed to restart {short}[/]",
                )
            import time
            time.sleep(1)
            self._refreshing = False
            self.app.call_from_thread(self._trigger_refresh)

        self._refreshing = True
        threading.Thread(target=_do_restart, daemon=True).start()

    def _show_result(self, msg: str) -> None:
        try:
            self.query_one("#edge-action-result", Static).update(msg)
        except Exception:
            pass

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        """Called by the app at 1 Hz."""
        self._update_pi_stats(state)
        self._update_services_from_health(state)

    def _update_pi_stats(self, state: dict) -> None:
        edge = state.get("edge_health", {})
        sys_info = edge.get("system", {})
        agent = edge.get("agent", {})

        if not sys_info:
            try:
                self.query_one("#edge-pi-stats", Static).update(
                    "[dim]Waiting for Pi health data...[/]"
                )
            except Exception:
                pass
            return

        cpu = sys_info.get("cpu_percent", 0)
        ram = sys_info.get("memory_percent", 0)
        temp = sys_info.get("cpu_temp", 0)
        disk = sys_info.get("disk_percent", 0)
        rss = agent.get("rss_mb", 0)

        text = (
            f"CPU: {cpu:5.1f}%    RAM: {ram:5.1f}%    Temp: {temp:4.1f}°C\n"
            f"Disk: {disk:4.1f}%    Agent RSS: {rss:.1f} MB"
        )
        try:
            self.query_one("#edge-pi-stats", Static).update(text)
        except Exception:
            pass

    def _update_services_from_health(self, state: dict) -> None:
        """Update service table from ROS2 health topic (passive, no SSH)."""
        edge = state.get("edge_health", {})
        services = edge.get("services", {})
        if not services:
            return

        try:
            table = self.query_one("#edge-services-table", DataTable)
            for svc in PI_SERVICES:
                svc_info = services.get(svc, {})
                if isinstance(svc_info, dict):
                    is_active = svc_info.get("active", False)
                    sub_state = svc_info.get("sub_state", "unknown")
                    status = "active" if is_active else sub_state
                else:
                    status = "unknown"

                short = svc.replace("rovac-edge-", "")
                indicator = _svc_indicator(status)
                try:
                    table.update_cell(svc, "Service", short)
                    table.update_cell(svc, "Status", indicator)
                except Exception:
                    pass
        except Exception:
            pass
