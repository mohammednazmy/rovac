"""Pure-logic tests for sense_hat_panel_node module-level constants.

The panel node imports rclpy + sense_hat, neither of which exists on a
dev machine. We stub them just enough to allow the module to import,
then assert on the constants. This catches typos in MODE_CYCLE /
FEATURE_CYCLE without needing the Pi.
"""
from __future__ import annotations

import os
import sys
import types

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


@pytest.fixture
def panel_module(monkeypatch):
    """Import sense_hat_panel_node with rclpy + sense_hat stubbed.

    We only need the module to *import* — we won't instantiate the Node.
    """
    edge_dir = os.path.join(REPO_ROOT, "scripts", "edge")
    monkeypatch.syspath_prepend(edge_dir)

    # Build minimal stubs for the ROS / hardware imports the panel node
    # makes at module level.
    stubs = {
        "rclpy": types.SimpleNamespace(init=lambda: None,
                                       shutdown=lambda: None,
                                       spin=lambda *a, **kw: None),
        "rclpy.node": types.ModuleType("rclpy.node"),
        "std_msgs.msg": types.ModuleType("std_msgs.msg"),
        "geometry_msgs.msg": types.ModuleType("geometry_msgs.msg"),
        "diagnostic_msgs.msg": types.ModuleType("diagnostic_msgs.msg"),
        "sense_hat": types.ModuleType("sense_hat"),
        "sense_hat.stick": types.ModuleType("sense_hat.stick"),
        "sense_hat_direct": types.ModuleType("sense_hat_direct"),
        "smbus2": types.ModuleType("smbus2"),
    }

    class _StubNode:
        def __init__(self, *a, **kw): pass
        def create_publisher(self, *a, **kw): return _StubPub()
        def create_subscription(self, *a, **kw): return None
        def create_timer(self, *a, **kw): return None
        def get_logger(self): return _StubLogger()
        def destroy_node(self): pass

    class _StubPub:
        def publish(self, *a, **kw): pass

    class _StubLogger:
        def info(self, *a, **kw): pass
        def warn(self, *a, **kw): pass
        def debug(self, *a, **kw): pass

    stubs["rclpy.node"].Node = _StubNode  # type: ignore
    stubs["std_msgs.msg"].Bool = type("Bool", (), {})  # type: ignore
    stubs["std_msgs.msg"].String = type(  # type: ignore
        "String", (), {"data": ""})

    # Twist must be instantiable with mutable .linear/.angular sub-objects.
    class _Twist:
        def __init__(self):
            self.linear = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.angular = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
    stubs["geometry_msgs.msg"].Twist = _Twist  # type: ignore

    stubs["diagnostic_msgs.msg"].DiagnosticArray = type(  # type: ignore
        "DiagnosticArray", (), {})

    class _SenseStick:
        direction_any = None
        def close(self): pass
    stubs["sense_hat.stick"].SenseStick = _SenseStick  # type: ignore

    class _SenseHatDirect:
        def __init__(self, *a, **kw): pass
        def set_pixels(self, *a, **kw): pass
        def clear(self, *a, **kw): pass
        def close(self): pass
    stubs["sense_hat_direct"].SenseHatDirect = _SenseHatDirect  # type: ignore

    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)

    # Drop any cached version so the import re-runs with our stubs.
    sys.modules.pop("sense_hat_panel_node", None)

    import sense_hat_panel_node  # noqa: E402
    return sense_hat_panel_node


class TestFeatureCycle:
    def test_three_feature_sets(self, panel_module):
        assert len(panel_module.FEATURE_CYCLE) == 3

    def test_feature_set_names(self, panel_module):
        assert panel_module.FEATURE_STATUS in panel_module.FEATURE_CYCLE
        assert panel_module.FEATURE_TELEOP in panel_module.FEATURE_CYCLE
        assert panel_module.FEATURE_RAINBOW in panel_module.FEATURE_CYCLE

    def test_feature_set_strings_are_unique(self, panel_module):
        assert len(set(panel_module.FEATURE_CYCLE)) == 3


class TestModeCycle:
    def test_includes_all_required_modes(self, panel_module):
        cycle = panel_module.MODE_CYCLE
        for required in ("IDLE", "TELEOP", "NAV", "SLAM", "ESTOP"):
            assert required in cycle

    def test_modes_are_unique(self, panel_module):
        assert len(set(panel_module.MODE_CYCLE)) == \
            len(panel_module.MODE_CYCLE)

    def test_estop_constant_matches(self, panel_module):
        assert panel_module.ESTOP_MODE == "ESTOP"
        assert panel_module.ESTOP_MODE in panel_module.MODE_CYCLE

    def test_every_mode_has_a_glyph(self, panel_module):
        """Each entry in MODE_CYCLE must have a corresponding glyph
        in MODE_GLYPHS, otherwise the renderer falls back to IDLE
        and the user sees 'wrong glyph for current mode'."""
        edge_dir = os.path.join(REPO_ROOT, "scripts", "edge")
        sys.path.insert(0, edge_dir)
        import sense_hat_glyphs as sg
        for mode in panel_module.MODE_CYCLE:
            assert mode in sg.MODE_GLYPHS, \
                f"mode {mode!r} has no glyph"


class TestTeleopMagnitudes:
    def test_linear_magnitude_at_or_below_max(self, panel_module):
        """ROVAC max linear = 0.57 m/s (CLAUDE.md). User wants top speed."""
        assert 0 < panel_module.TELEOP_LINEAR_MAGNITUDE <= 0.57

    def test_angular_magnitude_at_or_below_max(self, panel_module):
        """ROVAC max angular = 6.5 rad/s (CLAUDE.md)."""
        assert 0 < panel_module.TELEOP_ANGULAR_MAGNITUDE <= 6.5

    def test_estop_publish_rate_is_reasonable(self, panel_module):
        """Below 5 Hz risks losing the mux race, above 50 Hz is wasteful."""
        assert 5.0 <= panel_module.ESTOP_PUBLISH_HZ <= 50.0


class TestTimeouts:
    def test_mac_disconnect_timeout_is_reasonable(self, panel_module):
        """5–30s window: too low → false alarms on transient lag,
        too high → late warning."""
        assert 5.0 <= panel_module.MAC_DISCONNECT_TIMEOUT_S <= 30.0

    def test_diag_stale_timeout_is_reasonable(self, panel_module):
        """Diagnostics publish at 1 Hz from each ESP32, so 3-15s is fine."""
        assert 3.0 <= panel_module.DIAG_STALE_TIMEOUT_S <= 15.0
