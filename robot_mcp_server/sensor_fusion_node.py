#!/usr/bin/env python3
"""
Sensor Fusion Node for ROVAC Robot
Combines LIDAR, ultrasonic, and IMU data for enhanced perception and navigation
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan, Range, Imu
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import Float32MultiArray
import numpy as np
import math
from collections import deque
import tf2_ros
from tf2_ros import TransformException


class SensorFusionNode(Node):
    def __init__(self):
        super().__init__("sensor_fusion_node")

        # Subscription callbacks
        self.latest_lidar = None
        self.latest_ultrasonic = None
        self.latest_imu = None
        self.latest_odom = None

        # Buffers for temporal filtering
        self.lidar_buffer = deque(maxlen=5)
        self.imu_buffer = deque(maxlen=10)

        # TF2 for coordinate transformations
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # Publishers
        self.fused_scan_pub = self.create_publisher(
            LaserScan, "/sensors/fused_scan", 10
        )
        self.obstacle_alert_pub = self.create_publisher(
            Twist, "/sensors/obstacle_alert", 10
        )
        self.fused_odom_pub = self.create_publisher(Odometry, "/odom/fused", 10)

        # Subscribers
        self.lidar_sub = self.create_subscription(
            LaserScan, "/scan", self.lidar_callback, 10
        )
        self.ultrasonic_sub = self.create_subscription(
            Range, "/sensors/ultrasonic/range", self.ultrasonic_callback, 10
        )
        self.imu_sub = self.create_subscription(
            Imu, "/sensors/imu", self.imu_callback, 10
        )
        self.odom_sub = self.create_subscription(
            Odometry, "/odom", self.odom_callback, 10
        )

        # Timer for fused data publishing
        self.timer = self.create_timer(0.1, self.publish_fused_data)  # 10Hz

        # Parameters
        self.declare_parameter("min_obstacle_distance", 0.3)
        self.min_obstacle_distance = self.get_parameter("min_obstacle_distance").value

        self.declare_parameter("fusion_enabled", True)
        self.fusion_enabled = self.get_parameter("fusion_enabled").value

        self.get_logger().info("Sensor Fusion Node initialized")
        self.get_logger().info(f"Min obstacle distance: {self.min_obstacle_distance}m")

    def lidar_callback(self, msg):
        """Callback for LIDAR data"""
        self.latest_lidar = msg
        self.lidar_buffer.append(msg)

    def ultrasonic_callback(self, msg):
        """Callback for ultrasonic sensor data"""
        self.latest_ultrasonic = msg

        # Immediate obstacle alert if too close
        if msg.range < self.min_obstacle_distance and msg.range > 0.01:
            alert_msg = Twist()
            alert_msg.linear.x = -0.2  # Emergency reverse
            alert_msg.angular.z = 0.0
            self.obstacle_alert_pub.publish(alert_msg)
            self.get_logger().warn(
                f"Obstacle detected at {msg.range:.2f}m - Emergency stop triggered"
            )

    def imu_callback(self, msg):
        """Callback for IMU data"""
        self.latest_imu = msg
        self.imu_buffer.append(msg)

    def odom_callback(self, msg):
        """Callback for odometry data"""
        self.latest_odom = msg

    def fuse_lidar_ultrasonic(self, lidar_scan, ultrasonic_range):
        """Fuse LIDAR and ultrasonic data for enhanced obstacle detection"""
        if lidar_scan is None:
            return None

        # Create a copy of the LIDAR scan
        fused_scan = LaserScan()
        fused_scan.header = lidar_scan.header
        fused_scan.angle_min = lidar_scan.angle_min
        fused_scan.angle_max = lidar_scan.angle_max
        fused_scan.angle_increment = lidar_scan.angle_increment
        fused_scan.time_increment = lidar_scan.time_increment
        fused_scan.scan_time = lidar_scan.scan_time
        fused_scan.range_min = lidar_scan.range_min
        fused_scan.range_max = lidar_scan.range_max

        # Copy ranges
        fused_ranges = list(lidar_scan.ranges)

        # If we have ultrasonic data, enhance front detection
        if ultrasonic_range is not None and ultrasonic_range.range > 0.01:
            # Find front-facing LIDAR points (approximately center 30 degrees)
            center_index = len(fused_ranges) // 2
            angle_span = int(30.0 / (lidar_scan.angle_increment * 180.0 / math.pi)) // 2

            start_idx = max(0, center_index - angle_span)
            end_idx = min(len(fused_ranges), center_index + angle_span)

            # Fuse ultrasonic data with LIDAR in the front sector
            for i in range(start_idx, end_idx):
                # Take the minimum of LIDAR and ultrasonic for safety
                if fused_ranges[i] > ultrasonic_range.range:
                    fused_ranges[i] = ultrasonic_range.range

        fused_scan.ranges = fused_ranges
        return fused_scan

    def integrate_imu_odom(self, odom_msg, imu_msg):
        """Integrate IMU data with odometry for improved positioning"""
        if odom_msg is None or imu_msg is None:
            return odom_msg

        # Create fused odometry message
        fused_odom = Odometry()
        fused_odom.header = odom_msg.header
        fused_odom.child_frame_id = odom_msg.child_frame_id
        fused_odom.pose = odom_msg.pose
        fused_odom.twist = odom_msg.twist

        # Enhance orientation with IMU data (simple complementary filter)
        # In a real implementation, this would be more sophisticated
        fused_odom.pose.pose.orientation = imu_msg.orientation

        return fused_odom

    def kalman_filter_ranges(self, scan_buffer):
        """Apply temporal filtering to LIDAR ranges"""
        if len(scan_buffer) < 2:
            return scan_buffer[-1] if scan_buffer else None

        # Simple moving average for demonstration
        # In practice, this would be a proper Kalman filter
        latest_scan = scan_buffer[-1]
        if latest_scan is None:
            return None

        filtered_scan = LaserScan()
        filtered_scan.header = latest_scan.header
        filtered_scan.angle_min = latest_scan.angle_min
        filtered_scan.angle_max = latest_scan.angle_max
        filtered_scan.angle_increment = latest_scan.angle_increment
        filtered_scan.time_increment = latest_scan.time_increment
        filtered_scan.scan_time = latest_scan.scan_time
        filtered_scan.range_min = latest_scan.range_min
        filtered_scan.range_max = latest_scan.range_max

        # Apply filtering to ranges
        num_scans = len(scan_buffer)
        ranges_sum = [0.0] * len(latest_scan.ranges)

        for scan in scan_buffer:
            if scan is not None and len(scan.ranges) == len(ranges_sum):
                for i, range_val in enumerate(scan.ranges):
                    ranges_sum[i] += range_val

        filtered_ranges = [r / num_scans for r in ranges_sum]
        filtered_scan.ranges = filtered_ranges

        return filtered_scan

    def publish_fused_data(self):
        """Publish fused sensor data"""
        if not self.fusion_enabled:
            return

        # Fuse LIDAR and ultrasonic data
        fused_scan = self.fuse_lidar_ultrasonic(
            self.latest_lidar, self.latest_ultrasonic
        )
        if fused_scan is not None:
            self.fused_scan_pub.publish(fused_scan)

        # Apply temporal filtering to LIDAR data
        if len(self.lidar_buffer) > 0:
            filtered_scan = self.kalman_filter_ranges(self.lidar_buffer)
            # Could publish filtered scan on a separate topic if needed

        # Integrate IMU with odometry
        fused_odom = self.integrate_imu_odom(self.latest_odom, self.latest_imu)
        if fused_odom is not None:
            self.fused_odom_pub.publish(fused_odom)

    def get_fused_obstacle_distances(self):
        """Get obstacle distances from fused sensor data"""
        obstacles = {}

        # From fused LIDAR scan
        if self.latest_lidar is not None:
            ranges = self.latest_lidar.ranges
            angle = self.latest_lidar.angle_min

            for i, range_val in enumerate(ranges):
                if (
                    range_val > self.latest_lidar.range_min
                    and range_val < self.latest_lidar.range_max
                ):
                    # Convert angle to direction labels
                    if abs(angle) < 0.26:  # ~15 degrees
                        direction = "front"
                    elif angle > 0.26 and angle < 1.05:  # ~15-60 degrees
                        direction = "front_right"
                    elif angle > 1.05:  # > 60 degrees
                        direction = "right"
                    elif angle < -0.26 and angle > -1.05:  # ~-15 to -60 degrees
                        direction = "front_left"
                    else:  # < -60 degrees
                        direction = "left"

                    if direction not in obstacles or range_val < obstacles[direction]:
                        obstacles[direction] = range_val

                angle += self.latest_lidar.angle_increment

        return obstacles


def main(args=None):
    rclpy.init(args=args)
    node = SensorFusionNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
