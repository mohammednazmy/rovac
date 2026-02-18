#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import time

class CmdVelMonitor(Node):
    def __init__(self):
        super().__init__('cmd_vel_monitor')
        self.subscription = self.create_subscription(
            Twist,
            'cmd_vel_joy',
            self.listener_callback,
            10)
        self.get_logger().info('Monitoring /cmd_vel_joy...')
        self.last_print = 0

    def listener_callback(self, msg):
        now = time.time()
        # Print every 0.5s or if value changes significantly (simple logic for now: just print all non-zero or periodic zero)
        # Actually, let's just print everything but rate-limited to avoid spamming the log buffer if needed,
        # BUT for diagnosing "stops moving", we want to see the sequence.
        
        log_msg = f"CMD: lin={msg.linear.x:.2f} ang={msg.angular.z:.2f}"
        print(log_msg, flush=True)

def main(args=None):
    rclpy.init(args=args)
    cmd_vel_monitor = CmdVelMonitor()
    rclpy.spin(cmd_vel_monitor)
    cmd_vel_monitor.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
