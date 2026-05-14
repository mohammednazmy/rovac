"""ROVAC Command Center — Main Textual App."""
from __future__ import annotations

from typing import ClassVar, Protocol, cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane


class _PanelProtocol(Protocol):
    """Structural contract for every panel mounted in the TabbedContent.

    The App's _update_panels loop dispatches state to all panels via this
    method — any new panel must implement it with the same signature.
    Mypy uses this Protocol to verify the cast in _update_panels without
    requiring a common base class (panels inherit from Widget, which has
    no update_state).
    """

    def update_state(self, state: dict, logs: list,
                     proc_status: dict) -> None: ...


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

    # ClassVar — the binding registry is a class-level constant lookup
    # table; instances must not mutate it. Same pattern as drive.py's
    # _STATUS_COLORS and process_manager.py's _EXTERNAL_KILL_PATTERNS.
    # list[Binding] would conflict with App's invariant declaration
    # (`list[Binding | tuple[str, str] | tuple[str, str, str]]`). We
    # only use Binding instances, but mypy needs a wider tuple-friendly
    # type. Type as the same union the base class uses.
    BINDINGS: ClassVar[list[Binding | tuple[str, str]
                              | tuple[str, str, str]]] = [
        # ── Tab navigation ──────────────────────────────────────────────
        Binding("1", "switch_tab('dashboard')", "Dashboard", show=True),
        Binding("2", "switch_tab('drive')", "Drive", show=True),
        Binding("3", "switch_tab('sensors')", "Sensors", show=True),
        Binding("4", "switch_tab('slam')", "SLAM", show=True),
        Binding("5", "switch_tab('edge')", "Edge", show=True),
        Binding("6", "switch_tab('coverage')", "Coverage", show=True),
        # ── Drive controls (letter keys, footer-visible) ────────────────
        # These fire action_drive(key), which forwards to DrivePanel only
        # when the Drive tab is active; on other tabs they're no-ops. The
        # footer still lists them so the user always sees what's available.
        Binding("w",                "drive('w')",     "Fwd",     show=True),
        Binding("s",                "drive('s')",     "Rev",     show=True),
        Binding("a",                "drive('a')",     "Turn-L",  show=True),
        Binding("d",                "drive('d')",     "Turn-R",  show=True),
        Binding("q",                "drive('q')",     "Arc-L",   show=True),
        Binding("e",                "drive('e')",     "Arc-R",   show=True),
        Binding("space",            "drive('space')", "Stop",    show=True),
        Binding("equal,plus",       "drive('equal')", "Gear+",   show=True),
        Binding("minus,underscore", "drive('minus')", "Gear-",   show=True),
        Binding("t",                "drive('t')",     "TapRamp", show=True),
        # ── Arrow keys (dual-purpose, hidden in footer to avoid clutter)─
        # On Drive tab: drive (same as wasd). On other tabs: switch tabs.
        # show=False because the letter aliases above already cover the
        # drive labels — arrows would duplicate them.
        Binding("left",  "arrow('left')",  show=False, priority=True),
        Binding("right", "arrow('right')", show=False, priority=True),
        Binding("up",    "arrow('up')",    show=False, priority=True),
        Binding("down",  "arrow('down')",  show=False, priority=True),
        # ── App ────────────────────────────────────────────────────────
        Binding("ctrl+q", "quit_app", "Quit", show=True),
    ]

    def __init__(self, no_ros: bool = False, pi_host: str = "192.168.1.200",
                 pi_user: str = "pi", no_updater: bool = False) -> None:
        """
        Args:
            no_ros: Skip ROS bridge initialization. ``self.ros`` will be None.
                Used by ``./rovac --no-ros`` for UI dev without a robot.
            pi_host, pi_user: SSH target for Pi service queries.
            no_updater: Skip the ProcessManager background updater thread.
                Tests pass True so construction doesn't make real SSH calls
                to 192.168.1.200. ``self.pm`` is still a real ProcessManager;
                only its daemon thread is suppressed.
        """
        super().__init__()
        self.no_ros = no_ros

        # Initialize ROS bridge
        self.ros = None
        if not no_ros:
            from .ros_bridge import RosBridge
            self.ros = RosBridge()

        # Initialize process manager. start_updater=False suppresses the
        # daemon thread + SSH polling that would otherwise fire during
        # tests (which would block on a real network attempt).
        from .process_manager import ProcessManager
        self.pm = ProcessManager(
            pi_host=pi_host,
            pi_user=pi_user,
            log_fn=self.log_message,
            start_updater=not no_updater,
        )

    def log_message(self, msg: str) -> None:
        """Forward log messages to the ROS bridge log buffer (visible in the
        Dashboard log panel).

        Named ``log_message`` not ``_log`` to avoid shadowing Textual's
        internal ``App._log(verbosity, _textual_calling_frame, *args)``.
        The signature collision would only bite if Textual called its own
        ``_log`` on our instance — empirically it doesn't on the paths we
        exercise, but the name kept tripping mypy and is a real footgun.
        """
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

        from .panels.coverage import CoveragePanel
        from .panels.dashboard import DashboardPanel
        from .panels.drive import DrivePanel
        from .panels.edge import EdgePanel
        from .panels.sensors import SensorsPanel
        from .panels.slam import SlamPanel

        for PanelType in (DashboardPanel, DrivePanel, SensorsPanel, SlamPanel,
                          EdgePanel, CoveragePanel):
            try:
                # Cast to _PanelProtocol so mypy knows update_state exists —
                # the panels structurally satisfy the protocol but inherit
                # only from Widget, which doesn't declare it.
                panel = cast(_PanelProtocol, self.query_one(PanelType))
                panel.update_state(state, logs, proc_status)
            except Exception:
                pass

    # ── Key dispatch ────────────────────────────────────

    def on_key(self, event) -> None:
        """Dispatch key events to the active non-Drive panel.

        Textual events bubble UP from focused widget to Screen/App.
        Panels are children of TabPane (descendants of TabbedContent),
        so their on_key never fires. We catch keys here and dispatch.

        Drive keys are NOT dispatched from here — they're declared as
        App-level BINDINGS so they show up in the Footer, and they route
        through action_drive() instead. Keeping both paths would cause
        double-firing on the Drive tab.
        """
        from textual.widgets import Input

        # Don't intercept when an Input widget is focused
        if isinstance(self.focused, Input):
            return

        tabs = self.query_one(TabbedContent)
        active = tabs.active
        handled = False

        if active == "tab-slam":
            from .panels.slam import SlamPanel
            try:
                handled = self.query_one(SlamPanel).process_key(event.key)
            except Exception as e:
                self.log_message(f"Key dispatch error: {e}")
        elif active == "tab-edge":
            from .panels.edge import EdgePanel
            try:
                handled = self.query_one(EdgePanel).process_key(event.key)
            except Exception as e:
                self.log_message(f"Key dispatch error: {e}")
        elif active == "tab-coverage":
            from .panels.coverage import CoveragePanel
            try:
                handled = self.query_one(CoveragePanel).process_key(event.key)
            except Exception as e:
                self.log_message(f"Key dispatch error: {e}")

        if handled:
            event.stop()

    # ── Actions ────────────────────────────────────────

    def action_drive(self, key: str) -> None:
        """Footer-bound Drive key — forwards to DrivePanel only on Drive tab.

        Letter Drive keys (w/a/s/d/q/e/space/+/-/t) are App-level bindings
        so they appear in the Footer. On non-Drive tabs they're no-ops —
        the user sees them in the Footer as "what's available," but
        nothing happens unless they switch to the Drive tab first.
        """
        from textual.widgets import Input
        if isinstance(self.focused, Input):
            return  # don't intercept while typing in a text input

        tabs = self.query_one(TabbedContent)
        if tabs.active != "tab-drive":
            return

        from .panels.drive import DrivePanel
        try:
            self.query_one(DrivePanel).process_key(key)
        except Exception as e:
            self.log_message(f"Drive key error: {e}")

    def action_arrow(self, key: str) -> None:
        """Arrow keys — drive on Drive tab, switch tabs otherwise.

        Kept separate from action_drive so the arrow-as-tab-nav UX still
        works on Coverage/SLAM/Edge/Dashboard. show=False on the bindings
        keeps the footer uncluttered (letter aliases cover the labels).
        """
        from textual.widgets import Input
        if isinstance(self.focused, Input):
            return

        tabs = self.query_one(TabbedContent)
        if tabs.active == "tab-drive":
            from .panels.drive import DrivePanel
            try:
                self.query_one(DrivePanel).process_key(key)
            except Exception as e:
                self.log_message(f"Drive key error: {e}")
        else:
            # Non-Drive tab: left/right switch tabs via inner Tabs widget
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
        import contextlib
        with contextlib.suppress(Exception):
            self.pm.stop()  # stops the background updater thread
        try:
            if self.ros:
                self.ros.stop()
        except Exception:
            pass
        # Fire-and-forget local-process termination
        with contextlib.suppress(Exception):
            self.pm.stop_all()
        self.exit()
