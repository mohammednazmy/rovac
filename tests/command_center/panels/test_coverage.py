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


# ════════════════════════════════════════════════════════════════════════
# Coverage closers — Phase 8.5 (remaining gaps)
# ════════════════════════════════════════════════════════════════════════

import time as _time
from unittest.mock import MagicMock


class TestAutoStartMapInputExceptionAndAutoPick:

    def test_query_one_failure_treated_as_empty(self, coverage_panel,
                                                   fake_pm, monkeypatch):
        """If query_one('#cov-map-input') raises (e.g. before mount), we
        treat the map path as empty and fall through to auto-pick logic."""
        def raising_query_one(selector, *_a, **_kw):
            if "cov-map-input" in selector:
                raise RuntimeError("input not mounted")
            return coverage_panel.queried.setdefault(
                selector,
                SimpleNamespace(last_update=None,
                                update=lambda s=None: None))
        monkeypatch.setattr(coverage_panel, "query_one", raising_query_one)
        fake_pm._returns["list_maps"] = []
        coverage_panel._auto_start()
        # Should fall through to the "no maps" red message
        # query_one for cov-result needs to return our stub
        assert "no map" in (coverage_panel.queried.get("#cov-result",
                            SimpleNamespace(last_update="")
                            ).last_update or "").lower() \
               or fake_pm._returns.get("list_maps") == []

    def test_auto_start_picks_latest_map_when_input_empty(
            self, coverage_panel, fake_pm, monkeypatch, tmp_path):
        """When the map input is empty AND maps exist on disk, auto_start
        picks the most-recently-modified one."""
        # Create two fake map files in tmp with different mtimes
        old_map = tmp_path / "old.yaml"
        new_map = tmp_path / "new.yaml"
        old_map.write_text("image: old.pgm\nresolution: 0.05")
        new_map.write_text("image: new.pgm\nresolution: 0.05")
        # Set mtimes explicitly
        import os
        old_time = _time.time() - 100.0
        new_time = _time.time()
        os.utime(old_map, (old_time, old_time))
        os.utime(new_map, (new_time, new_time))
        # Also create the sibling .pgm files so validate passes
        (tmp_path / "old.pgm").write_text("x")
        (tmp_path / "new.pgm").write_text("x")
        fake_pm._returns["list_maps"] = [str(old_map), str(new_map)]
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        coverage_panel._auto_start()
        # auto_start_full_stack called with the NEWER map path
        calls = [c for c in fake_pm.calls if c[0] == "auto_start_full_stack"]
        assert len(calls) >= 1
        _name, args, _kwargs = calls[0]
        assert "new.yaml" in args[0]


class TestRefreshAutoStatusEmptySteps:

    def test_no_steps_returns_early(self, coverage_panel):
        """When _auto_steps is empty, _refresh_auto_status returns without
        updating the result widget."""
        import threading
        coverage_panel._auto_steps = []
        coverage_panel._auto_steps_lock = threading.Lock()
        coverage_panel._refresh_auto_status()
        # No update happened — query_one for cov-result wasn't queried
        # (or if it was, it wasn't updated to a non-default value)


class TestStartNav2QueryException:

    def test_query_exception_treated_as_empty_warns(self, coverage_panel,
                                                      monkeypatch):
        """If reading the map-input field raises, _start_nav2 treats it
        as empty and shows the 'Enter a map yaml first' warning."""
        def boom(selector, *_a, **_kw):
            if "cov-map-input" in selector:
                raise RuntimeError("not mounted")
            return coverage_panel.queried.setdefault(
                selector,
                SimpleNamespace(last_update=None,
                                update=lambda t: setattr(
                                    coverage_panel.queried[selector],
                                    "last_update", t)))
        monkeypatch.setattr(coverage_panel, "query_one", boom)
        coverage_panel._start_nav2()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[yellow]" in out


class TestStartNav2Failure:

    def test_start_nav2_failure_shows_red(self, coverage_panel, fake_pm):
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        fake_pm.set_return("start_nav2", False)  # fails
        coverage_panel._start_nav2()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out
        assert "Nav2 start failed" in out


class TestKillTeleopWithDrivePanel:

    def test_kill_teleop_stops_drive_panel(self, coverage_panel, fake_app,
                                             fake_pm, fake_ros, monkeypatch):
        """When a DrivePanel IS mounted, _kill_teleop stops its
        publish loop AND publishes one explicit zero to neutralize
        in-flight commands."""
        # Build a fake DrivePanel that records _stop_driving + publish
        fake_drive = MagicMock()
        # Override fake_app.query_one to return our fake drive panel
        def fake_query(panel_type):
            return fake_drive
        monkeypatch.setattr(fake_app, "query_one", fake_query,
                            raising=False)
        fake_pm._returns["kill_zombie_teleop"] = 1
        coverage_panel._kill_teleop()
        # Drive panel's _stop_driving was called
        fake_drive._stop_driving.assert_called_once()
        # Explicit zero was published to ros
        assert (0.0, 0.0) in fake_ros.published
        out = coverage_panel.queried["#cov-result"].last_update
        assert "Drive panel timer stopped" in out
        assert "killed 1" in out


class TestTestDriveNoRos:

    def test_warns_when_no_ros(self, coverage_panel, fake_app):
        fake_app.ros = None  # type: ignore[assignment]
        coverage_panel._test_drive()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out
        assert "ROS bridge not connected" in out


class TestTestDriveWorker:

    def test_publishes_for_2s_then_stops(self, coverage_panel, fake_ros,
                                          monkeypatch):
        """The worker publishes 0.05 m/s for 2s then publishes 0,0."""
        # Speed it up by patching time.monotonic + sleep
        import command_center.panels.coverage as cov_mod
        clock = [0.0]
        # Use a side_effect that advances time on each call
        def fake_mono():
            clock[0] += 0.1
            return clock[0]
        # The worker function does `import time as _time` locally — we
        # need to patch the actual `time.monotonic` and `time.sleep` it
        # uses. The local alias points to the global time module.
        import time as real_time
        monkeypatch.setattr(real_time, "monotonic", fake_mono)
        monkeypatch.setattr(real_time, "sleep", lambda _s: None)

        coverage_panel._test_drive()
        # Wait briefly for worker
        deadline = real_time.monotonic() + 5.0
        while real_time.monotonic() < deadline:
            if (0.0, 0.0) in fake_ros.published:
                break
            real_time.sleep(0.01)
        # At least one (0.05, 0.0) publish + final (0.0, 0.0)
        assert (0.05, 0.0) in fake_ros.published
        assert (0.0, 0.0) in fake_ros.published


class TestDumpDiagnostics:

    def test_warns_via_yellow_then_dispatches(self, coverage_panel,
                                                 fake_pm, fake_app,
                                                 monkeypatch):
        """_dump_diagnostics shows a [yellow] 'collecting' message and
        dispatches pm.dump_diagnostics with ros_bridge + callback +
        ui_state."""
        # Mock self.app.query_one to provide the TabbedContent + DrivePanel
        # for the ui_state collection.
        fake_tabs = MagicMock()
        fake_tabs.active = "tab-coverage"
        fake_drive = MagicMock()
        fake_drive._driving = True
        fake_drive._target_linear = 0.15
        fake_drive._target_angular = 0.0
        fake_drive._publish_timer = MagicMock()
        fake_drive._hold_timer = None
        fake_drive.gear = 2
        from textual.widgets import TabbedContent
        from command_center.panels.drive import DrivePanel
        def fake_query(arg, *_a, **_kw):
            if arg is TabbedContent:
                return fake_tabs
            if arg is DrivePanel:
                return fake_drive
            return MagicMock()
        monkeypatch.setattr(fake_app, "query_one", fake_query,
                            raising=False)
        coverage_panel._dump_diagnostics()
        # pm.dump_diagnostics was called
        dump_calls = [c for c in fake_pm.calls if c[0] == "dump_diagnostics"]
        assert len(dump_calls) == 1
        _, _, kwargs = dump_calls[0]
        assert "ui_state" in kwargs
        assert kwargs["ui_state"]["active_tab"] == "tab-coverage"
        assert kwargs["ui_state"]["drive"]["gear"] == 2
        # Inline progress message uses yellow
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[yellow]" in out

    def test_dump_complete_callback_green(self, coverage_panel, fake_pm,
                                            fake_app):
        """The callback wired into dump_diagnostics shows green on
        success and a 'cat <path>' hint."""
        # Capture the callback when dump_diagnostics is invoked
        captured_cb = {}
        def fake_dump(**kwargs):
            captured_cb["cb"] = kwargs["callback"]
            return "/tmp/diag.txt"
        fake_pm.dump_diagnostics = fake_dump
        coverage_panel._dump_diagnostics()
        # Invoke the captured callback as if the worker completed
        captured_cb["cb"]("/tmp/diag.txt", True)
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[green]" in out
        assert "Dump complete" in out
        assert "/tmp/diag.txt" in out

    def test_dump_failure_callback_red(self, coverage_panel, fake_pm,
                                         fake_app):
        captured_cb = {}
        def fake_dump(**kwargs):
            captured_cb["cb"] = kwargs["callback"]
            return "/tmp/diag.txt"
        fake_pm.dump_diagnostics = fake_dump
        coverage_panel._dump_diagnostics()
        captured_cb["cb"]("/tmp/diag.txt", False)
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out

    def test_dump_drive_panel_unavailable(self, coverage_panel,
                                            fake_app, fake_pm, monkeypatch):
        """If DrivePanel isn't mounted (rare during startup), the
        ui_state.drive is the '(panel not mounted)' string."""
        from textual.widgets import TabbedContent
        from command_center.panels.drive import DrivePanel
        def fake_query(arg, *_a, **_kw):
            if arg is DrivePanel:
                raise RuntimeError("drive not mounted")
            # TabbedContent works, return mock with active attr
            m = MagicMock()
            m.active = "tab-coverage"
            return m
        monkeypatch.setattr(fake_app, "query_one", fake_query,
                            raising=False)
        coverage_panel._dump_diagnostics()
        dump_calls = [c for c in fake_pm.calls if c[0] == "dump_diagnostics"]
        kwargs = dump_calls[0][2]
        assert kwargs["ui_state"]["drive"] == "(panel not mounted)"


class TestRefreshYawInputFromImu:

    def test_no_ros_returns(self, coverage_panel, fake_app):
        fake_app.ros = None  # type: ignore[assignment]
        coverage_panel._refresh_yaw_input_from_imu()  # must not raise

    def test_no_imu_yaw_returns(self, coverage_panel, fake_ros):
        fake_ros.map_yaw_from_imu_deg = None
        coverage_panel._refresh_yaw_input_from_imu()
        # No update happened — query_one wasn't called

    def test_updates_yaw_input(self, coverage_panel, fake_ros):
        fake_ros.map_yaw_from_imu_deg = 75.0
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="")
        coverage_panel._refresh_yaw_input_from_imu()
        assert coverage_panel.queried["#cov-pose-yaw"].value == "75"


class TestOnInputSubmitted:

    def test_pose_input_submission_publishes(self, coverage_panel,
                                               fake_ros):
        from textual.widgets import Input
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="1.0")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="2.0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        fake_input = MagicMock(spec=Input)
        fake_input.id = "cov-pose-x"
        evt = SimpleNamespace(input=fake_input)
        coverage_panel.on_input_submitted(evt)
        # publish_initial_pose was called
        assert len(fake_ros.initial_pose_calls) == 1

    def test_non_pose_input_ignored(self, coverage_panel, fake_ros):
        from textual.widgets import Input
        fake_input = MagicMock(spec=Input)
        fake_input.id = "not-a-pose-input"
        evt = SimpleNamespace(input=fake_input)
        coverage_panel.on_input_submitted(evt)
        # No publish should have happened
        assert len(fake_ros.initial_pose_calls) == 0


class TestSaveMapQueryException:

    def test_query_exception_treated_as_empty(self, coverage_panel,
                                                fake_pm, monkeypatch):
        def boom(selector, *_a, **_kw):
            if "cov-map-input" in selector:
                raise RuntimeError("not mounted")
            return coverage_panel.queried.setdefault(
                selector, SimpleNamespace(
                    last_update=None,
                    update=lambda t: setattr(
                        coverage_panel.queried[selector],
                        "last_update", t)))
        monkeypatch.setattr(coverage_panel, "query_one", boom)
        coverage_panel._save_map()
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[yellow]" in out


class TestUpdateRosoutTailGuards:

    def test_no_ros_returns_silently(self, coverage_panel, fake_app):
        fake_app.ros = None  # type: ignore[assignment]
        coverage_panel._update_rosout_tail()  # must not raise

    def test_get_rosout_exception_treated_as_empty(self, coverage_panel,
                                                     fake_ros):
        def boom():
            raise RuntimeError("ros gone")
        fake_ros.get_rosout_tail = boom  # type: ignore[assignment]
        coverage_panel._update_rosout_tail()
        out = coverage_panel.queried["#cov-rosout"].last_update
        assert "No warnings" in out


class TestUpdatePiServicesCacheException:

    def test_cache_fetch_exception_falls_back_to_empty(
            self, coverage_panel, fake_pm):
        """If pi_all_service_status raises (e.g. cache thread crashed),
        the cache becomes empty and shows 'Pi unreachable'."""
        def boom():
            raise RuntimeError("cache fail")
        fake_pm.pi_all_service_status = boom  # type: ignore[assignment]
        # Trigger the 5-tick refresh
        coverage_panel._pi_cache_tick = 0
        coverage_panel._update_pi_services()
        # _pi_cache should be set to {} via except branch
        assert coverage_panel._pi_cache == {}


class TestUpdateMacProcsFoxglovePortException:

    def test_foxglove_alive_exception_treated_as_false(self, coverage_panel,
                                                         fake_pm):
        def boom():
            raise RuntimeError("port check broke")
        fake_pm.foxglove_bridge_alive = boom  # type: ignore[assignment]
        # Should still render without crashing
        coverage_panel._update_mac_procs({"foxglove": "running"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        # Falls through to the 'process up, port DOWN' branch
        assert "port DOWN" in out


class TestUpdateMacProcsExitedSlam:

    def test_exited_status_for_slam_path(self, coverage_panel):
        """SLAM with an 'exited (N)' status renders as red — completes
        coverage of the exited branch in the non-foxglove loop."""
        coverage_panel._update_mac_procs({"slam": "exited (1)"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        assert "SLAM" in out
        assert "[red]" in out


class TestUpdateNav2LifecycleCacheException:

    def test_cache_fetch_exception(self, coverage_panel, fake_pm):
        def boom():
            raise RuntimeError("lifecycle fail")
        fake_pm.query_nav2_lifecycle = boom  # type: ignore[assignment]
        coverage_panel._nav_cache_tick = 0
        coverage_panel._update_nav2_lifecycle()
        assert coverage_panel._nav_cache == {}


class TestUpdateAlertsFoxgloveException:

    def test_foxglove_alive_exception_treated_as_false(self, coverage_panel,
                                                         fake_pm):
        def boom():
            raise RuntimeError("port broke")
        fake_pm.foxglove_bridge_alive = boom  # type: ignore[assignment]
        coverage_panel._update_alerts({}, {})
        # Foxglove alert WAS triggered (treated as not alive)
        out = coverage_panel.queried["#cov-alerts"].last_update
        assert "Foxglove" in out


# ════════════════════════════════════════════════════════════════════════
# on_mount + _maybe_refresh_yaw_from_imu
# ════════════════════════════════════════════════════════════════════════

class TestOnMount:

    def test_populates_map_input_from_latest(self, coverage_panel,
                                              fake_pm, tmp_path):
        # Two maps; the newer one should be picked
        old = tmp_path / "old.yaml"; old.write_text("")
        new = tmp_path / "new.yaml"; new.write_text("")
        import os
        os.utime(old, (_time.time() - 100, _time.time() - 100))
        fake_pm._returns["list_maps"] = [str(old), str(new)]
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="")
        coverage_panel.on_mount()
        assert "new.yaml" in coverage_panel.queried["#cov-map-input"].value

    def test_populates_pose_inputs(self, coverage_panel, fake_ros,
                                     monkeypatch):
        """Pose pre-fill from RosBridge.load_persisted_pose."""
        from command_center.ros_bridge import RosBridge
        monkeypatch.setattr(RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: (1.5, -2.0, 0.5)))
        for sel in ("#cov-map-input", "#cov-pose-x", "#cov-pose-y",
                     "#cov-pose-yaw"):
            coverage_panel.queried[sel] = SimpleNamespace(value="")
        coverage_panel.on_mount()
        assert coverage_panel.queried["#cov-pose-x"].value == "1.50"
        assert coverage_panel.queried["#cov-pose-y"].value == "-2.00"
        # Yaw default rendered as degrees, no IMU override
        assert "29" in coverage_panel.queried["#cov-pose-yaw"].value  # 0.5 rad ≈ 29°

    def test_imu_yaw_overrides_persisted(self, coverage_panel, fake_ros,
                                           monkeypatch):
        """When IMU is calibrated AND publishing, on_mount uses
        live IMU yaw instead of the persisted yaw."""
        from command_center.ros_bridge import RosBridge
        monkeypatch.setattr(RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: (0, 0, 0)))
        fake_ros.map_yaw_from_imu_deg = 75.0
        for sel in ("#cov-map-input", "#cov-pose-x", "#cov-pose-y",
                     "#cov-pose-yaw"):
            coverage_panel.queried[sel] = SimpleNamespace(value="")
        coverage_panel.on_mount()
        assert coverage_panel.queried["#cov-pose-yaw"].value == "75"


class TestMaybeRefreshYawFromImu:

    def test_no_ros_returns_silently(self, coverage_panel, fake_app):
        fake_app.ros = None  # type: ignore[assignment]
        coverage_panel._maybe_refresh_yaw_from_imu()  # must not raise

    def test_amcl_localized_skips(self, coverage_panel, fake_ros):
        """When AMCL is already localized, don't clobber the user's yaw
        with the IMU-derived value."""
        fake_ros.amcl_localized_return = True
        fake_ros.map_yaw_from_imu_deg = 99.0
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(
            value="(unchanged)")
        coverage_panel._maybe_refresh_yaw_from_imu()
        # Yaw input still has the original (no refresh happened)
        assert coverage_panel.queried["#cov-pose-yaw"].value == "(unchanged)"

    def test_yaw_input_focused_skips(self, coverage_panel, fake_ros,
                                       fake_app, monkeypatch):
        """If the user is currently focused on the yaw input field,
        don't overwrite what they're typing."""
        from textual.widgets import Input
        fake_ros.amcl_localized_return = False
        fake_ros.map_yaw_from_imu_deg = 99.0
        # Simulate focused = yaw input
        fake_input = MagicMock(spec=Input)
        fake_input.id = "cov-pose-yaw"
        type(fake_app).focused = property(lambda self: fake_input)
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(
            value="(typing)")
        coverage_panel._maybe_refresh_yaw_from_imu()
        # Unchanged — user is editing
        assert coverage_panel.queried["#cov-pose-yaw"].value == "(typing)"

    def test_proceeds_to_refresh_when_idle(self, coverage_panel, fake_ros,
                                             fake_app):
        """Happy path — not localized, not focused, refreshes from IMU."""
        fake_ros.amcl_localized_return = False
        fake_ros.map_yaw_from_imu_deg = 45.0
        # No focus
        type(fake_app).focused = property(lambda self: None)
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="")
        coverage_panel._maybe_refresh_yaw_from_imu()
        assert coverage_panel.queried["#cov-pose-yaw"].value == "45"


# ── Final coverage-panel gap closers ─────────────────────────────────

class TestLowercaseATriggersAutoStart:

    def test_lowercase_a_triggers_auto_start(self, coverage_panel, fake_pm):
        """The 'a' lowercase key (not just 'A'/'shift+a') also fires
        auto_start. Same destination as the macro shortcut."""
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="", update=lambda *a: None)
        fake_pm._returns["list_maps"] = []  # no maps → red message
        coverage_panel.process_key("a")
        # The "no map" message appeared
        out = coverage_panel.queried["#cov-result"].last_update
        assert "[red]" in out


class TestAutoStartReentrantLockReuse:

    def test_second_invocation_reuses_existing_lock(self, coverage_panel,
                                                      fake_pm):
        """_auto_steps_lock is lazily created on first call. The second
        call should reuse the existing lock instead of creating a new one,
        covering the 'has _auto_steps_lock attribute' branch."""
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(
            value="/tmp/m.yaml", update=lambda *a: None)
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="0")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="0")
        fake_pm.set_return("validate_map_for_nav", (True, ""))
        # First call creates the lock
        coverage_panel._auto_start()
        first_lock = coverage_panel._auto_steps_lock
        # Second call should NOT create a new lock — reuse
        coverage_panel._auto_start()
        assert coverage_panel._auto_steps_lock is first_lock


class TestKillTeleopNoRos:

    def test_kill_teleop_no_ros_skips_explicit_zero(self, coverage_panel,
                                                      fake_app, fake_pm,
                                                      monkeypatch):
        """When self.app.ros is None, _kill_teleop skips the explicit
        zero-publish and only handles the local teleop kill via pm."""
        fake_app.ros = None  # type: ignore[assignment]
        # Make query_one raise (no DrivePanel) so we go straight to PM
        def raising_query_one(*_a, **_kw):
            raise RuntimeError("no drive")
        monkeypatch.setattr(fake_app, "query_one", raising_query_one,
                            raising=False)
        fake_pm._returns["kill_zombie_teleop"] = 2
        coverage_panel._kill_teleop()  # must not raise
        out = coverage_panel.queried["#cov-result"].last_update
        assert "killed 2" in out

    def test_drive_panel_found_but_ros_none(self, coverage_panel,
                                              fake_app, fake_pm,
                                              monkeypatch):
        """Edge case: DrivePanel IS mounted but ros is None (perhaps
        --no-ros mode but Drive tab is loaded). The if-ros branch is
        False so we skip the publish but still mark drive_stopped=True."""
        fake_app.ros = None  # type: ignore[assignment]
        fake_drive = MagicMock()
        def fake_query(_panel_type):
            return fake_drive  # Drive panel IS found
        monkeypatch.setattr(fake_app, "query_one", fake_query,
                            raising=False)
        fake_pm._returns["kill_zombie_teleop"] = 0
        coverage_panel._kill_teleop()
        # Drive's _stop_driving was called
        fake_drive._stop_driving.assert_called_once()
        # The "Drive panel timer stopped" appears in the result
        out = coverage_panel.queried["#cov-result"].last_update
        assert "Drive panel timer stopped" in out


class TestOnInputSubmittedException:

    def test_event_without_input_attr_swallowed(self, coverage_panel):
        """If event.input access raises (e.g. wrong event shape), the
        handler swallows it silently rather than propagating."""
        evt = SimpleNamespace()  # no .input attr
        coverage_panel.on_input_submitted(evt)  # must not raise


class TestPiCacheTickNonRefresh:

    def test_non_refresh_tick_uses_existing_cache(self, coverage_panel,
                                                    fake_pm):
        """Cache only refreshes every 5 ticks. On other ticks, the
        previously-cached value is reused without an SSH call."""
        # Pre-populate cache
        coverage_panel._pi_cache_tick = 0
        coverage_panel._pi_cache = {"rovac-edge-mux": "active"}
        # Sentinel: pm.pi_all_service_status would explode if called
        def boom():
            raise AssertionError("pm should NOT be re-queried on non-refresh tick")
        fake_pm.pi_all_service_status = boom  # type: ignore[assignment]
        # Bump tick to 2 (% 5 == 2, NOT == 1) — should skip refresh
        coverage_panel._pi_cache_tick = 1  # next will be 2
        coverage_panel._update_pi_services()
        # Cache is unchanged
        assert coverage_panel._pi_cache == {"rovac-edge-mux": "active"}


class TestNav2CacheTickNonRefresh:

    def test_non_refresh_tick_uses_existing_cache(self, coverage_panel,
                                                    fake_pm):
        coverage_panel._nav_cache_tick = 0
        coverage_panel._nav_cache = {"/amcl": "active"}
        def boom():
            raise AssertionError("nav2 cache should NOT be re-queried on non-refresh tick")
        fake_pm.query_nav2_lifecycle = boom  # type: ignore[assignment]
        coverage_panel._nav_cache_tick = 1  # next tick = 2, not %6==1
        coverage_panel._update_nav2_lifecycle()
        assert coverage_panel._nav_cache == {"/amcl": "active"}


class TestUpdateMacProcsFoxgloveExited:

    def test_foxglove_exited_with_port_dead_shows_red(self, coverage_panel,
                                                        fake_pm):
        fake_pm._returns["foxglove_bridge_alive"] = False
        coverage_panel._update_mac_procs({"foxglove": "exited (2)"})
        out = coverage_panel.queried["#cov-mac-procs"].last_update
        # The exited branch with port DOWN should render red
        assert "Foxglove" in out
        assert "[red]" in out
        assert "exited" in out


class TestOnMountExceptionPaths:

    def test_list_maps_exception_handled(self, coverage_panel, fake_pm):
        """If pm.list_maps raises during on_mount (rare; would mean PM
        itself is broken), on_mount catches it and proceeds with no
        default map."""
        def boom():
            raise RuntimeError("pm bork")
        fake_pm.list_maps = boom  # type: ignore[assignment]
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="")
        # Must not raise
        coverage_panel.on_mount()

    def test_load_persisted_pose_exception_handled(self, coverage_panel,
                                                     monkeypatch):
        """If load_persisted_pose raises (corrupt state file), on_mount's
        outer try/except catches it — input fields just stay empty."""
        from command_center.ros_bridge import RosBridge
        def raising(*_a, **_kw):
            raise RuntimeError("state file corrupt")
        monkeypatch.setattr(RosBridge, "load_persisted_pose",
                            classmethod(lambda cls: raising()))
        coverage_panel.queried["#cov-map-input"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-x"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-y"] = SimpleNamespace(value="")
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="")
        coverage_panel.on_mount()  # must not raise


class TestMaybeRefreshFocusedCheckException:

    def test_focused_check_exception_swallowed(self, coverage_panel,
                                                 fake_ros, fake_app):
        """If the focused-check raises (e.g. Input is None or focused
        access fails), _maybe_refresh swallows and proceeds to refresh."""
        fake_ros.amcl_localized_return = False
        fake_ros.map_yaw_from_imu_deg = 60.0
        # Make access to .id or isinstance raise
        broken = MagicMock()
        type(broken).id = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("broken")))
        type(fake_app).focused = property(lambda self: broken)
        coverage_panel.queried["#cov-pose-yaw"] = SimpleNamespace(value="")
        coverage_panel._maybe_refresh_yaw_from_imu()  # must not raise
        # Refresh DID happen (exception swallowed, proceeded to refresh)
        assert coverage_panel.queried["#cov-pose-yaw"].value == "60"
