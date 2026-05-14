"""Shared fixtures for command_center tests.

Three problems each fixture solves:

1. ``DrivePanel`` / other panels inherit from ``textual.widget.Widget`` and
   need an ``App`` to be useful. Mounting a real Textual App per test costs
   ~100ms/test and pulls in async machinery. For pure-logic tests we
   monkey-patch ``Widget.app`` to a fake.

2. ``self.app.ros.publish_cmd_vel(...)`` and ``self.app._log(...)`` are
   sprinkled throughout panel code. The fake app exposes both as no-op /
   recording stubs so tests can assert what was published.

3. Timers (``self.set_interval``, ``self.set_timer``) are async and pull in
   the Textual event loop. For pure-logic tests we replace them with
   call-counting stubs.

UI tests that need the real Textual harness should use ``App.run_test()``
and the ``pilot`` fixture pattern — see the comment at the bottom for an
example. Those live in their own files marked with ``@pytest.mark.slow``.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pytest

# ── Locate scripts/ on sys.path so `import command_center.panels.drive`
#    works without an install step. Mirrors tests/edge/ convention.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))


# ── Fakes ───────────────────────────────────────────────────────────────

@dataclass
class FakeRosBridge:
    """Drop-in for ``RosBridge`` — records publishes, returns canned state.

    Tests can read ``published`` to assert what was sent to the mux,
    set ``state`` / ``logs`` to control what ``get_state`` returns, and
    mutate ``_hz`` to drive pipeline-health checks.

    Additional canned-return surfaces used by panels:
      - ``rosout_tail`` — list returned by get_rosout_tail
      - ``yaw_offset_deg`` — value returned by load_yaw_offset_deg (None = uncalibrated)
      - ``map_yaw_from_imu_deg`` — value returned by get_map_yaw_from_imu_deg
      - ``amcl_localized_return`` — value returned by is_amcl_localized
      - ``initial_pose_calls`` / ``calibrate_calls`` / ``global_localize_calls`` — assertion lists
    """
    state: dict = field(default_factory=dict)
    logs: list = field(default_factory=list)
    published: list[tuple[float, float]] = field(default_factory=list)
    _hz: dict = field(default_factory=lambda: {
        "cmd_vel_teleop": _FakeHzTracker(0.0),
        "cmd_vel": _FakeHzTracker(0.0),
    })
    rosout_tail: list = field(default_factory=list)
    yaw_offset_deg: float | None = None
    map_yaw_from_imu_deg: float | None = None
    amcl_localized_return: bool = False
    initial_pose_calls: list[tuple[float, float, float]] = field(default_factory=list)
    initial_pose_return: bool = True
    calibrate_calls: list = field(default_factory=list)
    calibrate_return: tuple = (True, 0.0, "calibrated")
    global_localize_calls: int = 0
    global_localize_return: bool = True

    def publish_cmd_vel(self, linear: float, angular: float) -> None:
        self.published.append((linear, angular))
        self.state["cmd_vel_linear"] = linear
        self.state["cmd_vel_angular"] = angular

    def add_log(self, msg: str) -> None:
        self.logs.append(msg)

    def get_state(self) -> dict:
        return dict(self.state)

    def get_logs(self) -> list:
        return list(self.logs)

    def get_rosout_tail(self) -> list:
        return list(self.rosout_tail)

    def load_yaw_offset_deg(self):
        return self.yaw_offset_deg

    def get_map_yaw_from_imu_deg(self):
        return self.map_yaw_from_imu_deg

    def is_amcl_localized(self, max_age_s: float = 5.0) -> bool:
        return self.amcl_localized_return

    def publish_initial_pose(self, x: float, y: float, yaw: float,
                              **_kwargs) -> bool:
        self.initial_pose_calls.append((x, y, yaw))
        return self.initial_pose_return

    def calibrate_yaw_offset(self) -> tuple:
        self.calibrate_calls.append(True)
        return self.calibrate_return

    def trigger_global_localization(self) -> bool:
        self.global_localize_calls += 1
        return self.global_localize_return


class _FakeHzTracker:
    """Stand-in for the ros_bridge's HzTracker — returns a fixed value."""
    def __init__(self, hz: float):
        self._hz = hz

    def hz(self) -> float:
        return self._hz


class FakePm:
    """Stand-in for ProcessManager — records every call.

    Method names mirror the real ProcessManager surface used by panels:
    start_/stop_/get_status/pi_service_action/save_map/etc. Each returns
    a sensible default; tests can override per-instance attributes for
    custom return values, and assert on ``calls`` for invocation tracking.
    """
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []
        # Per-method canned returns; override in tests as needed.
        self._returns: dict[str, object] = {}

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self._returns.get(name, True)

    def set_return(self, method_name: str, value):
        """Override the canned return for one method call."""
        self._returns[method_name] = value

    # ── Production surface methods (record + return canned value) ─────
    def start_slam(self): return self._record("start_slam")
    def stop_slam(self): return self._record("stop_slam")
    def start_foxglove(self): return self._record("start_foxglove")
    def stop_foxglove(self): return self._record("stop_foxglove")
    def start_ekf(self): return self._record("start_ekf")
    def stop_ekf(self): return self._record("stop_ekf")
    def start_nav2(self, m): return self._record("start_nav2", m)
    def stop_nav2(self): return self._record("stop_nav2")
    def start_coverage(self, **k): return self._record("start_coverage", **k)
    def stop_coverage(self): return self._record("stop_coverage")
    def start_coverage_tracker(self): return self._record("start_coverage_tracker")
    def stop_coverage_tracker(self): return self._record("stop_coverage_tracker")
    def get_status(self): return self._returns.get("get_status", {})
    def pi_service_action(self, svc, action):
        return self._record("pi_service_action", svc, action)
    def pi_all_service_status(self):
        return self._returns.get("pi_all_service_status", {})
    def query_nav2_lifecycle(self):
        return self._returns.get("query_nav2_lifecycle", {})
    def foxglove_bridge_alive(self):
        return self._returns.get("foxglove_bridge_alive", False)
    def save_map(self, name): return self._record("save_map", name)
    def list_maps(self): return self._returns.get("list_maps", [])
    def validate_map_for_nav(self, path):
        return self._returns.get("validate_map_for_nav", (True, ""))
    def kill_zombie_teleop(self):
        return self._returns.get("kill_zombie_teleop", 0)
    def recover_nav2_lifecycle(self):
        return self._record("recover_nav2_lifecycle")
    def auto_start_full_stack(self, *a, **k):
        return self._record("auto_start_full_stack", *a, **k)
    def stop_all(self): return self._record("stop_all")
    def dump_diagnostics(self, **k):
        return self._returns.get("dump_diagnostics", "/tmp/diag.txt")


@dataclass
class FakeApp:
    """Drop-in for the Textual App on a panel — only the bits panels touch.

    ``log_message`` mirrors the real App's logger (which dispatches to
    ``self.ros.add_log``) so tests can assert what was logged.
    ``pm`` is a FakePm — the SLAM, Edge, and Coverage panels call into it.
    """
    ros: FakeRosBridge = field(default_factory=FakeRosBridge)
    pm: FakePm = field(default_factory=FakePm)

    def log_message(self, msg: str) -> None:
        self.ros.add_log(msg)

    def call_from_thread(self, func, *args, **kwargs):
        """Stub for Textual's thread-safe scheduler — just call inline."""
        return func(*args, **kwargs)


class FakeTimer:
    """Stand-in for a Textual Timer — just supports .stop()."""
    def __init__(self):
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def fake_ros() -> FakeRosBridge:
    """A fresh FakeRosBridge per test — no state leaks between tests."""
    return FakeRosBridge()


@pytest.fixture
def fake_timer() -> FakeTimer:
    """A FakeTimer — exposed as a fixture so tests don't have to know
    about the conftest module's import path (pytest discovers test files
    as standalone, not as a package)."""
    return FakeTimer()


@pytest.fixture
def fake_pm() -> FakePm:
    """A fresh FakePm per test — no call history leaks."""
    return FakePm()


@pytest.fixture
def fake_app(fake_ros: FakeRosBridge, fake_pm: FakePm) -> FakeApp:
    """A FakeApp wired to the per-test fake_ros + fake_pm."""
    return FakeApp(ros=fake_ros, pm=fake_pm)


def _build_panel(PanelClass, fake_app, monkeypatch):
    """Generic helper — instantiate a Textual panel with the App descriptor
    patched and Textual machinery stubbed. Used by every panel fixture.

    Returns the panel; the caller is responsible for any panel-specific
    extra setup (e.g. populating ``_service_statuses`` for EdgePanel).
    """
    # Inject the fake app via property override (Widget.app has no setter).
    monkeypatch.setattr(PanelClass, "app",
                        property(lambda self: fake_app))

    panel = PanelClass()

    # Stub Textual timer machinery so action handlers don't try to schedule
    # real callbacks.
    publish_timer = FakeTimer()
    panel.set_interval = lambda *a, **k: publish_timer  # type: ignore[method-assign]
    panel.set_timer = lambda *a, **k: FakeTimer()       # type: ignore[method-assign]

    # query_one returns a stub that .update() / .add_columns() etc on.
    # Each (selector, type) pair gets a fresh stub so tests can inspect
    # the last value set per widget via panel.queried[selector].last_update.
    queried: dict = {}
    panel.queried = queried  # type: ignore[attr-defined]

    class _StubWidget:
        def __init__(self, name=""):
            self.name = name
            self.last_update = None
            self.cursor_type = None
            self.cursor_row = 0
            self.rows = []
            self.value = ""  # for Input widgets
        def update(self, text):
            self.last_update = text
        def add_columns(self, *cols):
            self.cols = cols
        def add_row(self, *vals, key=None):
            self.rows.append((vals, key))
        def update_cell(self, *a, **k):
            pass

    def fake_query_one(selector, _widget_type=None):
        if selector not in queried:
            queried[selector] = _StubWidget(selector)
        return queried[selector]
    panel.query_one = fake_query_one  # type: ignore[method-assign]
    return panel


@pytest.fixture
def drive_panel(fake_app: FakeApp, monkeypatch: pytest.MonkeyPatch):
    """A DrivePanel wired to fake_app via _build_panel. See _build_panel
    docstring for why we monkey-patch Widget.app instead of subclassing.
    """
    from command_center.panels import drive
    return _build_panel(drive.DrivePanel, fake_app, monkeypatch)


@pytest.fixture
def dashboard_panel(fake_app: FakeApp, monkeypatch: pytest.MonkeyPatch):
    """A DashboardPanel ready for update_state() tests."""
    from command_center.panels import dashboard
    return _build_panel(dashboard.DashboardPanel, fake_app, monkeypatch)


@pytest.fixture
def sensors_panel(fake_app: FakeApp, monkeypatch: pytest.MonkeyPatch):
    """A SensorsPanel ready for update_state() tests."""
    from command_center.panels import sensors
    return _build_panel(sensors.SensorsPanel, fake_app, monkeypatch)


@pytest.fixture
def slam_panel(fake_app: FakeApp, monkeypatch: pytest.MonkeyPatch):
    """A SlamPanel ready for process_key() + update_state() tests."""
    from command_center.panels import slam
    return _build_panel(slam.SlamPanel, fake_app, monkeypatch)


@pytest.fixture
def edge_panel(fake_app: FakeApp, monkeypatch: pytest.MonkeyPatch):
    """An EdgePanel ready for process_key() + update_state() tests.

    Note: EdgePanel.__init__ doesn't take args, but populates instance
    state used by callbacks. We don't call on_mount() — that would try
    to register a DataTable cursor type and call _trigger_refresh which
    spawns a thread.
    """
    from command_center.panels import edge
    return _build_panel(edge.EdgePanel, fake_app, monkeypatch)


@pytest.fixture
def coverage_panel(fake_app: FakeApp, monkeypatch: pytest.MonkeyPatch):
    """A CoveragePanel — the biggest panel, but uses the same _build_panel
    pattern. Tests should pre-populate ``panel.queried["#cov-map-input"]``
    etc. when exercising paths that read Input values."""
    from command_center.panels import coverage
    return _build_panel(coverage.CoveragePanel, fake_app, monkeypatch)


# ── ROS message factories ───────────────────────────────────────────────
#
# These build minimal namespace objects that quack like the real ROS msg
# types — only the attributes our callbacks actually read. They keep
# rclpy out of the test path entirely, which makes the suite installable
# anywhere Python runs.

import math as _math
import types
from types import SimpleNamespace


def _quat_from_yaw(yaw: float) -> types.SimpleNamespace:
    """Return a quaternion (x, y, z, w) representing a yaw-only rotation."""
    return types.SimpleNamespace(
        x=0.0, y=0.0,
        z=_math.sin(yaw / 2.0),
        w=_math.cos(yaw / 2.0),
    )


@pytest.fixture
def make_odom_msg():
    """Factory for a nav_msgs/Odometry-shaped message."""
    def _make(x=0.0, y=0.0, yaw=0.0, vx=0.0, wz=0.0):
        return types.SimpleNamespace(
            pose=types.SimpleNamespace(
                pose=types.SimpleNamespace(
                    position=types.SimpleNamespace(x=x, y=y, z=0.0),
                    orientation=_quat_from_yaw(yaw),
                ),
            ),
            twist=types.SimpleNamespace(
                twist=types.SimpleNamespace(
                    linear=types.SimpleNamespace(x=vx, y=0.0, z=0.0),
                    angular=types.SimpleNamespace(x=0.0, y=0.0, z=wz),
                ),
            ),
        )
    return _make


@pytest.fixture
def make_imu_msg():
    """Factory for a sensor_msgs/Imu-shaped BNO055 message."""
    def _make(ax=0.0, ay=0.0, az=0.0, gx=0.0, gy=0.0, gz=0.0,
              roll=0.0, pitch=0.0, yaw=0.0):
        cr, sr = _math.cos(roll / 2), _math.sin(roll / 2)
        cp, sp = _math.cos(pitch / 2), _math.sin(pitch / 2)
        cy, sy = _math.cos(yaw / 2), _math.sin(yaw / 2)
        return types.SimpleNamespace(
            linear_acceleration=types.SimpleNamespace(x=ax, y=ay, z=az),
            angular_velocity=types.SimpleNamespace(x=gx, y=gy, z=gz),
            orientation=types.SimpleNamespace(
                w=cr * cp * cy + sr * sp * sy,
                x=sr * cp * cy - cr * sp * sy,
                y=cr * sp * cy + sr * cp * sy,
                z=cr * cp * sy - sr * sp * cy,
            ),
        )
    return _make


@pytest.fixture
def make_scan_msg():
    """Factory for a sensor_msgs/LaserScan-shaped message."""
    def _make(ranges, range_min=0.1, range_max=12.0):
        return types.SimpleNamespace(
            ranges=ranges,
            range_min=range_min,
            range_max=range_max,
        )
    return _make


@pytest.fixture
def make_map_msg():
    """Factory for a nav_msgs/OccupancyGrid-shaped message.

    `cells` is a flat list of int8 values: -1 unknown, 0 free, 100 occupied.
    Wrapped in ``array.array('b', ...)`` because the bridge does
    ``bytes(msg.data)`` which expects a buffer-protocol object —
    ``bytes([-1, 100])`` fails because list-iteration requires 0–255.
    Real ROS2 sends ``array.array('b', ...)`` so this matches production.
    """
    import array

    def _make(cells, width=10, height=10, resolution=0.05):
        if not isinstance(cells, (bytes, bytearray, array.array)):
            cells = array.array("b", cells)
        return types.SimpleNamespace(
            data=cells,
            info=types.SimpleNamespace(
                width=width, height=height, resolution=resolution,
            ),
        )
    return _make


@pytest.fixture
def make_diag_msg():
    """Factory for a diagnostic_msgs/DiagnosticArray-shaped message.

    `statuses` is a list of (name, [(key, value), ...]) tuples.
    """
    def _make(statuses):
        return types.SimpleNamespace(
            status=[
                types.SimpleNamespace(
                    name=name,
                    values=[
                        types.SimpleNamespace(key=k, value=v)
                        for k, v in kv
                    ],
                )
                for name, kv in statuses
            ],
        )
    return _make


@pytest.fixture
def make_amcl_msg():
    """Factory for a geometry_msgs/PoseWithCovarianceStamped-shaped message."""
    def _make(x=0.0, y=0.0, yaw=0.0, cov_xx=0.25, cov_yy=0.25, cov_yaw=0.05):
        cov = [0.0] * 36
        cov[0] = cov_xx
        cov[7] = cov_yy
        cov[35] = cov_yaw
        return types.SimpleNamespace(
            pose=types.SimpleNamespace(
                pose=types.SimpleNamespace(
                    position=types.SimpleNamespace(x=x, y=y, z=0.0),
                    orientation=_quat_from_yaw(yaw),
                ),
                covariance=cov,
            ),
        )
    return _make


@pytest.fixture
def make_rosout_msg():
    """Factory for an rcl_interfaces/Log-shaped message.

    `level` should be the numeric constant: 10 DEBUG, 20 INFO, 30 WARN,
    40 ERROR, 50 FATAL — only WARN+ is kept by the bridge.
    """
    def _make(level=30, name="some_node", msg=""):
        return types.SimpleNamespace(level=level, name=name, msg=msg)
    return _make


@pytest.fixture
def bridge():
    """A fresh RosBridge instance — no ROS init, no spin thread.

    The bridge's pure state, log buffer, HzTracker, and callbacks are all
    testable without ever calling `start()`. Tests that need the spin
    loop or real publishers should mock rclpy at the module level.
    """
    from command_center.ros_bridge import RosBridge
    return RosBridge()


# ── process_manager fixtures ────────────────────────────────────────────

class FakeCompletedProcess:
    """Stand-in for ``subprocess.CompletedProcess`` — minimal attrs only."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakePopen:
    """Stand-in for ``subprocess.Popen``.

    Records pid (incremented per instance), the cmd list, exposes
    ``poll()`` / ``wait()`` / ``returncode``. Default behavior: process
    is "still running" until ``set_exited(code)`` is called, then poll()
    returns the code.
    """
    _next_pid = 50000

    def __init__(self, cmd, *_args, **_kwargs):
        FakePopen._next_pid += 1
        self.pid = FakePopen._next_pid
        self.cmd = cmd
        self.returncode = None  # None = still running

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode if self.returncode is not None else 0

    def set_exited(self, code: int = 0):
        self.returncode = code


@pytest.fixture
def fake_popens():
    """Returns the list of FakePopen instances created during the test."""
    return []


@pytest.fixture
def mock_subprocess(monkeypatch, fake_popens):
    """Single fixture installing fake subprocess.run AND subprocess.Popen
    at the ``command_center.process_manager.subprocess`` module attribute.

    The returned namespace exposes:
      - ``set_run_result(returncode, stdout, stderr)`` — what run() returns
      - ``run_calls`` — list of (args, kwargs) tuples for every run() call
      - ``popens`` — list of FakePopen instances

    For tests that need different responses per call, set ``run_handler``
    to a callable ``(args, kwargs) -> FakeCompletedProcess``.
    """
    state = SimpleNamespace(
        run_calls=[],
        popens=fake_popens,
        run_handler=None,
        _default=FakeCompletedProcess(returncode=0, stdout="", stderr=""),
    )

    def fake_run(args, **kwargs):
        state.run_calls.append((args, kwargs))
        if state.run_handler is not None:
            return state.run_handler(args, kwargs)
        return state._default

    def fake_popen(cmd, *args, **kwargs):
        proc = FakePopen(cmd, *args, **kwargs)
        fake_popens.append(proc)
        return proc

    def set_run_result(returncode=0, stdout="", stderr=""):
        state._default = FakeCompletedProcess(returncode, stdout, stderr)

    state.set_run_result = set_run_result

    # Patch on the module where process_manager imports subprocess.
    from command_center import process_manager
    monkeypatch.setattr(process_manager.subprocess, "run", fake_run)
    monkeypatch.setattr(process_manager.subprocess, "Popen", fake_popen)

    return state


@pytest.fixture
def pm(mock_subprocess):
    """A ProcessManager with the background updater disabled and all
    subprocess calls mocked. The returned ProcessManager records every
    log line into ``pm.captured_logs`` for easy assertions.
    """
    from command_center.process_manager import ProcessManager
    captured: list[str] = []
    pm = ProcessManager(log_fn=captured.append, start_updater=False)
    pm.captured_logs = captured  # type: ignore[attr-defined]
    yield pm
    pm.stop()


# ── UI test note ────────────────────────────────────────────────────────
#
# For tests that need a real Textual event loop (key dispatch, focus,
# binding firing, footer rendering, etc.), use App.run_test():
#
#     @pytest.mark.slow
#     async def test_drive_tab_responds_to_w(monkeypatch):
#         from command_center.app import RovacCommandCenter
#         app = RovacCommandCenter(no_ros=True)
#         async with app.run_test() as pilot:
#             await pilot.press("2")           # switch to Drive tab
#             await pilot.press("w")
#             # assert something on the DrivePanel
#
# Such tests are slow (~100-500ms each) and run in CI separately. Keep
# them in a dedicated file (e.g. test_app_pilot.py) so the fast-tier
# suite stays sub-second.
