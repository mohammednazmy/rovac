#!/usr/bin/env python3
"""
System Health Monitor for ROVAC Robot
Monitors hardware, software, and network status with automatic recovery mechanisms
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from sensor_msgs.msg import BatteryState
import psutil
import time
import subprocess
import threading
import json
import os
from datetime import datetime


class SystemHealthMonitor(Node):
    def __init__(self):
        super().__init__("system_health_monitor")

        # Publishers
        self.diagnostics_pub = self.create_publisher(
            DiagnosticArray, "/diagnostics", 10
        )
        self.health_status_pub = self.create_publisher(
            String, "/system/health_status", 10
        )
        self.battery_pub = self.create_publisher(
            BatteryState, "/sensors/battery_state", 10
        )

        # Subscribers for external health checks
        self.motor_health_sub = self.create_subscription(
            Bool, "/system/motor_health", self.motor_health_callback, 10
        )
        self.sensor_health_sub = self.create_subscription(
            Bool, "/system/sensor_health", self.sensor_health_callback, 10
        )

        # Health status tracking
        self.motor_healthy = True
        self.sensor_healthy = True
        self.network_healthy = True
        self.cpu_healthy = True
        self.memory_healthy = True

        # Timer for periodic health checks
        self.timer = self.create_timer(5.0, self.perform_health_check)

        # Recovery attempt tracking
        self.recovery_attempts = {}
        self.max_recovery_attempts = 3

        self.get_logger().info("System Health Monitor initialized")

    def motor_health_callback(self, msg):
        """Callback for motor health status"""
        self.motor_healthy = msg.data

    def sensor_health_callback(self, msg):
        """Callback for sensor health status"""
        self.sensor_healthy = msg.data

    def check_cpu_usage(self):
        """Check CPU usage levels"""
        cpu_percent = psutil.cpu_percent(interval=1)
        self.cpu_healthy = cpu_percent < 85.0  # Alert if over 85%
        return cpu_percent

    def check_memory_usage(self):
        """Check memory usage levels"""
        memory = psutil.virtual_memory()
        self.memory_healthy = memory.percent < 85.0  # Alert if over 85%
        return memory.percent

    def check_network_connectivity(self):
        """Check network connectivity to Pi"""
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", "192.168.1.200"],
                capture_output=True,
                timeout=5,
            )
            self.network_healthy = result.returncode == 0
            return self.network_healthy
        except subprocess.TimeoutExpired:
            self.network_healthy = False
            return False

    def check_battery_level(self):
        """Simulate battery level checking (would interface with actual battery sensor)"""
        # In a real implementation, this would read from a battery sensor
        # For now, we'll simulate a reasonable battery level
        battery_msg = BatteryState()
        battery_msg.voltage = 12.0  # volts
        battery_msg.percentage = 0.85  # 85%
        battery_msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
        battery_msg.present = True
        battery_msg.header.stamp = self.get_clock().now().to_msg()

        self.battery_pub.publish(battery_msg)
        return 0.85

    def check_ros_nodes(self):
        """Check if critical ROS nodes are running"""
        try:
            # This would typically use ros2node or check topic availability
            # For now, we'll return a simulated result
            return True
        except Exception as e:
            self.get_logger().warn(f"Error checking ROS nodes: {e}")
            return False

    def attempt_recovery(self, component):
        """Attempt automatic recovery for a failed component"""
        if component not in self.recovery_attempts:
            self.recovery_attempts[component] = 0

        if self.recovery_attempts[component] >= self.max_recovery_attempts:
            self.get_logger().error(f"Max recovery attempts reached for {component}")
            return False

        self.recovery_attempts[component] += 1
        self.get_logger().info(
            f"Attempting recovery for {component} (attempt {self.recovery_attempts[component]})"
        )

        try:
            if component == "network":
                # Network recovery actions
                subprocess.run(
                    ["sudo", "systemctl", "restart", "networking"], timeout=10
                )
                time.sleep(5)
                return self.check_network_connectivity()

            elif component == "ros_nodes":
                # Restart critical nodes
                subprocess.run(
                    [
                        "ssh",
                        "pi@192.168.1.200",
                        "sudo systemctl restart rovac-edge.target",
                    ],
                    timeout=15,
                )
                time.sleep(10)
                return self.check_ros_nodes()

            elif component == "lidar":
                # Restart LIDAR service
                subprocess.run(
                    [
                        "ssh",
                        "pi@192.168.1.200",
                        "sudo systemctl restart rovac-edge-lidar.service",
                    ],
                    timeout=10,
                )
                time.sleep(5)
                return True

        except Exception as e:
            self.get_logger().error(f"Recovery attempt for {component} failed: {e}")
            return False

    def perform_health_check(self):
        """Perform comprehensive system health check"""
        self.get_logger().debug("Performing system health check...")

        # Perform all checks
        cpu_usage = self.check_cpu_usage()
        memory_usage = self.check_memory_usage()
        network_ok = self.check_network_connectivity()
        battery_level = self.check_battery_level()
        ros_nodes_ok = self.check_ros_nodes()

        # Create diagnostic array
        diag_array = DiagnosticArray()
        diag_array.header.stamp = self.get_clock().now().to_msg()

        # CPU Status
        cpu_status = DiagnosticStatus()
        cpu_status.name = "CPU Usage"
        cpu_status.hardware_id = "macbook_pro"
        cpu_status.level = (
            DiagnosticStatus.OK if self.cpu_healthy else DiagnosticStatus.WARN
        )
        cpu_status.message = f"CPU usage: {cpu_usage:.1f}%"
        cpu_status.values = [
            {"key": "usage_percent", "value": str(cpu_usage)},
            {"key": "healthy", "value": str(self.cpu_healthy)},
        ]
        diag_array.status.append(cpu_status)

        # Memory Status
        mem_status = DiagnosticStatus()
        mem_status.name = "Memory Usage"
        mem_status.hardware_id = "macbook_pro"
        mem_status.level = (
            DiagnosticStatus.OK if self.memory_healthy else DiagnosticStatus.WARN
        )
        mem_status.message = f"Memory usage: {memory_usage:.1f}%"
        mem_status.values = [
            {"key": "usage_percent", "value": str(memory_usage)},
            {"key": "healthy", "value": str(self.memory_healthy)},
        ]
        diag_array.status.append(mem_status)

        # Network Status
        net_status = DiagnosticStatus()
        net_status.name = "Network Connectivity"
        net_status.hardware_id = "rovac_network"
        net_status.level = DiagnosticStatus.OK if network_ok else DiagnosticStatus.ERROR
        net_status.message = "Connected to Pi" if network_ok else "Cannot reach Pi"
        net_status.values = [
            {"key": "pi_reachable", "value": str(network_ok)},
            {"key": "pi_ip", "value": "192.168.1.200"},
        ]
        diag_array.status.append(net_status)

        # Battery Status
        battery_status = DiagnosticStatus()
        battery_status.name = "Battery Level"
        battery_status.hardware_id = "yahboom_g1_tank"
        battery_status.level = (
            DiagnosticStatus.OK if battery_level > 0.2 else DiagnosticStatus.WARN
        )
        battery_status.message = f"Battery level: {battery_level * 100:.1f}%"
        battery_status.values = [
            {"key": "level_percent", "value": str(battery_level * 100)},
            {"key": "voltage", "value": "12.0"},
        ]
        diag_array.status.append(battery_status)

        # Overall System Status
        overall_healthy = (
            self.cpu_healthy
            and self.memory_healthy
            and network_ok
            and self.motor_healthy
            and self.sensor_healthy
            and ros_nodes_ok
        )

        overall_status = DiagnosticStatus()
        overall_status.name = "Overall System Health"
        overall_status.hardware_id = "rovac_robot"
        overall_status.level = (
            DiagnosticStatus.OK if overall_healthy else DiagnosticStatus.ERROR
        )
        overall_status.message = (
            "System healthy" if overall_healthy else "System issues detected"
        )
        diag_array.status.append(overall_status)

        # Publish diagnostics
        self.diagnostics_pub.publish(diag_array)

        # Publish simple health status
        health_msg = String()
        health_msg.data = json.dumps(
            {
                "timestamp": datetime.now().isoformat(),
                "healthy": overall_healthy,
                "components": {
                    "cpu": self.cpu_healthy,
                    "memory": self.memory_healthy,
                    "network": network_ok,
                    "motors": self.motor_healthy,
                    "sensors": self.sensor_healthy,
                    "ros_nodes": ros_nodes_ok,
                },
                "metrics": {
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory_usage,
                    "battery_level": battery_level,
                },
            }
        )
        self.health_status_pub.publish(health_msg)

        # Attempt recovery if needed
        if not network_ok:
            self.attempt_recovery("network")
        elif not ros_nodes_ok:
            self.attempt_recovery("ros_nodes")

        self.get_logger().debug(
            f"Health check complete. System healthy: {overall_healthy}"
        )


def main(args=None):
    rclpy.init(args=args)
    node = SystemHealthMonitor()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
