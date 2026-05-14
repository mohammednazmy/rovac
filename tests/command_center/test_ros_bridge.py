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


# ════════════════════════════════════════════════════════════════════════
# _run — rclpy spin-loop wrapper (uses fake_rclpy fixture)
# ════════════════════════════════════════════════════════════════════════
#
# These tests verify the subscription/publisher wiring inside _run() by
# letting the function run end-to-end against a fake rclpy hierarchy. The
# fake's `rclpy.spin` returns immediately (real spin blocks forever), so
# _run() completes after wiring everything up.

class TestRunSubscriptions:

    # Every topic _run subscribes to, with the bridge method it routes to.
    EXPECTED_SUBSCRIPTIONS = {
        "/odom": "_on_odom",
        "/scan": "_on_scan",
        "/map": "_on_map",
        "/diagnostics": "_on_diagnostics",
        "/rovac/edge/health": "_on_edge_health",
        "/sensors/ultrasonic/front": "_on_range",  # via lambda
        "/sensors/ultrasonic/rear": "_on_range",
        "/sensors/ultrasonic/left": "_on_range",
        "/sensors/ultrasonic/right": "_on_range",
        "/sensors/cliff/detected": "_on_cliff",
        "/cmd_vel": "_on_cmd_vel_out",
        "/cmd_vel_teleop": "_tick_pipeline",     # via lambda
        "/cmd_vel_joy": "_tick_pipeline",
        "/cmd_vel_smoothed": "_tick_pipeline",
        "/cmd_vel_mux/active": "_on_mux_active",
        "/coverage_path": "_on_coverage_path",
        "/coverage/visited": "_on_coverage_visited",
        "/amcl_pose": "_on_amcl_pose",
        "/imu/data": "_on_bno055_imu",
        "/rosout": "_on_rosout",
    }

    def test_init_and_node_created(self, fake_rclpy):
        b = RosBridge()
        b._run()
        fake_rclpy.init.assert_called_once()
        assert len(fake_rclpy.created_nodes) == 1
        node = fake_rclpy.created_nodes[0]
        assert node.name == "rovac_command_center"

    def test_spin_invoked(self, fake_rclpy):
        b = RosBridge()
        b._run()
        # The fake spin returns immediately. Verify it WAS called with the
        # node so we know the wiring completed and spin would have started.
        fake_rclpy.spin.assert_called_once()
        assert fake_rclpy.spin.call_args.args[0] is fake_rclpy.created_nodes[0]

    def test_ros_connected_flips_true_after_setup(self, fake_rclpy):
        b = RosBridge()
        assert b.state["ros_connected"] is False
        b._run()
        assert b.state["ros_connected"] is True

    def test_all_expected_topics_subscribed(self, fake_rclpy):
        b = RosBridge()
        b._run()
        topics = {s.topic for s in fake_rclpy.created_nodes[0].subscriptions}
        missing = set(self.EXPECTED_SUBSCRIPTIONS) - topics
        assert not missing, f"Missing subscriptions: {missing}"

    def test_cmd_vel_teleop_publisher_created(self, fake_rclpy):
        b = RosBridge()
        b._run()
        pubs = fake_rclpy.created_nodes[0].publishers
        teleop_pubs = [p for p in pubs if p.topic == "/cmd_vel_teleop"]
        assert len(teleop_pubs) == 1
        # Bridge stores reference for publish_cmd_vel to use
        assert b._pub_cmd_vel is teleop_pubs[0]

    def test_log_message_recorded(self, fake_rclpy):
        b = RosBridge()
        b._run()
        logs = b.get_logs()
        # The bridge logs 'ROS2 bridge connected' on successful wire-up
        assert any("connected" in msg.lower() for _, msg in logs)

    def test_exception_during_setup_marks_disconnected(
            self, fake_rclpy, monkeypatch):
        """If anything in _run blows up (e.g. rclpy.init fails), the
        exception handler logs the error and leaves ros_connected=False."""
        fake_rclpy.init.side_effect = RuntimeError("rclpy refused to init")
        b = RosBridge()
        b._run()  # must not raise
        assert b.state["ros_connected"] is False
        logs = b.get_logs()
        assert any("ROS2 error" in msg for _, msg in logs)


class TestRunQoSProfiles:
    """Verify each subscription uses the right QoS reliability — the
    most common QoS-mismatch bug is best-effort publisher with reliable
    subscriber (or vice versa) silently dropping messages."""

    @pytest.mark.parametrize("topic,want_reliability", [
        ("/odom", "best_effort"),         # sensor data
        ("/scan", "best_effort"),
        ("/imu/data", "best_effort"),
        ("/diagnostics", "best_effort"),
        ("/cmd_vel_teleop", "reliable"),  # control commands
        ("/cmd_vel_joy", "reliable"),
        ("/cmd_vel_smoothed", "reliable"),
        ("/cmd_vel_mux/active", "reliable"),
        ("/amcl_pose", "reliable"),
        ("/rosout", "reliable"),
        ("/coverage_path", "reliable"),
        ("/coverage/visited", "reliable"),
    ])
    def test_topic_uses_expected_reliability(self, fake_rclpy, topic,
                                              want_reliability):
        b = RosBridge()
        b._run()
        subs = {s.topic: s for s in fake_rclpy.created_nodes[0].subscriptions}
        assert topic in subs
        # QoSProfile is a SimpleNamespace of its kwargs
        actual = subs[topic].qos.reliability
        assert actual == want_reliability

    def test_map_uses_transient_local_durability(self, fake_rclpy):
        """/map is published once at SLAM start with TRANSIENT_LOCAL so
        late-joining subscribers (us) still receive it."""
        b = RosBridge()
        b._run()
        subs = {s.topic: s for s in fake_rclpy.created_nodes[0].subscriptions}
        assert subs["/map"].qos.durability == "transient_local"

    def test_mux_active_uses_transient_local(self, fake_rclpy):
        """cmd_vel_mux publishes its source ONLY on transitions, not
        periodically. TRANSIENT_LOCAL means late-joiners get the latest
        value within a few ms instead of waiting for the next transition."""
        b = RosBridge()
        b._run()
        subs = {s.topic: s for s in fake_rclpy.created_nodes[0].subscriptions}
        assert subs["/cmd_vel_mux/active"].qos.durability == "transient_local"


class TestRunUltrasonicLambdas:
    """The 4 ultrasonic subscribers each pass a lambda binding `direction`."""

    @pytest.mark.parametrize("direction", ["front", "rear", "left", "right"])
    def test_lambda_routes_to_correct_direction_key(self, fake_rclpy,
                                                      direction):
        b = RosBridge()
        b._run()
        subs = {s.topic: s for s in fake_rclpy.created_nodes[0].subscriptions}
        sub = subs[f"/sensors/ultrasonic/{direction}"]
        # Invoke the callback with a fake Range message; should update the
        # right state key.
        sub.callback(SimpleNamespace(range=0.42))
        assert b.state[f"ultra_{direction}"] == 0.42


# ════════════════════════════════════════════════════════════════════════
# publish_initial_pose
# ════════════════════════════════════════════════════════════════════════

class TestPublishInitialPose:

    def test_returns_false_when_node_not_ready(self, fake_rclpy):
        """Before _run() has created the node, publish should silently
        return False — the UI calls this on user keypress and shouldn't
        crash if the bridge hasn't connected yet."""
        b = RosBridge()
        # _node is None — never ran _run
        assert b.publish_initial_pose(1, 2, 0.5) is False

    def test_creates_publisher_lazily_on_first_call(self, fake_rclpy):
        b = RosBridge()
        b._run()
        assert b._pub_initialpose is None  # not yet
        ok = b.publish_initial_pose(1.0, 2.0, 0.5)
        assert ok is True
        assert b._pub_initialpose is not None
        # Topic name and one published msg
        assert b._pub_initialpose.topic == "/initialpose"

    def test_reuses_publisher_on_subsequent_calls(self, fake_rclpy):
        b = RosBridge()
        b._run()
        b.publish_initial_pose(0, 0, 0)
        pub1 = b._pub_initialpose
        b.publish_initial_pose(1, 1, 0.5)
        pub2 = b._pub_initialpose
        assert pub1 is pub2

    def test_published_message_fields(self, fake_rclpy):
        b = RosBridge()
        b._run()
        b.publish_initial_pose(1.5, -2.0, math.pi / 2,
                                xy_covar=0.5, yaw_covar=0.25)
        msg = b._pub_initialpose.published[-1]
        # Header
        assert msg.header.frame_id == "map"
        # Position
        assert msg.pose.pose.position.x == 1.5
        assert msg.pose.pose.position.y == -2.0
        # Orientation: yaw → quaternion (z = sin(yaw/2), w = cos(yaw/2))
        assert msg.pose.pose.orientation.z == pytest.approx(
            math.sin(math.pi / 4))
        assert msg.pose.pose.orientation.w == pytest.approx(
            math.cos(math.pi / 4))
        # Covariance: diag has xx, yy, yaw at indices 0, 7, 35
        assert msg.pose.covariance[0] == 0.5
        assert msg.pose.covariance[7] == 0.5
        assert msg.pose.covariance[35] == 0.25

    def test_log_records_published_pose(self, fake_rclpy):
        b = RosBridge()
        b._run()
        b.publish_initial_pose(1.0, 2.0, math.radians(45))
        logs = b.get_logs()
        published_logs = [m for _, m in logs if "/initialpose" in m]
        assert len(published_logs) == 1
        assert "1.00" in published_logs[0]
        assert "2.00" in published_logs[0]
        assert "45" in published_logs[0]


# ════════════════════════════════════════════════════════════════════════
# trigger_global_localization
# ════════════════════════════════════════════════════════════════════════

class TestTriggerGlobalLocalization:

    def test_returns_false_when_node_not_ready(self, fake_rclpy):
        b = RosBridge()
        assert b.trigger_global_localization() is False

    def test_dispatches_to_worker_thread(self, fake_rclpy):
        b = RosBridge()
        b._run()
        assert b.trigger_global_localization() is True
        # Worker thread is daemon; wait briefly for client creation
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if fake_rclpy.created_nodes[0].clients:
                break
            time.sleep(0.02)
        clients = fake_rclpy.created_nodes[0].clients
        assert len(clients) == 1
        assert clients[0].name == "/reinitialize_global_localization"

    def test_service_unavailable_logged(self, fake_rclpy, monkeypatch):
        """If wait_for_service returns False, log the failure rather than
        hanging."""
        b = RosBridge()
        b._run()
        node = fake_rclpy.created_nodes[0]
        # Wrap node.create_client so any client created has service_ready
        # forced to False — simulating the service not being reachable.
        original_create_client = node.create_client

        def unavailable_wrapper(srv_type, name):
            client = original_create_client(srv_type, name)
            client.service_ready = False
            return client
        monkeypatch.setattr(node, "create_client", unavailable_wrapper)

        b.trigger_global_localization()
        # Worker thread is daemon — wait briefly for the log line
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if any("unavailable" in m for _, m in b.get_logs()):
                break
            time.sleep(0.02)
        logs = b.get_logs()
        assert any("unavailable" in m for _, m in logs)

    def test_worker_exception_logged(self, fake_rclpy, monkeypatch):
        """If anything inside the worker raises (e.g. create_client itself
        explodes), the outer try/except in the worker catches it and logs
        'Global localization error'."""
        b = RosBridge()
        b._run()
        node = fake_rclpy.created_nodes[0]
        def boom(srv_type, name):
            raise RuntimeError("rclpy broke")
        monkeypatch.setattr(node, "create_client", boom)
        b.trigger_global_localization()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if any("Global localization error" in m for _, m in b.get_logs()):
                break
            time.sleep(0.02)
        logs = b.get_logs()
        assert any("Global localization error" in m for _, m in logs)


# ════════════════════════════════════════════════════════════════════════
# Coverage closers — Phase 8.6
# ════════════════════════════════════════════════════════════════════════

import threading as _threading


class TestHzRefreshLoop:

    def test_one_iteration_refreshes_state(self, bridge, monkeypatch):
        """The background _hz_refresh_loop polls each tracker's hz() and
        writes to state[*_hz]. Test by mocking the stop event to exit
        after one wait, then running the loop in the main thread."""
        # Pre-populate _hz with trackers that return distinct values
        class FixedHz:
            def __init__(self, v): self._v = v
            def hz(self): return self._v
        bridge._hz = {
            "odom": FixedHz(20.5),
            "cmd_vel": FixedHz(10.0),
        }
        # Arm the stop event after the first wait
        bridge._stop_hz_refresh = _threading.Event()
        original_wait = bridge._stop_hz_refresh.wait
        def fake_wait(timeout=None):
            bridge._stop_hz_refresh.set()
            return True
        bridge._stop_hz_refresh.wait = fake_wait  # type: ignore[assignment]
        # Run one iteration
        bridge._hz_refresh_loop()
        assert bridge.state["odom_hz"] == 20.5
        assert bridge.state["cmd_vel_hz"] == 10.0

    def test_exception_in_iteration_silently_continues(self, bridge,
                                                         monkeypatch):
        """If a tracker raises during the refresh, the except: pass at
        line 127 catches it and the loop continues."""
        class BrokenTracker:
            def hz(self):
                raise RuntimeError("tracker broke")
        bridge._hz = {"odom": BrokenTracker()}
        bridge._stop_hz_refresh = _threading.Event()
        bridge._stop_hz_refresh.wait = lambda timeout=None: (
            bridge._stop_hz_refresh.set() or True)  # type: ignore[assignment]
        bridge._hz_refresh_loop()  # must not raise


class TestStartLifecycle:

    def test_start_spawns_spin_thread_and_hz_refresh(self, bridge,
                                                       monkeypatch):
        """start() spawns both the spin daemon thread AND the hz refresh
        background thread. Use mocked threading.Thread to verify."""
        from unittest.mock import MagicMock
        from command_center import ros_bridge as rb_mod
        threads_made = []
        class FakeThread:
            def __init__(self, *, target, daemon, **k):
                threads_made.append((target, daemon))
            def start(self):
                pass
        monkeypatch.setattr(rb_mod.threading, "Thread", FakeThread)
        bridge.start()
        # Both _run and _hz_refresh_loop threads were created
        targets = [t.__name__ if hasattr(t, "__name__") else str(t)
                   for t, _d in threads_made]
        assert "_run" in targets
        assert "_hz_refresh_loop" in targets
        # _stop_hz_refresh event was created
        assert hasattr(bridge, "_stop_hz_refresh")


class TestStopLifecycle:

    def test_stop_handles_no_hz_refresh_attr(self, bridge):
        """stop() should not crash if _stop_hz_refresh was never created
        (i.e. start() was never called)."""
        bridge.stop()  # must not raise

    def test_stop_with_node_and_publisher_destroys_them(self, fake_rclpy):
        """When _node and _pub_cmd_vel exist, stop() calls destroy_publisher
        + destroy_node, then rclpy.shutdown."""
        b = RosBridge()
        b._run()  # creates node + cmd_vel publisher
        b._stop_hz_refresh = _threading.Event()
        node = b._node
        pub = b._pub_cmd_vel
        b.stop()
        # Stop event was set
        assert b._stop_hz_refresh.is_set()
        # Publisher destroyed
        assert pub not in node.publishers
        # Node destroyed flag set
        assert node.destroyed is True
        # rclpy.shutdown called
        fake_rclpy.shutdown.assert_called()

    def test_stop_swallows_destroy_publisher_exception(self, fake_rclpy,
                                                        monkeypatch):
        b = RosBridge()
        b._run()
        b._stop_hz_refresh = _threading.Event()
        def boom(pub):
            raise RuntimeError("destroy boom")
        monkeypatch.setattr(b._node, "destroy_publisher", boom)
        b.stop()  # must not raise

    def test_stop_swallows_node_destroy_exception(self, fake_rclpy,
                                                    monkeypatch):
        b = RosBridge()
        b._run()
        b._stop_hz_refresh = _threading.Event()
        def boom():
            raise RuntimeError("destroy_node boom")
        monkeypatch.setattr(b._node, "destroy_node", boom)
        b.stop()  # must not raise

    def test_stop_swallows_rclpy_shutdown_exception(self, fake_rclpy):
        b = RosBridge()
        b._run()
        b._stop_hz_refresh = _threading.Event()
        fake_rclpy.shutdown.side_effect = RuntimeError("shutdown boom")
        b.stop()  # must not raise

    def test_stop_skips_shutdown_when_not_ok(self, fake_rclpy):
        """When rclpy.ok() returns False (already shut down), skip shutdown."""
        b = RosBridge()
        b._run()
        b._stop_hz_refresh = _threading.Event()
        fake_rclpy.ok.return_value = False
        b.stop()
        # shutdown was NOT called
        fake_rclpy.shutdown.assert_not_called()

    def test_stop_skips_save_current_pose_exception(self, bridge,
                                                      monkeypatch):
        """The save_current_pose call is wrapped in suppress(Exception)."""
        def boom():
            raise RuntimeError("save boom")
        monkeypatch.setattr(bridge, "save_current_pose", boom)
        bridge.stop()  # must not raise

    def test_stop_skips_thread_join_when_no_thread(self, bridge):
        """If _thread is None (never started), the thread.is_alive +
        join steps are skipped."""
        bridge._thread = None
        bridge.stop()  # must not raise

    def test_stop_joins_alive_thread(self, bridge, monkeypatch):
        """When _thread.is_alive(), stop() joins it with a 2s timeout."""
        from unittest.mock import MagicMock
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        bridge._thread = fake_thread
        bridge.stop()
        fake_thread.join.assert_called_once_with(timeout=2.0)


class TestStatePersistenceDefensiveExcepts:

    def test_read_state_file_returns_empty_on_parse_error(self, tmp_path,
                                                            monkeypatch):
        """If the state file exists but is corrupted, _read_state_file
        catches the JSONDecodeError and returns empty dict."""
        bad = tmp_path / "state.json"
        bad.write_text("not valid json {")
        monkeypatch.setattr(RosBridge, "_STATE_FILE", str(bad))
        assert RosBridge._read_state_file() == {}

    def test_write_state_file_returns_false_on_io_error(self, monkeypatch):
        """If writing fails (e.g. permission denied), _write_state_file
        returns False instead of raising."""
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            "/nonexistent_dir_xyz/state.json")
        assert RosBridge._write_state_file({"x": 1}) is False

    def test_load_persisted_pose_returns_origin_on_parse_error(
            self, tmp_path, monkeypatch):
        """If saved pose values can't be coerced to float, fall back
        to (0, 0, 0) defaults rather than crashing."""
        bad = tmp_path / "state.json"
        bad.write_text('{"last_pose": {"x": "not_a_number"}}')
        monkeypatch.setattr(RosBridge, "_STATE_FILE", str(bad))
        # The float conversion will raise; outer try catches → (0,0,0)
        x, y, yaw = RosBridge.load_persisted_pose()
        assert (x, y, yaw) == (0.0, 0.0, 0.0)

    def test_load_yaw_offset_returns_none_on_parse_error(self, tmp_path,
                                                          monkeypatch):
        """If map_yaw_offset_deg can't be coerced to float, return None
        (treated as 'never calibrated')."""
        bad = tmp_path / "state.json"
        bad.write_text('{"map_yaw_offset_deg": "not_a_float"}')
        monkeypatch.setattr(RosBridge, "_STATE_FILE", str(bad))
        assert RosBridge.load_yaw_offset_deg() is None


class TestCalibrateYawWriteFailure:

    def test_write_failure_returns_failure_message(self, bridge,
                                                    monkeypatch,
                                                    make_amcl_msg):
        bridge._on_amcl_pose(make_amcl_msg(yaw=math.radians(45)))
        bridge.state["bno055_imu_hz"] = 10.0
        bridge.state["bno055_orient_yaw"] = 30.0
        # Make _write_state_file fail
        monkeypatch.setattr(RosBridge, "_write_state_file",
                            classmethod(lambda cls, updates: False))
        ok, offset, msg = bridge.calibrate_yaw_offset()
        assert ok is False
        assert "Failed to save" in msg


class TestCalibrateMagCalCoercion:

    def test_mag_cal_non_numeric_treated_as_zero(self, bridge, tmp_path,
                                                   monkeypatch,
                                                   make_amcl_msg):
        """If diag's imu_cal_mag field isn't numeric (corrupt diag), treat
        as 0 (worst calibration) and emit the warning."""
        monkeypatch.setattr(RosBridge, "_STATE_FILE",
                            str(tmp_path / "s.json"))
        bridge._on_amcl_pose(make_amcl_msg(yaw=math.radians(45)))
        bridge.state["bno055_imu_hz"] = 10.0
        bridge.state["bno055_orient_yaw"] = 30.0
        # Non-numeric mag_cal
        bridge.state["diag_motor"] = {"imu_cal_mag": "garbled"}
        ok, _, msg = bridge.calibrate_yaw_offset()
        assert ok is True
        # mag_cal was coerced to 0; warning fires
        assert "mag cal = 0/3" in msg


class TestOnMapNumpyFallback:

    def test_falls_back_to_python_sum_when_numpy_fails(self, bridge,
                                                         make_map_msg,
                                                         monkeypatch):
        """If numpy.frombuffer raises (e.g. malformed buffer in some
        edge case), _on_map falls back to a Python sum loop."""
        msg = make_map_msg([0, 0, 100, -1, 0], width=5, height=1)
        # Sabotage numpy import inside the function
        import sys, types
        # Inject a fake numpy that raises on frombuffer
        fake_numpy = types.ModuleType("numpy")
        def boom(*a, **k): raise RuntimeError("numpy broke")
        fake_numpy.frombuffer = boom
        fake_numpy.int8 = int  # placeholder
        monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
        bridge._on_map(msg)
        # Python fallback computes free_cells via sum-over-data
        assert bridge.state["coverage_free_cells"] == 3  # three 0s


class TestPublishInitialPoseExceptionPath:

    def test_exception_during_publish_logs_and_returns_false(
            self, fake_rclpy, monkeypatch):
        b = RosBridge()
        b._run()
        # Make create_publisher raise when publish_initial_pose tries
        def boom(*a, **k):
            raise RuntimeError("publisher creation broke")
        monkeypatch.setattr(b._node, "create_publisher", boom)
        ok = b.publish_initial_pose(1.0, 2.0, 0.5)
        assert ok is False
        logs = b.get_logs()
        assert any("publish failed" in m for _, m in logs)


class TestTickPipeline:

    def test_missing_key_returns_silently(self, bridge):
        """_tick_pipeline is called by the lambdas in _run. If somehow
        invoked with a key not in _hz (defensive), it returns without
        updating state."""
        bridge._tick_pipeline("nonexistent_topic")  # must not raise
        # State doesn't get a _hz entry for this key
        assert "nonexistent_topic_hz" not in bridge.state

    def test_known_key_ticks_tracker_and_updates_state(self, bridge):
        """Known keys (from __init__) get their tracker ticked and the
        state[*_hz] is updated to whatever hz() returns."""
        # Pre-existing key from __init__ — cmd_vel_teleop
        bridge._tick_pipeline("cmd_vel_teleop")
        # state[*_hz] was updated (likely 0.0 since only 1 tick)
        assert "cmd_vel_teleop_hz" in bridge.state


class TestOnCoverageVisitedException:

    def test_numpy_failure_swallowed(self, bridge, make_map_msg,
                                       monkeypatch):
        """If numpy parsing raises in _on_coverage_visited, the outer
        except swallows it — no state update, no crash."""
        msg = make_map_msg([100, -1, 0], width=3, height=1)
        import sys, types
        fake_numpy = types.ModuleType("numpy")
        def boom(*a, **k): raise RuntimeError("numpy broke")
        fake_numpy.frombuffer = boom
        fake_numpy.int8 = int
        monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
        bridge._on_coverage_visited(msg)  # must not raise

    def test_zero_free_total_doesnt_compute_pct(self, bridge, make_map_msg):
        """When free_total is 0 (no free cells AND no /map cache),
        coverage_pct is NOT computed — avoids ZeroDivisionError. The
        visited cells count is still recorded."""
        # Visited grid with only -1 (unknown) and 100 (visited) cells.
        # Without a /map setting coverage_free_cells, free_total = (arr != -1).sum() = 1
        # To force free_total=0, we need all cells to be -1 (unknown).
        # All cells -1: visited=0, free_total=0 → skip pct computation.
        msg = make_map_msg([-1, -1, -1], width=3, height=1)
        bridge._on_coverage_visited(msg)
        assert bridge.state["coverage_visited_cells"] == 0
        # coverage_pct was NOT set (free_total was 0, so the branch
        # skipped the assignment). State value remains absent or 0.
        assert "coverage_pct" not in bridge.state or \
               bridge.state.get("coverage_pct") == 0


class TestStopHzRefreshSetException:

    def test_stop_swallows_hz_refresh_set_exception(self, bridge,
                                                      monkeypatch):
        """If _stop_hz_refresh.set() raises (shouldn't happen, but
        defensive), the outer try/except at line 153 catches it."""
        # Install a _stop_hz_refresh that raises on set()
        from types import SimpleNamespace
        bridge._stop_hz_refresh = SimpleNamespace(
            set=lambda: (_ for _ in ()).throw(RuntimeError("set broke")))
        bridge.stop()  # must not raise
