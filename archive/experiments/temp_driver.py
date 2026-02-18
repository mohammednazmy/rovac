#!/usr/bin/env python3
"""
ROS2 Tank Motor Driver - Direct /cmd_vel_joy subscription
Bypasses Yahboom mux entirely to ensure direct control
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32
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
        
        # GPIO pins (BCM numbering) - SAME AS MANUAL TEST
        self.ENA = 16  # Left motor PWM
        self.ENB = 13  # Right motor PWM
        self.IN1 = 20  # Left forward
        self.IN2 = 21  # Left backward
        self.IN3 = 19  # Right forward
        self.IN4 = 26  # Right backward
        
        self.speed_percent = 70  # Same as manual test
        self.pwm_freq = 1000     # Same as manual test
        self.gpio_handle = None
        
        # Initialize GPIO exactly as in working manual test
        if GPIO_AVAILABLE:
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)
                # Claim all pins as outputs with initial state 0
                for pin in [self.ENA, self.ENB, self.IN1, self.IN2, self.IN3, self.IN4]:
                    lgpio.gpio_claim_output(self.gpio_handle, pin, 0)
                
                self.get_logger().info('GPIO initialized - Direct /cmd_vel_joy subscription')
            except Exception as e:
                self.get_logger().error(f'GPIO init failed: {e}')
                self.gpio_handle = None
        
        # SUBSCRIBE DIRECTLY TO /cmd_vel_joy - bypassing Yahboom mux
        # Also subscribe to /cmd_vel as backup
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
        
        self.get_logger().info('Tank motor driver ready - Subscribed to cmd_vel_joy and cmd_vel')

    def speed_callback(self, msg):
        self.speed_percent = max(0, min(100, msg.data))
        self.get_logger().info(f'Speed set to {self.speed_percent}%')

    def set_motor(self, side, direction, pwm_val):
        if not self.gpio_handle:
            return
            
        # Ensure PWM value is within range
        pwm_val = max(0, min(100, pwm_val))
        
        if side == 'left':
            pwm_pin = self.ENA
            in1 = self.IN1
            in2 = self.IN2
        else:
            pwm_pin = self.ENB
            in1 = self.IN3
            in2 = self.IN4
            
        # Set direction pins
        if direction > 0:  # Forward
            lgpio.gpio_write(self.gpio_handle, in1, 1)
            lgpio.gpio_write(self.gpio_handle, in2, 0)
        elif direction < 0:  # Backward
            lgpio.gpio_write(self.gpio_handle, in1, 0)
            lgpio.gpio_write(self.gpio_handle, in2, 1)
        else:  # Stop
            lgpio.gpio_write(self.gpio_handle, in1, 0)
            lgpio.gpio_write(self.gpio_handle, in2, 0)
            pwm_val = 0
            
        # Set PWM
        lgpio.tx_pwm(self.gpio_handle, pwm_pin, self.pwm_freq, pwm_val)

    def cmd_vel_callback(self, msg):
        if not self.gpio_handle:
            return

        linear = msg.linear.x
        angular = msg.angular.z
        
        # Deadzone to prevent jitter
        if abs(linear) < 0.1 and abs(angular) < 0.1:
            self.set_motor('left', 0, 0)
            self.set_motor('right', 0, 0)
            return

        # Special handling for turns (Low linear, High angular)
        if abs(linear) < 0.2 and abs(angular) > 0.2:
            turn_power = self.speed_percent
            if angular > 0: # Left Turn
                # Left motor backward, Right motor forward
                self.set_motor('left', -1, turn_power)
                self.set_motor('right', 1, turn_power)
                self.get_logger().info(f"Turning LEFT at {turn_power}%")
            else: # Right Turn
                # Left motor forward, Right motor backward
                self.set_motor('left', 1, turn_power)
                self.set_motor('right', -1, turn_power)
                self.get_logger().info(f"Turning RIGHT at {turn_power}%")
            return

        # Normal differential drive for movement with turning
        left_speed = linear - angular
        right_speed = linear + angular
        
        # Normalize
        max_val = max(abs(left_speed), abs(right_speed))
        if max_val > 1.0:
            left_speed /= max_val
            right_speed /= max_val
            
        # Convert to PWM
        left_pwm = abs(left_speed) * self.speed_percent
        right_pwm = abs(right_speed) * self.speed_percent
        
        # Direction
        left_dir = 1 if left_speed >= 0 else -1
        if abs(left_speed) < 0.05: left_dir = 0
        
        right_dir = 1 if right_speed >= 0 else -1
        if abs(right_speed) < 0.05: right_dir = 0
        
        self.set_motor('left', left_dir, left_pwm)
        self.set_motor('right', right_dir, right_pwm)

    def destroy_node(self):
        if self.gpio_handle:
            # Stop motors
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
