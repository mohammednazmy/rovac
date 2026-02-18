#!/usr/bin/env python3
"""
ROS2 Tank Motor Driver - Auto-Refresh Version
Handles voltage drops/hardware resets by continuously refreshing motor state.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32

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
        
        self.speed_percent = 60  # Reduced slightly to prevent voltage sag
        self.pwm_freq = 1000
        self.gpio_handle = None
        
        # Current Target State
        self.left_target = {'dir': 0, 'pwm': 0}
        self.right_target = {'dir': 0, 'pwm': 0}
        
        # Initialize GPIO
        if GPIO_AVAILABLE:
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)
                for pin in [self.ENA, self.ENB, self.IN1, self.IN2, self.IN3, self.IN4]:
                    lgpio.gpio_claim_output(self.gpio_handle, pin, 0)
                self.get_logger().info('GPIO initialized - Auto-Refresh Enabled')
            except Exception as e:
                self.get_logger().error(f'GPIO init failed: {e}')
                self.gpio_handle = None
        
        # Subscriptions
        self.joy_sub = self.create_subscription(
            Twist,
            'cmd_vel_joy',
            self.cmd_vel_callback,
            10
        )
        self.cmd_sub = self.create_subscription(
            Twist,
            'cmd_vel',
            self.cmd_vel_callback,
            10
        )
        self.speed_sub = self.create_subscription(
            Int32,
            'tank/speed',
            self.speed_callback,
            10
        )

        # Refresh Timer (10Hz) - Re-applies GPIO state to handle hardware resets
        self.create_timer(0.1, self.refresh_motors)
        
        self.get_logger().info('Tank motor driver ready (Auto-Refresh)')

    def speed_callback(self, msg):
        self.speed_percent = max(0, min(100, msg.data))
        self.get_logger().info(f'Speed set to {self.speed_percent}%')

    def apply_motor_state(self, side, state):
        if not self.gpio_handle:
            return
            
        direction = state['dir']
        pwm_val = state['pwm']
        
        if side == 'left':
            pwm_pin = self.ENA
            in1 = self.IN1
            in2 = self.IN2
        else:
            pwm_pin = self.ENB
            in1 = self.IN3
            in2 = self.IN4
            
        # Write Pins
        if direction > 0:  # Forward
            lgpio.gpio_write(self.gpio_handle, in1, 1)
            lgpio.gpio_write(self.gpio_handle, in2, 0)
        elif direction < 0:  # Backward
            lgpio.gpio_write(self.gpio_handle, in1, 0)
            lgpio.gpio_write(self.gpio_handle, in2, 1)
        else:  # Stop
            lgpio.gpio_write(self.gpio_handle, in1, 0)
            lgpio.gpio_write(self.gpio_handle, in2, 0)
            
        # Write PWM
        lgpio.tx_pwm(self.gpio_handle, pwm_pin, self.pwm_freq, pwm_val)

    def refresh_motors(self):
        # Periodically re-apply the last known good state
        self.apply_motor_state('left', self.left_target)
        self.apply_motor_state('right', self.right_target)

    def update_targets(self, left_dir, left_pwm, right_dir, right_pwm):
        self.left_target = {'dir': left_dir, 'pwm': left_pwm}
        self.right_target = {'dir': right_dir, 'pwm': right_pwm}
        # Apply immediately as well
        self.refresh_motors()

    def cmd_vel_callback(self, msg):
        if not self.gpio_handle:
            return

        linear = msg.linear.x
        angular = msg.angular.z
        
        # Deadzone
        if abs(linear) < 0.1 and abs(angular) < 0.1:
            self.update_targets(0, 0, 0, 0)
            return

        # Special handling for turns
        if abs(linear) < 0.2 and abs(angular) > 0.2:
            turn_power = self.speed_percent
            if angular > 0: # Left Turn
                self.get_logger().info(f"Turning LEFT {turn_power}%", throttle_duration_sec=1.0)
                self.update_targets(-1, turn_power, 1, turn_power)
            else: # Right Turn
                self.get_logger().info(f"Turning RIGHT {turn_power}%", throttle_duration_sec=1.0)
                self.update_targets(1, turn_power, -1, turn_power)
            return

        # Differential drive
        left_speed = linear - angular
        right_speed = linear + angular
        
        # Normalize
        max_val = max(abs(left_speed), abs(right_speed))
        if max_val > 1.0:
            left_speed /= max_val
            right_speed /= max_val
            
        # Convert to PWM
        left_pwm = int(abs(left_speed) * self.speed_percent)
        right_pwm = int(abs(right_speed) * self.speed_percent)
        
        # Direction
        left_dir = 1 if left_speed >= 0 else -1
        if abs(left_speed) < 0.05: left_dir = 0
        
        right_dir = 1 if right_speed >= 0 else -1
        if abs(right_speed) < 0.05: right_dir = 0
        
        self.update_targets(left_dir, left_pwm, right_dir, right_pwm)

    def destroy_node(self):
        if self.gpio_handle:
            lgpio.gpio_write(self.gpio_handle, self.IN1, 0)
            lgpio.gpio_write(self.gpio_handle, self.IN2, 0)
            lgpio.gpio_write(self.gpio_handle, self.IN3, 0)
            lgpio.gpio_write(self.gpio_handle, self.IN4, 0)
            lgpio.tx_pwm(self.gpio_handle, self.ENA, 1000, 0)
            lgpio.tx_pwm(self.gpio_handle, self.ENB, 1000, 0)
            lgpio.gpiochip_close(self.gpio_handle)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TankMotorDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
