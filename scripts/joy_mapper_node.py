#!/usr/bin/env python3
"""
Joy Mapper Node - Maps Nintendo Pro Controller inputs to robot functions.

macOS SDL Mapping (Nintendo Pro Controller via Bluetooth):
  Axes:
    0: Left Stick X (left=-1, right=+1)
    1: Left Stick Y (up=+1, down=-1) - NOTE: inverted from typical
    2: Right Stick X
    3: Right Stick Y
    4/5: Often ZL/ZR analog triggers (rest ~+1.0, pressed toward -1.0)
    6/7: Often D-Pad hat axes (rest 0.0, pressed to -1/1)

  Buttons (macOS SDL):
    0: B (East)
    1: A (South)
    2: X (North)
    3: Y (West)
    4: L (Left Bumper)
    5: R (Right Bumper)
    6: ZL (Left Trigger click) - may not be present
    7: ZR (Right Trigger click) - may not be present
    8: - (Minus/Select)
    9: + (Plus/Start)
    10: L3 (Left Stick click)
    11: R3 (Right Stick click)
    12: Home
    13: Capture

Note: SDL mappings vary; this node infers trigger/D-pad axes from the first
neutral ("rest") Joy message and falls back to digital trigger buttons.
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Joy
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32MultiArray, Int32MultiArray, Int32, Bool
import time
import platform


class JoyMapperNode(Node):
    def __init__(self):
        super().__init__("joy_mapper")

        # Detect platform for button mapping
        self.is_macos = platform.system() == "Darwin"

        # LED color states: [R, G, B] - each 0 or 1
        self.LED_COLORS = [
            [0, 0, 0],  # Off
            [1, 0, 0],  # Red
            [0, 1, 0],  # Green
            [0, 0, 1],  # Blue
            [1, 1, 0],  # Yellow
            [1, 0, 1],  # Magenta
            [0, 1, 1],  # Cyan
            [1, 1, 1],  # White
        ]
        self.led_color_index = 0
        self.led_intensity_index = 1  # Start with on

        # Speed control
        self.SPEED_MODES = [30, 100, 100]
        self.speed_mode_index = 1
        self.speed_percent = self.SPEED_MODES[self.speed_mode_index]
        self.speed_step = 10
        self.button_linear_base = 0.6
        self.button_angular_base = 1.5

        # Stick drive parameters
        self.stick_deadzone = 0.15  # Increased deadzone to prevent jitter from stick noise
        self.stick_linear_scale = 1.0
        self.stick_angular_scale = 2.0  # Increased angular scale
        self.stick_active = False

        # Servo state
        self.servo_angle = 0.0
        self.servo_speed = 2.0
        self.servo_deadzone = 0.1
        self.last_right_x = 0.0

        # Button debounce
        self.last_button_states = {}
        self.button_cooldowns = {}
        self.BUTTON_COOLDOWN = 0.3

        # Trigger thresholds (axes 6/7 on macOS)
        self.trigger_threshold = 0.5
        self.zl_active = False
        self.zr_active = False

        # D-pad states
        self.dpad_left_active = False
        self.dpad_right_active = False
        self.dpad_up_active = False
        self.dpad_down_active = False

        # Debug logging for raw joy input
        self.last_log_time = 0.0
        self.last_axes = []
        self.last_buttons = []
        self.log_interval = 0.2
        self.axis_rest = None

        # Rate limiting for cmd_vel publishing (prevents motor jitter from high-freq joy msgs)
        self.cmd_vel_rate_hz = 20.0  # Max publish rate in Hz
        self.cmd_vel_interval = 1.0 / self.cmd_vel_rate_hz  # 50ms between publishes
        self.last_cmd_vel_time = 0.0
        self.pending_twist = None  # Store latest twist for rate-limited publishing

        # Publishers
        self.servo_pub = self.create_publisher(
            Float32MultiArray, "/sensors/servo_cmd", 10
        )
        self.led_pub = self.create_publisher(Int32MultiArray, "/sensors/led_cmd", 10)
        self.buzzer_pub = self.create_publisher(Bool, "/sensors/buzzer_cmd", 10)
        self.speed_pub = self.create_publisher(Int32, "/tank/speed", 10)
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_joy", 10)

        # Subscribers
        self.joy_sub = self.create_subscription(Joy, "/tank/joy", self.joy_callback, 10)

        # Timer to flush pending cmd_vel (ensures last command is sent)
        self.create_timer(self.cmd_vel_interval, self.flush_pending_cmd_vel)

        self.get_logger().info(f"Joy Mapper started (Platform: {platform.system()})")
        self.get_logger().info(f"cmd_vel rate limited to {self.cmd_vel_rate_hz} Hz")
        self.get_logger().info("Controls:")
        self.get_logger().info("  Left Stick: Drive (forward/back + turn)")
        self.get_logger().info("  Right Stick X: Servo pan")
        self.get_logger().info("  A/B: LED intensity/Buzzer")
        self.get_logger().info("  X/Y: LED colors")
        self.get_logger().info("  L/R: Turn left/right")
        self.get_logger().info("  ZL/ZR (triggers): Reverse/Forward")
        self.get_logger().info("  D-Pad Up/Down: Speed up/down")

        self.publish_speed()

    def _infer_trigger_axes(self, axes):
        """Infer analog trigger axes indices for this controller mapping.

        Returns:
            (zl_axis, zr_axis) where each can be None.
        """
        if not self.axis_rest or len(axes) != len(self.axis_rest):
            return (None, None)

        # Common SDL mapping variants:
        # - Triggers as axes 4/5 with neutral at +1.0 and pressed toward -1.0
        # - Triggers as axes 6/7 with neutral at 0.0 and pressed toward +1.0 (handled elsewhere)
        if len(axes) > 5:
            rest4 = self.axis_rest[4]
            rest5 = self.axis_rest[5]
            if abs(rest4 - 1.0) < 0.2 and abs(rest5 - 1.0) < 0.2:
                return (4, 5)

        return (None, None)

    def _trigger_value_from_axis(self, raw_value, rest_value):
        """Normalize a trigger axis to 0.0..1.0 pressedness."""
        # Neutral at +1.0, pressed toward -1.0
        if abs(rest_value - 1.0) < 0.2:
            return max(0.0, min(1.0, (1.0 - raw_value) / 2.0))
        # Neutral at 0.0, pressed toward +1.0
        if abs(rest_value) < 0.2:
            return max(0.0, min(1.0, raw_value))
        # Neutral at -1.0, pressed toward +1.0
        if abs(rest_value + 1.0) < 0.2:
            return max(0.0, min(1.0, (raw_value + 1.0) / 2.0))
        return 0.0

    def button_pressed(self, button_id, buttons):
        """Check if button was just pressed (edge detection with cooldown)"""
        if button_id >= len(buttons):
            return False

        current = buttons[button_id]
        previous = self.last_button_states.get(button_id, 0)
        self.last_button_states[button_id] = current

        now = time.time()
        if button_id in self.button_cooldowns:
            if now - self.button_cooldowns[button_id] < self.BUTTON_COOLDOWN:
                return False

        if current == 1 and previous == 0:
            self.button_cooldowns[button_id] = now
            return True
        return False

    def apply_deadzone(self, value, deadzone):
        """Apply deadzone and rescale."""
        if abs(value) < deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - deadzone) / (1.0 - deadzone)

    def publish_cmd_vel(self, twist):
        """Rate-limited cmd_vel publishing to prevent motor jitter.

        Caps publish rate at cmd_vel_rate_hz to avoid flooding motor driver
        with high-frequency commands from the joystick (~100-200Hz input).
        """
        now = time.time()
        self.pending_twist = twist  # Always store latest

        # Check if enough time has passed since last publish
        if now - self.last_cmd_vel_time >= self.cmd_vel_interval:
            self.cmd_vel_pub.publish(twist)
            self.last_cmd_vel_time = now
            self.pending_twist = None

    def flush_pending_cmd_vel(self):
        """Timer callback to publish any pending cmd_vel.

        Ensures the latest command is always sent, even if it was rate-limited.
        This prevents commands from being "dropped" at the rate limit boundary.
        """
        if self.pending_twist is not None:
            self.cmd_vel_pub.publish(self.pending_twist)
            self.last_cmd_vel_time = time.time()
            self.pending_twist = None

    def joy_callback(self, msg):
        """Process joystick input"""
        axes = msg.axes
        buttons = msg.buttons

        # Capture axis neutral/rest state on first message (helps infer mapping reliably).
        if self.axis_rest is None and axes:
            self.axis_rest = list(axes)
            rest_str = ", ".join(f"{a:.2f}" for a in self.axis_rest)
            self.get_logger().info(f"Axis rest detected: [{rest_str}]")

        # Debug: log raw axes/buttons periodically when they change
        now = time.time()
        if now - self.last_log_time > self.log_interval and (
            list(axes) != self.last_axes or list(buttons) != self.last_buttons
        ):
            self.last_log_time = now
            self.last_axes = list(axes)
            self.last_buttons = list(buttons)
            axes_str = ", ".join(f"{a:.2f}" for a in axes)
            self.get_logger().info(f"JOY RAW axes=[{axes_str}] buttons={buttons}")
            self.get_logger().info(f"Servo angle: {self.servo_angle}")

        if len(axes) < 2:
            return

        # === Left Stick Drive ===
        # axes[0] = X (left/right), axes[1] = Y (forward/back)
        stick_x = self.apply_deadzone(
            axes[0] if len(axes) > 0 else 0.0, self.stick_deadzone
        )
        stick_y = self.apply_deadzone(
            axes[1] if len(axes) > 1 else 0.0, self.stick_deadzone
        )

        # Increase sensitivity for turning
        stick_x = stick_x * 1.5
        stick_y = stick_y * 1.2

        # Check if any drive button/trigger is active
        trigger_drive = False
        bumper_drive = False

        # === Triggers as Forward/Reverse (axes 6/7 on macOS, buttons 7/8 on Linux) ===
        zl_value = 0.0
        zr_value = 0.0

        # Prefer analog triggers if we can infer them safely.
        zl_axis, zr_axis = self._infer_trigger_axes(axes)
        if (
            zl_axis is not None
            and zr_axis is not None
            and self.axis_rest is not None
            and len(self.axis_rest) > max(zl_axis, zr_axis)
        ):
            zl_value = max(
                zl_value,
                self._trigger_value_from_axis(axes[zl_axis], self.axis_rest[zl_axis]),
            )
            zr_value = max(
                zr_value,
                self._trigger_value_from_axis(axes[zr_axis], self.axis_rest[zr_axis]),
            )
        else:
            # Fallback: triggers on axes 6/7 (common when D-pad is on axes 4/5).
            if (
                self.axis_rest is not None
                and len(axes) > 7
                and len(self.axis_rest) > 7
                and len(self.axis_rest) > 5
                and abs(self.axis_rest[4]) < 0.2
                and abs(self.axis_rest[5]) < 0.2
            ):
                zl_value = max(
                    zl_value,
                    self._trigger_value_from_axis(axes[6], self.axis_rest[6]),
                )
                zr_value = max(
                    zr_value,
                    self._trigger_value_from_axis(axes[7], self.axis_rest[7]),
                )

        # Fallback: treat buttons 6/7 as digital ZL/ZR (common on Nintendo Pro via macOS SDL)
        if zl_value <= 0.0 and len(buttons) > 6 and buttons[6] == 1:
            zl_value = 1.0
        if zr_value <= 0.0 and len(buttons) > 7 and buttons[7] == 1:
            zr_value = 1.0

        # Trigger drive
        if zr_value > self.trigger_threshold:
            if not self.zr_active:
                self.zr_active = True
                self.get_logger().info("ZR: Forward")
            twist = Twist()
            speed_ratio = self.speed_percent / 100.0
            twist.linear.x = self.button_linear_base * speed_ratio * zr_value
            self.publish_cmd_vel(twist)
            trigger_drive = True
        else:
            self.zr_active = False

        if zl_value > self.trigger_threshold:
            if not self.zl_active:
                self.zl_active = True
                self.get_logger().info("ZL: Reverse")
            twist = Twist()
            speed_ratio = self.speed_percent / 100.0
            twist.linear.x = -self.button_linear_base * speed_ratio * zl_value
            self.publish_cmd_vel(twist)
            trigger_drive = True
        else:
            self.zl_active = False

        # === Bumpers L/R for turning (buttons 4/5) ===
        if len(buttons) > 5:
            # Debug bumper inputs
            if buttons[4] == 1 or buttons[5] == 1:
                self.get_logger().info(f"Bumpers - L:{buttons[4]} R:{buttons[5]}")

            # L button (4) - turn left
            if buttons[4] == 1:
                if not self.dpad_left_active:
                    self.dpad_left_active = True
                    self.get_logger().info("L: Turn left")
                twist = Twist()
                speed_ratio = self.speed_percent / 100.0
                twist.angular.z = self.button_angular_base * speed_ratio
                self.publish_cmd_vel(twist)
                bumper_drive = True
            else:
                self.dpad_left_active = False

            # R button (5) - turn right
            if buttons[5] == 1:
                if not self.dpad_right_active:
                    self.dpad_right_active = True
                    self.get_logger().info("R: Turn right")
                twist = Twist()
                speed_ratio = self.speed_percent / 100.0
                twist.angular.z = -self.button_angular_base * speed_ratio
                self.publish_cmd_vel(twist)
                bumper_drive = True
            else:
                self.dpad_right_active = False

        # === Stick drive (only if no button/trigger drive) ===
        stick_active_now = False
        if not trigger_drive and not bumper_drive:
            if stick_x != 0.0 or stick_y != 0.0:
                twist = Twist()
                twist.linear.x = stick_y * self.stick_linear_scale
                twist.angular.z = (
                    stick_x * self.stick_angular_scale * 2.0
                )  # Double turning power
                self.publish_cmd_vel(twist)
                stick_active_now = True

        # Stop if stick was active but now released (and no button drive)
        if (
            self.stick_active
            and not stick_active_now
            and not trigger_drive
            and not bumper_drive
        ):
            # Use rate-limited publish for STOP too (prevents jitter from noise)
            self.publish_cmd_vel(Twist())
        self.stick_active = stick_active_now

        # === D-Pad for speed control (axes 4/5) ===
        dpad_y = None
        if self.axis_rest is not None and len(axes) == len(self.axis_rest):
            # Most stable heuristic:
            # - If axes 4/5 idle at +1.0, they are triggers, so D-pad is usually on axes 6/7.
            # - If axes 4/5 idle at 0.0, they are usually D-pad.
            if (
                len(self.axis_rest) > 5
                and abs(self.axis_rest[4] - 1.0) < 0.2
                and abs(self.axis_rest[5] - 1.0) < 0.2
            ):
                if (
                    len(axes) > 7
                    and abs(self.axis_rest[6]) < 0.2
                    and abs(self.axis_rest[7]) < 0.2
                ):
                    dpad_y = axes[7]
            elif (
                len(self.axis_rest) > 5
                and abs(self.axis_rest[4]) < 0.2
                and abs(self.axis_rest[5]) < 0.2
            ):
                dpad_y = axes[5]

        if dpad_y is not None:
            # Convention: Up=-1, Down=+1 (verify via JOY RAW if needed)

            # D-Pad Up - speed up
            if dpad_y < -0.5:
                if not self.dpad_up_active:
                    self.dpad_up_active = True
                    self.speed_percent = min(100, self.speed_percent + self.speed_step)
                    self.publish_speed()
                    self.get_logger().info(f"Speed: {self.speed_percent}%")
            else:
                self.dpad_up_active = False

            # D-Pad Down - speed down
            if dpad_y > 0.5:
                if not self.dpad_down_active:
                    self.dpad_down_active = True
                    self.speed_percent = max(10, self.speed_percent - self.speed_step)
                    self.publish_speed()
                    self.get_logger().info(f"Speed: {self.speed_percent}%")
            else:
                self.dpad_down_active = False

        # === Right Stick X -> Servo Pan ===
        if len(axes) > 2:
            right_x = axes[2]
            # Some mappings expose right stick X on axis 3; fall back if axis 2 looks idle.
            if (
                len(axes) > 3
                and abs(right_x) <= self.servo_deadzone
                and abs(axes[3]) > self.servo_deadzone
            ):
                right_x = axes[3]
            if abs(right_x) > self.servo_deadzone:
                if abs(right_x - self.last_right_x) >= 0.05:
                    self.last_right_x = right_x
                    self.servo_angle = max(-90, min(90, right_x * 90.0))
                    self.publish_servo()

        # === Face Buttons ===
        # B (0) - Buzzer
        if len(buttons) > 0:
            buzzer_msg = Bool()
            buzzer_msg.data = buttons[0] == 1
            self.buzzer_pub.publish(buzzer_msg)

        # A (1) - LED intensity toggle
        if self.button_pressed(1, buttons):
            self.led_intensity_index = 1 - self.led_intensity_index
            self.publish_led()
            self.get_logger().info(
                f"LED: {'ON' if self.led_intensity_index else 'OFF'}"
            )

        # X (2) - Cycle LED colors
        if self.button_pressed(2, buttons):
            self.led_color_index = (self.led_color_index + 1) % len(self.LED_COLORS)
            self.publish_led()
            colors = [
                "Off",
                "Red",
                "Green",
                "Blue",
                "Yellow",
                "Magenta",
                "Cyan",
                "White",
            ]
            self.get_logger().info(f"LED color: {colors[self.led_color_index]}")

        # Y (3) - Cycle speed modes
        if self.button_pressed(3, buttons):
            self.speed_mode_index = (self.speed_mode_index + 1) % len(self.SPEED_MODES)
            self.speed_percent = self.SPEED_MODES[self.speed_mode_index]
            self.publish_speed()
            modes = ["SLOW (30%)", "MEDIUM (60%)", "FAST (100%)"]
            self.get_logger().info(f"Speed mode: {modes[self.speed_mode_index]}")

        # +/- buttons (platform dependent) - incremental speed adjust
        minus_button = 8 if self.is_macos else 9
        plus_button = 9 if self.is_macos else 10
        if self.button_pressed(minus_button, buttons):
            self.speed_percent = max(10, self.speed_percent - self.speed_step)
            self.publish_speed()
            self.get_logger().info(f"Speed: {self.speed_percent}%")
        if self.button_pressed(plus_button, buttons):
            self.speed_percent = min(100, self.speed_percent + self.speed_step)
            self.publish_speed()
            self.get_logger().info(f"Speed: {self.speed_percent}%")

    def publish_servo(self):
        msg = Float32MultiArray()
        msg.data = [float(self.servo_angle)]
        self.servo_pub.publish(msg)

    def publish_led(self):
        msg = Int32MultiArray()
        color = self.LED_COLORS[self.led_color_index]
        intensity = self.led_intensity_index
        msg.data = [c * intensity for c in color]
        self.led_pub.publish(msg)

    def publish_speed(self):
        msg = Int32()
        msg.data = int(self.speed_percent)
        self.speed_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = JoyMapperNode()
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
