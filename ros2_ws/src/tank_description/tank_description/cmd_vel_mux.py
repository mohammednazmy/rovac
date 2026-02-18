#!/usr/bin/env python3
"""
cmd_vel Multiplexer with Obstacle Priority

Priority order (highest to lowest):
1. cmd_vel_obstacle - Emergency stop from obstacle detector (0.5s timeout)
2. cmd_vel_joy - Joystick commands (1.0s timeout)
3. cmd_vel_smoothed - Navigation commands (continuous)

The obstacle detector publishes zero-velocity Twist when danger is detected,
which immediately stops the robot regardless of other inputs.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class CmdVelMux(Node):
    def __init__(self):
        super().__init__("cmd_vel_mux")

        # Publisher to final cmd_vel
        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)

        # Subscribers (in priority order)
        self.obstacle_sub = self.create_subscription(
            Twist, "cmd_vel_obstacle", self.obstacle_callback, 10)
        self.joy_sub = self.create_subscription(
            Twist, "cmd_vel_joy", self.joy_callback, 10)
        self.nav_sub = self.create_subscription(
            Twist, "cmd_vel_smoothed", self.nav_callback, 10)

        # Timeouts
        self.obstacle_timeout = 0.5  # Short timeout - emergency stop
        self.joy_timeout = 1.0       # Medium timeout - manual control

        # Timestamps
        now = self.get_clock().now()
        self.last_obstacle_time = now
        self.last_joy_time = now

        # Last received commands
        self.last_obstacle_cmd = Twist()
        self.last_joy_cmd = Twist()
        self.last_nav_cmd = Twist()

        # Track if obstacle stop is active
        self.obstacle_active = False

        # Publish at 20Hz
        self.timer = self.create_timer(0.05, self.publish_cmd)

        self.get_logger().info("cmd_vel_mux with OBSTACLE PRIORITY ready")
        self.get_logger().info("Priority: obstacle > joystick > navigation")

    def obstacle_callback(self, msg):
        """Handle emergency stop from obstacle detector"""
        self.last_obstacle_cmd = msg
        self.last_obstacle_time = self.get_clock().now()

        # Check if this is an emergency stop (zero velocity)
        is_stop = (abs(msg.linear.x) < 0.01 and
                   abs(msg.linear.y) < 0.01 and
                   abs(msg.angular.z) < 0.01)

        if is_stop and not self.obstacle_active:
            self.get_logger().warn("OBSTACLE EMERGENCY STOP activated!")
            self.obstacle_active = True
        elif not is_stop and self.obstacle_active:
            self.get_logger().info("Obstacle cleared, resuming normal operation")
            self.obstacle_active = False

        # Immediately publish obstacle command for fastest response
        self.cmd_pub.publish(msg)

    def joy_callback(self, msg):
        """Handle joystick commands"""
        self.last_joy_cmd = msg
        self.last_joy_time = self.get_clock().now()

        # Only publish immediately if no active obstacle stop
        now = self.get_clock().now()
        obstacle_elapsed = (now - self.last_obstacle_time).nanoseconds / 1e9

        if obstacle_elapsed >= self.obstacle_timeout:
            self.cmd_pub.publish(msg)

    def nav_callback(self, msg):
        """Handle navigation commands"""
        self.last_nav_cmd = msg

    def publish_cmd(self):
        """Periodic command publication with priority logic"""
        now = self.get_clock().now()
        obstacle_elapsed = (now - self.last_obstacle_time).nanoseconds / 1e9
        joy_elapsed = (now - self.last_joy_time).nanoseconds / 1e9

        # Priority 1: Obstacle emergency stop
        if obstacle_elapsed < self.obstacle_timeout:
            self.cmd_pub.publish(self.last_obstacle_cmd)
            return

        # Clear obstacle active flag if timeout expired
        if self.obstacle_active:
            self.obstacle_active = False
            self.get_logger().info("Obstacle timeout expired, resuming control")

        # Priority 2: Joystick control
        if joy_elapsed < self.joy_timeout:
            self.cmd_pub.publish(self.last_joy_cmd)
            return

        # Priority 3: Navigation
        self.cmd_pub.publish(self.last_nav_cmd)


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelMux()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
