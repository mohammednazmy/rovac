#!/usr/bin/env python3
"""
Obstacle Avoidance Node for ROVAC Robot
Implements reactive obstacle avoidance using fused sensor data
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool
import math


class ObstacleAvoidanceNode(Node):
    def __init__(self):
        super().__init__("obstacle_avoidance_node")

        # Parameters
        self.declare_parameter("min_distance", 0.4)
        self.declare_parameter("max_linear_speed", 0.3)
        self.declare_parameter("max_angular_speed", 1.0)
        self.declare_parameter("enable_avoidance", True)

        self.min_distance = self.get_parameter("min_distance").value
        self.max_linear_speed = self.get_parameter("max_linear_speed").value
        self.max_angular_speed = self.get_parameter("max_angular_speed").value
        self.enable_avoidance = self.get_parameter("enable_avoidance").value

        # State variables
        self.latest_scan = None
        self.avoidance_active = False
        self.last_avoidance_command = Twist()

        # Publishers
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_avoidance", 10)
        self.avoidance_status_pub = self.create_publisher(
            Bool, "/system/avoidance_active", 10
        )

        # Subscribers
        self.scan_sub = self.create_subscription(
            LaserScan, "/sensors/fused_scan", self.scan_callback, 10
        )
        # Note: In a real implementation, you would also subscribe to cmd_vel commands
        # and modify them based on obstacle avoidance needs

        # Timer for continuous checking
        self.timer = self.create_timer(0.1, self.check_for_obstacles)  # 10Hz

        self.get_logger().info("Obstacle Avoidance Node initialized")
        self.get_logger().info(f"Minimum distance threshold: {self.min_distance}m")

    def scan_callback(self, msg):
        """Callback for fused LIDAR scan data"""
        self.latest_scan = msg

    def detect_obstacles(self, scan_msg):
        """Detect obstacles in different sectors"""
        if scan_msg is None:
            return {}

        obstacles = {
            "front": False,
            "front_left": False,
            "front_right": False,
            "left": False,
            "right": False,
        }

        ranges = scan_msg.ranges
        angle = scan_msg.angle_min

        # Define sector boundaries (in radians)
        sectors = {
            "front": (-0.26, 0.26),  # -15 to 15 degrees
            "front_left": (-0.79, -0.26),  # -45 to -15 degrees
            "front_right": (0.26, 0.79),  # 15 to 45 degrees
            "left": (-2.36, -0.79),  # -135 to -45 degrees
            "right": (0.79, 2.36),  # 45 to 135 degrees
        }

        # Check each sector for obstacles
        for sector_name, (min_angle, max_angle) in sectors.items():
            sector_obstacle = False

            # Reset angle to beginning of scan
            angle = scan_msg.angle_min

            for i, range_val in enumerate(ranges):
                if (
                    angle >= min_angle
                    and angle <= max_angle
                    and range_val < self.min_distance
                    and range_val > scan_msg.range_min
                ):
                    sector_obstacle = True
                    break
                angle += scan_msg.angle_increment

            obstacles[sector_name] = sector_obstacle

        return obstacles

    def calculate_avoidance_velocity(self, obstacles):
        """Calculate velocity command to avoid obstacles"""
        cmd_vel = Twist()

        if not any(obstacles.values()):
            # No obstacles, no avoidance needed
            self.avoidance_active = False
            return cmd_vel

        self.avoidance_active = True

        # Reactive obstacle avoidance algorithm
        # Front obstacle - stop and turn
        if obstacles["front"]:
            cmd_vel.linear.x = 0.0
            # Turn away from side with more space
            if not obstacles["left"] and obstacles["right"]:
                cmd_vel.angular.z = self.max_angular_speed  # Turn left
            elif obstacles["left"] and not obstacles["right"]:
                cmd_vel.angular.z = -self.max_angular_speed  # Turn right
            else:
                # Random choice if both sides blocked
                cmd_vel.angular.z = self.max_angular_speed  # Turn left by default

        # Front-left obstacle - turn right
        elif obstacles["front_left"]:
            cmd_vel.linear.x = self.max_linear_speed * 0.5  # Slow forward
            cmd_vel.angular.z = -self.max_angular_speed * 0.7  # Turn right

        # Front-right obstacle - turn left
        elif obstacles["front_right"]:
            cmd_vel.linear.x = self.max_linear_speed * 0.5  # Slow forward
            cmd_vel.angular.z = self.max_angular_speed * 0.7  # Turn left

        # Side obstacles - proceed with caution
        else:
            cmd_vel.linear.x = self.max_linear_speed * 0.7  # Moderate speed
            if obstacles["left"]:
                cmd_vel.angular.z = -self.max_angular_speed * 0.3  # Slight right
            elif obstacles["right"]:
                cmd_vel.angular.z = self.max_angular_speed * 0.3  # Slight left

        self.last_avoidance_command = cmd_vel
        return cmd_vel

    def check_for_obstacles(self):
        """Main obstacle checking and avoidance function"""
        if not self.enable_avoidance or self.latest_scan is None:
            return

        # Detect obstacles in different sectors
        obstacles = self.detect_obstacles(self.latest_scan)

        # Calculate avoidance velocity
        avoidance_cmd = self.calculate_avoidance_velocity(obstacles)

        # Publish avoidance command if active
        if self.avoidance_active:
            self.cmd_vel_pub.publish(avoidance_cmd)
            self.get_logger().warn(
                f"Obstacle avoidance active: linear={avoidance_cmd.linear.x:.2f}, angular={avoidance_cmd.angular.z:.2f}"
            )

        # Publish avoidance status
        status_msg = Bool()
        status_msg.data = self.avoidance_active
        self.avoidance_status_pub.publish(status_msg)


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
