"""Tests for ``command_center.panels.coverage``.

This is the biggest panel (1016 LOC) and exercises every fake we built:
``fake_pm``, ``fake_ros`` (with the panel-specific extensions), and the
``coverage_panel`` fixture.
"""
from __future__ import annotations

import math
import time
from types import SimpleNamespace

import pytest

from command_center.panels import coverage
from command_center.panels.coverage import (
    GRAY_DOT,
    GREEN_DOT,
    RED_DOT,
    YELLOW_DOT,
    CoveragePanel,
    _status_dot,
)


# ════════════════════════════════════════════════════════════════════════
# Module constants + _status_dot helper
# ════════════════════════════════════════════════════════════════════════

class TestModuleConstants:

    def test_dot_colors_distinct(self):
        # If two of these collide, status rows lose visual distinction.
        assert len({GREEN_DOT, RED_DOT, GRAY_DOT, YELLOW_DOT}) == 4

    def test_dot_glyphs_use_correct_colors(self):
        assert "[green]" in GREEN_DOT
        assert "[red]" in RED_DOT
        assert "[dim]" in GRAY_DOT
        assert "[yellow]" in YELLOW_DOT


class TestStatusDot:

    def test_missing_overrides_active(self):
        # missing=True always wins.
        assert _status_dot(active=True, missing=True) == GRAY_DOT
        assert _status_dot(active=False, missing=True) == GRAY_DOT

    def test_active_true_is_green(self):
        assert _status_dot(active=True) == GREEN_DOT

    def test_active_false_is_red(self):
        assert _status_dot(active=False) == RED_DOT


# ════════════════════════════════════════════════════════════════════════
# process_key dispatch — every binding listed in the docstring
# ════════════════════════════════════════════════════════════════════════

class TestProcessKey:

    # Lowercase keys
    @pytest.mark.parametrize("key", [
        "e", "n", "f", "t", "p", "r", "l", "k", "i",
        "c", "d", "s",
    ])
    def test_lowercase_keys_handled(self, coverage_panel, key):
        # Some keys read input fields — pre-populate to avoid early-return
        # paths that wouldn't trigger the handler at all.
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="ignored", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        assert coverage_panel.process_key(key) is True

    # Capital-letter aliases
    @pytest.mark.parametrize("key", [
        "A", "shift+a",
        "F", "shift+f",
        "S", "shift+s",
        "X", "shift+x",
        "I", "shift+i",
        "T", "shift+t",
    ])
    def test_capital_keys_handled(self, coverage_panel, key):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="ignored", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        assert coverage_panel.process_key(key) is True

    @pytest.mark.parametrize("key", ["z", "q", "left", "space"])
    def test_unknown_keys_not_handled(self, coverage_panel, key):
        assert coverage_panel.process_key(key) is False

    def test_capital_a_takes_auto_start_path(self, coverage_panel, fake_pm):
        # Shift+A and 'A' both go to _auto_start (the priority case in
        # the if/elif chain — both before the lowercase 'a' branch).
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(
            value="0", update=lambda *a: None)
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        coverage_panel.process_key("A")
        # auto_start_full_stack should have been called
        assert any(c[0] == "auto_start_full_stack" for c in fake_pm.calls)


# ════════════════════════════════════════════════════════════════════════
# Simple action handlers
# ════════════════════════════════════════════════════════════════════════

class TestStartEkf:

    def test_success(self, coverage_panel, fake_pm):
        fake_pm.set_return("start_ekf", True)
        coverage_panel._start_ekf()
        assert any(c[0] == "start_ekf" for c in fake_pm.calls)
        assert "[green]" in coverage_panel.queried["#cov-result"].last_update

    def test_failure(self, coverage_panel, fake_pm):
        fake_pm.set_return("start_ekf", False)
        coverage_panel._start_ekf()
        assert "[red]" in coverage_panel.queried["#cov-result"].last_update


class TestStartNav2:

    def test_warns_when_no_map_path(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="", update=lambda *a: None)
        coverage_panel._start_nav2()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[yellow]" in out
        assert "map" in out.lower()
        assert not any(c[0] == "start_nav2" for c in fake_pm.calls)

    def test_validate_failure_blocks_nav2(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/bad/path.yaml", update=lambda *a: None)
        fake_pm.set_return("validate_map_for_nav",
                           (False, "Map yaml not found"))
        coverage_panel._start_nav2()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out
        assert "not found" in out
        assert not any(c[0] == "start_nav2" for c in fake_pm.calls)

    def test_starts_when_map_valid(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        fake_pm.set_return("start_nav2", True)
        coverage_panel._start_nav2()
        assert any(c[0] == "start_nav2" for c in fake_pm.calls)
        assert "[green]" in coverage_panel.queried["#cov-result"].last_update


class TestToggleFoxglove:

    def test_starts_when_not_running(self, coverage_panel, fake_pm):
        fake_pm._returns["get_status"] = {"foxglove": "stopped"}
        fake_pm.set_return("start_foxglove", True)
        coverage_panel._toggle_foxglove()
        assert any(c[0] == "start_foxglove" for c in fake_pm.calls)

    def test_stops_when_running(self, coverage_panel, fake_pm):
        fake_pm._returns["get_status"] = {"foxglove": "running"}
        coverage_panel._toggle_foxglove()
        assert any(c[0] == "stop_foxglove" for c in fake_pm.calls)


class TestToggleTracker:

    @pytest.mark.parametrize("st", ["running", "running (external)"])
    def test_stops_when_running(self, coverage_panel, fake_pm, st):
        fake_pm._returns["get_status"] = {"tracker": st}
        coverage_panel._toggle_tracker()
        assert any(c[0] == "stop_coverage_tracker" for c in fake_pm.calls)

    def test_starts_when_stopped(self, coverage_panel, fake_pm):
        fake_pm._returns["get_status"] = {}
        fake_pm.set_return("start_coverage_tracker", True)
        coverage_panel._toggle_tracker()
        assert any(c[0] == "start_coverage_tracker" for c in fake_pm.calls)


class TestStartCoverage:

    def test_blocks_when_already_running(self, coverage_panel, fake_pm):
        fake_pm._returns["get_status"] = {"coverage": "running"}
        coverage_panel._start_coverage(preview=True)
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[yellow]" in out
        assert "already" in out.lower()
        assert not any(c[0] == "start_coverage" for c in fake_pm.calls)

    def test_preview_mode_dispatches(self, coverage_panel, fake_pm):
        fake_pm._returns["get_status"] = {}
        coverage_panel._start_coverage(preview=True)
        assert ("start_coverage", (), {"preview_only": True}) in fake_pm.calls
        assert "PREVIEW" in coverage_panel.queried["#cov-result"].last_update

    def test_live_mode_dispatches(self, coverage_panel, fake_pm):
        fake_pm._returns["get_status"] = {}
        coverage_panel._start_coverage(preview=False)
        assert ("start_coverage", (), {"preview_only": False}) in fake_pm.calls
        assert "LIVE" in coverage_panel.queried["#cov-result"].last_update


class TestRecoverNav2:

    def test_dispatch_shows_yellow_message(self, coverage_panel, fake_pm):
        fake_pm.set_return("recover_nav2_lifecycle", True)
        coverage_panel._recover_nav2()
        assert any(c[0] == "recover_nav2_lifecycle" for c in fake_pm.calls)
        assert "[yellow]" in coverage_panel.queried["#cov-result"].last_update

    def test_failure_shows_red(self, coverage_panel, fake_pm):
        fake_pm.set_return("recover_nav2_lifecycle", False)
        coverage_panel._recover_nav2()
        assert "[red]" in coverage_panel.queried["#cov-result"].last_update


class TestKillAll:

    def test_dispatches_stop_all(self, coverage_panel, fake_pm):
        coverage_panel._kill_all()
        assert any(c[0] == "stop_all" for c in fake_pm.calls)
        assert "[yellow]" in coverage_panel.queried["#cov-result"].last_update


# ════════════════════════════════════════════════════════════════════════
# _read_pose_inputs — input parsing logic
# ════════════════════════════════════════════════════════════════════════

class TestReadPoseInputs:

    def test_parses_valid_inputs(self, coverage_panel):
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="1.5")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="-2.0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="90")
        x, y, yaw = coverage_panel._read_pose_inputs()
        assert x == 1.5
        assert y == -2.0
        assert yaw == pytest.approx(math.pi / 2)

    def test_empty_field_defaults_to_zero(self, coverage_panel):
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="  ")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="")
        x, y, yaw = coverage_panel._read_pose_inputs()
        assert (x, y, yaw) == (0.0, 0.0, 0.0)

    def test_non_numeric_raises_value_error(self, coverage_panel):
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="abc")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        with pytest.raises(ValueError):
            coverage_panel._read_pose_inputs()


# ════════════════════════════════════════════════════════════════════════
# _publish_initial_pose
# ════════════════════════════════════════════════════════════════════════

class TestPublishInitialPose:

    def test_warns_when_no_ros(self, coverage_panel, fake_app):
        fake_app.ros = None  # type: ignore[assignment]
        coverage_panel._publish_initial_pose()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out
        assert "ROS" in out

    def test_bad_inputs_show_red(self, coverage_panel):
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="abc")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        coverage_panel._publish_initial_pose()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out
        assert "number" in out.lower()

    def test_valid_inputs_dispatch_publish(self, coverage_panel, fake_ros):
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="1.0")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="2.0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="45")
        coverage_panel._publish_initial_pose()
        assert len(fake_ros.initial_pose_calls) == 1
        x, y, yaw = fake_ros.initial_pose_calls[0]
        assert (x, y) == (1.0, 2.0)
        assert yaw == pytest.approx(math.radians(45))
        assert "[green]" in coverage_panel.queried["#cov-result"].last_update

    def test_publish_failure_shows_red(self, coverage_panel, fake_ros):
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        fake_ros.initial_pose_return = False
        coverage_panel._publish_initial_pose()
        assert "[red]" in coverage_panel.queried["#cov-result"].last_update


# ════════════════════════════════════════════════════════════════════════
# IMU calibration / global localize
# ════════════════════════════════════════════════════════════════════════

class TestCalibrateImuYaw:

    def test_warns_when_no_ros(self, coverage_panel, fake_app):
        fake_app.ros = None  # type: ignore[assignment]
        coverage_panel._calibrate_imu_yaw()
        assert "[red]" in coverage_panel.queried["#cov-result"].last_update

    def test_success_uses_green(self, coverage_panel, fake_ros):
        fake_ros.calibrate_return = (True, 15.0, "Calibration saved")
        coverage_panel._calibrate_imu_yaw()
        assert len(fake_ros.calibrate_calls) == 1
        assert "[green]" in coverage_panel.queried["#cov-result"].last_update

    def test_failure_uses_red(self, coverage_panel, fake_ros):
        fake_ros.calibrate_return = (False, 0.0, "AMCL not localized")
        coverage_panel._calibrate_imu_yaw()
        assert "[red]" in coverage_panel.queried["#cov-result"].last_update


class TestGlobalLocalize:

    def test_warns_when_no_ros(self, coverage_panel, fake_app):
        fake_app.ros = None  # type: ignore[assignment]
        coverage_panel._global_localize()
        assert "[red]" in coverage_panel.queried["#cov-result"].last_update

    def test_dispatch_records_call(self, coverage_panel, fake_ros):
        fake_ros.global_localize_return = True
        coverage_panel._global_localize()
        assert fake_ros.global_localize_calls == 1
        assert "[yellow]" in coverage_panel.queried["#cov-result"].last_update

    def test_failure_shows_red(self, coverage_panel, fake_ros):
        fake_ros.global_localize_return = False
        coverage_panel._global_localize()
        assert "[red]" in coverage_panel.queried["#cov-result"].last_update


# ════════════════════════════════════════════════════════════════════════
# _kill_teleop — most-complex recovery action
# ════════════════════════════════════════════════════════════════════════

class TestKillTeleop:

    def test_kills_pm_teleop(self, coverage_panel, fake_pm, fake_app,
                              monkeypatch):
        fake_pm._returns["kill_zombie_teleop"] = 2
        # Suppress the DrivePanel lookup — fake app won't have one mounted.
        def raising_query_one(*_a, **_kw):
            raise RuntimeError("no drive")
        monkeypatch.setattr(fake_app, "query_one", raising_query_one,
                            raising=False)
        coverage_panel._kill_teleop()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "killed 2" in out
        assert "Pi cleanup dispatched" in out

    def test_skips_drive_stop_when_panel_missing(
            self, coverage_panel, fake_app, monkeypatch):
        def raising(*_a, **_kw):
            raise RuntimeError("not mounted")
        monkeypatch.setattr(fake_app, "query_one", raising, raising=False)
        # Should not raise, even when drive panel not found
        coverage_panel._kill_teleop()
        out = coverage_panel.queried["#cov-result"].last_update
        assert out is not None


# ════════════════════════════════════════════════════════════════════════
# _save_map
# ════════════════════════════════════════════════════════════════════════

class TestSaveMap:

    def test_empty_input_warns(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="", update=lambda *a: None)
        coverage_panel._save_map()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[yellow]" in out
        assert not any(c[0] == "save_map" for c in fake_pm.calls)

    def test_strips_path_and_extension(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="~/maps/kitchen.yaml", update=lambda *a: None)
        coverage_panel._save_map()
        # save_map called with 'kitchen', not '~/maps/kitchen.yaml'
        assert ("save_map", ("kitchen",), {}) in fake_pm.calls


# ════════════════════════════════════════════════════════════════════════
# Stop / restart actions
# ════════════════════════════════════════════════════════════════════════

class TestStopCoverage:

    def test_dispatches_stop_coverage(self, coverage_panel, fake_pm,
                                       mock_subprocess):
        coverage_panel._stop_coverage()
        assert any(c[0] == "stop_coverage" for c in fake_pm.calls)
        # Also fires pkill against any externally-spawned coverage_node
        pkill_calls = [c for c, _ in mock_subprocess.run_calls
                       if c[0] == "pkill"]
        assert len(pkill_calls) == 1
        assert "coverage_node.py" in pkill_calls[0]


class TestRestartFoxglove:

    def test_step1_stops_and_schedules_step2(self, coverage_panel, fake_pm):
        coverage_panel._restart_foxglove()
        assert any(c[0] == "stop_foxglove" for c in fake_pm.calls)
        assert "[yellow]" in coverage_panel.queried["#cov-result"].last_update

    def test_step2_starts(self, coverage_panel, fake_pm):
        fake_pm.set_return("start_foxglove", True)
        coverage_panel._restart_foxglove_step2()
        assert any(c[0] == "start_foxglove" for c in fake_pm.calls)
        assert "[green]" in coverage_panel.queried["#cov-result"].last_update


# ════════════════════════════════════════════════════════════════════════
# update_state subhandlers
# ════════════════════════════════════════════════════════════════════════

class TestUpdateAmclStatus:

    def test_not_localized(self, coverage_panel):
        coverage_panel._update_amcl_status({"amcl_localized": False})
        out = coverage_panel.queried["#cov-amcl-status"].last_update
        assert "NOT LOCALIZED" in out
        assert "[red]" in out

    def test_stale_shows_age(self, coverage_panel):
        coverage_panel._update_amcl_status({
            "amcl_localized": True,
            "amcl_last_update": time.monotonic() - 30.0,
        })
        out = coverage_panel.queried["#cov-amcl-status"].last_update
        assert "STALE" in out
        assert "[yellow]" in out

    def test_localized_renders_pose(self, coverage_panel):
        coverage_panel._update_amcl_status({
            "amcl_localized": True,
            "amcl_last_update": time.monotonic(),
            "amcl_x": 1.5, "amcl_y": -0.5, "amcl_yaw_deg": 45,
            "amcl_cov_xx": 0.01,
        })
        out = coverage_panel.queried["#cov-amcl-status"].last_update
        assert "LOCALIZED" in out
        assert "+1.50" in out
        assert "-0.50" in out
        assert "+45°" in out
        assert "tight" in out

    def test_localized_loose_cov(self, coverage_panel):
        coverage_panel._update_amcl_status({
            "amcl_localized": True,
            "amcl_last_update": time.monotonic(),
            "amcl_x": 0, "amcl_y": 0, "amcl_yaw_deg": 0,
            "amcl_cov_xx": 0.5,  # > 0.05
        })
        out = coverage_panel.queried["#cov-amcl-status"].last_update
        assert "loose" in out

    def test_imu_not_calibrated_line2(self, coverage_panel, fake_ros):
        fake_ros.yaw_offset_deg = None
        coverage_panel._update_amcl_status({"amcl_localized": False})
        out = coverage_panel.queried["#cov-amcl-status"].last_update
        assert "IMU calibration: not set" in out

    def test_imu_calibrated_but_bno055_silent(self, coverage_panel, fake_ros):
        fake_ros.yaw_offset_deg = 15.0
        fake_ros.map_yaw_from_imu_deg = None
        coverage_panel._update_amcl_status({"amcl_localized": False})
        out = coverage_panel.queried["#cov-amcl-status"].last_update
        assert "BNO055 not publishing" in out

    def test_imu_calibrated_and_publishing(self, coverage_panel, fake_ros):
        fake_ros.yaw_offset_deg = 15.0
        fake_ros.map_yaw_from_imu_deg = 75.0
        coverage_panel._update_amcl_status({"amcl_localized": False})
        out = coverage_panel.queried["#cov-amcl-status"].last_update
        assert "IMU yaw" in out and "+75" in out


class TestUpdateRosoutTail:

    def test_no_entries(self, coverage_panel, fake_ros):
        fake_ros.rosout_tail = []
        coverage_panel._update_rosout_tail()
        out = coverage_panel.queried["#cov-rosout"].last_update
        assert "No warnings" in out

    def test_renders_4_tuple_entries(self, coverage_panel, fake_ros):
        fake_ros.rosout_tail = [
            ("WARN",  "amcl", "scan match failed", 1),
            ("ERROR", "nav2", "lifecycle stuck", 1),
            ("FATAL", "ekf",  "out of memory", 1),
        ]
        coverage_panel._update_rosout_tail()
        out = coverage_panel.queried["#cov-rosout"].last_update
        assert "WARN" in out
        assert "ERROR" in out
        assert "FATAL" in out

    def test_dedup_count_shown_when_above_1(self, coverage_panel, fake_ros):
        fake_ros.rosout_tail = [
            ("WARN", "amcl", "repeated", 42),
        ]
        coverage_panel._update_rosout_tail()
        out = coverage_panel.queried["#cov-rosout"].last_update
        # Format: "(x42)" — ASCII 'x' (RUF001 disallows ambiguous multiplication
        # sign in user-facing strings).
        assert "x42" in out
        assert "repeated" in out

    def test_tolerates_legacy_3_tuple_entries(self, coverage_panel, fake_ros):
        # Old format before the dedup field was added.
        fake_ros.rosout_tail = [
            ("WARN", "amcl", "old format"),
        ]
        # Must not crash
        coverage_panel._update_rosout_tail()
        out = coverage_panel.queried["#cov-rosout"].last_update
        assert "old format" in out

    def test_caps_at_8_recent(self, coverage_panel, fake_ros):
        fake_ros.rosout_tail = [
            ("WARN", "n", f"msg-{i}", 1) for i in range(20)
        ]
        coverage_panel._update_rosout_tail()
        out = coverage_panel.queried["#cov-rosout"].last_update
        # Only last 8 entries
        assert "msg-19" in out
        assert "msg-11" not in out


class TestUpdatePiServices:

    def test_unreachable_when_no_cache(self, coverage_panel, fake_pm):
        fake_pm._returns["pi_all_service_status"] = {}
        coverage_panel._update_pi_services()
        out = coverage_panel.queried["#cov-pi-services"].last_update
        assert "unreachable" in out.lower()

    def test_active_services_show_green(self, coverage_panel, fake_pm):
        fake_pm._returns["pi_all_service_status"] = {
            "rovac-edge-motor-driver": "active",
            "rovac-edge-mux": "active",
            "rovac-edge-rplidar-c1": "failed",
        }
        coverage_panel._update_pi_services()
        out = coverage_panel.queried["#cov-pi-services"].last_update
        assert "[green]motor-driver" in out
        assert "[red]rplidar-c1" in out
        assert "(failed)" in out


class TestUpdateMacProcs:

    def test_running_proc_green(self, coverage_panel):
        coverage_panel._update_mac_procs({"ekf": "running"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        assert "[green]●" in out
        assert "running" in out

    def test_exited_proc_red(self, coverage_panel):
        coverage_panel._update_mac_procs({"ekf": "exited (1)"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        assert "[red]" in out
        assert "exited (1)" in out

    def test_external_proc_yellow(self, coverage_panel):
        coverage_panel._update_mac_procs(
            {"coverage": "running (external)"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        assert YELLOW_DOT in out

    def test_foxglove_port_alive_wins_over_status(
            self, coverage_panel, fake_pm):
        # When the port check says listening, render as green regardless
        # of proc_status (which might be wrong).
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel._update_mac_procs({"foxglove": "stopped"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        assert "Foxglove" in out
        assert "listening :8765" in out

    def test_foxglove_process_up_port_down(self, coverage_panel, fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = False
        coverage_panel._update_mac_procs({"foxglove": "running"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        assert "port DOWN" in out


class TestUpdateNav2Lifecycle:

    def test_not_running_when_cache_empty(self, coverage_panel, fake_pm):
        fake_pm._returns["query_nav2_lifecycle"] = {}
        coverage_panel._update_nav2_lifecycle()
        out = coverage_panel.queried["#cov-nav2-lifecycle"].last_update
        assert "Nav2 not running" in out

    @pytest.mark.parametrize("state,want_dot", [
        ("active", GREEN_DOT),
        ("inactive", YELLOW_DOT),
        ("unknown", GRAY_DOT),
        ("errored", RED_DOT),
    ])
    def test_state_to_dot_mapping(self, coverage_panel, fake_pm,
                                   state, want_dot):
        fake_pm._returns["query_nav2_lifecycle"] = {"/amcl": state}
        coverage_panel._update_nav2_lifecycle()
        out = coverage_panel.queried["#cov-nav2-lifecycle"].last_update
        assert want_dot in out


class TestUpdateCmdvel:

    def test_renders_all_pipeline_rates(self, coverage_panel):
        coverage_panel._update_cmdvel({
            "cmd_vel_teleop_hz": 20.0,
            "cmd_vel_joy_hz": 0.0,
            "cmd_vel_smoothed_hz": 5.0,
            "cmd_vel_hz": 5.0,
            "mux_active": "TELEOP",
        })
        out = coverage_panel.queried["#cov-cmdvel"].last_update
        assert "/cmd_vel_teleop" in out
        assert "/cmd_vel_joy" in out
        assert "/cmd_vel_smoothed" in out
        assert "TELEOP" in out

    def test_teleop_active_colored_red_when_high_hz(self, coverage_panel):
        coverage_panel._update_cmdvel({
            "cmd_vel_teleop_hz": 20.0, "mux_active": "TELEOP",
        })
        out = coverage_panel.queried["#cov-cmdvel"].last_update
        # teleop and joy are "expected_quiet" — > 0.5 means RED
        # (active teleop overrides Nav2 → bad sign during a coverage run)
        assert "[red]20.0[/]" in out


class TestUpdateProgress:

    def test_no_plan_when_not_running(self, coverage_panel):
        coverage_panel._update_progress({}, {})
        out = coverage_panel.queried["#cov-progress"].last_update
        assert "not running" in out

    def test_renders_progress(self, coverage_panel):
        coverage_panel._update_progress(
            {"coverage_total": 50,
             "coverage_pct": 32.5,
             "coverage_visited_cells": 100,
             "coverage_free_cells": 308},
            {"coverage": "running"})
        out = coverage_panel.queried["#cov-progress"].last_update
        assert "50" in out
        assert "100" in out
        assert "32.5%" in out


class TestUpdateAlerts:

    def test_no_alerts_when_idle(self, coverage_panel, fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel._update_alerts({}, {})
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "No alerts" in out
        assert "[green]" in out

    def test_zombie_teleop_alert(self, coverage_panel, fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel._update_alerts({"cmd_vel_teleop_hz": 5.0}, {})
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "zombie teleop" in out
        assert "OVERRIDES Nav2" in out

    def test_zombie_joy_alert(self, coverage_panel, fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel._update_alerts({"cmd_vel_joy_hz": 5.0}, {})
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "joy" in out
        assert "ps2" in out.lower()

    def test_foxglove_down_alert(self, coverage_panel, fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = False
        coverage_panel._update_alerts({}, {})
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "Foxglove" in out
        assert "8765" in out

    def test_nav2_stuck_alert(self, coverage_panel, fake_pm):
        # Prime nav2 cache with a non-active node.
        coverage_panel._nav_cache = {"/amcl": "inactive"}
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel._update_alerts({}, {})
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "Nav2" in out
        assert "amcl" in out

    def test_nav2_without_ekf_alert(self, coverage_panel, fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel._update_alerts(
            {}, {"nav2": "running", "ekf": "stopped"})
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "EKF" in out
        assert "/odometry/filtered" in out

    def test_coverage_without_tracker_alert(self, coverage_panel, fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel._update_alerts(
            {}, {"coverage": "running", "tracker": "stopped"})
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "tracker" in out
        assert "visited grid" in out


# ════════════════════════════════════════════════════════════════════════
# End-to-end smoke
# ════════════════════════════════════════════════════════════════════════

class TestUpdateStateSmoke:

    def test_minimal_state_no_crash(self, coverage_panel):
        coverage_panel.update_state({}, [], {})

    def test_full_state(self, coverage_panel, fake_pm, fake_ros):
        fake_pm._returns["pi_all_service_status"] = {
            "rovac-edge-motor-driver": "active",
        }
        fake_pm._returns["query_nav2_lifecycle"] = {"/amcl": "active"}
        fake_pm._returns["foxglove_bridge_alive"] = True
        coverage_panel.update_state({
            "amcl_localized": True,
            "amcl_last_update": time.monotonic(),
            "amcl_x": 0, "amcl_y": 0, "amcl_yaw_deg": 0,
            "amcl_cov_xx": 0.01,
            "cmd_vel_teleop_hz": 0.0, "cmd_vel_joy_hz": 0.0,
            "cmd_vel_smoothed_hz": 5.0, "cmd_vel_hz": 5.0,
            "mux_active": "NAV",
            "coverage_total": 0,
        }, [], {"ekf": "running", "nav2": "running",
                 "tracker": "running", "coverage": "stopped"})
        # All update targets should have been written to.
        for selector in ("#cov-pi-services", "#cov-mac-procs",
                          "#cov-nav2-lifecycle", "#cov-cmdvel",
                          "#cov-progress", "#cov-amcl-status",
                          "#cov-alerts", "#cov-rosout"):
            assert coverage_panel.queried[selector].last_update is not None


# ════════════════════════════════════════════════════════════════════════
# _auto_start orchestration
# ════════════════════════════════════════════════════════════════════════

class TestAutoStart:

    def test_no_map_and_no_saved_maps_shows_red(
            self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="", update=lambda *a: None)
        fake_pm._returns["list_maps"] = []
        coverage_panel._auto_start()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out
        assert "No map" in out
        assert not any(c[0] == "auto_start_full_stack"
                       for c in fake_pm.calls)

    def test_validate_failure_shows_error(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/x.yaml", update=lambda *a: None)
        fake_pm.set_return("validate_map_for_nav",
                           (False, "Map yaml not found"))
        coverage_panel._auto_start()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out
        assert "not found" in out

    def test_dispatches_with_pose_inputs(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="1.5")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="-2.0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="90")
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        coverage_panel._auto_start()
        # auto_start_full_stack called once with the parsed pose
        calls = [c for c in fake_pm.calls if c[0] == "auto_start_full_stack"]
        assert len(calls) == 1
        _, args, kwargs = calls[0]
        assert kwargs["initial_pose"][:2] == (1.5, -2.0)
        assert kwargs["initial_pose"][2] == pytest.approx(math.pi / 2)

    def test_bad_pose_falls_back_to_origin(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="abc")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        coverage_panel._auto_start()
        calls = [c for c in fake_pm.calls if c[0] == "auto_start_full_stack"]
        assert len(calls) == 1
        _, args, kwargs = calls[0]
        assert kwargs["initial_pose"] == (0.0, 0.0, 0.0)

    def test_reentrancy_guard_shows_yellow(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        fake_pm.set_return("auto_start_full_stack", False)  # in flight
        coverage_panel._auto_start()
        # The final result text should warn about reentrancy
        out = coverage_panel.queried["#cov-result"].last_update
        assert "already in progress" in out


class TestRefreshAutoStatus:

    def test_step_callback_accumulates(self, coverage_panel, fake_pm):
        """Drive the on_step callback by invoking auto_start_full_stack
        with a synthetic action that captures the callback and fires it
        with several status updates."""
        captured = {}
        def fake_aux(*_a, on_step=None, **_k):
            captured["on_step"] = on_step
            return True
        fake_pm.auto_start_full_stack = fake_aux  # type: ignore[assignment]

        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        fake_pm.set_return("validate_map_for_nav", (True, ""))

        coverage_panel._auto_start()
        cb = captured["on_step"]
        cb("EKF", "pending")
        cb("EKF", "ok")
        cb("Nav2", "pending")
        cb("Nav2", "failed")

        # Last update should show all 4 (well, 2 — EKF was replaced)
        out = coverage_panel.queried["#cov-result"].last_update
        assert "EKF" in out
        assert "Nav2" in out
        # Symbols
        assert "✓" in out  # EKF ok
        assert "✗" in out  # Nav2 failed
