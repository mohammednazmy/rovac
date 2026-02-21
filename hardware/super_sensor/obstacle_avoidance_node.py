#!/usr/bin/env python3
"""
Obstacle Avoidance Node for ROVAC
Integrates Super Sensor ultrasonic data with velocity control.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32MultiArray, Int32MultiArray
from sensor_msgs.msg import PointCloud2, PointField
import struct


class ObstacleAvoidanceNode(Node):
    """Obstacle avoidance using Super Sensor ultrasonic data."""

    SENSOR_POSITIONS = [
        (0.12, 0.0, 0.045),   # front_top
        (0.10, 0.03, 0.03),   # left
        (0.10, -0.03, 0.03),  # right
        (0.12, 0.0, 0.015),   # front_bottom
    ]
    
    SENSOR_DIRECTIONS = [
        (1.0, 0.0, 0.0),      # front_top: forward
        (0.0, 1.0, 0.0),      # left: left
        (0.0, -1.0, 0.0),     # right: right
        (1.0, 0.0, -0.1),     # front_bottom: forward/down
    ]

    def __init__(self):
        super().__init__("obstacle_avoidance_node")

        # Parameters
        self.declare_parameter("emergency_stop_distance", 0.15)
        self.declare_parameter("slow_down_distance", 0.40)
        self.declare_parameter("min_speed_factor", 0.3)
        self.declare_parameter("enable_costmap_points", True)
        self.declare_parameter("enable_led_feedback", True)

        self.emergency_stop_dist = self.get_parameter("emergency_stop_distance").value
        self.slow_down_dist = self.get_parameter("slow_down_distance").value
        self.min_speed_factor = self.get_parameter("min_speed_factor").value
        self.enable_costmap = self.get_parameter("enable_costmap_points").value
        self.enable_led = self.get_parameter("enable_led_feedback").value

        # State
        self.current_ranges = [float("inf")] * 4
        self.obstacle_detected = False
        self.emergency_stop = False

        # Subscribers
        self.ranges_sub = self.create_subscription(
            Float32MultiArray, "/super_sensor/ranges",
            self.ranges_callback, 10
        )
        
        # Publishers
        # Publish to /cmd_vel_obstacle so the mux can prioritize emergency stops
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_obstacle", 10)
        
        if self.enable_costmap:
            self.points_pub = self.create_publisher(
                PointCloud2, "/super_sensor/obstacle_points", 10
            )

        if self.enable_led:
            self.led_pub = self.create_publisher(
                Int32MultiArray, "/super_sensor/led_cmd", 10
            )

        # Timer for status updates
        self.create_timer(0.1, self.update_callback)

        self.get_logger().info("Obstacle Avoidance Node initialized")
        self.get_logger().info(f"  Emergency stop: {self.emergency_stop_dist}m")
        self.get_logger().info(f"  Slow down: {self.slow_down_dist}m")

    def ranges_callback(self, msg):
        """Update current range readings."""
        if len(msg.data) >= 4:
            self.current_ranges = list(msg.data[:4])
            
            # Check for obstacles
            valid_ranges = [r for r in self.current_ranges if 0 < r < float("inf")]
            if valid_ranges:
                min_range = min(valid_ranges)
                self.emergency_stop = min_range < self.emergency_stop_dist
                self.obstacle_detected = min_range < self.slow_down_dist
            else:
                self.emergency_stop = False
                self.obstacle_detected = False

            # Publish point cloud for costmap
            if self.enable_costmap:
                self.publish_obstacle_points()

    def publish_obstacle_points(self):
        """Publish ultrasonic readings as PointCloud2 for costmap."""
        points = []
        
        for pos, direction, range_m in zip(
            self.SENSOR_POSITIONS, self.SENSOR_DIRECTIONS, self.current_ranges
        ):
            if range_m <= 0 or range_m >= 5.0:
                continue
            
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

    def update_callback(self):
        """Periodic safety check: publish zero velocity on emergency stop."""
        if self.emergency_stop:
            self.cmd_vel_pub.publish(Twist())

        if self.enable_led:
            led_msg = Int32MultiArray()
            
            if self.emergency_stop:
                led_msg.data = [255, 0, 0]  # Red
            elif self.obstacle_detected:
                valid = [r for r in self.current_ranges if 0 < r < float("inf")]
                if valid:
                    min_r = min(valid)
                    intensity = int(255 * (1 - min_r / self.slow_down_dist))
                    led_msg.data = [intensity, intensity // 2, 0]  # Orange
                else:
                    led_msg.data = [0, 20, 0]
            else:
                led_msg.data = [0, 20, 0]  # Dim green
            
            self.led_pub.publish(led_msg)


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
