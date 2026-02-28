#!/usr/bin/env python3
"""
PS2 Joy Mapper Node — Maps Hiwonder PS2 Wireless Controller to robot functions.

Runs on the Pi alongside joy_node. Subscribes to /joy (sensor_msgs/Joy)
and publishes drive commands, servo, LED, buzzer, and speed topics.

Controller: Hiwonder PS2 Wireless (ShanWan ZD-V+ USB HID receiver)
  Product: https://www.hiwonder.com/products/ps2-wireless-handle-with-usb-receiver

Linux joydev axis/button mapping (confirmed via jstest/evtest):

  Axes (normalized -1.0 to +1.0 by joy_node via SDL2):
    0: Left Stick X   (left=-1, right=+1)
    1: Left Stick Y   (SDL2 mapped gamepad — convention varies)
    2: Right Stick X   (left=-1, right=+1)
    3: Right Stick Y   (SDL2 mapped gamepad — convention varies)
    4: D-Pad X         (left=-1, right=+1)
    5: D-Pad Y         (up=-1, down=+1)

  Buttons (0/1):
    0: Cross (X)       — BTN_SOUTH
    1: Circle (O)      — BTN_EAST
    2: L3 / BtnC       — BTN_C  (left stick click, if present)
    3: Triangle        — BTN_NORTH
    4: Square          — BTN_WEST
    5: R3 / BtnZ       — BTN_Z  (right stick click, if present)
    6: L1              — BTN_TL
    7: R1              — BTN_TR
    8: L2              — BTN_TL2  (digital, not analog)
    9: R2              — BTN_TR2  (digital, not analog)
   10: Select          — BTN_SELECT
   11: Start           — BTN_START
   12: Mode/Analog     — BTN_MODE

Controls:
  Right Stick:   Drive (Y=forward/back, X=turn)
  R2:            Forward (fixed speed)
  L2:            Reverse (fixed speed)
  L1:            Turn left
  R1:            Turn right
  Left Stick X:  Servo pan (camera)
  D-Pad Up/Down: Speed adjust ±10%
  Triangle:      Cycle speed modes (SLOW/MEDIUM/FAST)
  Cross:         Buzzer (hold)
  Circle:        LED on/off toggle
  Square:        Cycle LED colors
  Select:        Speed down 10%
  Start:         Speed up 10%
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Joy
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32MultiArray, Int32MultiArray, Int32, Bool
import time


# --- Button indices (Hiwonder PS2 via Linux joydev) ---
BTN_CROSS = 0       # X / South
BTN_CIRCLE = 1      # O / East
BTN_L3 = 2          # Left stick click (BtnC)
BTN_TRIANGLE = 3    # Triangle / North
BTN_SQUARE = 4      # Square / West
BTN_R3 = 5          # Right stick click (BtnZ)
BTN_L1 = 6          # Left bumper
BTN_R1 = 7          # Right bumper
BTN_L2 = 8          # Left trigger (digital)
BTN_R2 = 9          # Right trigger (digital)
BTN_SELECT = 10
BTN_START = 11
BTN_MODE = 12       # Analog / Mode toggle

# --- Axis indices ---
AXIS_LSTICK_X = 0   # Left stick horizontal
AXIS_LSTICK_Y = 1   # Left stick vertical (up=-1 on Linux!)
AXIS_RSTICK_X = 2   # Right stick horizontal
AXIS_RSTICK_Y = 3   # Right stick vertical
AXIS_DPAD_X = 4     # D-pad horizontal
AXIS_DPAD_Y = 5     # D-pad vertical (up=-1 on Linux!)


class PS2JoyMapper(Node):
    def __init__(self):
        super().__init__("ps2_joy_mapper")

        # LED color palette: [R, G, B] — each 0 or 1
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
        self.led_on = True

        # Speed control
        self.SPEED_MODES = [30, 60, 100]
        self.speed_mode_index = 1  # Start at MEDIUM
        self.speed_percent = self.SPEED_MODES[self.speed_mode_index]
        self.speed_step = 10

        # Drive parameters
        self.button_linear_base = 0.6   # Base linear speed for L2/R2
        self.button_angular_base = 6.5  # Base angular speed for L1/R1 (full motor power at 100%)
        self.stick_deadzone = 0.25  # Large deadzone — PS2 sticks drift up to ±0.19 at rest
        self.stick_linear_scale = 1.0
        self.stick_angular_scale = 6.5  # Full motor power in-place turn at full stick

        # Servo state
        self.servo_angle = 0.0
        self.servo_deadzone = 0.15
        self.last_right_x = 0.0

        # Button edge detection + cooldown
        self.last_button_states = {}
        self.button_cooldowns = {}
        self.BUTTON_COOLDOWN = 0.3

        # D-pad edge tracking
        self.dpad_up_active = False
        self.dpad_down_active = False

        # Debug logging (throttled)
        self.last_debug_time = 0.0
        self.debug_interval = 0.25  # Log at most 4x/sec

        # Rate limiting for cmd_vel (prevents motor jitter from high-freq joy msgs)
        self.cmd_vel_rate_hz = 20.0
        self.cmd_vel_interval = 1.0 / self.cmd_vel_rate_hz
        self.last_cmd_vel_time = 0.0
        self.pending_twist = None

        # Publishers
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_joy", 10)
        self.servo_pub = self.create_publisher(Float32MultiArray, "/sensors/servo_cmd", 10)
        self.led_pub = self.create_publisher(Int32MultiArray, "/sensors/led_cmd", 10)
        self.buzzer_pub = self.create_publisher(Bool, "/sensors/buzzer_cmd", 10)
        self.speed_pub = self.create_publisher(Int32, "/tank/speed", 10)

        # Subscriber
        self.create_subscription(Joy, "/joy", self.joy_callback, 10)

        # Timer to flush pending cmd_vel
        self.create_timer(self.cmd_vel_interval, self.flush_pending_cmd_vel)

        self.get_logger().info("PS2 Joy Mapper started")
        self.get_logger().info(f"  cmd_vel rate: {self.cmd_vel_rate_hz} Hz")
        self.get_logger().info(f"  speed: {self.speed_percent}%")
        self.get_logger().info("Controls:")
        self.get_logger().info("  Right Stick: Drive (forward/back + turn)")
        self.get_logger().info("  Left Stick : Servo pan")
        self.get_logger().info("  L2/R2      : Reverse / Forward")
        self.get_logger().info("  L1/R1      : Turn left / right")
        self.get_logger().info("  D-Pad U/D  : Speed ±10%")
        self.get_logger().info("  Triangle   : Cycle speed mode")
        self.get_logger().info("  Cross      : Buzzer (hold)")
        self.get_logger().info("  Circle     : LED toggle")
        self.get_logger().info("  Square     : LED color cycle")

        self.publish_speed()

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
        """Rate-limited cmd_vel to prevent motor jitter."""
        now = time.time()
        self.pending_twist = twist
        if now - self.last_cmd_vel_time >= self.cmd_vel_interval:
            self.cmd_vel_pub.publish(twist)
            self.last_cmd_vel_time = now
            self.pending_twist = None

    def flush_pending_cmd_vel(self):
        """Timer callback — publish any pending cmd_vel so last command isn't dropped."""
        if self.pending_twist is not None:
            self.cmd_vel_pub.publish(self.pending_twist)
            self.last_cmd_vel_time = time.time()
            self.pending_twist = None

    def publish_servo(self):
        msg = Float32MultiArray()
        msg.data = [float(self.servo_angle)]
        self.servo_pub.publish(msg)

    def publish_led(self):
        msg = Int32MultiArray()
        color = self.LED_COLORS[self.led_color_index]
        intensity = 1 if self.led_on else 0
        msg.data = [c * intensity for c in color]
        self.led_pub.publish(msg)

    def publish_speed(self):
        msg = Int32()
        msg.data = int(self.speed_percent)
        self.speed_pub.publish(msg)

    # ─── Main callback ────────────────────────────────────────

    def joy_callback(self, msg):
        axes = msg.axes
        buttons = msg.buttons

        if len(axes) < 6 or len(buttons) < 12:
            return

        speed_ratio = self.speed_percent / 100.0
        trigger_drive = False
        bumper_drive = False

        # Build a single twist from all drive inputs. Always publish
        # (even zero) so the mux never holds a stale command.
        twist = Twist()

        # === R2: Forward ===
        if self.button_held(BTN_R2, buttons):
            twist.linear.x = self.button_linear_base * speed_ratio
            trigger_drive = True

        # === L2: Reverse ===
        if self.button_held(BTN_L2, buttons):
            twist.linear.x = -self.button_linear_base * speed_ratio
            trigger_drive = True

        # === L1: Turn left ===
        if self.button_held(BTN_L1, buttons):
            twist.angular.z = self.button_angular_base * speed_ratio
            bumper_drive = True

        # === R1: Turn right ===
        if self.button_held(BTN_R1, buttons):
            twist.angular.z = -self.button_angular_base * speed_ratio
            bumper_drive = True

        # === Right stick drive (only when no button drive active) ===
        if not trigger_drive and not bumper_drive:
            raw_x = axes[AXIS_RSTICK_X]
            raw_y = axes[AXIS_RSTICK_Y]
            stick_x = self.apply_deadzone(raw_x, self.stick_deadzone)
            # Negate Y: SDL2 joydev reports forward (up) as negative
            stick_y = -self.apply_deadzone(raw_y, self.stick_deadzone)

            twist.linear.x = stick_y * self.stick_linear_scale * speed_ratio
            twist.angular.z = -stick_x * self.stick_angular_scale * speed_ratio

            # Debug: log when stick is active (throttled)
            now = time.time()
            if (stick_x != 0.0 or stick_y != 0.0) and now - self.last_debug_time > self.debug_interval:
                self.last_debug_time = now
                self.get_logger().info(
                    f"STICK raw_y={raw_y:+.3f}→neg={stick_y:+.3f} "
                    f"raw_x={raw_x:+.3f}→{stick_x:+.3f} "
                    f"cmd=(lin={twist.linear.x:+.3f},ang={twist.angular.z:+.3f})"
                )

        # Always publish — zero twist when idle ensures reliable stopping
        self.publish_cmd_vel(twist)

        # === Left stick X → servo pan ===
        left_x = axes[AXIS_LSTICK_X]
        if abs(left_x) > self.servo_deadzone:
            if abs(left_x - self.last_right_x) >= 0.05:
                self.last_right_x = left_x
                self.servo_angle = max(-90.0, min(90.0, left_x * 90.0))
                self.publish_servo()

        # === D-Pad Y: speed adjust ===
        dpad_y = axes[AXIS_DPAD_Y]
        # Up (dpad_y = -1) → speed up
        if dpad_y < -0.5:
            if not self.dpad_up_active:
                self.dpad_up_active = True
                self.speed_percent = min(100, self.speed_percent + self.speed_step)
                self.publish_speed()
                self.get_logger().info(f"Speed: {self.speed_percent}%")
        else:
            self.dpad_up_active = False
        # Down (dpad_y = +1) → speed down
        if dpad_y > 0.5:
            if not self.dpad_down_active:
                self.dpad_down_active = True
                self.speed_percent = max(10, self.speed_percent - self.speed_step)
                self.publish_speed()
                self.get_logger().info(f"Speed: {self.speed_percent}%")
        else:
            self.dpad_down_active = False

        # === Cross: Buzzer (hold) ===
        buzzer_msg = Bool()
        buzzer_msg.data = self.button_held(BTN_CROSS, buttons)
        self.buzzer_pub.publish(buzzer_msg)

        # === Circle: LED on/off toggle ===
        if self.button_pressed(BTN_CIRCLE, buttons):
            self.led_on = not self.led_on
            self.publish_led()
            self.get_logger().info(f"LED: {'ON' if self.led_on else 'OFF'}")

        # === Square: Cycle LED colors ===
        if self.button_pressed(BTN_SQUARE, buttons):
            self.led_color_index = (self.led_color_index + 1) % len(self.LED_COLORS)
            self.publish_led()
            names = ["Off", "Red", "Green", "Blue", "Yellow", "Magenta", "Cyan", "White"]
            self.get_logger().info(f"LED color: {names[self.led_color_index]}")

        # === Triangle: Cycle speed modes ===
        if self.button_pressed(BTN_TRIANGLE, buttons):
            self.speed_mode_index = (self.speed_mode_index + 1) % len(self.SPEED_MODES)
            self.speed_percent = self.SPEED_MODES[self.speed_mode_index]
            self.publish_speed()
            modes = ["SLOW (30%)", "MEDIUM (60%)", "FAST (100%)"]
            self.get_logger().info(f"Speed mode: {modes[self.speed_mode_index]}")

        # === Select: Speed down / Start: Speed up ===
        if self.button_pressed(BTN_SELECT, buttons):
            self.speed_percent = max(10, self.speed_percent - self.speed_step)
            self.publish_speed()
            self.get_logger().info(f"Speed: {self.speed_percent}%")
        if self.button_pressed(BTN_START, buttons):
            self.speed_percent = min(100, self.speed_percent + self.speed_step)
            self.publish_speed()
            self.get_logger().info(f"Speed: {self.speed_percent}%")


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
