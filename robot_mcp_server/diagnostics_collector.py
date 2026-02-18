#!/usr/bin/env python3
"""
Diagnostics Collector for ROVAC Robot
Collects system logs, ROS logs, and performance metrics for analysis
"""

import rclpy
from rclpy.node import Node
from diagnostic_msgs.msg import DiagnosticArray
from std_msgs.msg import String
import subprocess
import psutil
import time
import json
import os
from datetime import datetime
import threading


class DiagnosticsCollector(Node):
    def __init__(self):
        super().__init__("diagnostics_collector")

        # Parameters
        self.declare_parameter("log_directory", "/tmp/rovac_logs")
        self.declare_parameter("collection_interval", 30.0)  # seconds
        self.declare_parameter("max_log_files", 10)

        self.log_directory = self.get_parameter("log_directory").value
        self.collection_interval = self.get_parameter("collection_interval").value
        self.max_log_files = self.get_parameter("max_log_files").value

        # Create log directory if it doesn't exist
        os.makedirs(self.log_directory, exist_ok=True)

        # State variables
        self.diagnostics_data = []
        self.system_metrics = {}

        # Subscribers
        self.diagnostics_sub = self.create_subscription(
            DiagnosticArray, "/diagnostics", self.diagnostics_callback, 10
        )
        self.health_status_sub = self.create_subscription(
            String, "/system/health_status", self.health_status_callback, 10
        )

        # Timer for periodic data collection
        self.timer = self.create_timer(
            self.collection_interval, self.collect_system_diagnostics
        )

        # Background thread for continuous monitoring
        self.monitoring_thread = threading.Thread(
            target=self.continuous_monitoring, daemon=True
        )
        self.monitoring_thread.start()

        self.get_logger().info("Diagnostics Collector initialized")
        self.get_logger().info(f"Log directory: {self.log_directory}")

    def diagnostics_callback(self, msg):
        """Callback for diagnostic messages"""
        # Store diagnostic data
        timestamp = datetime.now().isoformat()
        diagnostic_entry = {
            "timestamp": timestamp,
            "status": [self.diagnostic_status_to_dict(status) for status in msg.status],
        }
        self.diagnostics_data.append(diagnostic_entry)

        # Keep only recent diagnostics
        if len(self.diagnostics_data) > 100:
            self.diagnostics_data = self.diagnostics_data[-50:]

    def diagnostic_status_to_dict(self, status):
        """Convert diagnostic status to dictionary"""
        return {
            "name": status.name,
            "hardware_id": status.hardware_id,
            "level": status.level,
            "message": status.message,
            "values": {kv.key: kv.value for kv in status.values},
        }

    def health_status_callback(self, msg):
        """Callback for system health status"""
        try:
            health_data = json.loads(msg.data)
            self.system_metrics = health_data
        except json.JSONDecodeError:
            self.get_logger().warn("Failed to parse health status JSON")

    def collect_system_diagnostics(self):
        """Collect system-level diagnostics"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"rovac_diagnostics_{timestamp}.json"
        log_filepath = os.path.join(self.log_directory, log_filename)

        # Collect comprehensive system information
        diagnostics_report = {
            "timestamp": datetime.now().isoformat(),
            "system_info": self.get_system_info(),
            "process_info": self.get_process_info(),
            "network_info": self.get_network_info(),
            "recent_diagnostics": self.diagnostics_data,
            "system_metrics": self.system_metrics,
            "ros_info": self.get_ros_info(),
        }

        # Save to file
        try:
            with open(log_filepath, "w") as f:
                json.dump(diagnostics_report, f, indent=2)
            self.get_logger().info(f"Diagnostics saved to {log_filepath}")

            # Clean up old log files
            self.cleanup_old_logs()

        except Exception as e:
            self.get_logger().error(f"Failed to save diagnostics: {e}")

    def get_system_info(self):
        """Get system information"""
        try:
            return {
                "cpu_count": psutil.cpu_count(),
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent,
                },
                "disk": {
                    "total": psutil.disk_usage("/").total,
                    "free": psutil.disk_usage("/").free,
                    "percent": psutil.disk_usage("/").percent,
                },
                "boot_time": psutil.boot_time(),
            }
        except Exception as e:
            self.get_logger().error(f"Error getting system info: {e}")
            return {}

    def get_process_info(self):
        """Get information about key processes"""
        processes = []
        try:
            for proc in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent"]
            ):
                # Focus on ROS-related processes
                if any(
                    keyword in proc.info["name"].lower()
                    for keyword in ["ros", "python", "node"]
                ):
                    processes.append(proc.info)
        except Exception as e:
            self.get_logger().error(f"Error getting process info: {e}")

        return processes[:20]  # Limit to top 20

    def get_network_info(self):
        """Get network interface information"""
        try:
            net_info = {}
            for interface, addrs in psutil.net_if_addrs().items():
                net_info[interface] = []
                for addr in addrs:
                    net_info[interface].append(
                        {
                            "family": str(addr.family),
                            "address": addr.address,
                            "netmask": addr.netmask,
                        }
                    )
            return net_info
        except Exception as e:
            self.get_logger().error(f"Error getting network info: {e}")
            return {}

    def get_ros_info(self):
        """Get ROS-related information"""
        ros_info = {}
        try:
            # Get ROS topics
            result = subprocess.run(
                ["ros2", "topic", "list"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                ros_info["topics"] = result.stdout.strip().split("\n")

            # Get ROS nodes
            result = subprocess.run(
                ["ros2", "node", "list"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                ros_info["nodes"] = result.stdout.strip().split("\n")

            # Get ROS services
            result = subprocess.run(
                ["ros2", "service", "list"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                ros_info["services"] = result.stdout.strip().split("\n")

        except subprocess.TimeoutExpired:
            self.get_logger().warn("Timeout getting ROS info")
        except Exception as e:
            self.get_logger().error(f"Error getting ROS info: {e}")

        return ros_info

    def cleanup_old_logs(self):
        """Remove old log files to prevent disk space issues"""
        try:
            log_files = [
                f
                for f in os.listdir(self.log_directory)
                if f.startswith("rovac_diagnostics_")
            ]
            log_files.sort()

            # Remove oldest files if we have too many
            if len(log_files) > self.max_log_files:
                files_to_remove = log_files[: len(log_files) - self.max_log_files]
                for filename in files_to_remove:
                    filepath = os.path.join(self.log_directory, filename)
                    os.remove(filepath)
                    self.get_logger().info(f"Removed old log file: {filename}")

        except Exception as e:
            self.get_logger().error(f"Error cleaning up logs: {e}")

    def continuous_monitoring(self):
        """Continuous monitoring in background thread"""
        while rclpy.ok():
            try:
                # Monitor system resources continuously
                cpu_percent = psutil.cpu_percent(interval=5)
                memory_percent = psutil.virtual_memory().percent

                # Log warnings if resources are constrained
                if cpu_percent > 85.0:
                    self.get_logger().warn(f"High CPU usage: {cpu_percent}%")

                if memory_percent > 85.0:
                    self.get_logger().warn(f"High memory usage: {memory_percent}%")

            except Exception as e:
                self.get_logger().error(f"Error in continuous monitoring: {e}")

            time.sleep(10)  # Check every 10 seconds

    def get_recent_diagnostics_summary(self):
        """Get a summary of recent diagnostics"""
        if not self.diagnostics_data:
            return "No diagnostics data available"

        # Get the most recent diagnostic entry
        latest = self.diagnostics_data[-1]
        summary = f"Latest diagnostics ({latest['timestamp']}):\n"

        for status in latest["status"]:
            level_str = (
                ["OK", "WARN", "ERROR", "STALE"][status["level"]]
                if status["level"] < 4
                else "UNKNOWN"
            )
            summary += f"  {status['name']}: {level_str} - {status['message']}\n"

        return summary


def main(args=None):
    rclpy.init(args=args)
    node = DiagnosticsCollector()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
