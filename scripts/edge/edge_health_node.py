#!/usr/bin/env python3
"""
ROVAC Edge Health Node — publishes comprehensive Pi edge health to ROS2.

Publishes JSON to /rovac/edge/health (std_msgs/String) every 5 seconds:
  - System stats (CPU, memory, disk, temperature)
  - Systemd service status for all edge services
  - Network reachability (Mac brain)
  - USB device presence for core peripherals
  - Transport process info for the motor driver (legacy field name: "agent")

Runs on Raspberry Pi 5 (Ubuntu 24.04, ROS2 Jazzy).
Does NOT depend on psutil — reads /proc and /sys directly.

Exit codes:
  0 = clean shutdown
  1 = startup failure
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# Edge services to monitor
SERVICES = [
    'rovac-edge-motor-driver',
    'rovac-edge-rplidar-c1',
    'rovac-edge-mux',
    'rovac-edge-tf',
    'rovac-edge-obstacle',
    'rovac-edge-supersensor',
    'rovac-edge-map-tf',
    'rovac-edge-rosbridge',
    'rovac-edge-ps2-joy',
    'rovac-edge-ps2-mapper',
    'rovac-edge-health',
]

# Network hosts to ping
NETWORK_HOSTS = {
    'mac_brain': os.environ.get('ROVAC_REMOTE_IP', '192.168.1.89'),
}

# USB devices to check
USB_DEVICES = {
    'esp32_motor': '/dev/esp32_motor',
    'rplidar_c1': '/dev/rplidar_c1',
    'super_sensor': '/dev/super_sensor',
}

PUBLISH_INTERVAL = 5.0


class EdgeHealthNode(Node):
    def __init__(self):
        super().__init__('edge_health')

        self._pub = self.create_publisher(String, '/rovac/edge/health', 10)
        self._timer = self.create_timer(PUBLISH_INTERVAL, self._publish_health)

        # Cache for CPU calculation
        self._prev_cpu_times = None

        self.get_logger().info(
            f'Edge health node started (publishing every {PUBLISH_INTERVAL}s)')

    def _publish_health(self):
        health = {
            'timestamp': time.time(),
            'hostname': self._get_hostname(),
            'system': self._get_system_stats(),
            'services': self._get_services(),
            'network': self._get_network(),
            'usb': self._get_usb(),
            'agent': self._get_transport_info(),
        }

        msg = String()
        msg.data = json.dumps(health)
        self._pub.publish(msg)

    # ── Hostname ─────────────────────────────────────────────────────────

    def _get_hostname(self):
        try:
            return os.uname().nodename
        except Exception:
            return 'unknown'

    # ── System Stats ─────────────────────────────────────────────────────

    def _get_system_stats(self):
        stats = {
            'cpu_percent': None,
            'memory_percent': None,
            'memory_used_mb': None,
            'memory_total_mb': None,
            'disk_percent': None,
            'disk_used_gb': None,
            'disk_total_gb': None,
            'cpu_temp': None,
        }

        # CPU percent — read /proc/stat and diff with previous sample
        try:
            cpu_times = self._read_cpu_times()
            if self._prev_cpu_times is not None and cpu_times is not None:
                prev = self._prev_cpu_times
                # Deltas: user, nice, system, idle, iowait, irq, softirq, steal
                deltas = [c - p for c, p in zip(cpu_times, prev)]
                total = sum(deltas)
                if total > 0:
                    idle_delta = deltas[3] + deltas[4]  # idle + iowait
                    stats['cpu_percent'] = round(
                        (1.0 - idle_delta / total) * 100.0, 1)
            self._prev_cpu_times = cpu_times
        except Exception as e:
            self.get_logger().debug(f'CPU stat read failed: {e}')

        # Memory — parse /proc/meminfo
        try:
            meminfo = self._read_meminfo()
            if meminfo:
                total_kb = meminfo.get('MemTotal', 0)
                avail_kb = meminfo.get('MemAvailable', 0)
                total_mb = total_kb / 1024.0
                used_mb = (total_kb - avail_kb) / 1024.0
                stats['memory_total_mb'] = round(total_mb, 0)
                stats['memory_used_mb'] = round(used_mb, 0)
                if total_kb > 0:
                    stats['memory_percent'] = round(
                        (1.0 - avail_kb / total_kb) * 100.0, 1)
        except Exception as e:
            self.get_logger().debug(f'Memory stat read failed: {e}')

        # Disk — shutil.disk_usage
        try:
            usage = shutil.disk_usage('/')
            total_gb = usage.total / (1024 ** 3)
            used_gb = usage.used / (1024 ** 3)
            stats['disk_total_gb'] = round(total_gb, 1)
            stats['disk_used_gb'] = round(used_gb, 1)
            if usage.total > 0:
                stats['disk_percent'] = round(
                    usage.used / usage.total * 100.0, 1)
        except Exception as e:
            self.get_logger().debug(f'Disk stat read failed: {e}')

        # CPU temperature
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                raw = f.read().strip()
            stats['cpu_temp'] = round(int(raw) / 1000.0, 1)
        except Exception as e:
            self.get_logger().debug(f'CPU temp read failed: {e}')

        return stats

    def _read_cpu_times(self):
        """Read aggregate CPU times from /proc/stat. Returns list of ints."""
        with open('/proc/stat', 'r') as f:
            for line in f:
                if line.startswith('cpu '):
                    parts = line.split()
                    # user, nice, system, idle, iowait, irq, softirq, steal
                    return [int(x) for x in parts[1:9]]
        return None

    def _read_meminfo(self):
        """Parse /proc/meminfo into dict of key → value_kb."""
        result = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(':')
                    result[key] = int(parts[1])  # value in kB
        return result

    # ── Service Status ───────────────────────────────────────────────────

    def _get_services(self):
        services = {}
        for svc in SERVICES:
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', svc],
                    capture_output=True, text=True, timeout=2)
                state = result.stdout.strip()
                is_active = (state == 'active')

                # Get sub-state for more detail
                sub_state = None
                try:
                    sub_result = subprocess.run(
                        ['systemctl', 'show', '-p', 'SubState',
                         '--value', svc],
                        capture_output=True, text=True, timeout=2)
                    sub_state = sub_result.stdout.strip() or None
                except Exception:
                    pass

                # Get memory for active services
                memory_mb = None
                try:
                    pid_result = subprocess.run(
                        ['systemctl', 'show', '-p', 'MainPID',
                         '--value', svc],
                        capture_output=True, text=True, timeout=2)
                    pid_str = pid_result.stdout.strip()
                    if pid_str and pid_str != '0':
                        memory_mb = self._get_process_rss_mb(int(pid_str))
                except Exception:
                    pass

                services[svc] = {
                    'active': is_active,
                    'sub_state': sub_state,
                    'memory_mb': memory_mb,
                }
            except Exception:
                services[svc] = {
                    'active': None,
                    'sub_state': None,
                    'memory_mb': None,
                }
        return services

    def _get_process_rss_mb(self, pid):
        """Read VmRSS from /proc/PID/status. Returns MB or None."""
        try:
            with open(f'/proc/{pid}/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        parts = line.split()
                        return round(int(parts[1]) / 1024.0, 1)
        except Exception:
            pass
        return None

    # ── Network Pings ────────────────────────────────────────────────────

    def _get_network(self):
        network = {}
        for name, ip in NETWORK_HOSTS.items():
            try:
                result = subprocess.run(
                    ['ping', '-c1', '-W1', ip],
                    capture_output=True, text=True, timeout=3)
                if result.returncode == 0:
                    # Parse "time=X.XX ms" from output
                    match = re.search(r'time[=<]([\d.]+)\s*ms', result.stdout)
                    latency = float(match.group(1)) if match else None
                    network[name] = {
                        'reachable': True,
                        'latency_ms': latency,
                    }
                else:
                    network[name] = {
                        'reachable': False,
                        'latency_ms': None,
                    }
            except Exception:
                network[name] = {
                    'reachable': None,
                    'latency_ms': None,
                }
        return network

    # ── USB Devices ──────────────────────────────────────────────────────

    def _get_usb(self):
        usb = {}
        for name, path in USB_DEVICES.items():
            try:
                usb[name] = os.path.exists(path)
            except Exception:
                usb[name] = None
        return usb

    # ── Transport process info ───────────────────────────────────────────

    def _get_transport_info(self):
        # Keep the "agent" JSON key for dashboard compatibility.
        info = {'pid': None, 'rss_mb': None, 'service': 'rovac-edge-motor-driver'}
        try:
            result = subprocess.run(
                ['systemctl', 'show', '-p', 'MainPID', '--value',
                 'rovac-edge-motor-driver'],
                capture_output=True, text=True, timeout=2)
            pid_str = result.stdout.strip()
            if pid_str and pid_str != '0':
                pid = int(pid_str)
                info['pid'] = pid
                info['rss_mb'] = self._get_process_rss_mb(pid)
        except Exception as e:
            self.get_logger().debug(f'Transport info read failed: {e}')
        return info


def main():
    rclpy.init()
    node = EdgeHealthNode()

    def shutdown(sig, frame):
        node.get_logger().info('Shutting down edge health node')
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
