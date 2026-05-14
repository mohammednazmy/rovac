"""Pure-logic tests for ``command_center.app``.

Covers:
  * BINDINGS list — shape, no key collisions, expected actions present
  * ``RovacCommandCenter.__init__`` with no_ros / no_updater opt-outs
  * ``log_message`` dispatch + no-op when ros absent
  * Action methods called directly without a Textual event loop

UI-bound behavior (key dispatch, footer rendering, focus, Tab switching
under a real Textual loop) is covered separately in test_app_pilot.py
which uses ``App.run_test()`` and is marked ``@pytest.mark.slow``.
"""
from __future__ import annotations

import pytest

from command_center.app import RovacCommandCenter, _PanelProtocol


# ════════════════════════════════════════════════════════════════════════
# BINDINGS shape
# ════════════════════════════════════════════════════════════════════════

class TestBindings:

    def test_no_duplicate_keys(self):
        """Every key gets exactly one binding. A collision would cause
        the second binding to silently win."""
        seen: dict[str, str] = {}
        for b in RovacCommandCenter.BINDINGS:
            for key in b.key.split(","):
                key = key.strip()
                assert key not in seen, (
                    f"key {key!r} bound twice: {seen[key]} and {b.action}")
                seen[key] = b.action

    def test_all_tabs_bound_1_to_6(self):
        actions = {b.action for b in RovacCommandCenter.BINDINGS}
        for tab in ("dashboard", "drive", "sensors", "slam",
                    "edge", "coverage"):
            assert f"switch_tab('{tab}')" in actions

    def test_drive_letter_keys_present(self):
        """w/s/a/d/q/e/space/+/-/t — the full Drive surface."""
        keys = {b.key for b in RovacCommandCenter.BINDINGS}
        for k in ("w", "s", "a", "d", "q", "e", "space", "t"):
            assert k in keys, f"missing Drive binding for {k!r}"

    def test_arrows_are_priority(self):
        """Arrow bindings need priority=True to intercept before Textual's
        TabbedContent consumes them for tab nav."""
        arrows = [b for b in RovacCommandCenter.BINDINGS
                  if b.key in ("left", "right", "up", "down")]
        assert len(arrows) == 4
        assert all(b.priority for b in arrows)

    def test_arrows_hidden_in_footer(self):
        """Arrow keys aren't shown in the footer — the letter aliases
        (w/s/a/d) already cover their meaning, and showing them would
        duplicate the footer chips."""
        arrows = [b for b in RovacCommandCenter.BINDINGS
                  if b.key in ("left", "right", "up", "down")]
        assert all(not b.show for b in arrows)

    def test_quit_binding_present(self):
        keys = {b.key for b in RovacCommandCenter.BINDINGS}
        assert "ctrl+q" in keys


# ════════════════════════════════════════════════════════════════════════
# Panel protocol
# ════════════════════════════════════════════════════════════════════════

class TestPanelProtocol:

    @pytest.mark.parametrize("panel_module,panel_class", [
        ("dashboard", "DashboardPanel"),
        ("drive", "DrivePanel"),
        ("sensors", "SensorsPanel"),
        ("slam", "SlamPanel"),
        ("edge", "EdgePanel"),
        ("coverage", "CoveragePanel"),
    ])
    def test_each_panel_implements_protocol(self, panel_module, panel_class):
        """Structural verification — each panel must have an update_state
        method matching _PanelProtocol's signature. If a new panel forgets
        to implement update_state, this test fires immediately."""
        import importlib
        mod = importlib.import_module(f"command_center.panels.{panel_module}")
        cls = getattr(mod, panel_class)
        assert hasattr(cls, "update_state"), \
            f"{panel_class} must implement update_state(state, logs, proc_status)"
        # Don't isinstance-check the Protocol — Protocols only support
        # isinstance with @runtime_checkable. Hasattr is the structural
        # equivalent that mirrors what mypy verifies at type-check time.


# ════════════════════════════════════════════════════════════════════════
# Construction
# ════════════════════════════════════════════════════════════════════════

class TestConstruction:

    def test_no_ros_skips_bridge(self):
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            assert app.ros is None
            assert app.no_ros is True
        finally:
            app.pm.stop()

    def test_no_updater_suppresses_pm_thread(self):
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            # pm exists but background updater thread is None
            assert app.pm is not None
            assert app.pm._updater is None
        finally:
            app.pm.stop()

    def test_default_pi_host(self):
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            assert app.pm.pi_host == "192.168.1.200"
            assert app.pm.pi_user == "pi"
        finally:
            app.pm.stop()

    def test_custom_pi_host(self):
        app = RovacCommandCenter(no_ros=True, no_updater=True,
                                  pi_host="10.0.0.5", pi_user="ubuntu")
        try:
            assert app.pm.pi_host == "10.0.0.5"
            assert app.pm.pi_user == "ubuntu"
        finally:
            app.pm.stop()


# ════════════════════════════════════════════════════════════════════════
# log_message
# ════════════════════════════════════════════════════════════════════════

class TestLogMessage:

    def test_silent_when_no_ros(self):
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            # Should not raise — silently no-ops when ros is None
            app.log_message("anything")
        finally:
            app.pm.stop()

    def test_forwards_to_ros_bridge(self, monkeypatch):
        """When ros IS present, log_message dispatches to add_log."""
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            # Inject a fake ros bridge
            captured = []
            class FakeRos:
                def add_log(self, msg):
                    captured.append(msg)
            app.ros = FakeRos()  # type: ignore[assignment]
            app.log_message("hello")
            assert captured == ["hello"]
        finally:
            app.pm.stop()


# ════════════════════════════════════════════════════════════════════════
# Coverage closer: no_ros=False creates a RosBridge
# ════════════════════════════════════════════════════════════════════════

class TestRosBridgeConstruction:

    def test_no_ros_false_creates_bridge(self, monkeypatch):
        """The default no_ros=False path imports RosBridge and instantiates
        it. Mock RosBridge to avoid spinning up real rclpy state."""
        from unittest.mock import MagicMock
        fake_bridge = MagicMock()
        # Patch where it's imported INSIDE __init__
        monkeypatch.setattr(
            "command_center.ros_bridge.RosBridge",
            MagicMock(return_value=fake_bridge))
        app = RovacCommandCenter(no_ros=False, no_updater=True)
        try:
            assert app.ros is fake_bridge
            assert app.no_ros is False
        finally:
            app.pm.stop()


# ════════════════════════════════════════════════════════════════════════
# Coverage closer: on_mount starts ros bridge when present
# ════════════════════════════════════════════════════════════════════════

class TestOnMount:

    def test_on_mount_starts_ros_when_present(self, monkeypatch):
        """on_mount calls self.ros.start() when ros bridge exists."""
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from unittest.mock import MagicMock
            app.ros = MagicMock()  # type: ignore[assignment]
            # Stub out Textual timer scheduling so the test doesn't try
            # to spin up an event loop.
            app.set_timer = MagicMock()  # type: ignore[method-assign]
            app.set_interval = MagicMock()  # type: ignore[method-assign]
            app.on_mount()
            app.ros.start.assert_called_once()
            # Both timer scheduling calls also happened
            app.set_timer.assert_called_once()
            app.set_interval.assert_called_once()
        finally:
            app.pm.stop()


# ════════════════════════════════════════════════════════════════════════
# Coverage closer: _update_panels exception swallowed per-panel
# ════════════════════════════════════════════════════════════════════════

class TestUpdatePanelsExceptionHandling:

    def test_panel_update_exception_doesnt_break_others(self, monkeypatch):
        """A panel that crashes during update_state must not prevent the
        other 5 panels from being updated."""
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            app.ros = None  # state = {}, logs = []
            # Mock query_one so all 6 panel lookups succeed
            from command_center.panels.dashboard import DashboardPanel
            from command_center.panels.drive import DrivePanel
            panels_called = []
            def fake_query(PanelType):
                if PanelType is DrivePanel:
                    # Drive panel's update_state raises
                    p = MagicMock()
                    p.update_state.side_effect = RuntimeError("drive broke")
                    panels_called.append("drive (will raise)")
                    return p
                p = MagicMock()
                panels_called.append(PanelType.__name__)
                return p
            app.query_one = fake_query  # type: ignore[method-assign]
            # Must not raise
            app._update_panels()
            # All 6 panels were queried (drive raised but didn't stop iteration)
            assert len(panels_called) == 6
        finally:
            app.pm.stop()


# ════════════════════════════════════════════════════════════════════════
# Coverage closer: on_key dispatch for non-drive tabs
# ════════════════════════════════════════════════════════════════════════

class TestOnKeyDispatch:
    """on_key dispatches keys to the active panel (drive is handled by
    bindings, but slam/edge/coverage still go through this path)."""

    def _make_event(self, key):
        from unittest.mock import MagicMock
        evt = MagicMock()
        evt.key = key
        return evt

    def _make_app_with_tab(self, monkeypatch, active_tab):
        """App with a stubbed TabbedContent reporting `active_tab`."""
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        # Stub query_one to return a fake TabbedContent with .active
        fake_tabs = MagicMock()
        fake_tabs.active = active_tab
        fake_panels = {}
        from command_center.panels.slam import SlamPanel
        from command_center.panels.edge import EdgePanel
        from command_center.panels.coverage import CoveragePanel
        from textual.widgets import TabbedContent
        def fake_query(arg, *a, **k):
            if arg is TabbedContent:
                return fake_tabs
            # Return a cached panel mock per type — re-querying must yield
            # the SAME instance so side_effects set in test setup persist.
            if arg not in fake_panels:
                p = MagicMock()
                p.process_key = MagicMock(return_value=True)
                fake_panels[arg] = p
            return fake_panels[arg]
        app.query_one = fake_query  # type: ignore[method-assign]
        # Ensure self.focused is not an Input (so on_key proceeds)
        from command_center.app import RovacCommandCenter as RCC
        monkeypatch.setattr(RCC, "focused",
                            property(lambda self: None))
        return app, fake_panels

    def test_slam_tab_dispatches_to_slam_panel(self, monkeypatch):
        from command_center.panels.slam import SlamPanel
        app, fake_panels = self._make_app_with_tab(monkeypatch, "tab-slam")
        try:
            evt = self._make_event("s")
            app.on_key(evt)
            assert SlamPanel in fake_panels
            fake_panels[SlamPanel].process_key.assert_called_once_with("s")
            evt.stop.assert_called_once()
        finally:
            app.pm.stop()

    def test_edge_tab_dispatches_to_edge_panel(self, monkeypatch):
        from command_center.panels.edge import EdgePanel
        app, fake_panels = self._make_app_with_tab(monkeypatch, "tab-edge")
        try:
            app.on_key(self._make_event("r"))
            assert EdgePanel in fake_panels
            fake_panels[EdgePanel].process_key.assert_called_once_with("r")
        finally:
            app.pm.stop()

    def test_coverage_tab_dispatches_to_coverage_panel(self, monkeypatch):
        from command_center.panels.coverage import CoveragePanel
        app, fake_panels = self._make_app_with_tab(monkeypatch,
                                                    "tab-coverage")
        try:
            app.on_key(self._make_event("a"))
            assert CoveragePanel in fake_panels
            fake_panels[CoveragePanel].process_key.assert_called_once_with("a")
        finally:
            app.pm.stop()

    def test_slam_panel_exception_logged(self, monkeypatch):
        """If the panel's process_key raises, the error is logged via
        log_message — doesn't propagate."""
        from command_center.panels.slam import SlamPanel
        app, fake_panels = self._make_app_with_tab(monkeypatch, "tab-slam")
        try:
            logs = []
            app.log_message = logs.append  # type: ignore[method-assign]
            # Need to call the path that actually catches — make process_key raise
            # First call to trigger fake_panels[SlamPanel] creation
            app.on_key(self._make_event("s"))
            fake_panels[SlamPanel].process_key.side_effect = RuntimeError(
                "panel boom")
            app.on_key(self._make_event("s"))
            # log_message captured the dispatch error
            assert any("Key dispatch error" in m for m in logs)
        finally:
            app.pm.stop()

    def test_edge_panel_exception_logged(self, monkeypatch):
        from command_center.panels.edge import EdgePanel
        app, fake_panels = self._make_app_with_tab(monkeypatch, "tab-edge")
        try:
            logs = []
            app.log_message = logs.append  # type: ignore[method-assign]
            app.on_key(self._make_event("r"))
            fake_panels[EdgePanel].process_key.side_effect = RuntimeError(
                "boom")
            app.on_key(self._make_event("r"))
            assert any("Key dispatch error" in m for m in logs)
        finally:
            app.pm.stop()

    def test_coverage_panel_exception_logged(self, monkeypatch):
        from command_center.panels.coverage import CoveragePanel
        app, fake_panels = self._make_app_with_tab(monkeypatch,
                                                    "tab-coverage")
        try:
            logs = []
            app.log_message = logs.append  # type: ignore[method-assign]
            app.on_key(self._make_event("a"))
            fake_panels[CoveragePanel].process_key.side_effect = RuntimeError(
                "boom")
            app.on_key(self._make_event("a"))
            assert any("Key dispatch error" in m for m in logs)
        finally:
            app.pm.stop()

    def test_input_focused_skips_dispatch(self, monkeypatch):
        """When an Input widget is focused, on_key returns early so the
        Input receives the keystroke normally."""
        from unittest.mock import MagicMock
        from textual.widgets import Input
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            # Override focused to return an Input-like object
            from command_center.app import RovacCommandCenter as RCC
            fake_input = MagicMock(spec=Input)
            monkeypatch.setattr(RCC, "focused",
                                property(lambda self: fake_input))
            app.query_one = MagicMock()  # type: ignore[method-assign]
            evt = self._make_event("x")
            app.on_key(evt)
            # query_one should NOT have been called — early return
            app.query_one.assert_not_called()
        finally:
            app.pm.stop()


# ════════════════════════════════════════════════════════════════════════
# Coverage closer: action_drive + action_arrow direct unit tests
# ════════════════════════════════════════════════════════════════════════

class TestActionDrive:

    def test_input_focused_skips(self, monkeypatch):
        from unittest.mock import MagicMock
        from textual.widgets import Input
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused",
                                property(lambda self: MagicMock(spec=Input)))
            app.query_one = MagicMock()  # type: ignore[method-assign]
            app.action_drive("w")
            app.query_one.assert_not_called()
        finally:
            app.pm.stop()

    def test_non_drive_tab_no_ops(self, monkeypatch):
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused", property(lambda self: None))
            fake_tabs = MagicMock()
            fake_tabs.active = "tab-dashboard"
            from textual.widgets import TabbedContent
            from command_center.panels.drive import DrivePanel
            drive_mock = MagicMock()
            def fake_query(arg, *a, **k):
                return fake_tabs if arg is TabbedContent else drive_mock
            app.query_one = fake_query  # type: ignore[method-assign]
            app.action_drive("w")
            # DrivePanel.process_key should NOT have been called
            drive_mock.process_key.assert_not_called()
        finally:
            app.pm.stop()

    def test_drive_panel_exception_logged(self, monkeypatch):
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused", property(lambda self: None))
            fake_tabs = MagicMock()
            fake_tabs.active = "tab-drive"
            from textual.widgets import TabbedContent
            from command_center.panels.drive import DrivePanel
            drive_mock = MagicMock()
            drive_mock.process_key.side_effect = RuntimeError("drive boom")
            def fake_query(arg, *a, **k):
                return fake_tabs if arg is TabbedContent else drive_mock
            app.query_one = fake_query  # type: ignore[method-assign]
            logs = []
            app.log_message = logs.append  # type: ignore[method-assign]
            app.action_drive("w")
            assert any("Drive key error" in m for m in logs)
        finally:
            app.pm.stop()


class TestActionArrow:

    def test_input_focused_skips(self, monkeypatch):
        from unittest.mock import MagicMock
        from textual.widgets import Input
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused",
                                property(lambda self: MagicMock(spec=Input)))
            app.query_one = MagicMock()  # type: ignore[method-assign]
            app.action_arrow("left")
            app.query_one.assert_not_called()
        finally:
            app.pm.stop()

    def test_drive_tab_dispatches_to_drive_panel(self, monkeypatch):
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused", property(lambda self: None))
            fake_tabs = MagicMock()
            fake_tabs.active = "tab-drive"
            from textual.widgets import TabbedContent
            from command_center.panels.drive import DrivePanel
            drive_mock = MagicMock()
            def fake_query(arg, *a, **k):
                return fake_tabs if arg is TabbedContent else drive_mock
            app.query_one = fake_query  # type: ignore[method-assign]
            app.action_arrow("up")
            drive_mock.process_key.assert_called_once_with("up")
        finally:
            app.pm.stop()

    def test_drive_panel_exception_logged(self, monkeypatch):
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused", property(lambda self: None))
            fake_tabs = MagicMock()
            fake_tabs.active = "tab-drive"
            from textual.widgets import TabbedContent
            from command_center.panels.drive import DrivePanel
            drive_mock = MagicMock()
            drive_mock.process_key.side_effect = RuntimeError("boom")
            def fake_query(arg, *a, **k):
                return fake_tabs if arg is TabbedContent else drive_mock
            app.query_one = fake_query  # type: ignore[method-assign]
            logs = []
            app.log_message = logs.append  # type: ignore[method-assign]
            app.action_arrow("up")
            assert any("Drive key error" in m for m in logs)
        finally:
            app.pm.stop()

    def test_non_drive_tab_switches_via_tabs_widget(self, monkeypatch):
        """On non-Drive tab, arrows go to tab navigation via the inner
        Tabs widget's action_{previous,next}_tab."""
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused", property(lambda self: None))
            fake_tabs = MagicMock()
            fake_tabs.active = "tab-coverage"
            fake_inner_tabs = MagicMock()
            fake_tabs.query_one.return_value = fake_inner_tabs
            from textual.widgets import TabbedContent
            def fake_query(arg, *a, **k):
                return fake_tabs if arg is TabbedContent else MagicMock()
            app.query_one = fake_query  # type: ignore[method-assign]
            app.action_arrow("left")
            fake_inner_tabs.action_previous_tab.assert_called_once()
            app.action_arrow("right")
            fake_inner_tabs.action_next_tab.assert_called_once()
        finally:
            app.pm.stop()

    def test_non_drive_tab_query_exception_swallowed(self, monkeypatch):
        """If finding the inner Tabs widget fails, the action_arrow path
        swallows the exception silently — arrow keys just do nothing."""
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused", property(lambda self: None))
            fake_tabs = MagicMock()
            fake_tabs.active = "tab-coverage"
            fake_tabs.query_one.side_effect = RuntimeError("no tabs")
            from textual.widgets import TabbedContent
            def fake_query(arg, *a, **k):
                return fake_tabs if arg is TabbedContent else MagicMock()
            app.query_one = fake_query  # type: ignore[method-assign]
            # Must not raise
            app.action_arrow("left")
        finally:
            app.pm.stop()

    @pytest.mark.parametrize("key", ["up", "down"])
    def test_non_drive_tab_up_down_arrows_no_op(self, monkeypatch, key):
        """Up/Down arrow keys on a non-Drive tab fall through the
        if/elif chain without calling action_previous/next_tab. The tab
        nav only honors left/right."""
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            from command_center.app import RovacCommandCenter as RCC
            monkeypatch.setattr(RCC, "focused", property(lambda self: None))
            fake_tabs = MagicMock()
            fake_tabs.active = "tab-coverage"
            fake_inner_tabs = MagicMock()
            fake_tabs.query_one.return_value = fake_inner_tabs
            from textual.widgets import TabbedContent
            def fake_query(arg, *a, **k):
                return fake_tabs if arg is TabbedContent else MagicMock()
            app.query_one = fake_query  # type: ignore[method-assign]
            app.action_arrow(key)
            # Neither tab-nav action should have fired
            fake_inner_tabs.action_previous_tab.assert_not_called()
            fake_inner_tabs.action_next_tab.assert_not_called()
        finally:
            app.pm.stop()


# ════════════════════════════════════════════════════════════════════════
# Coverage closer: action_quit_app teardown sequence
# ════════════════════════════════════════════════════════════════════════

class TestActionQuitApp:

    def test_quit_stops_pm_and_calls_exit(self, monkeypatch):
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            app.ros = None
            app.exit = MagicMock()  # type: ignore[method-assign]
            real_pm_stop = app.pm.stop
            stop_calls = [0]
            def counting_stop():
                stop_calls[0] += 1
                real_pm_stop()
            app.pm.stop = counting_stop  # type: ignore[method-assign]
            app.pm.stop_all = MagicMock()  # type: ignore[method-assign]
            app.action_quit_app()
            assert stop_calls[0] == 1
            app.pm.stop_all.assert_called_once()
            app.exit.assert_called_once()
        finally:
            # In case the test bailed early
            try: app.pm.stop()
            except Exception: pass

    def test_quit_stops_ros_when_present(self, monkeypatch):
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            fake_ros = MagicMock()
            app.ros = fake_ros
            app.exit = MagicMock()  # type: ignore[method-assign]
            app.action_quit_app()
            fake_ros.stop.assert_called_once()
        finally:
            try: app.pm.stop()
            except Exception: pass

    def test_quit_swallows_pm_stop_exception(self, monkeypatch):
        """If pm.stop or pm.stop_all raises, the quit handler still
        calls self.exit() so the user can actually quit."""
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            app.ros = None
            app.exit = MagicMock()  # type: ignore[method-assign]
            app.pm.stop = MagicMock(  # type: ignore[method-assign]
                side_effect=RuntimeError("stop boom"))
            app.pm.stop_all = MagicMock(  # type: ignore[method-assign]
                side_effect=RuntimeError("stop_all boom"))
            app.action_quit_app()  # must not raise
            app.exit.assert_called_once()
        finally:
            pass  # app.pm.stop already mocked to raise

    def test_quit_swallows_ros_stop_exception(self, monkeypatch):
        """If ros.stop raises, the inner try/except catches it."""
        from unittest.mock import MagicMock
        app = RovacCommandCenter(no_ros=True, no_updater=True)
        try:
            fake_ros = MagicMock()
            fake_ros.stop.side_effect = RuntimeError("ros stop boom")
            app.ros = fake_ros
            app.exit = MagicMock()  # type: ignore[method-assign]
            app.action_quit_app()
            app.exit.assert_called_once()
        finally:
            try: app.pm.stop()
            except Exception: pass
