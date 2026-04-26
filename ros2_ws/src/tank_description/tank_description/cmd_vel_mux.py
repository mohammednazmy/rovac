#!/usr/bin/env python3
"""
cmd_vel Multiplexer — Human Override Priority

Priority order (highest to lowest):
1. cmd_vel_teleop   - Keyboard teleop (same priority as joystick)
2. cmd_vel_joy      - Joystick / human driver
3. cmd_vel_obstacle - Obstacle avoidance (only blocks nav, never human)
4. cmd_vel_smoothed - Autonomous navigation (lowest priority)

Design principle: the human driver is always in control. Both keyboard
teleop and joystick are "human override" — whichever was active most
recently wins. Obstacle avoidance only overrides autonomous navigation
commands. When a human is actively driving, obstacle avoidance is
ignored — the human takes responsibility.

ALL velocity commands MUST go through this mux. Nothing else should
publish directly to /cmd_vel.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from std_msgs.msg import String


class CmdVelMux(Node):
    def __init__(self):
        super().__init__("cmd_vel_mux")

        # Publisher to final cmd_vel
        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)

        # Active-source publisher — latched, so any subscriber gets the
        # current state on connect. Used by the Command Center's Coverage
        # panel to show "active source: NAV" without scraping logs.
        active_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.active_pub = self.create_publisher(
            String, "cmd_vel_mux/active", active_qos)

        # Subscribers — human inputs (teleop + joy) at highest priority
        self.teleop_sub = self.create_subscription(
            Twist, "cmd_vel_teleop", self.teleop_callback, 10)
        self.joy_sub = self.create_subscription(
            Twist, "cmd_vel_joy", self.joy_callback, 10)
        self.obstacle_sub = self.create_subscription(
            Twist, "cmd_vel_obstacle", self.obstacle_callback, 10)
        self.nav_sub = self.create_subscription(
            Twist, "cmd_vel_smoothed", self.nav_callback, 10)

        # Timeouts (seconds)
        self.teleop_timeout = 0.5    # Keyboard teleop hold window
        self.joy_timeout = 1.0       # Joystick control window
        self.obstacle_timeout = 0.5  # Obstacle stop window
        self.nav_timeout = 1.0       # Nav command staleness window

        # Timestamps — initialize to epoch so nothing is "active" at start
        now = self.get_clock().now()
        self.last_teleop_time = now
        self.last_joy_time = now
        self.last_obstacle_time = now
        self.last_nav_time = now
        self._teleop_ever_received = False
        self._joy_ever_received = False
        self._obstacle_ever_received = False
        self._nav_ever_received = False

        # Last received commands
        self.last_teleop_cmd = Twist()
        self.last_joy_cmd = Twist()
        self.last_obstacle_cmd = Twist()
        self.last_nav_cmd = Twist()

        # Logging state
        self._active_source = ""

        # Publish at 20Hz
        self.timer = self.create_timer(0.05, self.publish_cmd)

        self.get_logger().info("cmd_vel_mux ready — HUMAN OVERRIDE priority")
        self.get_logger().info("Priority: joystick > obstacle > navigation")

    def teleop_callback(self, msg):
        """Keyboard teleop — highest priority, forwarded immediately."""
        self.last_teleop_cmd = msg
        self.last_teleop_time = self.get_clock().now()
        self._teleop_ever_received = True
        self.cmd_pub.publish(msg)

    def joy_callback(self, msg):
        """Joystick driver — same human-override tier, forwarded immediately."""
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
        self.last_nav_time = self.get_clock().now()
        self._nav_ever_received = True

    def _set_active(self, source: str):
        """Update active source label, log transitions, publish to topic."""
        if self._active_source == source:
            return
        self._active_source = source
        msg = {
            "teleop": ("TELEOP", "info"),
            "joy": ("JOYSTICK", "info"),
            "obstacle": ("OBSTACLE", "warn"),
            "nav": ("NAV", "info"),
            "idle": ("IDLE", "info"),
        }.get(source, (source.upper(), "info"))
        label, level = msg
        log = self.get_logger()
        line = f"Active source: {label}"
        if level == "warn":
            log.warn(line)
        else:
            log.info(line)
        # Publish so any subscriber (Command Center) sees it without
        # scraping logs.
        m = String()
        m.data = label
        self.active_pub.publish(m)

    def publish_cmd(self):
        """Periodic command publication with priority logic."""
        now = self.get_clock().now()

        teleop_elapsed = (now - self.last_teleop_time).nanoseconds / 1e9
        joy_elapsed = (now - self.last_joy_time).nanoseconds / 1e9
        obstacle_elapsed = (now - self.last_obstacle_time).nanoseconds / 1e9
        nav_elapsed = (now - self.last_nav_time).nanoseconds / 1e9

        # Priority 1: Keyboard teleop (human override — highest)
        if self._teleop_ever_received and teleop_elapsed < self.teleop_timeout:
            self.cmd_pub.publish(self.last_teleop_cmd)
            self._set_active("teleop")
            return

        # Priority 2: Joystick (human override)
        if self._joy_ever_received and joy_elapsed < self.joy_timeout:
            self.cmd_pub.publish(self.last_joy_cmd)
            self._set_active("joy")
            return

        # Priority 3: Obstacle avoidance (only when human is NOT driving)
        if self._obstacle_ever_received and obstacle_elapsed < self.obstacle_timeout:
            self.cmd_pub.publish(self.last_obstacle_cmd)
            self._set_active("obstacle")
            return

        # Priority 4: Autonomous navigation (only if fresh)
        if self._nav_ever_received and nav_elapsed < self.nav_timeout:
            self.cmd_pub.publish(self.last_nav_cmd)
            self._set_active("nav")
            return

        # No active source — don't publish anything.
        # The motor controller has its own watchdog (500ms cmd_vel timeout)
        # that safely stops the motors when commands stop arriving.
        self._set_active("idle")


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
