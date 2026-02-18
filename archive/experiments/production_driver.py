#!/usr/bin/env python3
"""
ROS2 Tank Motor Driver - FINAL PRODUCTION VERSION
Restored to the robust logic verified by manual testing, now that power is fixed.
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
        
        self.speed_percent = 100  # Full power for skid steering
        self.pwm_freq = 1000
        self.gpio_handle = None
        
        # Initialize GPIO
        if GPIO_AVAILABLE:
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)
                for pin in [self.ENA, self.ENB, self.IN1, self.IN2, self.IN3, self.IN4]:
                    lgpio.gpio_claim_output(self.gpio_handle, pin, 0)
                self.get_logger().info('GPIO initialized - High Performance Mode')
            except Exception as e:
                self.get_logger().error(f'GPIO init failed: {e}')
                self.gpio_handle = None
        
        # Subscriptions
        self.create_subscription(Twist, 'cmd_vel_joy', self.cmd_vel_callback, 10)
        self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        self.create_subscription(Int32, 'tank/speed', self.speed_callback, 10)
        
        self.get_logger().info('Tank motor driver ready')

    def speed_callback(self, msg):
        self.speed_percent = max(0, min(100, msg.data))
        self.get_logger().info(f'Speed set to {self.speed_percent}%')

    def set_motor(self, side, direction, pwm_val):
        if not self.gpio_handle: return
        
        pwm_val = max(0, min(100, int(pwm_val)))
        
        if side == 'left':
            pwm_pin = self.ENA; in1 = self.IN1; in2 = self.IN2
        else:
            pwm_pin = self.ENB; in1 = self.IN3; in2 = self.IN4
            
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
            
        lgpio.tx_pwm(self.gpio_handle, pwm_pin, self.pwm_freq, pwm_val)

    def cmd_vel_callback(self, msg):
        linear = msg.linear.x
        angular = msg.angular.z
        
        # Deadzone
        if abs(linear) < 0.1 and abs(angular) < 0.1:
            self.set_motor('left', 0, 0)
            self.set_motor('right', 0, 0)
            return

        # Explicit Turn Handling
        if abs(linear) < 0.2 and abs(angular) > 0.2:
            turn_power = self.speed_percent
            if angular > 0: # Left Turn
                self.set_motor('left', -1, turn_power)
                self.set_motor('right', 1, turn_power)
            else: # Right Turn
                self.set_motor('left', 1, turn_power)
                self.set_motor('right', -1, turn_power)
            return

        # Differential Drive
        left_speed = linear - angular
        right_speed = linear + angular
        
        max_val = max(abs(left_speed), abs(right_speed))
        if max_val > 1.0:
            left_speed /= max_val
            right_speed /= max_val
            
        left_pwm = int(abs(left_speed) * self.speed_percent)
        right_pwm = int(abs(right_speed) * self.speed_percent)
        
        left_dir = 1 if left_speed >= 0 else -1
        if abs(left_speed) < 0.05: left_dir = 0
        right_dir = 1 if right_speed >= 0 else -1
        if abs(right_speed) < 0.05: right_dir = 0
        
        self.set_motor('left', left_dir, left_pwm)
        self.set_motor('right', right_dir, right_pwm)

    def destroy_node(self):
        if self.gpio_handle: lgpio.gpiochip_close(self.gpio_handle)
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = TankMotorDriver()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
