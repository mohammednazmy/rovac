"""Tests for ``command_center.panels.dashboard``.

Covers the rendering helpers (`_dot`, `_bar`, `_hz`) and each `update_*`
sub-method on the panel.
"""
from __future__ import annotations

import math

import pytest

from command_center.panels import dashboard
from command_center.panels.dashboard import DashboardPanel, _bar, _dot, _hz


# ── Rendering helpers ───────────────────────────────────────────────────

class TestDot:

    def test_true_is_green(self):
        assert _dot(True) == "[green]●[/]"

    def test_false_is_red(self):
        assert _dot(False) == "[red]●[/]"

    def test_none_is_dim_open_circle(self):
        out = _dot(None)
        assert "[dim]" in out and "○" in out


class TestBar:

    def test_zero_pct_all_empty(self):
        out = _bar(0)
        # 0/10 = 0 filled → 10 empty chars + "  0%"
        assert "█" not in out
        assert "░" * 10 in out
        assert "0%" in out

    def test_full_pct_all_filled(self):
        out = _bar(100)
        assert "█" * 10 in out
        assert "░" not in out
        assert "100%" in out

    @pytest.mark.parametrize("pct,expected_color", [
        (10, "green"),
        (50, "green"),
        (59.9, "green"),
        (60, "yellow"),
        (75, "yellow"),
        (79.9, "yellow"),
        (80, "red"),
        (100, "red"),
        (150, "red"),  # over-100 still classified as red
    ])
    def test_color_thresholds(self, pct, expected_color):
        assert f"[{expected_color}]" in _bar(pct)

    def test_filled_count_proportional(self):
        # 50% on width 10 → 5 filled chars
        out = _bar(50, width=10)
        # Strip Rich tags then count
        body = out.split("]", 1)[1].split("[")[0]
        assert body.count("█") == 5
        assert body.count("░") == 5

    def test_negative_pct_clamped_to_zero(self):
        # max(0, ...) should keep filled count from going negative
        out = _bar(-50)
        assert "[green]" in out  # falls in <60 bucket

    def test_custom_width(self):
        out = _bar(50, width=20)
        body = out.split("]", 1)[1].split("[")[0]
        assert body.count("█") == 10
        assert body.count("░") == 10


class TestHz:

    @pytest.mark.parametrize("val", [0, -0.5, -100])
    def test_non_positive_is_dim(self, val):
        out = _hz(val)
        assert "[dim]" in out

    def test_positive_is_green_with_one_decimal(self):
        assert _hz(10.0) == "[green]10.0[/]"

    def test_formats_to_one_decimal(self):
        assert "20.3" in _hz(20.345)


# ── Panel update methods ────────────────────────────────────────────────

class TestUpdateConnectivity:

    def test_all_systems_green_when_connected(self, dashboard_panel):
        state = {
            "ros_connected": True,
            "edge_health": {
                "usb": {"esp32_motor": True},
                "services": {
                    "rovac-edge-rplidar-c1": {"active": True},
                },
            },
            "bno055_imu_hz": 20.0,
        }
        proc_status = {"foxglove": "running"}
        dashboard_panel.update_state(state, [], proc_status)
        out = dashboard_panel.queried["#dash-connectivity"].last_update
        assert out is not None
        # ROS, Pi, Motor, LIDAR all green; Foxglove green
        assert out.count("[green]●[/]") >= 4
        assert "ws://localhost:8765" in out

    def test_foxglove_off_when_not_running(self, dashboard_panel):
        dashboard_panel.update_state({"ros_connected": False}, [],
                                      {"foxglove": "exited (0)"})
        out = dashboard_panel.queried["#dash-connectivity"].last_update
        assert "[dim]○ OFF[/]" in out

    def test_bno055_silent_shown_as_dim(self, dashboard_panel):
        dashboard_panel.update_state(
            {"bno055_imu_hz": 0}, [], {"foxglove": "stopped"})
        out = dashboard_panel.queried["#dash-connectivity"].last_update
        assert "BNO055" in out
        # Dim circle when no IMU
        assert "[dim]○ ---[/]" in out


class TestUpdatePiSystem:

    def test_waiting_message_when_no_health_data(self, dashboard_panel):
        dashboard_panel.update_state({}, [], {})
        out = dashboard_panel.queried["#dash-pi-system"].last_update
        assert "Waiting" in out

    def test_renders_cpu_ram_temp_disk(self, dashboard_panel):
        state = {"edge_health": {
            "system": {
                "cpu_percent": 45,
                "memory_percent": 60,
                "cpu_temp": 55,
                "disk_percent": 70,
            },
            "agent": {"rss_mb": 120},
        }}
        dashboard_panel.update_state(state, [], {})
        out = dashboard_panel.queried["#dash-pi-system"].last_update
        assert "CPU" in out
        assert "RAM" in out
        assert "Disk" in out
        assert "55°C" in out
        assert "120 MB" in out


class TestUpdateTopicsRobot:

    def test_zeros_when_no_data(self, dashboard_panel):
        dashboard_panel.update_state({}, [], {})
        out = dashboard_panel.queried["#dash-topics-robot"].last_update
        assert "/odom" in out
        assert "0.0" in out

    def test_renders_position_and_velocity(self, dashboard_panel):
        state = {
            "odom_hz": 20, "scan_hz": 10, "map_hz": 1,
            "odom_x": 1.5, "odom_y": -2.0,
            "odom_yaw": math.pi / 4, "odom_vx": 0.15, "odom_wz": 0.3,
            "odom_total_dist": 12.34,
        }
        dashboard_panel.update_state(state, [], {})
        out = dashboard_panel.queried["#dash-topics-robot"].last_update
        assert "+1.50" in out
        assert "-2.00" in out
        assert "+45.0" in out  # yaw degrees
        assert "12.3m" in out  # distance


class TestUpdateEdgeServices:

    def test_waiting_when_no_services(self, dashboard_panel):
        dashboard_panel.update_state({"edge_health": {}}, [], {})
        out = dashboard_panel.queried["#dash-edge-services"].last_update
        assert "Waiting" in out

    def test_renders_active_service_dots(self, dashboard_panel):
        services = {svc: {"active": True} for svc in [
            "rovac-edge-motor-driver",
            "rovac-edge-sensor-hub",
        ]}
        dashboard_panel.update_state(
            {"edge_health": {"services": services}}, [], {})
        out = dashboard_panel.queried["#dash-edge-services"].last_update
        # Each rendered active service shows the green dot + short name
        assert "[green]●[/]" in out
        assert "motor-driver" in out
        assert "sensor-hub" in out


class TestUpdateLog:

    def test_empty_log(self, dashboard_panel):
        dashboard_panel.update_state({}, [], {})
        out = dashboard_panel.queried["#dash-log"].last_update
        assert "No log entries" in out

    def test_shows_last_six_entries(self, dashboard_panel):
        logs = [(f"00:00:{i:02d}", f"event-{i}") for i in range(10)]
        dashboard_panel.update_state({}, logs, {})
        out = dashboard_panel.queried["#dash-log"].last_update
        # Only the last 6 entries should appear
        for i in range(4, 10):
            assert f"event-{i}" in out
        assert "event-3" not in out


# ── End-to-end smoke ────────────────────────────────────────────────────

class TestUpdateStateSmoke:

    def test_minimal_state_doesnt_crash(self, dashboard_panel):
        dashboard_panel.update_state({}, [], {})

    def test_realistic_state(self, dashboard_panel):
        state = {
            "ros_connected": True,
            "edge_health": {
                "usb": {"esp32_motor": True},
                "services": {svc: {"active": True} for svc in
                              ["rovac-edge-motor-driver",
                               "rovac-edge-sensor-hub"]},
                "system": {"cpu_percent": 30, "memory_percent": 50,
                            "cpu_temp": 50, "disk_percent": 40},
                "agent": {"rss_mb": 100},
            },
            "bno055_imu_hz": 20,
            "odom_hz": 20, "scan_hz": 10, "map_hz": 1,
            "odom_x": 0, "odom_y": 0, "odom_yaw": 0,
            "odom_vx": 0, "odom_wz": 0, "odom_total_dist": 0,
        }
        logs = [("00:00:00", "started")]
        proc_status = {"foxglove": "running"}
        dashboard_panel.update_state(state, logs, proc_status)
        # All 5 IDs were touched.
        for selector in ("#dash-connectivity", "#dash-pi-system",
                          "#dash-topics-robot", "#dash-edge-services",
                          "#dash-log"):
            assert selector in dashboard_panel.queried
            assert dashboard_panel.queried[selector].last_update is not None
