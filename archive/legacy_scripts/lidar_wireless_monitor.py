#!/usr/bin/env python3
"""
LIDAR Wireless Health Monitor — reports /scan topic status to systemd journal.

Subscribes to /scan (best_effort QoS) and logs health every 30 seconds:
  - Receive rate (Hz)
  - Average valid points per scan
  - Latest RPM (from /diagnostics)
  - Checksum errors (from /diagnostics)

Designed to run as a systemd service alongside the micro-ROS Agent.
The LIDAR ESP32 publishes /scan wirelessly — this monitor verifies the data
is flowing through the Agent to the ROS2 network.

Exit codes:
  0 = clean shutdown
  1 = startup failure
"""
import math
import signal
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan
from diagnostic_msgs.msg import DiagnosticArray


class LidarMonitor(Node):
    def __init__(self):
        super().__init__('lidar_wireless_monitor')

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

        self.scan_sub = self.create_subscription(
            LaserScan, '/scan', self._scan_cb, qos)
        self.diag_sub = self.create_subscription(
            DiagnosticArray, '/diagnostics', self._diag_cb, qos)

        self.report_timer = self.create_timer(30.0, self._report)

        # Scan tracking
        self._scan_times = []
        self._valid_points = []
        self._last_scan_time = 0.0

        # Diagnostics from LIDAR ESP32
        self._lidar_rpm = 0.0
        self._checksum_errors = 0
        self._lidar_rssi = 0

        # Stale tracking
        self._no_data_reports = 0

        self.get_logger().info('LIDAR wireless monitor started')

    def _scan_cb(self, msg: LaserScan):
        now = time.time()
        self._scan_times.append(now)
        valid = sum(1 for r in msg.ranges if not math.isinf(r) and r > 0)
        self._valid_points.append(valid)
        self._last_scan_time = now

    def _diag_cb(self, msg: DiagnosticArray):
        for status in msg.status:
            if 'LIDAR' not in status.name:
                continue
            for kv in status.values:
                if kv.key == 'lidar_rpm':
                    self._lidar_rpm = float(kv.value)
                elif kv.key == 'checksum_errors':
                    self._checksum_errors = int(kv.value)
                elif kv.key == 'wifi_rssi':
                    self._lidar_rssi = int(kv.value)

    def _report(self):
        now = time.time()

        if not self._scan_times:
            self._no_data_reports += 1
            if self._no_data_reports <= 2:
                self.get_logger().warn('No /scan data received (waiting for LIDAR ESP32)')
            elif self._no_data_reports % 10 == 0:
                self.get_logger().error(
                    f'No /scan data for {self._no_data_reports * 30}s '
                    '— check LIDAR ESP32 power and WiFi')
            return

        self._no_data_reports = 0

        # Calculate rate from scans in last 30s window
        cutoff = now - 30.0
        recent = [t for t in self._scan_times if t > cutoff]
        recent_valid = [v for t, v in zip(self._scan_times, self._valid_points)
                        if t > cutoff]

        if len(recent) >= 2:
            dt = recent[-1] - recent[0]
            hz = (len(recent) - 1) / dt if dt > 0 else 0
        else:
            hz = 0

        avg_valid = sum(recent_valid) / len(recent_valid) if recent_valid else 0
        stale_s = now - self._last_scan_time

        self.get_logger().info(
            f'/scan: {hz:.1f} Hz, {avg_valid:.0f}/360 avg pts, '
            f'RPM={self._lidar_rpm:.0f}, '
            f'RSSI={self._lidar_rssi} dBm, '
            f'chksum_err={self._checksum_errors}')

        if hz < 2.0 and len(recent) > 2:
            self.get_logger().warn(
                f'Low scan rate: {hz:.1f} Hz (expected ~5 Hz)')

        # Keep only last 30s of data
        self._scan_times = recent
        self._valid_points = recent_valid


def main():
    rclpy.init()
    node = LidarMonitor()

    def shutdown(sig, frame):
        node.get_logger().info('Shutting down LIDAR monitor')
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
