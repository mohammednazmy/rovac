#!/usr/bin/env python3
"""
PS2 Joy Mapper Node — Maps Hiwonder controller to ROVAC tank drive.

Runs on the Pi alongside joy_node. Subscribes to /joy (sensor_msgs/Joy)
and publishes drive commands on /cmd_vel_joy.

Controller: Hiwonder PS2-style (ShanWan ZD-V+ USB HID receiver)
  - Xbox-style face buttons: Y/B/A/X
  - Only LEFT stick is analog (right stick has click only)
  - D-Pad is digital axes (±1)
  - L1/R1 bumpers, L2/R2 triggers (all digital)

Button mapping (verified via live scan 2026-03-02):
  Index  Button
  0      Y (top face)
  1      B (right face)
  2      A (bottom face)
  3      X (left face)
  4      L1 (left bumper)
  5      R1 (right bumper)
  6      L2 (left trigger)
  7      R2 (right trigger)
  8      SELECT
  9      START
  10     L3 (left stick click)
  11     R3 (right stick click)
  12     (MODE — hardware toggle, not reported)

Axis mapping (verified via live scan 2026-03-02):
  Index  Input           Polarity
  0      Left Stick X    left=+1, right=-1 (inverted)
  1      Left Stick Y    up=+1, down=-1
  2      (unused — right stick not analog)
  3      (unused — right stick not analog)
  4      D-Pad X         left=+1, right=-1
  5      D-Pad Y         up=+1, down=-1

Controls:
  Left Stick:    Drive (analog — Y=forward/back, X=turn)
  D-Pad:         Drive (digital — Up/Down=fwd/back, Left/Right=turn)
  R2 (hold):     Forward at current speed
  L2 (hold):     Reverse at current speed
  R1 (hold):     Turn right
  L1 (hold):     Turn left
  Y (press):     Cycle speed mode: SLOW(30%) → MED(60%) → FAST(90%) → MAX(100%)
  A (press):     Emergency stop (zero all motor output)

  Default speed: 100% (MAX)

Motor driver: ESP32-S3 + AT8236 via /cmd_vel
  - max_linear_speed=0.5 → M 255 (full motor power)
  - max_angular_speed=3.0 → full differential turn
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Joy
from geometry_msgs.msg import Twist
import time


# --- Button indices (verified live scan 2026-03-02) ---
BTN_Y = 0
BTN_B = 1
BTN_A = 2
BTN_X = 3
BTN_L1 = 4
BTN_R1 = 5
BTN_L2 = 6
BTN_R2 = 7
BTN_SELECT = 8
BTN_START = 9
BTN_L3 = 10
BTN_R3 = 11

# --- Axis indices (verified live scan 2026-03-02) ---
AXIS_LSTICK_X = 0   # left=+1, right=-1 (inverted from standard)
AXIS_LSTICK_Y = 1   # up=+1, down=-1
AXIS_DPAD_X = 4     # left=+1, right=-1
AXIS_DPAD_Y = 5     # up=+1, down=-1


class PS2JoyMapper(Node):
    def __init__(self):
        super().__init__("ps2_joy_mapper")

        # Speed modes: cycle with Y button
        self.SPEED_MODES = [30, 60, 90, 100]
        self.SPEED_NAMES = ["SLOW (30%)", "MED (60%)", "FAST (90%)", "MAX (100%)"]
        self.speed_mode_index = 3  # Start at MAX (100%)
        self.speed_percent = self.SPEED_MODES[self.speed_mode_index]

        # Drive parameters — matched to ESP32 AT8236 driver limits
        # Driver: max_linear_speed=0.5 → M 255, max_angular_speed=6.5
        # Pure turn math: motor_cmd = angular * wheel_sep/2 * scale
        #   scale = 255/0.5 = 510, wheel_sep = 0.155m
        #   angular=6.5 → 6.5 * 0.0775 * 510 = 256.9 → M 255 (full power)
        self.linear_max = 0.5    # linear.x value for full motor power
        self.angular_max = 6.5   # angular.z value for full turn power

        # Stick config
        self.stick_deadzone = 0.25  # PS2 sticks drift up to ±0.19

        # Button edge detection + cooldown
        self.last_button_states = {}
        self.button_cooldowns = {}
        self.BUTTON_COOLDOWN = 0.3

        # Rate limiting for cmd_vel (prevents motor jitter)
        self.cmd_vel_rate_hz = 20.0
        self.cmd_vel_interval = 1.0 / self.cmd_vel_rate_hz
        self.last_cmd_vel_time = 0.0
        self.pending_twist = None

        # Wireless dropout filter — the ShanWan PS2 receiver drops signal
        # briefly (~50-150ms), causing zero-axis reports mid-drive. Hold the
        # last non-zero command for up to 200ms before accepting a zero.
        self.dropout_hold_sec = 0.2
        self.last_nonzero_twist = None
        self.last_nonzero_time = 0.0

        # Emergency stop state
        self.e_stopped = False

        # Publishers
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_joy", 10)

        # Subscriber
        self.create_subscription(Joy, "/joy", self.joy_callback, 10)

        # Timer to flush pending cmd_vel
        self.create_timer(self.cmd_vel_interval, self.flush_pending_cmd_vel)

        self.get_logger().info("PS2 Joy Mapper started (v2.0)")
        self.get_logger().info(f"  Speed: {self.SPEED_NAMES[self.speed_mode_index]}")
        self.get_logger().info(f"  cmd_vel rate: {self.cmd_vel_rate_hz} Hz")
        self.get_logger().info("Controls:")
        self.get_logger().info("  Left Stick : Drive (analog)")
        self.get_logger().info("  D-Pad      : Drive (digital)")
        self.get_logger().info("  L2/R2      : Reverse / Forward")
        self.get_logger().info("  L1/R1      : Turn left / right")
        self.get_logger().info("  Y          : Cycle speed mode")
        self.get_logger().info("  A          : Emergency stop")

    # ─── Helpers ───────────────────────────────────────────────

    def apply_deadzone(self, value, deadzone):
        """Apply deadzone and rescale to full range."""
        if abs(value) < deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - deadzone) / (1.0 - deadzone)

    def button_pressed(self, btn_id, buttons):
        """Return True on rising edge (0→1) with cooldown debounce."""
        if btn_id >= len(buttons):
            return False
        current = buttons[btn_id]
        previous = self.last_button_states.get(btn_id, 0)
        self.last_button_states[btn_id] = current
        now = time.time()
        if btn_id in self.button_cooldowns:
            if now - self.button_cooldowns[btn_id] < self.BUTTON_COOLDOWN:
                return False
        if current == 1 and previous == 0:
            self.button_cooldowns[btn_id] = now
            return True
        return False

    def button_held(self, btn_id, buttons):
        """Return True while button is held down."""
        if btn_id >= len(buttons):
            return False
        return buttons[btn_id] == 1

    def publish_cmd_vel(self, twist):
        """Rate-limited cmd_vel with wireless dropout filtering."""
        now = time.time()
        is_zero = abs(twist.linear.x) < 0.01 and abs(twist.angular.z) < 0.01

        if not is_zero:
            # Non-zero command — update hold state and publish
            self.last_nonzero_twist = twist
            self.last_nonzero_time = now
        elif self.last_nonzero_twist is not None:
            # Zero command but we were driving recently — check hold period
            if now - self.last_nonzero_time < self.dropout_hold_sec:
                # Within hold period — substitute last non-zero command
                twist = self.last_nonzero_twist
            else:
                # Hold expired — accept the zero (user actually released)
                self.last_nonzero_twist = None

        self.pending_twist = twist
        if now - self.last_cmd_vel_time >= self.cmd_vel_interval:
            self.cmd_vel_pub.publish(twist)
            self.last_cmd_vel_time = now
            self.pending_twist = None

    def flush_pending_cmd_vel(self):
        """Timer callback — publish any pending cmd_vel."""
        if self.pending_twist is not None:
            self.cmd_vel_pub.publish(self.pending_twist)
            self.last_cmd_vel_time = time.time()
            self.pending_twist = None

    # ─── Main callback ────────────────────────────────────────

    def joy_callback(self, msg):
        axes = msg.axes
        buttons = msg.buttons

        if len(axes) < 6 or len(buttons) < 10:
            return

        # === A: Emergency stop ===
        if self.button_pressed(BTN_A, buttons):
            self.e_stopped = not self.e_stopped
            if self.e_stopped:
                self.get_logger().warn("EMERGENCY STOP activated! Press A again to resume.")
                self.publish_cmd_vel(Twist())
                return
            else:
                self.get_logger().info("Emergency stop released. Driving enabled.")

        if self.e_stopped:
            self.publish_cmd_vel(Twist())
            return

        # === Y: Cycle speed mode ===
        if self.button_pressed(BTN_Y, buttons):
            self.speed_mode_index = (self.speed_mode_index + 1) % len(self.SPEED_MODES)
            self.speed_percent = self.SPEED_MODES[self.speed_mode_index]
            self.get_logger().info(f"Speed: {self.SPEED_NAMES[self.speed_mode_index]}")

        speed_ratio = self.speed_percent / 100.0

        # Build drive command from all inputs
        twist = Twist()
        has_button_drive = False

        # === Triggers: R2=forward, L2=reverse ===
        if self.button_held(BTN_R2, buttons):
            twist.linear.x = self.linear_max * speed_ratio
            has_button_drive = True
        if self.button_held(BTN_L2, buttons):
            twist.linear.x = -self.linear_max * speed_ratio
            has_button_drive = True

        # === Bumpers: L1=turn left, R1=turn right ===
        if self.button_held(BTN_L1, buttons):
            twist.angular.z = self.angular_max * speed_ratio
            has_button_drive = True
        if self.button_held(BTN_R1, buttons):
            twist.angular.z = -self.angular_max * speed_ratio
            has_button_drive = True

        # === D-Pad drive (digital, full speed) ===
        dpad_y = axes[AXIS_DPAD_Y]  # up=+1, down=-1
        dpad_x = axes[AXIS_DPAD_X]  # left=+1, right=-1

        has_dpad_drive = abs(dpad_y) > 0.5 or abs(dpad_x) > 0.5

        if has_dpad_drive and not has_button_drive:
            if dpad_y > 0.5:
                twist.linear.x = self.linear_max * speed_ratio
            elif dpad_y < -0.5:
                twist.linear.x = -self.linear_max * speed_ratio
            # D-pad left=+1 should turn left (positive angular.z)
            if dpad_x > 0.5:
                twist.angular.z = self.angular_max * speed_ratio
            elif dpad_x < -0.5:
                twist.angular.z = -self.angular_max * speed_ratio

        # === Left stick drive (analog, proportional) ===
        if not has_button_drive and not has_dpad_drive:
            # Axis polarity: Y up=+1 (forward), X left=+1/right=-1
            stick_y = self.apply_deadzone(axes[AXIS_LSTICK_Y], self.stick_deadzone)
            stick_x = self.apply_deadzone(axes[AXIS_LSTICK_X], self.stick_deadzone)

            # stick_y positive = forward = positive linear.x (correct)
            twist.linear.x = stick_y * self.linear_max * speed_ratio
            # stick_x positive = left = positive angular.z (turn left, correct)
            twist.angular.z = stick_x * self.angular_max * speed_ratio

        # Always publish — zero twist when idle ensures reliable stopping
        self.publish_cmd_vel(twist)


def main(args=None):
    rclpy.init(args=args)
    node = PS2JoyMapper()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
