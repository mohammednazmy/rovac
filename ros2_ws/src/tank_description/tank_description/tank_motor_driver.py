#!/usr/bin/env python3
"""
ROS2 Tank Motor Driver - WITH SMOOTHING
Subscribes to /cmd_vel and drives GPIO motors with smooth ramping.
For Yahboom G1 Tank on Raspberry Pi 5

Pin Mapping (BCM GPIO):
  Left Motor:  IN1=20, IN2=21, ENA=16 (PWM)
  Right Motor: IN3=19, IN4=26, ENB=13 (PWM)
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32
import sys
import time

try:
    import lgpio
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("Warning: lgpio not available")


class TankMotorDriver(Node):
    def __init__(self):
        super().__init__('tank_motor_driver')

        # GPIO pins (BCM numbering)
        self.ENA = 16  # Left motor PWM
        self.ENB = 13  # Right motor PWM
        self.IN1 = 20  # Left forward
        self.IN2 = 21  # Left backward
        self.IN3 = 19  # Right forward
        self.IN4 = 26  # Right backward

        self.speed_percent = 100  # Default speed (0-100)
        self.pwm_freq = 1000  # PWM frequency Hz
        self.gpio_handle = None
        self.min_pwm = 20  # Minimum PWM to overcome stall

        # ============================================
        # SMOOTHING PARAMETERS
        # ============================================
        self.smoothing_factor = 0.3  # Lower = smoother (0.1-0.3 recommended) - increased for responsiveness
        self.deadzone = 0.08  # Ignore small values
        self.ramp_rate = 0.15  # Max change per update cycle - increased for faster response

        # Current smoothed motor values (-1.0 to 1.0)
        self.current_left = 0.0
        self.current_right = 0.0

        # Target motor values (from cmd_vel)
        self.target_left = 0.0
        self.target_right = 0.0

        # Last applied PWM values (to avoid unnecessary updates)
        self.last_left_pwm = 0.0
        self.last_right_pwm = 0.0
        self.last_left_dir = 0
        self.last_right_dir = 0
        # ============================================

        # Initialize GPIO
        if GPIO_AVAILABLE:
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)  # Pi 5 uses gpiochip4
                for pin in [self.ENA, self.ENB, self.IN1, self.IN2, self.IN3, self.IN4]:
                    lgpio.gpio_claim_output(self.gpio_handle, pin, 0)
                self.get_logger().info('GPIO motor driver initialized (with smoothing)')
            except Exception as e:
                self.get_logger().error(f'GPIO init failed: {e}')
                self.gpio_handle = None
        else:
            self.get_logger().warn('lgpio module not found. Motors will not move.')

        # Subscribe to cmd_vel
        self.cmd_sub = self.create_subscription(
            Twist,
            'cmd_vel',
            self.cmd_vel_callback,
            10
        )

        # Subscribe to speed setting
        self.speed_sub = self.create_subscription(
            Int32,
            'tank/speed',
            self.speed_callback,
            10
        )

        # Safety timeout - stop if no commands received
        self.last_cmd_time = self.get_clock().now()
        self.timeout_timer = self.create_timer(0.5, self.check_timeout)

        # Smooth motor update loop (50 Hz for smooth PWM changes)
        self.motor_update_timer = self.create_timer(0.02, self.update_motors)

        self.get_logger().info(f'Tank motor driver ready (speed: {self.speed_percent}%, smoothing: {self.smoothing_factor})')

    def speed_callback(self, msg):
        self.speed_percent = max(0, min(100, msg.data))
        self.get_logger().info(f'Speed set to {self.speed_percent}%')

    def apply_deadzone(self, value):
        """Apply deadzone and rescale"""
        if abs(value) < self.deadzone:
            return 0.0
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - self.deadzone) / (1.0 - self.deadzone)

    def cmd_vel_callback(self, msg):
        """Receive cmd_vel and set target speeds (smoothing happens in update_motors)"""
        self.last_cmd_time = self.get_clock().now()

        linear = msg.linear.x   # Forward/backward: -1.0 to 1.0
        angular = msg.angular.z  # Turn: -1.0 to 1.0 (positive = left)

        # Apply deadzone to inputs
        linear = self.apply_deadzone(linear)
        angular = self.apply_deadzone(angular)

        # Convert to differential drive
        left_speed = linear - angular
        right_speed = linear + angular

        # Normalize to -1.0 to 1.0
        max_val = max(abs(left_speed), abs(right_speed), 1.0)
        left_speed /= max_val
        right_speed /= max_val

        # Set targets (smoothing happens in update_motors)
        self.target_left = left_speed
        self.target_right = right_speed

    def update_motors(self):
        """Called at 50Hz to smoothly update motor speeds"""
        if not self.gpio_handle:
            return

        # Exponential smoothing toward target
        self.current_left += self.smoothing_factor * (self.target_left - self.current_left)
        self.current_right += self.smoothing_factor * (self.target_right - self.current_right)

        # Clamp rate of change (prevents sudden jumps)
        # This is a secondary safety measure
        if abs(self.current_left - self.target_left) > self.ramp_rate:
            if self.target_left > self.current_left:
                self.current_left = min(self.current_left + self.ramp_rate, self.target_left)
            else:
                self.current_left = max(self.current_left - self.ramp_rate, self.target_left)

        if abs(self.current_right - self.target_right) > self.ramp_rate:
            if self.target_right > self.current_right:
                self.current_right = min(self.current_right + self.ramp_rate, self.target_right)
            else:
                self.current_right = max(self.current_right - self.ramp_rate, self.target_right)

        # Snap to zero if very small (prevents motor whine at low PWM)
        if abs(self.current_left) < 0.02:
            self.current_left = 0.0
        if abs(self.current_right) < 0.02:
            self.current_right = 0.0

        # Determine direction (1=forward, -1=backward, 0=stopped)
        left_dir = 0 if abs(self.current_left) < 0.02 else (1 if self.current_left > 0 else -1)
        right_dir = 0 if abs(self.current_right) < 0.02 else (1 if self.current_right > 0 else -1)

        # Calculate PWM values with minimum threshold to overcome stall
        if left_dir != 0:
            effective_min = min(self.min_pwm, self.speed_percent)
            pwm_range = self.speed_percent - effective_min
            left_pwm = effective_min + abs(self.current_left) * pwm_range
        else:
            left_pwm = 0

        if right_dir != 0:
            effective_min = min(self.min_pwm, self.speed_percent)
            pwm_range = self.speed_percent - effective_min
            right_pwm = effective_min + abs(self.current_right) * pwm_range
        else:
            right_pwm = 0

        # Only update GPIO if values changed significantly (reduces GPIO calls)
        left_pwm_changed = abs(left_pwm - self.last_left_pwm) > 0.5 or left_dir != self.last_left_dir
        right_pwm_changed = abs(right_pwm - self.last_right_pwm) > 0.5 or right_dir != self.last_right_dir

        if left_pwm_changed:
            self.set_motor('left', left_dir, left_pwm)
            self.last_left_pwm = left_pwm
            self.last_left_dir = left_dir
            if left_dir != 0:
                self.get_logger().info(f'LEFT: dir={left_dir} pwm={left_pwm:.1f}%')

        if right_pwm_changed:
            self.set_motor('right', right_dir, right_pwm)
            self.last_right_pwm = right_pwm
            self.last_right_dir = right_dir
            if right_dir != 0:
                self.get_logger().info(f'RIGHT: dir={right_dir} pwm={right_pwm:.1f}%')

    def set_motor(self, motor, direction, pwm):
        """Set motor direction and PWM"""
        if not self.gpio_handle:
            return

        if motor == 'left':
            in1, in2, ena = self.IN1, self.IN2, self.ENA
        else:
            in1, in2, ena = self.IN3, self.IN4, self.ENB

        if direction == 0:  # Stopped
            lgpio.gpio_write(self.gpio_handle, in1, 0)
            lgpio.gpio_write(self.gpio_handle, in2, 0)
            lgpio.tx_pwm(self.gpio_handle, ena, self.pwm_freq, 0)
        elif direction > 0:  # Forward
            lgpio.gpio_write(self.gpio_handle, in1, 1)
            lgpio.gpio_write(self.gpio_handle, in2, 0)
            lgpio.tx_pwm(self.gpio_handle, ena, self.pwm_freq, pwm)
        else:  # Backward
            lgpio.gpio_write(self.gpio_handle, in1, 0)
            lgpio.gpio_write(self.gpio_handle, in2, 1)
            lgpio.tx_pwm(self.gpio_handle, ena, self.pwm_freq, pwm)

    def check_timeout(self):
        """Stop motors if no command received for 1 second"""
        elapsed = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
        if elapsed > 1.0:
            self.target_left = 0.0
            self.target_right = 0.0

    def stop_motors(self):
        if not self.gpio_handle:
            return
        self.target_left = 0.0
        self.target_right = 0.0
        self.current_left = 0.0
        self.current_right = 0.0
        for pin in [self.IN1, self.IN2, self.IN3, self.IN4]:
            lgpio.gpio_write(self.gpio_handle, pin, 0)
        lgpio.tx_pwm(self.gpio_handle, self.ENA, self.pwm_freq, 0)
        lgpio.tx_pwm(self.gpio_handle, self.ENB, self.pwm_freq, 0)

    def cleanup(self):
        self.stop_motors()
        if self.gpio_handle:
            lgpio.gpiochip_close(self.gpio_handle)


def main(args=None):
    rclpy.init(args=args)
    node = TankMotorDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.cleanup()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
