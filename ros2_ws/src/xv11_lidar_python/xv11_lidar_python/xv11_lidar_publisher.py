#!/usr/bin/env python3
"""
XV11 LIDAR Publisher — Full-Revolution Accumulation

Publishes sensor_msgs/LaserScan on /scan by accumulating a full 360° sweep
from XV11 packet indices 0-89 before publishing. Detects revolution boundaries
by tracking packet index wrap-around.

Version: 3.0.0
"""

import math
import os
import termios
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

BYTES_PER_PACKET = 22
PACKETS_PER_REVOLUTION = 90
POINTS_PER_PACKET = 4
TOTAL_POINTS = PACKETS_PER_REVOLUTION * POINTS_PER_PACKET
PACKET_START = 0xFA


class XV11LidarNode(Node):
    def __init__(self):
        super().__init__("xv11_lidar")

        self.declare_parameter("port", "/dev/ttyAMA0")
        self.declare_parameter("frame_id", "laser_frame")
        self.declare_parameter("range_min", 0.06)
        self.declare_parameter("range_max", 5.0)
        self.declare_parameter("target_rpm", 300)

        self.port = self.get_parameter("port").value
        self.frame_id = self.get_parameter("frame_id").value
        self.range_min = self.get_parameter("range_min").value
        self.range_max = self.get_parameter("range_max").value
        self.target_rpm = self.get_parameter("target_rpm").value

        self.publisher = self.create_publisher(LaserScan, "/scan", 10)

        # Revolution accumulation state
        self._reset_revolution()
        self.prev_packet_idx = -1
        self.rev_start_time = time.monotonic()

        # Statistics
        self.scan_count = 0
        self.total_bytes = 0
        self.last_report = time.monotonic()

        self.get_logger().info(
            f"XV11 LIDAR v3.0: port={self.port}, frame={self.frame_id}, "
            f"range={self.range_min}-{self.range_max}m, target_rpm={self.target_rpm}"
        )

    def _reset_revolution(self):
        """Reset scan accumulation for a new revolution."""
        self.ranges = [float("inf")] * TOTAL_POINTS
        self.intensities = [0.0] * TOTAL_POINTS
        self.packets_seen = set()
        self.rpm_sum = 0.0
        self.rpm_count = 0
        self.rev_start_time = time.monotonic()

    def _publish_revolution(self):
        """Publish accumulated revolution data as a LaserScan."""
        if len(self.packets_seen) < 10:
            return  # Too few packets for a useful scan

        scan = LaserScan()
        scan.header.stamp = self.get_clock().now().to_msg()
        scan.header.frame_id = self.frame_id
        scan.angle_min = 0.0
        scan.angle_max = 2.0 * math.pi
        scan.angle_increment = (2.0 * math.pi) / TOTAL_POINTS
        scan.range_min = self.range_min
        scan.range_max = self.range_max
        scan.ranges = self.ranges
        scan.intensities = self.intensities

        if self.rpm_count > 0:
            avg_rpm_raw = self.rpm_sum / self.rpm_count
            rpm = avg_rpm_raw / 64.0
            # scan_time = time for one full revolution
            if rpm > 0:
                scan.scan_time = 60.0 / rpm
                scan.time_increment = scan.scan_time / TOTAL_POINTS
            else:
                scan.scan_time = 0.0
                scan.time_increment = 0.0
        else:
            scan.scan_time = 0.0
            scan.time_increment = 0.0

        self.publisher.publish(scan)
        self.scan_count += 1

        valid = sum(1 for r in self.ranges if r != float("inf"))
        if self.scan_count <= 5 or self.scan_count % 50 == 0:
            rpm_str = f"{rpm:.0f}" if self.rpm_count > 0 else "?"
            self.get_logger().info(
                f"Scan #{self.scan_count}: {valid}/{TOTAL_POINTS} pts, "
                f"{len(self.packets_seen)}/{PACKETS_PER_REVOLUTION} pkts, "
                f"RPM={rpm_str}"
            )

    def process_packet(self, packet):
        """Process a single 22-byte XV11 packet into the current revolution."""
        index_byte = packet[1]

        is_fa = packet[0] == PACKET_START
        if is_fa and 0xA0 <= index_byte <= 0xF9:
            pkt_idx = index_byte - 0xA0
        elif not is_fa and 0x00 <= index_byte <= 0x59:
            pkt_idx = index_byte
        else:
            return

        # Detect revolution boundary: index wrapped back to start
        if (self.prev_packet_idx >= 70 and pkt_idx <= 10 and
                len(self.packets_seen) >= 10):
            self._publish_revolution()
            self._reset_revolution()

        self.prev_packet_idx = pkt_idx

        # RPM from bytes 2-3 (raw value, divide by 64 for actual RPM)
        rpm_raw = packet[2] | (packet[3] << 8)
        self.rpm_sum += rpm_raw
        self.rpm_count += 1
        self.packets_seen.add(pkt_idx)

        # Extract 4 data points
        for j in range(POINTS_PER_PACKET):
            offset = 4 + 4 * j
            byte0 = packet[offset]
            byte1 = packet[offset + 1]
            byte2 = packet[offset + 2]
            byte3 = packet[offset + 3]

            point_idx = pkt_idx * POINTS_PER_PACKET + j
            if point_idx >= TOTAL_POINTS:
                continue

            # XV11 invalid flag: bit 7 of byte1
            if byte1 & 0x80:
                continue

            distance_mm = byte0 | ((byte1 & 0x3F) << 8)
            distance = distance_mm / 1000.0

            if self.range_min <= distance <= self.range_max:
                self.ranges[point_idx] = distance

            intensity = byte2 | (byte3 << 8)
            self.intensities[point_idx] = float(intensity)

    def report_statistics(self):
        now = time.monotonic()
        if now - self.last_report >= 10.0:
            elapsed = now - self.last_report
            scan_rate = self.scan_count / elapsed if elapsed > 0 else 0
            bytes_rate = self.total_bytes / elapsed if elapsed > 0 else 0
            self.get_logger().info(
                f"Stats: {scan_rate:.1f} Hz, {bytes_rate:.0f} B/s, "
                f"{self.scan_count} scans in {elapsed:.0f}s"
            )
            self.scan_count = 0
            self.total_bytes = 0
            self.last_report = now


def configure_serial(fd):
    """Configure serial port for raw 115200 baud 8N1."""
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0  # iflag: raw
    attrs[1] = 0  # oflag: raw
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag: 8N1
    attrs[3] = 0  # lflag: raw
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def parse_packets(buf):
    """Yield (packet, consumed_up_to) for each valid XV11 packet in buf."""
    i = 0
    buf_len = len(buf)
    while i <= buf_len - BYTES_PER_PACKET:
        if buf[i] in (0xFA, 0xFB):
            index_byte = buf[i + 1]
            is_fa = buf[i] == 0xFA
            valid = ((is_fa and 0xA0 <= index_byte <= 0xF9) or
                     (not is_fa and 0x00 <= index_byte <= 0x59))
            if valid:
                yield bytes(buf[i:i + BYTES_PER_PACKET]), i + BYTES_PER_PACKET
                i += BYTES_PER_PACKET
                continue
        i += 1


def main(args=None):
    rclpy.init(args=args)
    node = XV11LidarNode()
    port = node.port

    node.get_logger().info(f"Opening {port}")

    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        configure_serial(fd)
        node.get_logger().info(f"{port} connected")
    except Exception as e:
        node.get_logger().error(f"Failed to open {port}: {e}")
        rclpy.shutdown()
        return

    # Tell ESP32 to target the RPM that matches hardware capability
    try:
        target_cmd = f"!target {node.target_rpm}\n".encode()
        os.write(fd, target_cmd)
        node.get_logger().info(f"Sent !target {node.target_rpm} to ESP32 bridge")
    except OSError:
        pass

    buf = bytearray()
    empty_reads = 0
    revolution_timeout = 1.0  # Publish partial revolution after 1s stall

    try:
        while rclpy.ok():
            # Read serial data
            try:
                chunk = os.read(fd, 4096)
                if chunk:
                    buf.extend(chunk)
                    node.total_bytes += len(chunk)
                    empty_reads = 0
                else:
                    empty_reads += 1
            except BlockingIOError:
                empty_reads += 1
            except OSError as e:
                node.get_logger().warn(f"Read error: {e}")
                empty_reads += 1

            if empty_reads > 50:
                time.sleep(0.001)
                empty_reads = 0

            # Parse all complete packets from buffer
            last_consumed = 0
            for packet, consumed in parse_packets(buf):
                node.process_packet(packet)
                last_consumed = consumed

            if last_consumed > 0:
                buf = buf[last_consumed:]

            # Timeout: publish partial revolution if data stalls
            if (node.packets_seen and
                    time.monotonic() - node.rev_start_time > revolution_timeout):
                node._publish_revolution()
                node._reset_revolution()

            # Prevent unbounded buffer growth
            if len(buf) > 8192:
                buf = buf[-2048:]

            # Spin ROS2 for message dispatch
            try:
                rclpy.spin_once(node, timeout_sec=0)
            except Exception:
                pass

            node.report_statistics()
            time.sleep(0.001)

    except KeyboardInterrupt:
        node.get_logger().info("Shutting down")
    except Exception as e:
        node.get_logger().error(f"Fatal: {e}")
    finally:
        try:
            os.close(fd)
        except Exception:
            pass
        try:
            node.destroy_node()
        except Exception:
            pass
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
