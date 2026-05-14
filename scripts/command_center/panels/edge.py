"""Edge panel — Pi service management and system health."""

from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, cast

from textual.containers import Container, Horizontal
from textual.widget import Widget
from textual.widgets import DataTable, Static

from ..process_manager import PI_SERVICES

if TYPE_CHECKING:
    # Avoid the circular import at runtime — app.py imports EdgePanel.
    from command_center.app import RovacCommandCenter


# systemd state → Rich-formatted status indicator. dict lookup with a
# fallback is cheaper than 3 conditional branches and pins the supported
# states in one place.
_SVC_INDICATORS: dict[str, str] = {
    "active":   "[green]● active[/]",
    "failed":   "[red]● failed[/]",
    "inactive": "[dim]○ inactive[/]",
}
_SVC_INDICATOR_UNKNOWN = "[yellow]? unknown[/]"


def _svc_indicator(status: str) -> str:
    """Status dot for a systemd service. Any unrecognized status is
    rendered as yellow ``? unknown`` rather than silently dropped."""
    return _SVC_INDICATORS.get(status, _SVC_INDICATOR_UNKNOWN)


class EdgePanel(Widget):
    """Pi edge service management and system monitoring."""

    def __init__(self) -> None:
        super().__init__()
        self._service_statuses: dict[str, str] = {}
        self._refreshing = False

    @property
    def _app(self) -> RovacCommandCenter:
        """Typed accessor — same pattern as DrivePanel / SlamPanel."""
        return cast("RovacCommandCenter", self.app)

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
                statuses = self._app.pm.pi_all_service_status()
                self._service_statuses = statuses
                try:
                    self._app.call_from_thread(self._apply_service_statuses)
                    self._app.call_from_thread(
                        self._show_result, "[green]Refreshed[/]"
                    )
                    # Auto-clear after 4s so a stale "Refreshed" doesn't
                    # mask a later operation's feedback. This was the
                    # "stuck refresh" UX bug — message persisting forever.
                    self._app.call_from_thread(
                        self.set_timer, 4.0,
                        lambda: self._show_result(" "))
                except Exception:
                    pass  # App may have shut down
            except Exception:
                try:
                    self._app.call_from_thread(
                        self._show_result, "[red]SSH refresh failed[/]"
                    )
                    self._app.call_from_thread(
                        self.set_timer, 8.0,
                        lambda: self._show_result(" "))
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
            ok = self._app.pm.pi_service_action("rovac-edge.target", "restart")
            if ok:
                self._app.call_from_thread(
                    self._show_result,
                    "[green]All services restarted[/]",
                )
            else:
                self._app.call_from_thread(
                    self._show_result,
                    "[red]Failed to restart services[/]",
                )
            # Refresh after a moment
            import time
            time.sleep(2)
            self._refreshing = False
            self._app.call_from_thread(self._trigger_refresh)

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
            ok = self._app.pm.pi_service_action(svc, "restart")
            if ok:
                self._app.call_from_thread(
                    self._show_result,
                    f"[green]{short} restarted[/]",
                )
            else:
                self._app.call_from_thread(
                    self._show_result,
                    f"[red]Failed to restart {short}[/]",
                )
            import time
            time.sleep(1)
            self._refreshing = False
            self._app.call_from_thread(self._trigger_refresh)

        self._refreshing = True
        threading.Thread(target=_do_restart, daemon=True).start()

    def _show_result(self, msg: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#edge-action-result", Static).update(msg)

    def update_state(self, state: dict, logs: list, proc_status: dict) -> None:
        """Called by the app at 1 Hz."""
        self._update_pi_stats(state)
        self._update_services_from_health(state)

    def _update_pi_stats(self, state: dict) -> None:
        edge = state.get("edge_health", {})
        sys_info = edge.get("system", {})
        transport = edge.get("agent", {})

        if not sys_info:
            with contextlib.suppress(Exception):
                self.query_one("#edge-pi-stats", Static).update(
                    "[dim]Waiting for Pi health data...[/]"
                )
            return

        cpu = sys_info.get("cpu_percent", 0)
        ram = sys_info.get("memory_percent", 0)
        temp = sys_info.get("cpu_temp", 0)
        disk = sys_info.get("disk_percent", 0)
        rss = transport.get("rss_mb", 0)

        text = (
            f"CPU: {cpu:5.1f}%    RAM: {ram:5.1f}%    Temp: {temp:4.1f}°C\n"
            f"Disk: {disk:4.1f}%    Motor driver RSS: {rss:.1f} MB"
        )
        with contextlib.suppress(Exception):
            self.query_one("#edge-pi-stats", Static).update(text)

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
