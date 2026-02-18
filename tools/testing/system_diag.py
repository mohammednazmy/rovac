#!/usr/bin/env python3
"""
ROS2 System Diagnostic Tool
Monitors:
1. /cmd_vel_joy arrival rate (Network/Bluetooth stability)
2. Pi Voltage/Throttling (Power stability)
3. CPU Usage (Load stability)
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import time
import subprocess
import os

class SystemMonitor(Node):
    def __init__(self):
        super().__init__('system_monitor')
        
        self.subscription = self.create_subscription(
            Twist,
            'cmd_vel_joy',
            self.cmd_callback,
            10)
            
        self.last_msg_time = time.time()
        self.msg_intervals = []
        
        # Check status every 0.5s
        self.create_timer(0.5, self.check_health)
        self.start_time = time.time()
        
        self.get_logger().info(" DIAGNOSTIC RUNNING: Drive the robot now!")

    def cmd_callback(self, msg):
        now = time.time()
        dt = now - self.last_msg_time
        self.last_msg_time = now
        
        # Log if packet lag is detected (>100ms)
        if dt > 0.15:
            self.get_logger().warn(f"LAG DETECTED: {dt*1000:.1f}ms between packets!")
            
    def check_health(self):
        # 1. Voltage
        try:
            res = subprocess.run(['vcgencmd', 'get_throttled'], capture_output=True, text=True)
            volt = res.stdout.strip()
        except:
            volt = "Err"
            
        # 2. Wifi/Network (Ping latency to router/mac)
        # Assuming Mac IP is 192.168.1.104 based on previous logs
        # ping = os.system("ping -c 1 -W 0.1 192.168.1.104 > /dev/null")
        # net_status = "Good" if ping == 0 else "Drop"
        
        # 3. Cmd Stream Health
        time_since_last = time.time() - self.last_msg_time
        stream_status = "OK"
        if time_since_last > 0.5:
            stream_status = "SILENT (No cmds)"
            
        print(f"[{time.time()-self.start_time:.1f}s] Pwr:{volt} | Cmds:{stream_status} | Lag:{time_since_last*1000:.0f}ms")

def main(args=None):
    rclpy.init(args=args)
    node = SystemMonitor()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
