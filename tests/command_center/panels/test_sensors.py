"""Tests for ``command_center.panels.sensors``."""
from __future__ import annotations

import math

import pytest

from command_center.panels import sensors
from command_center.panels.sensors import SensorsPanel, _fmt_heap, _fmt_uptime


# ── Formatting helpers ──────────────────────────────────────────────────

class TestFmtUptime:

    @pytest.mark.parametrize("inp,want", [
        ("0", "0s"),
        ("30", "30s"),
        ("59", "59s"),
        ("60", "1m 00s"),
        ("90", "1m 30s"),
        ("3599", "59m 59s"),
        ("3600", "1h 00m"),
        ("3660", "1h 01m"),
        ("7200", "2h 00m"),
    ])
    def test_valid_inputs(self, inp, want):
        assert _fmt_uptime(inp) == want

    @pytest.mark.parametrize("bad", ["abc", "", None, "1.2.3"])
    def test_invalid_returns_dashes(self, bad):
        assert _fmt_uptime(bad) == "---"

    def test_accepts_float_string(self):
        # ESP32 publishes "120.5" sometimes
        assert _fmt_uptime("120.5") == "2m 00s"


class TestFmtHeap:

    @pytest.mark.parametrize("inp,want", [
        ("1024", "1 KB"),
        ("100000", "98 KB"),
        ("204800", "200 KB"),
    ])
    def test_formats_to_kb(self, inp, want):
        assert _fmt_heap(inp) == want

    @pytest.mark.parametrize("bad", ["abc", "", None])
    def test_invalid_returns_dashes(self, bad):
        assert _fmt_heap(bad) == "---"


# ── Panel update methods ────────────────────────────────────────────────

class TestUpdateOdom:

    def test_zero_state_renders_zeros(self, sensors_panel):
        sensors_panel.update_state({}, [], {})
        out = sensors_panel.queried["#sens-odom"].last_update
        assert "0.000 m" in out
        assert "0.0" in out

    def test_renders_pose_and_velocity(self, sensors_panel):
        state = {
            "odom_x": 1.234, "odom_y": -2.345,
            "odom_yaw": math.pi / 4,
            "odom_vx": 0.15, "odom_wz": 0.3,
            "odom_total_dist": 5.67,
            "odom_hz": 19.8,
        }
        sensors_panel.update_state(state, [], {})
        out = sensors_panel.queried["#sens-odom"].last_update
        assert "1.234" in out
        assert "-2.345" in out
        assert "45.0" in out  # yaw degrees
        assert "0.150" in out
        assert "5.67" in out
        assert "19.8" in out


class TestUpdateLidar:

    def test_no_data_shows_dim_status(self, sensors_panel):
        sensors_panel.update_state({}, [], {})
        out = sensors_panel.queried["#sens-lidar"].last_update
        assert "No data" in out

    def test_active_status_when_publishing(self, sensors_panel):
        sensors_panel.update_state(
            {"scan_hz": 10.0, "scan_count": 500,
             "scan_min": 0.05, "scan_max": 12.0}, [], {})
        out = sensors_panel.queried["#sens-lidar"].last_update
        assert "Active" in out
        assert "10.0 Hz" in out
        assert "500" in out
        assert "0.05" in out
        assert "12.00" in out


class TestUpdateUltra:

    def test_no_data_shows_dashes(self, sensors_panel):
        sensors_panel.update_state({}, [], {})
        out = sensors_panel.queried["#sens-ultra"].last_update
        # All 4 should be dashed
        assert out.count("---") >= 4

    def test_distances_rendered_when_present(self, sensors_panel):
        sensors_panel.update_state({
            "ultra_front": 0.5, "ultra_rear": 1.0,
            "ultra_left": 0.3, "ultra_right": 2.0,
        }, [], {})
        out = sensors_panel.queried["#sens-ultra"].last_update
        assert "0.50 m" in out
        assert "1.00 m" in out
        assert "0.30 m" in out
        assert "2.00 m" in out

    def test_cliff_clear_when_false(self, sensors_panel):
        sensors_panel.update_state({"cliff_detected": False}, [], {})
        out = sensors_panel.queried["#sens-ultra"].last_update
        assert "CLEAR" in out

    def test_cliff_alert_when_true(self, sensors_panel):
        sensors_panel.update_state({"cliff_detected": True}, [], {})
        out = sensors_panel.queried["#sens-ultra"].last_update
        assert "CLIFF" in out
        assert "[red bold]" in out


class TestUpdateDiagMotor:

    def test_no_diag_shows_dim(self, sensors_panel):
        sensors_panel.update_state({"diag_motor": {}}, [], {})
        out = sensors_panel.queried["#sens-diag-motor"].last_update
        assert "No motor diagnostics" in out

    def test_renders_wifi_heap_uptime(self, sensors_panel):
        sensors_panel.update_state({"diag_motor": {
            "wifi_rssi": "-55",
            "heap_free": "120000",
            "uptime_s": "3600",
        }}, [], {})
        out = sensors_panel.queried["#sens-diag-motor"].last_update
        assert "-55 dBm" in out
        assert "117 KB" in out
        assert "1h 00m" in out

    @pytest.mark.parametrize("rssi,want_color", [
        ("-30", "green"),
        ("-49", "green"),
        ("-50", "yellow"),  # boundary: > -50 only
        ("-60", "yellow"),
        ("-70", "red"),     # boundary: > -70 only
        ("-80", "red"),
    ])
    def test_rssi_color_thresholds(self, sensors_panel, rssi, want_color):
        sensors_panel.update_state({"diag_motor": {
            "wifi_rssi": rssi, "heap_free": "0", "uptime_s": "0",
        }}, [], {})
        out = sensors_panel.queried["#sens-diag-motor"].last_update
        assert f"[{want_color}]" in out

    def test_non_numeric_rssi_falls_back_to_dim(self, sensors_panel):
        sensors_panel.update_state({"diag_motor": {
            "wifi_rssi": "n/a", "heap_free": "0", "uptime_s": "0",
        }}, [], {})
        out = sensors_panel.queried["#sens-diag-motor"].last_update
        assert "[dim]" in out


class TestUpdateBno055Imu:

    def test_no_imu_data_shows_dim(self, sensors_panel):
        sensors_panel.update_state({"bno055_imu_hz": 0}, [], {})
        out = sensors_panel.queried["#sens-bno055-imu"].last_update
        assert "No BNO055" in out

    def test_renders_accel_gyro_orientation(self, sensors_panel):
        sensors_panel.update_state({
            "bno055_imu_hz": 20,
            "bno055_accel_x": 0.1, "bno055_accel_y": -0.2, "bno055_accel_z": 9.81,
            "bno055_gyro_x": 0.01, "bno055_gyro_y": -0.02, "bno055_gyro_z": 0.03,
            "bno055_orient_roll": 1.5,
            "bno055_orient_pitch": -2.3,
            "bno055_orient_yaw": 45.0,
        }, [], {})
        out = sensors_panel.queried["#sens-bno055-imu"].last_update
        assert "Accel" in out
        assert "Gyro" in out
        assert "Orient" in out
        assert "9.81" in out
        assert "+45.0" in out
        assert "20 Hz" in out


class TestUpdateStateSmoke:

    def test_minimal_state(self, sensors_panel):
        sensors_panel.update_state({}, [], {})

    def test_realistic_state(self, sensors_panel):
        sensors_panel.update_state({
            "odom_x": 1, "odom_y": 1, "odom_yaw": 0,
            "scan_hz": 10, "scan_count": 360,
            "ultra_front": 0.5, "cliff_detected": False,
            "diag_motor": {"wifi_rssi": "-60", "heap_free": "100000",
                            "uptime_s": "60"},
            "bno055_imu_hz": 20,
        }, [], {})
        # All 5 panel widgets touched
        for selector in ("#sens-odom", "#sens-lidar", "#sens-ultra",
                          "#sens-diag-motor", "#sens-bno055-imu"):
            assert sensors_panel.queried[selector].last_update is not None
