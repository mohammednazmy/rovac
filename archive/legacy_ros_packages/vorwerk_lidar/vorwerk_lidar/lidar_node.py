import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
import os
import termios
import threading
import math
import time

class VorwerkLidarNode(Node):
    def __init__(self):
        super().__init__('vorwerk_lidar_node')
        self.declare_parameter('serial_port', '/dev/ttyAMA0')
        self.declare_parameter('baud_rate', 115200)
        self.declare_parameter('frame_id', 'laser_frame')
        self.declare_parameter('scan_topic', 'scan')

        self.serial_port = self.get_parameter('serial_port').get_parameter_value().string_value
        self.frame_id = self.get_parameter('frame_id').get_parameter_value().string_value
        self.scan_topic = self.get_parameter('scan_topic').get_parameter_value().string_value

        self.publisher_ = self.create_publisher(LaserScan, self.scan_topic, 10)

        # Open serial port in NON-BLOCKING mode for maximum throughput
        self.fd = None
        try:
            self.fd = os.open(self.serial_port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            attrs = termios.tcgetattr(self.fd)
            attrs[0] = 0  # Input flags
            attrs[1] = 0  # Output flags
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # 8N1
            attrs[3] = 0  # Local flags - raw mode
            attrs[4] = termios.B115200
            attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = 0  # Non-blocking
            attrs[6][termios.VTIME] = 0  # No timeout
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            termios.tcflush(self.fd, termios.TCIOFLUSH)
            self.get_logger().info(f'Connected to LIDAR on {self.serial_port} (non-blocking mode)')
        except Exception as e:
            self.get_logger().error(f'Failed to open serial port: {e}')
            return

        self.ranges = [float('inf')] * 360
        self.intensities = [0.0] * 360
        self.scan_rpm = 0.0
        self.publish_count = 0
        self.buffer = bytearray()

        self.running = True
        self.read_thread = threading.Thread(target=self.read_loop)
        self.read_thread.daemon = True
        self.read_thread.start()

    def read_loop(self):
        PACKET_SIZE = 22
        empty_reads = 0

        while self.running and rclpy.ok():
            try:
                try:
                    chunk = os.read(self.fd, 4096)
                    if chunk:
                        self.buffer.extend(chunk)
                        empty_reads = 0
                    else:
                        empty_reads += 1
                except BlockingIOError:
                    empty_reads += 1
                except Exception as e:
                    self.get_logger().warn(f"Read error: {e}")
                    empty_reads += 1

                # Only sleep after many empty reads
                if empty_reads > 50:
                    time.sleep(0.001)
                    empty_reads = 0

                while len(self.buffer) >= PACKET_SIZE:
                    try:
                        start_idx = self.buffer.index(0xFA)
                    except ValueError:
                        self.buffer.clear()
                        break

                    if start_idx > 0:
                        del self.buffer[:start_idx]

                    if len(self.buffer) < PACKET_SIZE:
                        break

                    index = self.buffer[1]
                    if index < 0xA0 or index > 0xF9:
                        del self.buffer[0]
                        continue

                    data = bytes(self.buffer[2:22])
                    del self.buffer[:PACKET_SIZE]
                    self.process_packet(index, data)

            except Exception as e:
                self.get_logger().warn(f"Loop error: {e}")
                time.sleep(0.1)

    def process_packet(self, index, data):
        speed_rpm = (data[1] << 8 | data[0]) / 64.0
        self.scan_rpm = speed_rpm
        packet_index = index - 0xA0
        base_angle_idx = packet_index * 4

        for i in range(4):
            offset = 2 + (i * 4)
            byte0, byte1, byte2, byte3 = data[offset], data[offset+1], data[offset+2], data[offset+3]
            raw_dist = (byte1 << 8) | byte0
            dist_mm = raw_dist & 0x3FFF
            invalid_data = (byte1 & 0x80) >> 7
            strength = (byte3 << 8) | byte2
            current_angle_idx = base_angle_idx + i

            if current_angle_idx < 360:
                if invalid_data == 0 and dist_mm > 0:
                    self.ranges[current_angle_idx] = dist_mm / 1000.0
                    self.intensities[current_angle_idx] = float(strength)
                else:
                    self.ranges[current_angle_idx] = float('inf')
                    self.intensities[current_angle_idx] = 0.0

        if index == 0xF9:
            self.publish_scan()

    def publish_scan(self):
        scan_msg = LaserScan()
        scan_msg.header.stamp = self.get_clock().now().to_msg()
        scan_msg.header.frame_id = self.frame_id
        scan_msg.angle_min = 0.0
        scan_msg.angle_max = 2.0 * math.pi
        scan_msg.angle_increment = (2.0 * math.pi) / 360.0
        if self.scan_rpm > 0:
            scan_time = 60.0 / self.scan_rpm
            scan_msg.time_increment = scan_time / 360.0
            scan_msg.scan_time = scan_time
        else:
            scan_msg.time_increment = 0.0
            scan_msg.scan_time = 0.0
        scan_msg.range_min = 0.15
        scan_msg.range_max = 6.0
        scan_msg.ranges = self.ranges[:]
        scan_msg.intensities = self.intensities[:]
        self.publisher_.publish(scan_msg)
        self.publish_count += 1
        if self.publish_count % 50 == 0:
            self.get_logger().info(f'Published {self.publish_count} scans. RPM: {self.scan_rpm:.1f}')

    def destroy_node(self):
        self.running = False
        if self.read_thread.is_alive():
            self.read_thread.join(timeout=1.0)
        if self.fd is not None:
            os.close(self.fd)
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = VorwerkLidarNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
