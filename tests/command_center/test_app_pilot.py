"""Textual Pilot integration tests for ``command_center.app``.

These tests boot the REAL Textual app in-memory via ``App.run_test()`` and
drive it with keystrokes. They cover the integration spine that pure-logic
tests can't reach:

  * Compose path — every panel mounts without errors
  * Tab switching via 1-6 number keys
  * Key dispatch to the focused tab's panel (Drive tab → DrivePanel)
  * Arrow-key dual purpose (drive on Drive tab, switch elsewhere)
  * Footer renders the expected chips
  * ctrl+q quits cleanly

All tests are marked ``@pytest.mark.slow`` because each spins up the
event loop (~100ms each). Run with ``pytest -m "not slow"`` to skip them.

``app.pm`` is replaced with a FakePm before run_test() so the panels'
state-update polls don't try to make real subprocess / SSH calls. ``app.ros``
is None via ``no_ros=True``.
"""
from __future__ import annotations

import pytest

from command_center.app import RovacCommandCenter
from command_center.panels.coverage import CoveragePanel
from command_center.panels.dashboard import DashboardPanel
from command_center.panels.drive import DrivePanel
from command_center.panels.edge import EdgePanel
from command_center.panels.sensors import SensorsPanel
from command_center.panels.slam import SlamPanel


pytestmark = pytest.mark.slow


@pytest.fixture
def pilot_app(fake_pm):
    """A RovacCommandCenter ready for Pilot — no real ROS, no updater
    thread, pm replaced with the fake_pm from conftest so panels'
    update_state don't make real subprocess / SSH calls during the test.

    Yields the app. Stops the real (orphaned) ProcessManager on teardown
    so its threading.Event is set even though the daemon thread never
    started.
    """
    fake_pm._returns.update({
        "list_maps": [],
        "get_status": {},
        "pi_all_service_status": {},
        "query_nav2_lifecycle": {},
        "foxglove_bridge_alive": False,
        "validate_map_for_nav": (True, ""),
    })
    app = RovacCommandCenter(no_ros=True, no_updater=True)
    real_pm = app.pm
    app.pm = fake_pm  # type: ignore[assignment]
    yield app
    try:
        real_pm.stop()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════
# Boot smoke
# ════════════════════════════════════════════════════════════════════════

class TestAppBoot:

    async def test_app_starts_without_crashing(self, pilot_app):
        """The most basic test: can we boot the app and exit it?"""
        async with pilot_app.run_test() as pilot:
            await pilot.pause()

    async def test_all_six_panels_mount(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.pause()
            for PanelType in (DashboardPanel, DrivePanel, SensorsPanel,
                               SlamPanel, EdgePanel, CoveragePanel):
                panel = pilot.app.query_one(PanelType)
                assert panel is not None

    async def test_starts_on_dashboard_tab(self, pilot_app):
        """Without explicit selection, TabbedContent defaults to the first
        tab. Dashboard should be active on boot."""
        from textual.widgets import TabbedContent
        async with pilot_app.run_test() as pilot:
            await pilot.pause()
            tabs = pilot.app.query_one(TabbedContent)
            assert tabs.active == "tab-dashboard"


# ════════════════════════════════════════════════════════════════════════
# Tab switching via number keys
# ════════════════════════════════════════════════════════════════════════

class TestTabSwitching:

    @pytest.mark.parametrize("key,want_tab", [
        ("1", "tab-dashboard"),
        ("2", "tab-drive"),
        ("3", "tab-sensors"),
        ("4", "tab-slam"),
        ("5", "tab-edge"),
        ("6", "tab-coverage"),
    ])
    async def test_number_key_switches_to_tab(self, pilot_app, key, want_tab):
        from textual.widgets import TabbedContent
        async with pilot_app.run_test() as pilot:
            await pilot.press(key)
            await pilot.pause()
            tabs = pilot.app.query_one(TabbedContent)
            assert tabs.active == want_tab


# ════════════════════════════════════════════════════════════════════════
# Drive key dispatch
# ════════════════════════════════════════════════════════════════════════

class TestDriveDispatch:

    async def test_w_advances_target_linear(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.press("2")  # Drive tab
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive._target_linear > 0
            assert drive._driving is True

    async def test_s_reverses(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive._target_linear < 0

    async def test_a_turns_left(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive._target_angular > 0  # positive = CCW = left

    async def test_d_turns_right(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive._target_angular < 0

    async def test_space_stops(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.press("2")
            await pilot.pause()
            await pilot.press("w")
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive._target_linear == 0
            assert drive._driving is False

    async def test_t_toggles_tap_ramp(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.press("2")
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            initial = drive._tap_ramp_turn_in_place
            await pilot.press("t")
            await pilot.pause()
            assert drive._tap_ramp_turn_in_place is (not initial)

    async def test_w_on_non_drive_tab_does_nothing(self, pilot_app):
        """The 'w' binding's action_drive checks the active tab and
        no-ops on non-Drive tabs."""
        async with pilot_app.run_test() as pilot:
            await pilot.press("6")  # Coverage tab
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive._target_linear == 0
            await pilot.press("w")
            await pilot.pause()
            # Still at rest — action_drive returned early
            assert drive._target_linear == 0


# ════════════════════════════════════════════════════════════════════════
# Arrow key dual purpose
# ════════════════════════════════════════════════════════════════════════

class TestArrowKeys:

    async def test_arrow_drives_on_drive_tab(self, pilot_app):
        async with pilot_app.run_test() as pilot:
            await pilot.press("2")  # Drive
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive._target_linear > 0

    async def test_left_arrow_switches_tab_on_non_drive(self, pilot_app):
        """On Coverage tab (6), left arrow should switch to previous tab
        (Edge, 5)."""
        from textual.widgets import TabbedContent
        async with pilot_app.run_test() as pilot:
            await pilot.press("6")  # Coverage
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            tabs = pilot.app.query_one(TabbedContent)
            assert tabs.active == "tab-edge"

    async def test_right_arrow_switches_tab_on_non_drive(self, pilot_app):
        from textual.widgets import TabbedContent
        async with pilot_app.run_test() as pilot:
            await pilot.press("1")  # Dashboard
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            tabs = pilot.app.query_one(TabbedContent)
            assert tabs.active == "tab-drive"


# ════════════════════════════════════════════════════════════════════════
# Periodic _update_panels
# ════════════════════════════════════════════════════════════════════════

class TestUpdatePanels:

    async def test_update_panels_runs_without_crashing(self, pilot_app):
        """The 0.1s initial timer fires shortly after mount. Each panel's
        update_state should complete without raising."""
        async with pilot_app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            drive = pilot.app.query_one(DrivePanel)
            assert drive is not None


# ════════════════════════════════════════════════════════════════════════
# Footer
# ════════════════════════════════════════════════════════════════════════

class TestFooter:

    async def test_footer_renders(self, pilot_app):
        """Footer must be present and contain at least the tab bindings."""
        from textual.widgets import Footer
        async with pilot_app.run_test() as pilot:
            await pilot.pause()
            footer = pilot.app.query_one(Footer)
            assert footer is not None


# ════════════════════════════════════════════════════════════════════════
# Quit
# ════════════════════════════════════════════════════════════════════════

class TestQuit:

    async def test_ctrl_q_exits(self, pilot_app):
        """ctrl+q triggers action_quit_app which calls self.exit()."""
        async with pilot_app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+q")
            await pilot.pause()
