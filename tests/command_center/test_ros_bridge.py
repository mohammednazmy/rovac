"""Tests for ``command_center.ros_bridge``.

Covers everything that doesn't require a running rclpy spin loop:

  * ``HzTracker`` sliding window + stale-decay
  * ``RosBridge`` state, log buffer, rosout tail
  * Every message callback (``_on_odom``, ``_on_scan``, ``_on_map``,
    ``_on_diagnostics``, ``_on_edge_health``, ``_on_range``, ``_on_cliff``,
    ``_on_amcl_pose``, ``_on_rosout``, ``_on_bno055_imu``,
    ``_on_mux_active``, ``_on_coverage_path``, ``_on_coverage_visited``,
    ``_on_cmd_vel_out``) — using namespace-shaped fake messages from
    conftest.
  * Pose persistence + yaw-offset calibration (with ``tmp_path``).
  * ``publish_cmd_vel`` happy and not-yet-ready paths.
  * AMCL localization age check.

Intentionally NOT covered (deferred to integration phase):
  * ``_run`` (rclpy.init + subscription wiring)
  * ``start()`` / ``stop()`` lifecycle
  * ``_hz_refresh_loop`` background thread
  * ``trigger_global_localization`` (service call in worker thread)
  * ``publish_initial_pose`` (needs a real ``rclpy`` for the publisher)
"""
from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from command_center.ros_bridge import HzTracker, RosBridge


# ════════════════════════════════════════════════════════════════════════
# HzTracker
# ════════════════════════════════════════════════════════════════════════

class TestHzTracker:
    """Sliding-window frequency estimator with stale-decay."""

    def test_zero_when_no_ticks(self):
        assert HzTracker().hz() == 0.0

    def test_zero_with_only_one_tick(self):
        t = HzTracker()
        t.tick()
        assert t.hz() == 0.0  # need >= 2 timestamps

    def test_steady_rate(self, monkeypatch):
        """Tick at exactly 10 Hz over 1 second — hz() should be ~10."""
        from command_center import ros_bridge
        clock = [100.0]
        monkeypatch.setattr(ros_bridge.time, "monotonic", lambda: clock[0])
        t = HzTracker(window_size=11)
        for _ in range(11):
            t.tick()
            clock[0] += 0.1
        # 10 intervals across 1.0s = 10 Hz
        clock[0] -= 0.1  # don't let staleness fire
        assert t.hz() == pytest.approx(10.0, abs=0.01)

    def test_stale_decays_to_zero(self, monkeypatch):
        from command_center import ros_bridge
        clock = [100.0]
        monkeypatch.setattr(ros_bridge.time, "monotonic", lambda: clock[0])
        t = HzTracker(window_size=5, max_age_s=2.0)
        for _ in range(5):
            t.tick()
            clock[0] += 0.1
        # Now jump forward beyond max_age_s
        clock[0] += 5.0
        assert t.hz() == 0.0

    def test_window_size_bounds_memory(self):
        """The deque should cap at window_size, not grow unbounded."""
        t = HzTracker(window_size=5)
        for _ in range(20):
            t.tick()
        assert len(t.times) == 5

    def test_zero_when_duplicate_timestamps(self, monkeypatch):
        """If the clock doesn't advance (shouldn't happen, but be safe)."""
        from command_center import ros_bridge
        monkeypatch.setattr(ros_bridge.time, "monotonic", lambda: 100.0)
        t = HzTracker()
        for _ in range(5):
            t.tick()
        assert t.hz() == 0.0


# ════════════════════════════════════════════════════════════════════════
# State + accessors
# ════════════════════════════════════════════════════════════════════════

class TestBridgeInit:

    def test_initial_state_has_all_keys(self, bridge):
        # Spot-check the documented schema is intact. If a key is removed
        # or renamed, a panel reading it would silently see 0.0 or None
        # depending on its .get() default — pin them down.
        expected_keys = {
            "odom_x", "odom_y", "odom_yaw", "odom_vx", "odom_wz",
            "odom_hz", "odom_total_dist",
            "scan_hz", "scan_count", "scan_min", "scan_max",
            "map_hz", "map_width", "map_height", "map_resolution",
            "diag_motor", "edge_health",
            "ultra_front", "ultra_rear", "ultra_left", "ultra_right",
            "cliff_detected",
            "bno055_imu_hz",
            "bno055_accel_x", "bno055_accel_y", "bno055_accel_z",
            "bno055_gyro_x", "bno055_gyro_y", "bno055_gyro_z",
            "bno055_orient_roll", "bno055_orient_pitch", "bno055_orient_yaw",
            "cmd_vel_linear", "cmd_vel_angular",
            "amcl_localized", "amcl_x", "amcl_y", "amcl_yaw_deg",
            "amcl_cov_xx", "amcl_cov_yy", "amcl_cov_yaw",
            "amcl_last_update",
            "ros_connected", "topics_seen",
        }
        missing = expected_keys - set(bridge.state.keys())
        assert not missing, f"missing state keys: {missing}"

    def test_ultrasonic_default_to_inf(self, bridge):
        # Inf is the "no obstacle" sentinel — panels rely on it for
        # _range_color to show grey '---'. Don't change to 0.0.
        for d in ("front", "rear", "left", "right"):
            assert bridge.state[f"ultra_{d}"] == float("inf")

    def test_not_connected_initially(self, bridge):
        assert bridge.state["ros_connected"] is False

    def test_publishers_none_until_run(self, bridge):
        assert bridge._pub_cmd_vel is None
        assert bridge._pub_initialpose is None

    def test_log_buffer_bounded(self, bridge):
        assert isinstance(bridge._logs, deque)
        assert bridge._logs.maxlen == 200

    def test_rosout_tail_bounded(self, bridge):
        assert isinstance(bridge._rosout_tail, deque)
        assert bridge._rosout_tail.maxlen == 50


class TestStateAccessors:

    def test_get_state_returns_copy(self, bridge):
        snap = bridge.get_state()
        snap["odom_x"] = 999.0
        # The bridge's own state must not be mutated by external edits.
        assert bridge.state["odom_x"] == 0.0

    def test_get_logs_returns_copy(self, bridge):
        bridge.add_log("hello")
        logs = bridge.get_logs()
        logs.clear()
        assert len(bridge.get_logs()) == 1

    def test_get_rosout_tail_returns_copy(self, bridge):
        bridge._rosout_tail.append(("WARN", "node", "msg", 1))
        tail = bridge.get_rosout_tail()
        tail.clear()
        assert len(bridge.get_rosout_tail()) == 1


class TestAddLog:

    def test_appends_with_timestamp(self, bridge):
        bridge.add_log("first")
        logs = bridge.get_logs()
        assert len(logs) == 1
        ts, msg = logs[0]
        assert msg == "first"
        # Timestamp format is HH:MM:SS
        assert len(ts) == 8 and ts[2] == ":" and ts[5] == ":"

    def test_evicts_oldest_when_full(self, bridge):
        for i in range(250):
            bridge.add_log(f"msg-{i}")
        logs = bridge.get_logs()
        assert len(logs) == 200
        # First message was evicted; only the last 200 remain.
        assert logs[0][1] == "msg-50"
        assert logs[-1][1] == "msg-249"

    def test_thread_safe(self, bridge):
        """Hammer add_log from 8 threads — final count must equal total
        and no log entry should be malformed."""
        def worker():
            for _ in range(50):
                bridge.add_log("x")
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        logs = bridge.get_logs()
        # 8 × 50 = 400 sent, but buffer caps at 200.
        assert len(logs) == 200
        assert all(isinstance(ts, str) and msg == "x" for ts, msg in logs)


# ════════════════════════════════════════════════════════════════════════
# Message callbacks
# ════════════════════════════════════════════════════════════════════════

class TestOnOdom:

    def test_extracts_pose(self, bridge, make_odom_msg):
        msg = make_odom_msg(x=1.5, y=-2.5, yaw=math.pi / 4)
        bridge._on_odom(msg)
        assert bridge.state["odom_x"] == 1.5
        assert bridge.state["odom_y"] == -2.5
        assert bridge.state["odom_yaw"] == pytest.approx(math.pi / 4, abs=1e-6)

    def test_extracts_twist(self, bridge, make_odom_msg):
        bridge._on_odom(make_odom_msg(vx=0.3, wz=1.2))
        assert bridge.state["odom_vx"] == 0.3
        assert bridge.state["odom_wz"] == 1.2

    def test_accumulates_distance_across_calls(self, bridge, make_odom_msg):
        bridge._on_odom(make_odom_msg(x=0, y=0))
        bridge._on_odom(make_odom_msg(x=3, y=4))   # +5 (3-4-5 triangle)
        bridge._on_odom(make_odom_msg(x=3, y=0))   # +4
        assert bridge.state["odom_total_dist"] == pytest.approx(9.0)

    def test_yaw_wraps_around(self, bridge, make_odom_msg):
        bridge._on_odom(make_odom_msg(yaw=-math.pi / 2))
        assert bridge.state["odom_yaw"] == pytest.approx(-math.pi / 2, abs=1e-6)


class TestOnScan:

    def test_filters_to_valid_range(self, bridge, make_scan_msg):
        ranges = [0.05, 0.5, 1.0, 5.0, 15.0]  # 0.05 below min, 15 above max
        bridge._on_scan(make_scan_msg(ranges, range_min=0.1, range_max=12.0))
        assert bridge.state["scan_count"] == 3
        assert bridge.state["scan_min"] == 0.5
        assert bridge.state["scan_max"] == 5.0

    def test_empty_valid_set(self, bridge, make_scan_msg):
        bridge._on_scan(make_scan_msg([100.0, 200.0]))  # all out of range
        assert bridge.state["scan_count"] == 0
        assert bridge.state["scan_min"] == 0.0
        assert bridge.state["scan_max"] == 0.0


class TestOnMap:

    def test_extracts_dims(self, bridge, make_map_msg):
        # 4x4 with a mix of values
        cells = [0] * 16
        msg = make_map_msg(cells, width=4, height=4, resolution=0.1)
        bridge._on_map(msg)
        assert bridge.state["map_width"] == 4
        assert bridge.state["map_height"] == 4
        assert bridge.state["map_resolution"] == 0.1

    def test_counts_free_cells_for_coverage_denominator(
            self, bridge, make_map_msg):
        # 5 free (0), 3 occupied (100), 2 unknown (-1)
        cells = [0, 0, 0, 0, 0, 100, 100, 100, -1, -1]
        bridge._on_map(make_map_msg(cells, width=10, height=1))
        assert bridge.state["coverage_free_cells"] == 5


class TestOnDiagnostics:

    def test_extracts_motor_status(self, bridge, make_diag_msg):
        # Only the status whose name contains 'motor' should be captured.
        msg = make_diag_msg([
            ("ROVAC Sensor Hub", [("hz", "10")]),
            ("ROVAC Motor Serial", [("heap", "120000"), ("imu_cal", "3")]),
        ])
        bridge._on_diagnostics(msg)
        assert bridge.state["diag_motor"] == {"heap": "120000", "imu_cal": "3"}

    def test_ignores_non_motor_statuses(self, bridge, make_diag_msg):
        bridge._on_diagnostics(make_diag_msg([
            ("ROVAC LIDAR", [("hz", "10")]),
            ("Battery", [("voltage", "12.4")]),
        ]))
        assert bridge.state["diag_motor"] == {}


class TestOnEdgeHealth:

    def test_parses_valid_json(self, bridge):
        msg = SimpleNamespace(
            data=json.dumps({"services": {"x": {"active": True}}}))
        bridge._on_edge_health(msg)
        assert bridge.state["edge_health"]["services"]["x"]["active"] is True

    def test_silently_ignores_invalid_json(self, bridge):
        bridge._on_edge_health(SimpleNamespace(data="not-json"))
        # State should be unchanged from init.
        assert bridge.state["edge_health"] == {}


class TestOnRange:

    @pytest.mark.parametrize("direction", ["front", "rear", "left", "right"])
    def test_writes_to_correct_key(self, bridge, direction):
        bridge._on_range(SimpleNamespace(range=0.42), direction)
        assert bridge.state[f"ultra_{direction}"] == 0.42

    def test_other_directions_untouched(self, bridge):
        bridge._on_range(SimpleNamespace(range=0.5), "front")
        assert bridge.state["ultra_rear"] == float("inf")
        assert bridge.state["ultra_left"] == float("inf")
        assert bridge.state["ultra_right"] == float("inf")


class TestOnCliff:

    def test_sets_state(self, bridge):
        bridge._on_cliff(SimpleNamespace(data=True))
        assert bridge.state["cliff_detected"] is True
        bridge._on_cliff(SimpleNamespace(data=False))
        assert bridge.state["cliff_detected"] is False


class TestOnAmclPose:

    def test_extracts_pose_and_marks_localized(self, bridge, make_amcl_msg):
        msg = make_amcl_msg(x=2.5, y=-1.0, yaw=math.pi / 2)
        bridge._on_amcl_pose(msg)
        assert bridge.state["amcl_x"] == 2.5
        assert bridge.state["amcl_y"] == -1.0
        assert bridge.state["amcl_yaw_deg"] == pytest.approx(90.0, abs=0.01)
        assert bridge.state["amcl_localized"] is True
        assert bridge.state["amcl_last_update"] > 0

    def test_extracts_covariance_diag(self, bridge, make_amcl_msg):
        msg = make_amcl_msg(cov_xx=0.10, cov_yy=0.15, cov_yaw=0.02)
        bridge._on_amcl_pose(msg)
        assert bridge.state["amcl_cov_xx"] == 0.10
        assert bridge.state["amcl_cov_yy"] == 0.15
        assert bridge.state["amcl_cov_yaw"] == 0.02


class TestIsAmclLocalized:

    def test_false_when_never_localized(self, bridge):
        assert bridge.is_amcl_localized() is False

    def test_true_when_recent(self, bridge, make_amcl_msg):
        bridge._on_amcl_pose(make_amcl_msg())
        assert bridge.is_amcl_localized(max_age_s=5.0) is True

    def test_false_when_stale(self, bridge, make_amcl_msg, monkeypatch):
        from command_center import ros_bridge
        clock = [100.0]
        # Patch the module's monotonic that the callback uses, then the one
        # is_amcl_localized uses (both via `import time as _time`).
        monkeypatch.setattr(ros_bridge.time, "monotonic", lambda: clock[0])
        bridge._on_amcl_pose(make_amcl_msg())
        clock[0] += 100.0
        assert bridge.is_amcl_localized(max_age_s=5.0) is False


class TestOnMuxActive:

    @pytest.mark.parametrize("value", [
        "TELEOP", "JOYSTICK", "OBSTACLE", "NAV", "IDLE", "",
    ])
    def test_stores_string(self, bridge, value):
        bridge._on_mux_active(SimpleNamespace(data=value))
        assert bridge.state["mux_active"] == value


class TestOnCoveragePath:

    def test_stores_pose_count(self, bridge):
        msg = SimpleNamespace(poses=[1, 2, 3, 4, 5])  # opaque
        bridge._on_coverage_path(msg)
        assert bridge.state["coverage_total"] == 5

    def test_empty_path(self, bridge):
        bridge._on_coverage_path(SimpleNamespace(poses=[]))
        assert bridge.state["coverage_total"] == 0


class TestOnCoverageVisited:

    def test_pct_when_map_denominator_present(
            self, bridge, make_map_msg):
        # Step 1: map says 10 free cells
        bridge._on_map(make_map_msg([0] * 10, width=10, height=1))
        # Step 2: visited grid says 5 visited
        cells = [100, 100, 100, 100, 100, -1, -1, -1, -1, -1]
        bridge._on_coverage_visited(make_map_msg(cells, width=10, height=1))
        assert bridge.state["coverage_visited_cells"] == 5
        assert bridge.state["coverage_pct"] == pytest.approx(50.0)

    def test_falls_back_to_visited_grid_when_no_map(
            self, bridge, make_map_msg):
        # No /map yet — denominator is the non-unknown cells in visited grid.
        cells = [100, 100, -1, -1, 0]  # 2 visited, 3 known total
        bridge._on_coverage_visited(make_map_msg(cells, width=5, height=1))
        assert bridge.state["coverage_visited_cells"] == 2
        # Denominator: cells != -1 → 3, percent = 2/3 × 100 ≈ 66.7
        assert bridge.state["coverage_pct"] == pytest.approx(200.0 / 3.0)


class TestOnRosout:

    def test_drops_below_warn(self, bridge, make_rosout_msg):
        bridge._on_rosout(make_rosout_msg(level=10, msg="debug"))
        bridge._on_rosout(make_rosout_msg(level=20, msg="info"))
        assert len(bridge.get_rosout_tail()) == 0

    @pytest.mark.parametrize("level,want", [
        (30, "WARN"), (40, "ERROR"), (50, "FATAL"),
    ])
    def test_kept_levels_normalize(self, bridge, make_rosout_msg,
                                    level, want):
        bridge._on_rosout(make_rosout_msg(level=level, msg="m"))
        tail = bridge.get_rosout_tail()
        assert tail[-1][0] == want

    def test_unknown_level_becomes_question_mark(self, bridge,
                                                  make_rosout_msg):
        bridge._on_rosout(make_rosout_msg(level=999, msg="m"))
        tail = bridge.get_rosout_tail()
        assert tail[-1][0] == "?"

    def test_dedupes_consecutive_identical_messages(self, bridge,
                                                     make_rosout_msg):
        msg = make_rosout_msg(level=30, name="amcl", msg="cannot publish")
        for _ in range(5):
            bridge._on_rosout(msg)
        tail = bridge.get_rosout_tail()
        assert len(tail) == 1
        lvl, node, text, count = tail[0]
        assert (lvl, node, text, count) == ("WARN", "amcl",
                                             "cannot publish", 5)

    def test_different_messages_get_separate_entries(self, bridge,
                                                      make_rosout_msg):
        bridge._on_rosout(make_rosout_msg(level=30, msg="alpha"))
        bridge._on_rosout(make_rosout_msg(level=30, msg="beta"))
        bridge._on_rosout(make_rosout_msg(level=30, msg="alpha"))
        tail = bridge.get_rosout_tail()
        # alpha, beta, alpha — NOT collapsed because they're non-consecutive
        # (beta breaks the run).
        assert len(tail) == 3

    def test_long_messages_truncated_with_ellipsis(self, bridge,
                                                    make_rosout_msg):
        long_msg = "x" * 200
        bridge._on_rosout(make_rosout_msg(level=30, msg=long_msg))
        tail = bridge.get_rosout_tail()
        _, _, text, _ = tail[-1]
        assert len(text) == 80
        assert text.endswith("...")

    def test_short_messages_not_truncated(self, bridge, make_rosout_msg):
        bridge._on_rosout(make_rosout_msg(level=30, msg="short"))
        _, _, text, _ = bridge.get_rosout_tail()[-1]
        assert text == "short"

    def test_empty_msg_doesnt_crash(self, bridge, make_rosout_msg):
        bridge._on_rosout(make_rosout_msg(level=30, msg=""))
        _, _, text, _ = bridge.get_rosout_tail()[-1]
        assert text == ""

    def test_buffer_bounded(self, bridge, make_rosout_msg):
        for i in range(60):
            bridge._on_rosout(make_rosout_msg(level=30, msg=f"unique-{i}"))
        tail = bridge.get_rosout_tail()
        assert len(tail) == 50  # capped at maxlen


class TestOnBno055Imu:

    def test_accel_passed_through(self, bridge, make_imu_msg):
        bridge._on_bno055_imu(make_imu_msg(ax=1.0, ay=2.0, az=9.81))
        assert bridge.state["bno055_accel_x"] == 1.0
        assert bridge.state["bno055_accel_y"] == 2.0
        assert bridge.state["bno055_accel_z"] == 9.81

    def test_gyro_passed_through(self, bridge, make_imu_msg):
        bridge._on_bno055_imu(make_imu_msg(gx=0.1, gy=-0.2, gz=0.3))
        assert bridge.state["bno055_gyro_x"] == 0.1
        assert bridge.state["bno055_gyro_y"] == -0.2
        assert bridge.state["bno055_gyro_z"] == 0.3

    def test_yaw_only_quaternion_extracts_yaw(self, bridge, make_imu_msg):
        bridge._on_bno055_imu(make_imu_msg(yaw=math.pi / 2))  # 90°
        assert bridge.state["bno055_orient_yaw"] == pytest.approx(90.0, abs=0.01)
        assert bridge.state["bno055_orient_roll"] == pytest.approx(0.0, abs=0.01)
        assert bridge.state["bno055_orient_pitch"] == pytest.approx(0.0, abs=0.01)

    def test_roll_pitch_yaw(self, bridge, make_imu_msg):
        bridge._on_bno055_imu(make_imu_msg(
            roll=math.radians(30),
            pitch=math.radians(-15),
            yaw=math.radians(45)))
        assert bridge.state["bno055_orient_roll"] == pytest.approx(30.0, abs=0.1)
        assert bridge.state["bno055_orient_pitch"] == pytest.approx(-15.0, abs=0.1)
        assert bridge.state["bno055_orient_yaw"] == pytest.approx(45.0, abs=0.1)


class TestOnCmdVelOut:

    def test_noop_does_not_overwrite_published_cmd_vel(self, bridge):
        # We publish cmd_vel=(0.5, 0.0) — the mux echo of /cmd_vel should
        # not overwrite the state['cmd_vel_*'] which tracks OUR publish.
        bridge.state["cmd_vel_linear"] = 0.5
        bridge.state["cmd_vel_angular"] = 0.0
        bridge._on_cmd_vel_out(SimpleNamespace(linear=SimpleNamespace(x=999)))
        assert bridge.state["cmd_vel_linear"] == 0.5
        assert bridge.state["cmd_vel_angular"] == 0.0


# ════════════════════════════════════════════════════════════════════════
# publish_cmd_vel
# ════════════════════════════════════════════════════════════════════════

class TestPublishCmdVel:

    def test_silent_when_publisher_not_ready(self, bridge):
        """Pre-_run, no publisher exists. Calling publish must be a no-op
        not a crash."""
        assert bridge._pub_cmd_vel is None
        # Should not raise.
        bridge.publish_cmd_vel(0.2, 0.5)

    def test_state_unchanged_when_publisher_not_ready(self, bridge):
        bridge.publish_cmd_vel(0.2, 0.5)
        assert bridge.state["cmd_vel_linear"] == 0.0
        assert bridge.state["cmd_vel_angular"] == 0.0

    def test_publishes_twist_when_ready(self, bridge, monkeypatch):
        # Mock the twist module so we don't need ROS message classes.
        twist_instances = []

        class FakeTwist:
            def __init__(self):
                twist_instances.append(self)
                self.linear = SimpleNamespace(x=0)
                self.angular = SimpleNamespace(z=0)

        import sys
        fake_mod = SimpleNamespace(Twist=FakeTwist)
        monkeypatch.setitem(sys.modules, "geometry_msgs.msg", fake_mod)

        fake_pub = MagicMock()
        bridge._pub_cmd_vel = fake_pub

        bridge.publish_cmd_vel(0.15, -0.5)

        assert len(twist_instances) == 1
        assert twist_instances[0].linear.x == 0.15
        assert twist_instances[0].angular.z == -0.5
        fake_pub.publish.assert_called_once_with(twist_instances[0])
        assert bridge.state["cmd_vel_linear"] == 0.15
        assert bridge.state["cmd_vel_angular"] == -0.5


# ════════════════════════════════════════════════════════════════════════
# Pose persistence & yaw calibration
# ════════════════════════════════════════════════════════════════════════

class TestStatePersistence:

    def test_load_returns_empty_when_file_missing(
            self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "missing.json"))
        assert RosBridge._read_state_file() == {}

    def test_write_then_read_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "state.json"))
        ok = RosBridge._write_state_file({"map_yaw_offset_deg": 42.5})
        assert ok is True
        assert RosBridge._read_state_file() == {"map_yaw_offset_deg": 42.5}

    def test_load_persisted_pose_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "absent.json"))
        assert RosBridge.load_persisted_pose() == (0.0, 0.0, 0.0)

    def test_load_persisted_pose_from_file(self, tmp_path, monkeypatch):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({
            "last_pose": {"x": 1.0, "y": 2.0, "yaw_rad": 0.5}}))
        monkeypatch.setattr(RosBridge, "_STATE_FILE", str(path))
        assert RosBridge.load_persisted_pose() == (1.0, 2.0, 0.5)

    def test_load_yaw_offset_none_when_uncalibrated(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "u.json"))
        assert RosBridge.load_yaw_offset_deg() is None

    def test_load_yaw_offset_returns_float(self, tmp_path, monkeypatch):
        path = tmp_path / "s.json"
        path.write_text(json.dumps({"map_yaw_offset_deg": -42.5}))
        monkeypatch.setattr(RosBridge, "_STATE_FILE", str(path))
        assert RosBridge.load_yaw_offset_deg() == -42.5

    def test_has_yaw_calibration_reflects_offset_presence(
            self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "h.json"))
        assert bridge.has_yaw_calibration() is False
        RosBridge._write_state_file({"map_yaw_offset_deg": 10.0})
        assert bridge.has_yaw_calibration() is True

    def test_save_current_pose_requires_localized(
            self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "p.json"))
        # Not localized → False, nothing written.
        assert bridge.save_current_pose() is False

    def test_save_current_pose_persists_when_localized(
            self, bridge, tmp_path, monkeypatch, make_amcl_msg):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "p.json"))
        bridge._on_amcl_pose(make_amcl_msg(x=1.2, y=3.4,
                                            yaw=math.radians(45)))
        assert bridge.save_current_pose() is True
        x, y, yaw_rad = RosBridge.load_persisted_pose()
        assert x == pytest.approx(1.2)
        assert y == pytest.approx(3.4)
        assert yaw_rad == pytest.approx(math.radians(45), abs=1e-4)


class TestCalibrateYawOffset:

    def test_fails_when_not_localized(self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "c.json"))
        ok, _, msg = bridge.calibrate_yaw_offset()
        assert ok is False
        assert "AMCL" in msg

    def test_fails_when_imu_silent(self, bridge, tmp_path, monkeypatch,
                                    make_amcl_msg):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "c.json"))
        bridge._on_amcl_pose(make_amcl_msg())
        # bno055_imu_hz is 0 by default → IMU silent
        ok, _, msg = bridge.calibrate_yaw_offset()
        assert ok is False
        assert "BNO055" in msg

    def test_succeeds_with_localized_and_imu_active(
            self, bridge, tmp_path, monkeypatch, make_amcl_msg, make_imu_msg):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "c.json"))
        bridge._on_amcl_pose(make_amcl_msg(yaw=math.radians(45)))
        # Manually tick the IMU tracker so hz > 0
        bridge._hz["bno055_imu"] = HzTracker()
        # Push enough ticks to register as publishing
        for _ in range(10):
            bridge._hz["bno055_imu"].tick()
        # Manually populate state['bno055_imu_hz'] (calibrate_yaw_offset
        # reads state, not the tracker directly)
        bridge.state["bno055_imu_hz"] = 10.0
        bridge.state["bno055_orient_yaw"] = 30.0  # IMU thinks heading is 30°
        bridge.state["diag_motor"] = {"imu_cal_mag": "3"}
        ok, offset, msg = bridge.calibrate_yaw_offset()
        assert ok is True
        assert offset == pytest.approx(15.0)  # 45 - 30
        # Saved
        assert RosBridge.load_yaw_offset_deg() == pytest.approx(15.0)
        # Message doesn't warn about cal because mag=3
        assert "mag cal" not in msg

    def test_warns_when_magnetometer_uncalibrated(
            self, bridge, tmp_path, monkeypatch, make_amcl_msg):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "c.json"))
        bridge._on_amcl_pose(make_amcl_msg(yaw=math.radians(45)))
        bridge.state["bno055_imu_hz"] = 10.0
        bridge.state["bno055_orient_yaw"] = 0.0
        bridge.state["diag_motor"] = {"imu_cal_mag": "1"}  # poor mag cal
        ok, _, msg = bridge.calibrate_yaw_offset()
        assert ok is True
        assert "mag cal = 1/3" in msg

    def test_offset_wraps_to_signed_half_revolution(
            self, bridge, tmp_path, monkeypatch, make_amcl_msg):
        """If AMCL says 170° and IMU says -170°, raw offset is 340° but
        should wrap to -20° to stay in the (-180, +180] convention."""
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "c.json"))
        bridge._on_amcl_pose(make_amcl_msg(yaw=math.radians(170)))
        bridge.state["bno055_imu_hz"] = 10.0
        bridge.state["bno055_orient_yaw"] = -170.0
        ok, offset, _ = bridge.calibrate_yaw_offset()
        assert ok is True
        assert offset == pytest.approx(-20.0, abs=0.01)


class TestGetMapYawFromImu:

    def test_none_when_no_calibration(self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "g.json"))
        assert bridge.get_map_yaw_from_imu_deg() is None

    def test_none_when_imu_silent(self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "g.json"))
        RosBridge._write_state_file({"map_yaw_offset_deg": 10.0})
        # bno055_imu_hz remains 0 — no current reading.
        assert bridge.get_map_yaw_from_imu_deg() is None

    def test_computes_yaw_with_offset(self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "g.json"))
        RosBridge._write_state_file({"map_yaw_offset_deg": 15.0})
        bridge.state["bno055_imu_hz"] = 10.0
        bridge.state["bno055_orient_yaw"] = 30.0
        # 30 + 15 = 45, no wrap needed.
        assert bridge.get_map_yaw_from_imu_deg() == pytest.approx(45.0)

    def test_wraps_to_signed(self, bridge, tmp_path, monkeypatch):
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "g.json"))
        RosBridge._write_state_file({"map_yaw_offset_deg": 50.0})
        bridge.state["bno055_imu_hz"] = 10.0
        bridge.state["bno055_orient_yaw"] = 170.0  # raw = 220 → -140
        assert bridge.get_map_yaw_from_imu_deg() == pytest.approx(-140.0)
