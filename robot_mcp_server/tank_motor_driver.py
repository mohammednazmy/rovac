#!/usr/bin/env python3
"""
ROS2 Tank Motor Driver - BINARY TURN VERSION (DIAGNOSTIC)
Eliminates PWM jitter during turns by using 100% POWER ONLY.
Tests if the "jitter" is caused by weak PWM signals vs carpet friction.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
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
        self.ENA = 16; self.ENB = 13
        self.IN1 = 20; self.IN2 = 21
        self.IN3 = 19; self.IN4 = 26
        
        self.gpio_handle = None
        self.last_cmd_time = self.get_clock().now()
        
        if GPIO_AVAILABLE:
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)
                for pin in [self.ENA, self.ENB, self.IN1, self.IN2, self.IN3, self.IN4]:
                    lgpio.gpio_claim_output(self.gpio_handle, pin, 0)
                self.get_logger().info('GPIO Ready: BINARY MODE')
            except Exception as e:
                self.get_logger().error(f'GPIO Fail: {e}')

        self.create_subscription(Twist, 'cmd_vel_joy', self.cmd_vel_callback, 10)
        self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        
        # Deadman timer
        self.create_timer(0.2, self.check_timeout)

    def cmd_vel_callback(self, msg):
        self.last_cmd_time = self.get_clock().now()
        
        linear = msg.linear.x
        angular = msg.angular.z
        
        # BINARY LOGIC
        # If stick is moved, go 100%. No smooth, no 50%.
        
        # TURN LOGIC (Dominates)
        if abs(angular) > 0.2:
            if angular > 0: # LEFT
                self.set_state("LEFT_FULL")
            else: # RIGHT
                self.set_state("RIGHT_FULL")
            return
            
        # DRIVE LOGIC
        if abs(linear) > 0.2:
            if linear > 0: # FWD
                self.set_state("FWD_FULL")
            else: # BWD
                self.set_state("BWD_FULL")
            return
            
        # STOP
        self.set_state("STOP")

    def set_state(self, state):
        if not self.gpio_handle: return
        
        # Default ALL OFF
        l_fwd=0; l_bwd=0; l_pwm=0
        r_fwd=0; r_bwd=0; r_pwm=0
        
        if state == "FWD_FULL":
            l_fwd=1; l_pwm=100
            r_fwd=1; r_pwm=100
        elif state == "BWD_FULL":
            l_bwd=1; l_pwm=100
            r_bwd=1; r_pwm=100
        elif state == "LEFT_FULL":
            l_bwd=1; l_pwm=100  # Left spins back
            r_fwd=1; r_pwm=100  # Right spins fwd
        elif state == "RIGHT_FULL":
            l_fwd=1; l_pwm=100  # Left spins fwd
            r_bwd=1; r_pwm=100  # Right spins back
            
        # Apply Left
        lgpio.gpio_write(self.gpio_handle, self.IN1, l_fwd)
        lgpio.gpio_write(self.gpio_handle, self.IN2, l_bwd)
        lgpio.tx_pwm(self.gpio_handle, self.ENA, 100, l_pwm) # 100Hz
        
        # Apply Right
        lgpio.gpio_write(self.gpio_handle, self.IN3, r_fwd)
        lgpio.gpio_write(self.gpio_handle, self.IN4, r_bwd)
        lgpio.tx_pwm(self.gpio_handle, self.ENB, 100, r_pwm) # 100Hz

    def check_timeout(self):
        if (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9 > 0.5:
            self.set_state("STOP")

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