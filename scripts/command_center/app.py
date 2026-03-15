"""ROVAC Command Center — Main Textual App."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, TabbedContent, TabPane


class RovacCommandCenter(App):
    """ROVAC Robot Command Center — unified TUI for robot control and monitoring."""

    TITLE = "ROVAC Command Center"
    SUB_TITLE = "Robot Control & Monitoring"

    CSS = """
    Screen {
        background: $surface;
    }

    /* ── Tab content area ─────────────────────────────── */
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 0;
    }

    /* ── Shared panel styling ─────────────────────────── */
    .panel-box {
        border: solid $accent;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
    }
    .panel-box-green {
        border: solid green;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        border-title-color: green;
    }
    .panel-box-blue {
        border: solid dodgerblue;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        border-title-color: dodgerblue;
    }
    .panel-box-cyan {
        border: solid darkcyan;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        border-title-color: darkcyan;
    }
    .panel-box-yellow {
        border: solid yellow;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        border-title-color: yellow;
    }
    .panel-box-magenta {
        border: solid magenta;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        border-title-color: magenta;
    }

    /* ── Dashboard ────────────────────────────────────── */
    #dashboard-top-row {
        layout: horizontal;
        height: auto;
    }
    #dashboard-top-row > .panel-box-green,
    #dashboard-top-row > .panel-box-blue {
        width: 1fr;
    }
    #dashboard-bottom-row {
        layout: horizontal;
        height: auto;
    }
    #dashboard-bottom-row > .panel-box-cyan,
    #dashboard-bottom-row > .panel-box-magenta {
        width: 1fr;
    }
    #dash-log-box {
        height: 10;
        overflow-y: auto;
    }

    /* ── Drive panel ──────────────────────────────────── */
    #drive-lower {
        layout: horizontal;
        height: auto;
    }
    #drive-lower > .panel-box-cyan,
    #drive-lower > .panel-box-yellow {
        width: 1fr;
    }

    /* ── Sensors panel ────────────────────────────────── */
    #sensors-diag-row {
        layout: horizontal;
        height: auto;
    }
    #sensors-diag-row > .panel-box-magenta {
        width: 1fr;
    }

    /* ── SLAM panel ───────────────────────────────────── */
    #slam-layout {
        layout: horizontal;
        height: auto;
    }
    #slam-layout > .panel-box-green,
    #slam-layout > .panel-box-blue,
    #slam-layout > .panel-box-cyan {
        width: 1fr;
    }
    #slam-map-input {
        width: 40;
        margin: 0 1;
    }

    /* ── Edge panel ───────────────────────────────────── */
    #edge-services-box {
        height: auto;
        max-height: 20;
    }
    #edge-lower {
        layout: horizontal;
        height: auto;
    }
    #edge-lower > .panel-box-blue,
    #edge-lower > .panel-box-yellow {
        width: 1fr;
    }
    #edge-services-table {
        height: auto;
        max-height: 16;
    }

    /* ── General label / value styling ────────────────── */
    .stat-label {
        width: auto;
        color: $text-muted;
    }
    .stat-value {
        width: auto;
    }
    """

    BINDINGS = [
        Binding("1", "switch_tab('dashboard')", "Dashboard", show=True),
        Binding("2", "switch_tab('drive')", "Drive", show=True),
        Binding("3", "switch_tab('sensors')", "Sensors", show=True),
        Binding("4", "switch_tab('slam')", "SLAM", show=True),
        Binding("5", "switch_tab('edge')", "Edge", show=True),
        Binding("ctrl+q", "quit_app", "Quit", show=True),
    ]

    def __init__(self, no_ros=False, pi_host="192.168.1.200", pi_user="pi"):
        super().__init__()
        self.no_ros = no_ros

        # Initialize ROS bridge
        self.ros = None
        if not no_ros:
            from .ros_bridge import RosBridge
            self.ros = RosBridge()

        # Initialize process manager
        from .process_manager import ProcessManager
        self.pm = ProcessManager(
            pi_host=pi_host,
            pi_user=pi_user,
            log_fn=self._log,
        )

    def _log(self, msg: str):
        """Forward log messages to ROS bridge log buffer."""
        if self.ros:
            self.ros.add_log(msg)

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                from .panels.dashboard import DashboardPanel
                yield DashboardPanel()
            with TabPane("Drive", id="tab-drive"):
                from .panels.drive import DrivePanel
                yield DrivePanel()
            with TabPane("Sensors", id="tab-sensors"):
                from .panels.sensors import SensorsPanel
                yield SensorsPanel()
            with TabPane("SLAM", id="tab-slam"):
                from .panels.slam import SlamPanel
                yield SlamPanel()
            with TabPane("Edge", id="tab-edge"):
                from .panels.edge import EdgePanel
                yield EdgePanel()
        yield Footer()

    def on_mount(self) -> None:
        if self.ros:
            self.ros.start()
        # Periodic UI refresh at 1 Hz
        self.set_interval(1.0, self._update_panels)

    def _update_panels(self) -> None:
        """Push latest state to every panel once per second."""
        state = self.ros.get_state() if self.ros else {}
        logs = self.ros.get_logs() if self.ros else []
        proc_status = self.pm.get_status()

        from .panels.dashboard import DashboardPanel
        from .panels.drive import DrivePanel
        from .panels.sensors import SensorsPanel
        from .panels.slam import SlamPanel
        from .panels.edge import EdgePanel

        for PanelType in (DashboardPanel, DrivePanel, SensorsPanel, SlamPanel, EdgePanel):
            try:
                panel = self.query_one(PanelType)
                panel.update_state(state, logs, proc_status)
            except Exception:
                pass

    # ── Key dispatch ────────────────────────────────────

    def on_key(self, event) -> None:
        """Dispatch key events to the active panel.

        Textual events bubble UP from focused widget to Screen/App.
        Panels are children of TabPane (descendants of TabbedContent),
        so their on_key never fires. We catch keys here and dispatch.
        """
        from textual.widgets import Input

        # Don't intercept when an Input widget is focused
        if isinstance(self.focused, Input):
            return

        tabs = self.query_one(TabbedContent)
        active = tabs.active
        handled = False

        if active == "tab-drive":
            from .panels.drive import DrivePanel
            try:
                handled = self.query_one(DrivePanel).handle_key(event.key)
            except Exception:
                pass
        elif active == "tab-slam":
            from .panels.slam import SlamPanel
            try:
                handled = self.query_one(SlamPanel).handle_key(event.key)
            except Exception:
                pass
        elif active == "tab-edge":
            from .panels.edge import EdgePanel
            try:
                handled = self.query_one(EdgePanel).handle_key(event.key)
            except Exception:
                pass

        if handled:
            event.stop()

    # ── Actions ────────────────────────────────────────

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.active = f"tab-{tab_id}"

    def action_quit_app(self) -> None:
        self.pm.stop_all()
        if self.ros:
            self.ros.stop()
        self.exit()
