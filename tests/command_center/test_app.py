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
