#!/usr/bin/env python3
"""
cmd_vel Multiplexer — Human Override Priority

Priority order (highest to lowest):
1. cmd_vel_joy      - Joystick / human driver (ALWAYS wins)
2. cmd_vel_obstacle - Obstacle avoidance (only blocks nav, never human)
3. cmd_vel_smoothed - Autonomous navigation (lowest priority)

Design principle: the human driver is always in control. Obstacle
avoidance only overrides autonomous navigation commands. When a human
is actively driving (joystick messages within timeout), obstacle
avoidance is ignored — the human takes responsibility.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class CmdVelMux(Node):
    def __init__(self):
        super().__init__("cmd_vel_mux")

        # Publisher to final cmd_vel
        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)

        # Subscribers
        self.joy_sub = self.create_subscription(
            Twist, "cmd_vel_joy", self.joy_callback, 10)
        self.obstacle_sub = self.create_subscription(
            Twist, "cmd_vel_obstacle", self.obstacle_callback, 10)
        self.nav_sub = self.create_subscription(
            Twist, "cmd_vel_smoothed", self.nav_callback, 10)

        # Timeouts (seconds)
        self.joy_timeout = 1.0       # Human control window
        self.obstacle_timeout = 0.5  # Obstacle stop window

        # Timestamps — initialize to epoch so nothing is "active" at start
        self.last_joy_time = self.get_clock().now()
        self.last_obstacle_time = self.get_clock().now()
        self._joy_ever_received = False
        self._obstacle_ever_received = False

        # Last received commands
        self.last_joy_cmd = Twist()
        self.last_obstacle_cmd = Twist()
        self.last_nav_cmd = Twist()

        # Logging state
        self._active_source = ""

        # Publish at 20Hz
        self.timer = self.create_timer(0.05, self.publish_cmd)

        self.get_logger().info("cmd_vel_mux ready — HUMAN OVERRIDE priority")
        self.get_logger().info("Priority: joystick > obstacle > navigation")

    def joy_callback(self, msg):
        """Human driver — highest priority, always forwarded immediately."""
        self.last_joy_cmd = msg
        self.last_joy_time = self.get_clock().now()
        self._joy_ever_received = True
        self.cmd_pub.publish(msg)

    def obstacle_callback(self, msg):
        """Obstacle avoidance — only effective when human is NOT driving."""
        self.last_obstacle_cmd = msg
        self.last_obstacle_time = self.get_clock().now()
        self._obstacle_ever_received = True

    def nav_callback(self, msg):
        """Autonomous navigation — lowest priority."""
        self.last_nav_cmd = msg

    def publish_cmd(self):
        """Periodic command publication with priority logic."""
        now = self.get_clock().now()

        joy_elapsed = (now - self.last_joy_time).nanoseconds / 1e9
        obstacle_elapsed = (now - self.last_obstacle_time).nanoseconds / 1e9

        # Priority 1: Human joystick (always wins)
        if self._joy_ever_received and joy_elapsed < self.joy_timeout:
            self.cmd_pub.publish(self.last_joy_cmd)
            if self._active_source != "joy":
                self._active_source = "joy"
                self.get_logger().info("Active source: JOYSTICK (human override)")
            return

        # Priority 2: Obstacle avoidance (only when human is NOT driving)
        if self._obstacle_ever_received and obstacle_elapsed < self.obstacle_timeout:
            self.cmd_pub.publish(self.last_obstacle_cmd)
            if self._active_source != "obstacle":
                self._active_source = "obstacle"
                self.get_logger().warn("Active source: OBSTACLE avoidance")
            return

        # Priority 3: Autonomous navigation
        self.cmd_pub.publish(self.last_nav_cmd)
        if self._active_source != "nav":
            self._active_source = "nav"
            self.get_logger().info("Active source: NAVIGATION")


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
