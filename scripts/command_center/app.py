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

    /* ── Panel widgets fill their TabPane ───────────── */
    DashboardPanel, DrivePanel, SensorsPanel, SlamPanel, EdgePanel, CoveragePanel {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }

    /* ── Coverage panel rows ──────────────────────────── */
    #cov-row-1, #cov-row-2, #cov-row-3 {
        layout: horizontal;
        height: auto;
    }
    #cov-row-1 > .panel-box-green,
    #cov-row-1 > .panel-box-blue,
    #cov-row-1 > .panel-box-cyan {
        width: 1fr;
    }
    #cov-row-2 > .panel-box-yellow,
    #cov-row-2 > .panel-box-magenta {
        width: 1fr;
    }
    #cov-row-3 > .panel-box-blue,
    #cov-row-3 > .panel-box-green {
        width: 1fr;
    }
    #cov-map-input {
        width: 50;
        margin: 0 1;
    }
    #cov-pose-row {
        layout: horizontal;
        height: auto;
    }
    #cov-pose-row > Input {
        width: 1fr;
        margin: 0 1;
    }

    /* ── Shared panel styling ─────────────────────────── */
    .panel-box, .panel-box-green, .panel-box-blue,
    .panel-box-cyan, .panel-box-yellow, .panel-box-magenta {
        padding: 0 1;
        height: auto;
        min-height: 3;
    }
    .panel-box { border: solid $accent; }
    .panel-box-green { border: solid green; border-title-color: green; }
    .panel-box-blue { border: solid dodgerblue; border-title-color: dodgerblue; }
    .panel-box-cyan { border: solid darkcyan; border-title-color: darkcyan; }
    .panel-box-yellow { border: solid yellow; border-title-color: yellow; }
    .panel-box-magenta { border: solid magenta; border-title-color: magenta; }

    /* ── Dashboard ────────────────────────────────────── */
    #dashboard-top-row {
        layout: horizontal;
        height: auto;
    }
    #dashboard-top-row > .panel-box-green {
        width: 2fr;
    }
    #dashboard-top-row > .panel-box-blue {
        width: 3fr;
    }
    #dashboard-mid-row {
        layout: horizontal;
        height: auto;
    }
    #dashboard-mid-row > .panel-box-cyan {
        width: 1fr;
    }
    #dash-log-box {
        height: 1fr;
        min-height: 4;
        max-height: 10;
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
        Binding("6", "switch_tab('coverage')", "Coverage", show=True),
        # Arrow keys — priority bindings to intercept before Tabs widget
        Binding("left", "arrow('left')", show=False, priority=True),
        Binding("right", "arrow('right')", show=False, priority=True),
        Binding("up", "arrow('up')", show=False, priority=True),
        Binding("down", "arrow('down')", show=False, priority=True),
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
            with TabPane("Coverage", id="tab-coverage"):
                from .panels.coverage import CoveragePanel
                yield CoveragePanel()
        yield Footer()

    def on_mount(self) -> None:
        if self.ros:
            self.ros.start()
        # Immediate first update so panels aren't empty
        self.set_timer(0.1, self._update_panels)
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
        from .panels.coverage import CoveragePanel

        for PanelType in (DashboardPanel, DrivePanel, SensorsPanel, SlamPanel,
                          EdgePanel, CoveragePanel):
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
                handled = self.query_one(DrivePanel).process_key(event.key)
            except Exception as e:
                self._log(f"Key dispatch error: {e}")
        elif active == "tab-slam":
            from .panels.slam import SlamPanel
            try:
                handled = self.query_one(SlamPanel).process_key(event.key)
            except Exception as e:
                self._log(f"Key dispatch error: {e}")
        elif active == "tab-edge":
            from .panels.edge import EdgePanel
            try:
                handled = self.query_one(EdgePanel).process_key(event.key)
            except Exception as e:
                self._log(f"Key dispatch error: {e}")
        elif active == "tab-coverage":
            from .panels.coverage import CoveragePanel
            try:
                handled = self.query_one(CoveragePanel).process_key(event.key)
            except Exception as e:
                self._log(f"Key dispatch error: {e}")

        if handled:
            event.stop()

    # ── Actions ────────────────────────────────────────

    def action_arrow(self, key: str) -> None:
        """Handle arrow keys — drive on Drive tab, switch tabs otherwise."""
        tabs = self.query_one(TabbedContent)
        if tabs.active == "tab-drive":
            from .panels.drive import DrivePanel
            try:
                self.query_one(DrivePanel).process_key(key)
            except Exception as e:
                self._log(f"Drive key error: {e}")
        else:
            # Default: let left/right switch tabs via inner Tabs widget
            from textual.widgets import Tabs
            try:
                inner_tabs = tabs.query_one(Tabs)
                if key == "left":
                    inner_tabs.action_previous_tab()
                elif key == "right":
                    inner_tabs.action_next_tab()
            except Exception:
                pass

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.active = f"tab-{tab_id}"

    def action_quit_app(self) -> None:
        """Fast quit. SSH-based cleanup is best-effort and runs in background
        threads that we let the OS reap when the process dies. We do NOT
        wait for them — that's what made Ctrl-Q hang previously."""
        try:
            self.pm.stop()  # stops the background updater thread
        except Exception:
            pass
        try:
            if self.ros:
                self.ros.stop()
        except Exception:
            pass
        # Fire-and-forget local-process termination
        try:
            self.pm.stop_all()
        except Exception:
            pass
        self.exit()
