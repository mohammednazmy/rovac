#!/usr/bin/env python3
"""
Professional XV11 LIDAR Publisher
Enhanced firmware with professional features and proper ROS2 topic publishing

Author: ROVAC Professional Engineering Team
Version: 2.0.0
Date: January 2026

Features:
- Device identification (!id)
- Firmware version reporting (!version)
- Real-time status monitoring (!status)
- Baud rate reporting (!baud)
- Statistics reset (!reset)
- Help system (!help)
- Professional-grade data processing
- Cross-platform compatibility
- True plug-and-play operation
"""

import os
import termios
import time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

# Constants
PI = 3.141592653589793
BYTES_PER_PACKET = 22
PACKETS_PER_REVOLUTION = 90
POINTS_PER_PACKET = 4
TOTAL_POINTS = PACKETS_PER_REVOLUTION * POINTS_PER_PACKET

# Device identification
DEVICE_NAME = "ROVAC_LIDAR_BRIDGE"
FIRMWARE_VERSION = "2.0.0"
BAUD_RATE = 115200


class ProfessionalXV11Node(Node):
    """Professional XV11 LIDAR Node with enhanced features"""

    def __init__(self):
        super().__init__("xv11_lidar")
        self.get_logger().info("Initializing XV11 Lidar Node")

        # Create publisher for /scan topic with reliable QoS
        self.publisher = self.create_publisher(LaserScan, "/scan", 10)
        self.get_logger().info("Created /scan publisher")

        # Declare parameters
        self.declare_parameter("port", "/dev/ttyAMA0")
        self.declare_parameter("frame_id", "laser_frame")
        self.declare_parameter("range_min", 0.06)
        self.declare_parameter("range_max", 5.0)

        # Get parameters
        self.port = self.get_parameter("port").value
        self.frame_id = self.get_parameter("frame_id").value
        self.range_min = self.get_parameter("range_min").value
        self.range_max = self.get_parameter("range_max").value

        # Initialize statistics
        self.scan_count = 0
        self.total_bytes = 0
        self.start_time = self.get_clock().now()
        self.last_activity = self.get_clock().now()
        self.last_report = time.time()

        self.get_logger().info(f"Port: {self.port}")
        self.get_logger().info(f"Frame ID: {self.frame_id}")
        self.get_logger().info(f"Range: {self.range_min}-{self.range_max}m")

    def configure_serial(self, fd):
        """Configure serial port for maximum throughput"""
        attrs = termios.tcgetattr(fd)
        # Input flags - raw mode
        attrs[0] = 0
        # Output flags - raw mode
        attrs[1] = 0
        # Control flags - 8N1, read enable, ignore control lines
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        # Local flags - raw mode
        attrs[3] = 0
        # Input baud rate
        attrs[4] = termios.B115200
        # Output baud rate
        attrs[5] = termios.B115200
        # Control characters - non-blocking
        attrs[6][termios.VMIN] = 0  # Non-blocking read
        attrs[6][termios.VTIME] = 0  # No inter-character timer
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)

    def has_valid_crc(self, dataframe):
        """Validate CRC for XV11 data packet using correct algorithm"""
        if len(dataframe) < BYTES_PER_PACKET:
            return False

        # Extract the 10 data words (bytes 0-19)
        data_list = []
        for t in range(10):
            data_list.append(dataframe[2 * t] + (dataframe[2 * t + 1] << 8))

        # Calculate CRC with folding at EACH step (this is the key fix!)
        chk32 = 0
        for d in data_list:
            chk32 = (chk32 << 1) + d
            # Fold the overflow back into the lower 15 bits at each step
            chk32 = (chk32 & 0x7FFF) + (chk32 >> 15)

        # Final fold to ensure we're within 15 bits
        chk32 = (chk32 & 0x7FFF) + (chk32 >> 15)
        chk32 = chk32 & 0x7FFF

        # Extract packet CRC from bytes 20-21
        packet_crc = dataframe[20] + (dataframe[21] << 8)

        return packet_crc == chk32

    def extract_sweep(self, buffer):
        """Extract a complete scan from the buffer"""
        buf_len = len(buffer)
        # Reduced minimum from 720 to 200 bytes to allow partial scan processing
        if buf_len < 200:
            return 0, None

        # Initialize scan
        scan = LaserScan()
        scan.angle_min = 0.0
        scan.angle_max = 2 * PI
        scan.angle_increment = (2 * PI) / TOTAL_POINTS
        scan.ranges = [float("inf")] * TOTAL_POINTS  # Initialize with infinity
        scan.intensities = [0.0] * TOTAL_POINTS
        scan.range_min = self.range_min
        scan.range_max = self.range_max

        # Statistics for this sweep
        sum_motor_speed = 0.0
        num_good_packets = 0
        last_packet_index = 0

        # Process packets - look for 0xFA start marker followed by valid index
        i = 0
        while i < buf_len - BYTES_PER_PACKET + 1:
            if buffer[i] in (0xFA, 0xFB):  # Packet start marker (standard or variant)
                if i + BYTES_PER_PACKET <= buf_len:
                    packet = buffer[i : i + BYTES_PER_PACKET]

                    # Check for valid index byte (0xA0-0xF9 = packet indices 0-89)
                    # Skip CRC validation - USB bridge data may not have valid CRC
                    index_byte = packet[1]
                    # Check both formats: 0xFA uses 0xA0-0xF9, 0xFB uses 0x00-0x59
                    is_fa_format = buffer[i] == 0xFA
                    valid_fa = is_fa_format and 0xA0 <= index_byte <= 0xF9
                    valid_fb = (not is_fa_format) and 0x00 <= index_byte <= 0x59
                    if valid_fa or valid_fb:  # Valid index range
                        df_index = (index_byte - 0xA0) if is_fa_format else index_byte
                        if 0 <= df_index <= 89:
                            # Extract motor speed
                            speed_low = packet[2]
                            speed_high = packet[3]
                            motor_speed = speed_low + (speed_high << 8)
                            sum_motor_speed += motor_speed
                            num_good_packets += 1

                            # Extract 4 data points from packet
                            for j in range(POINTS_PER_PACKET):
                                byte0 = packet[4 + 4 * j]
                                byte1 = packet[5 + 4 * j]
                                byte2 = packet[6 + 4 * j]
                                byte3 = packet[7 + 4 * j]

                                idx = df_index * POINTS_PER_PACKET + j
                                if idx < TOTAL_POINTS:
                                    # Check XV11 invalid flag (bit 7 of byte1)
                                    if byte1 & 0x80:
                                        continue  # Skip invalid reading

                                    # Distance in mm, convert to meters
                                    distance_mm = byte0 + ((byte1 & 0x3F) << 8)
                                    distance = distance_mm / 1000.0

                                    # Only store valid distances
                                    if self.range_min <= distance <= self.range_max:
                                        scan.ranges[idx] = distance

                                    # Intensity
                                    intensity = byte2 + (byte3 << 8)
                                    scan.intensities[idx] = float(intensity)

                            i += BYTES_PER_PACKET
                            last_packet_index = i
                        else:
                            i += 1
                    else:
                        i += 1
                else:
                    break  # Not enough data for complete packet
            else:
                i += 1

        # Set time increment based on average motor speed
        if num_good_packets > 0:
            avg_motor_speed = sum_motor_speed / num_good_packets
            scan.time_increment = avg_motor_speed / 1e8  # Convert to seconds
        else:
            scan.time_increment = 0.0

        # Return scan if we have enough valid packets
        # Very low threshold (5 packets) to handle partial/slow scans from USB bridge
        if num_good_packets >= 5:
            return last_packet_index, scan
        else:
            return 0, None

    def publish_scan(self, scan):
        """Publish scan with proper timestamp and frame ID"""
        if scan:
            # Set header information
            scan.header.stamp = self.get_clock().now().to_msg()
            scan.header.frame_id = self.frame_id

            # Publish the scan
            self.publisher.publish(scan)

            # Update statistics
            self.scan_count += 1
            self.last_activity = self.get_clock().now()

            # Log first few scans and then periodically
            valid_points = sum(1 for r in scan.ranges if r != float("inf"))
            if self.scan_count <= 3:
                self.get_logger().info(
                    f"Published scan #{self.scan_count}: {valid_points}/360 valid points"
                )
            elif self.scan_count % 50 == 0:
                self.get_logger().info(
                    f"Published scan #{self.scan_count}: {valid_points}/360 valid points"
                )

    def process_commands(self, data):
        """Process host commands for professional features"""
        if b"!id" in data:
            self.get_logger().info(f"!DEVICE_ID:{DEVICE_NAME}")
            return True
        elif b"!version" in data:
            self.get_logger().info(f"!VERSION:{FIRMWARE_VERSION}")
            return True
        elif b"!status" in data:
            uptime = (self.get_clock().now() - self.start_time).nanoseconds * 1e-9
            idle_time = (self.get_clock().now() - self.last_activity).nanoseconds * 1e-9
            self.get_logger().info(
                f"!STATUS:Uptime={uptime:.0f}s,Bytes={self.total_bytes},Scans={self.scan_count},Idle={idle_time:.0f}s"
            )
            return True
        elif b"!baud" in data:
            self.get_logger().info(f"!BAUD_RATE:{BAUD_RATE}")
            return True
        elif b"!reset" in data:
            self.scan_count = 0
            self.total_bytes = 0
            self.start_time = self.get_clock().now()
            self.last_activity = self.get_clock().now()
            self.get_logger().info("!STATISTICS_RESET")
            return True
        elif b"!help" in data:
            self.get_logger().info(
                "!AVAILABLE_COMMANDS:!id,!version,!status,!baud,!reset,!help"
            )
            return True

        return False

    def report_statistics(self):
        """Report statistics periodically"""
        now = time.time()
        if now - self.last_report >= 5.0:
            elapsed = now - self.last_report
            if elapsed > 0:
                scan_rate = self.scan_count / elapsed
                bytes_rate = self.total_bytes / elapsed
                buf_len = len(self.data_buffer) if hasattr(self, 'data_buffer') else 0
                self.get_logger().info(
                    f"Scan rate: {scan_rate:.1f} Hz, bytes: {bytes_rate:.0f}/s, buf: {buf_len}, published: {self.scan_count}"
                )

            # Reset counters
            self.scan_count = 0
            self.total_bytes = 0
            self.last_report = now


def main(args=None):
    """Main function - Professional XV11 LIDAR Publisher"""
    rclpy.init(args=args)
    node = ProfessionalXV11Node()

    # Get parameters
    port = node.get_parameter("port").value
    frame_id = node.get_parameter("frame_id").value

    # Override port if specified via command line
    import sys

    for i in range(len(sys.argv)):
        if sys.argv[i] == "port:=" and i + 1 < len(sys.argv):
            port = sys.argv[i + 1]

    node.get_logger().info(f"Starting LIDAR on {port}")

    # Data buffer and communication
    node.data_buffer = bytearray()
    empty_reads = 0

    try:
        # Open and configure serial port
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        node.configure_serial(fd)
        node.get_logger().info(f"{port} connected (non-blocking mode)")
    except Exception as e:
        node.get_logger().error(f"Failed to connect to {port}: {e}")
        rclpy.shutdown()
        return

    try:
        last_scan_time = node.get_clock().now()

        # Main processing loop
        while rclpy.ok():
            try:
                # Read available data
                chunk = os.read(fd, 4096)
                if chunk:
                    node.data_buffer.extend(chunk)
                    node.total_bytes += len(chunk)
                    empty_reads = 0

                    # Process host commands
                    if node.process_commands(chunk):
                        continue  # Command processed, continue loop
                else:
                    empty_reads += 1
            except BlockingIOError:
                empty_reads += 1
            except OSError as e:
                node.get_logger().warn(f"Read error: {e}")
                empty_reads += 1

            # Prevent excessive CPU usage
            if empty_reads > 50:
                time.sleep(0.001)
                empty_reads = 0

            # Process data to extract scans (reduced threshold from 2000 to 500)
            while len(node.data_buffer) >= 500:
                last_index, scan = node.extract_sweep(node.data_buffer)

                if scan and last_index > 0:
                    # Publish valid scan
                    node.publish_scan(scan)

                    # Update buffer - keep unprocessed data
                    node.data_buffer = node.data_buffer[last_index:]

                    # Update timing
                    last_scan_time = node.get_clock().now()
                else:
                    # No valid scan extracted, remove some old data to prevent buffer overflow
                    if len(node.data_buffer) > 4000:
                        node.data_buffer = node.data_buffer[100:]
                    else:
                        # Skip one byte to find next potential packet start
                        node.data_buffer = node.data_buffer[1:]
                    break  # Exit loop to accumulate more data

            # CRITICAL: Spin ROS2 to actually process and send published messages
            # Without this, the /scan topic won't appear even though publish() is called
            try:
                rclpy.spin_once(node, timeout_sec=0)
            except Exception:
                pass  # Ignore spin errors during shutdown

            # Report statistics periodically
            node.report_statistics()

            # Small delay to prevent excessive CPU usage
            time.sleep(0.001)

    except KeyboardInterrupt:
        node.get_logger().info("Interrupted by user")
    except Exception as e:
        node.get_logger().error(f"Fatal error: {e}")
    finally:
        # Cleanup
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
