#!/usr/bin/env python3
"""
ROS2 Tank Motor Driver - DEEP DEBUG VERSION
Logs every step of the process to diagnose stalling/signal issues.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int32
import subprocess
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
        self.ENA = 16
        self.ENB = 13
        self.IN1 = 20
        self.IN2 = 21
        self.IN3 = 19
        self.IN4 = 26
        
        self.speed_percent = 60
        self.pwm_freq = 1000
        self.gpio_handle = None
        
        # Debug counters
        self.msg_count = 0
        self.gpio_write_count = 0
        
        # Initialize GPIO
        if GPIO_AVAILABLE:
            try:
                self.gpio_handle = lgpio.gpiochip_open(4)
                for pin in [self.ENA, self.ENB, self.IN1, self.IN2, self.IN3, self.IN4]:
                    lgpio.gpio_claim_output(self.gpio_handle, pin, 0)
                self.get_logger().info('GPIO initialized successfully')
            except Exception as e:
                self.get_logger().error(f'GPIO init failed: {e}')
                self.gpio_handle = None
        
        # Subscriptions
        self.joy_sub = self.create_subscription(Twist, 'cmd_vel_joy', self.cmd_vel_callback, 10)
        self.cmd_sub = self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        self.speed_sub = self.create_subscription(Int32, 'tank/speed', self.speed_callback, 10)
        
        # Timer to check voltage/throttling every 1s
        self.create_timer(1.0, self.check_system_health)
        
        self.get_logger().info('DEBUG Motor Driver Ready')

    def check_system_health(self):
        try:
            # Check for undervoltage/throttling
            result = subprocess.run(['vcgencmd', 'get_throttled'], capture_output=True, text=True)
            throttled = result.stdout.strip()
            # 0x0 means normal. Anything else indicates past or present issues.
            # 0x50000 or 0x50005 are common for undervoltage.
            if throttled != "throttled=0x0":
                self.get_logger().warn(f"SYSTEM ALERT: {throttled}")
        except Exception as e:
            pass

    def speed_callback(self, msg):
        self.speed_percent = max(0, min(100, msg.data))
        self.get_logger().info(f'Speed set to {self.speed_percent}%')

    def log_gpio(self, side, pin_fwd, pin_bwd, pwm_pin, dir_val, pwm_val):
        # Helper to log exactly what we are sending to the hardware
        state = "STOP"
        if dir_val > 0: state = "FWD"
        elif dir_val < 0: state = "BWD"
        
        self.get_logger().info(f"GPIO {side}: {state} (PWM={pwm_val}) -> Pins: {pin_fwd}={1 if dir_val>0 else 0}, {pin_bwd}={1 if dir_val<0 else 0}")

    def set_motor(self, side, direction, pwm_val):
        if not self.gpio_handle:
            self.get_logger().error("No GPIO handle!")
            return
            
        pwm_val = max(0, min(100, int(pwm_val)))
        
        if side == 'left':
            pwm_pin = self.ENA
            in1 = self.IN1
            in2 = self.IN2
        else:
            pwm_pin = self.ENB
            in1 = self.IN3
            in2 = self.IN4
            
        # Log the attempt
        # self.log_gpio(side, in1, in2, pwm_pin, direction, pwm_val)
            
        try:
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
            self.gpio_write_count += 1
        except Exception as e:
            self.get_logger().error(f"GPIO WRITE ERROR: {e}")

    def cmd_vel_callback(self, msg):
        self.msg_count += 1
        
        linear = msg.linear.x
        angular = msg.angular.z
        
        # Log input every 10 messages or if it's a significant command
        if abs(linear) > 0.1 or abs(angular) > 0.1 or self.msg_count % 20 == 0:
             self.get_logger().info(f"RX: lin={linear:.2f} ang={angular:.2f}")

        # Deadzone
        if abs(linear) < 0.1 and abs(angular) < 0.1:
            self.set_motor('left', 0, 0)
            self.set_motor('right', 0, 0)
            return

        # Turn Handling
        if abs(linear) < 0.2 and abs(angular) > 0.2:
            turn_power = self.speed_percent
            if angular > 0: # Left Turn
                self.get_logger().info(f"ACTION: Turn LEFT (Power={turn_power})")
                self.set_motor('left', -1, turn_power)
                self.set_motor('right', 1, turn_power)
            else: # Right Turn
                self.get_logger().info(f"ACTION: Turn RIGHT (Power={turn_power})")
                self.set_motor('left', 1, turn_power)
                self.set_motor('right', -1, turn_power)
            return

        # Diff Drive
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
        
        if self.msg_count % 10 == 0:
             self.get_logger().info(f"ACTION: Drive L={left_dir}({left_pwm}%) R={right_dir}({right_pwm}%)")
             
        self.set_motor('left', left_dir, left_pwm)
        self.set_motor('right', right_dir, right_pwm)

    def destroy_node(self):
        if self.gpio_handle:
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
