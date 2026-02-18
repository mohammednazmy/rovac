#!/usr/bin/env python3
"""
ROS2 Tank Motor Driver - LOW POWER / SOFT START VERSION
Designed to operate under undervoltage conditions by preventing current spikes.
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
        
        self.ENA = 16; self.ENB = 13
        self.IN1 = 20; self.IN2 = 21
        self.IN3 = 19; self.IN4 = 26
        
        # POWER CAP: Keep this low to prevent voltage collapse
        self.MAX_POWER = 45 
        
        self.current_left_pwm = 0
        self.current_right_pwm = 0
        self.target_left_pwm = 0
        self.target_right_pwm = 0
        self.target_left_dir = 0
        self.target_right_dir = 0
        
        self.gpio_handle = None
        
        if GPIO_AVAILABLE:
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)
                for pin in [self.ENA, self.ENB, self.IN1, self.IN2, self.IN3, self.IN4]:
                    lgpio.gpio_claim_output(self.gpio_handle, pin, 0)
                self.get_logger().info(f'GPIO Ready - LOW POWER MODE (Max {self.MAX_POWER}%)')
            except Exception as e:
                self.get_logger().error(f'GPIO Fail: {e}')

        # Subscribe
        self.create_subscription(Twist, 'cmd_vel_joy', self.cmd_vel_callback, 10)
        self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        
        # RAMP TIMER: Update PWM at 20Hz for smooth ramping
        self.create_timer(0.05, self.update_motors)

    def cmd_vel_callback(self, msg):
        linear = msg.linear.x
        angular = msg.angular.z
        
        # Deadzone
        if abs(linear) < 0.1 and abs(angular) < 0.1:
            self.target_left_pwm = 0
            self.target_right_pwm = 0
            self.target_left_dir = 0
            self.target_right_dir = 0
            return

        # Simple logic for stability
        left = linear - angular
        right = linear + angular
        
        # Normalize
        m = max(abs(left), abs(right))
        if m > 1.0:
            left /= m
            right /= m
            
        # Direction
        self.target_left_dir = 1 if left >= 0 else -1
        self.target_right_dir = 1 if right >= 0 else -1
        
        # Target PWM (Capped)
        self.target_left_pwm = int(abs(left) * self.MAX_POWER)
        self.target_right_pwm = int(abs(right) * self.MAX_POWER)

    def update_motors(self):
        if not self.gpio_handle: return
        
        # RAMPING LOGIC: Change PWM by max 5% per cycle (0.05s)
        # This prevents current spikes
        step = 5
        
        if self.current_left_pwm < self.target_left_pwm:
            self.current_left_pwm = min(self.current_left_pwm + step, self.target_left_pwm)
        elif self.current_left_pwm > self.target_left_pwm:
            self.current_left_pwm = max(self.current_left_pwm - step, self.target_left_pwm)
            
        if self.current_right_pwm < self.target_right_pwm:
            self.current_right_pwm = min(self.current_right_pwm + step, self.target_right_pwm)
        elif self.current_right_pwm > self.target_right_pwm:
            self.current_right_pwm = max(self.current_right_pwm - step, self.target_right_pwm)
            
        # Apply to hardware
        self.set_gpio('left', self.target_left_dir, self.current_left_pwm)
        self.set_gpio('right', self.target_right_dir, self.current_right_pwm)

    def set_gpio(self, side, d, pwm):
        if side == 'left':
            pins = (self.IN1, self.IN2, self.ENA)
        else:
            pins = (self.IN3, self.IN4, self.ENB)
            
        if pwm == 0:
            lgpio.gpio_write(self.gpio_handle, pins[0], 0)
            lgpio.gpio_write(self.gpio_handle, pins[1], 0)
        elif d > 0:
            lgpio.gpio_write(self.gpio_handle, pins[0], 1)
            lgpio.gpio_write(self.gpio_handle, pins[1], 0)
        else:
            lgpio.gpio_write(self.gpio_handle, pins[0], 0)
            lgpio.gpio_write(self.gpio_handle, pins[1], 1)
            
        lgpio.tx_pwm(self.gpio_handle, pins[2], 1000, pwm)

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
