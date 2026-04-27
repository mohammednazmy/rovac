#!/usr/bin/env python3
"""
Obstacle Avoidance Node for ROVAC — Sensor Hub Edition

Subscribes to 4x ultrasonic Range + cliff detected Bool from the ESP32
sensor hub, publishes zero-velocity Twist on emergency stop or cliff
detection, and obstacle PointCloud2 for Nav2 costmap integration.

Replaces the legacy super_sensor obstacle_avoidance_node.py.
"""

import struct
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Range, PointCloud2, PointField
from std_msgs.msg import Bool


class ObstacleAvoidanceNode(Node):
    """Obstacle avoidance using sensor hub ultrasonic + cliff data."""

    # Sensor mounting positions relative to base_link (meters).
    # Measured 2026-04-20 after physical mounting on Yahboom G1 Tank chassis.
    #
    # min_valid: per-sensor floor for accepting a reading. Anything below
    # this is filtered out (treated as no obstacle). The front sensor sits
    # 4cm above the floor with a 30° forward cone; geometrically the floor
    # enters its cone at ~14cm, so any reading <13cm is floor-bounce, not
    # a real obstacle. Without this filter the floor reading triggered
    # permanent emergency stop. Tune per-sensor based on its mount.
    SENSOR_CONFIG = {
        "front": {"pos": (0.250, 0.0, 0.04), "dir": (1.0, 0.0, 0.0),
                  "min_valid": 0.13},
        "rear":  {"pos": (-0.115, 0.0, 0.04), "dir": (-1.0, 0.0, 0.0),
                  "min_valid": 0.05},
        "left":  {"pos": (0.0, 0.067, 0.04), "dir": (0.0, 1.0, 0.0),
                  "min_valid": 0.05},
        "right": {"pos": (0.0, -0.067, 0.04), "dir": (0.0, -1.0, 0.0),
                  "min_valid": 0.05},
    }

    def __init__(self):
        super().__init__("obstacle_avoidance_node")

        # Parameters
        self.declare_parameter("emergency_stop_distance", 0.15)
        self.declare_parameter("slow_down_distance", 0.40)
        self.declare_parameter("enable_costmap_points", True)

        self.emergency_stop_dist = self.get_parameter("emergency_stop_distance").value
        self.slow_down_dist = self.get_parameter("slow_down_distance").value
        self.enable_costmap = self.get_parameter("enable_costmap_points").value

        # State
        self.us_ranges = {"front": float("inf"), "rear": float("inf"),
                          "left": float("inf"), "right": float("inf")}
        self.cliff_detected = False
        self.emergency_stop = False

        # Subscribe to sensor hub ultrasonic Range topics
        reliable_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        self.create_subscription(
            Range, "/sensors/ultrasonic/front",
            lambda msg: self._us_callback("front", msg), reliable_qos)
        self.create_subscription(
            Range, "/sensors/ultrasonic/rear",
            lambda msg: self._us_callback("rear", msg), reliable_qos)
        self.create_subscription(
            Range, "/sensors/ultrasonic/left",
            lambda msg: self._us_callback("left", msg), reliable_qos)
        self.create_subscription(
            Range, "/sensors/ultrasonic/right",
            lambda msg: self._us_callback("right", msg), reliable_qos)

        # Subscribe to cliff detection
        self.create_subscription(
            Bool, "/sensors/cliff/detected",
            self._cliff_callback, reliable_qos)

        # Publisher: zero-velocity emergency stop via mux
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_obstacle", 10)

        # Publisher: obstacle points for Nav2 costmap
        if self.enable_costmap:
            self.points_pub = self.create_publisher(
                PointCloud2, "/obstacle/points", 10)

        # 10 Hz safety check timer
        self.create_timer(0.1, self._safety_check)

        self.get_logger().info("Obstacle avoidance initialized (sensor hub edition)")
        self.get_logger().info(
            f"  Emergency stop: {self.emergency_stop_dist}m, "
            f"slow down: {self.slow_down_dist}m")

    def _us_callback(self, name: str, msg: Range):
        """Update ultrasonic range for a given sensor."""
        self.us_ranges[name] = msg.range

    def _cliff_callback(self, msg: Bool):
        """Update cliff detection state."""
        self.cliff_detected = msg.data

    def _safety_check(self):
        """Periodic safety evaluation — publish emergency stop if needed."""
        # Apply per-sensor min_valid filter so geometric artifacts (e.g.
        # floor-bounce on the front sensor) don't trip emergency stop.
        # Track WHICH sensor produced min_range so the log message tells
        # the user which physical sensor needs investigation.
        valid_ranges = []
        for name, r in self.us_ranges.items():
            min_valid = self.SENSOR_CONFIG[name].get("min_valid", 0.0)
            if min_valid <= r < float("inf"):
                valid_ranges.append((r, name))
        if valid_ranges:
            min_range, min_sensor = min(valid_ranges, key=lambda t: t[0])
        else:
            min_range, min_sensor = float("inf"), "none"
        us_emergency = min_range < self.emergency_stop_dist

        # Emergency stop on obstacle OR cliff
        self.emergency_stop = us_emergency or self.cliff_detected

        if self.emergency_stop:
            self.cmd_vel_pub.publish(Twist())  # Zero velocity
            if self.cliff_detected:
                self.get_logger().warning(
                    "CLIFF DETECTED — emergency stop active",
                    throttle_duration_sec=2.0)
            else:
                self.get_logger().warning(
                    f"OBSTACLE at {min_range:.2f}m on {min_sensor.upper()} "
                    f"sensor — emergency stop active",
                    throttle_duration_sec=2.0)

        # Publish obstacle points for costmap
        if self.enable_costmap:
            self._publish_obstacle_points()

    def _publish_obstacle_points(self):
        """Publish ultrasonic readings as PointCloud2 for Nav2 costmap."""
        points = []

        for name, config in self.SENSOR_CONFIG.items():
            range_m = self.us_ranges[name]
            min_valid = config.get("min_valid", 0.0)
            # Same filter as _safety_check — don't seed costmap with
            # geometric artifacts that would create phantom obstacles.
            if range_m < min_valid or range_m >= 4.0:
                continue

            pos = config["pos"]
            direction = config["dir"]
            x = pos[0] + direction[0] * range_m
            y = pos[1] + direction[1] * range_m
            z = pos[2] + direction[2] * range_m
            points.append((x, y, z))

        if not points:
            return

        msg = PointCloud2()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "base_link"
        msg.height = 1
        msg.width = len(points)
        msg.fields = [
            PointField(name="x", offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8, datatype=PointField.FLOAT32, count=1),
        ]
        msg.is_bigendian = False
        msg.point_step = 12
        msg.row_step = msg.point_step * len(points)
        msg.is_dense = True
        msg.data = b"".join(struct.pack("fff", *p) for p in points)

        self.points_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleAvoidanceNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
