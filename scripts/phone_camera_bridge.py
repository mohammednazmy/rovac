#!/usr/bin/env python3
"""
Phone Camera HTTP Bridge — streams MJPEG from the phone's HTTP server
and publishes as sensor_msgs/CompressedImage on ROS 2.

Usage:
    source config/ros2_env.sh
    python3 scripts/phone_camera_bridge.py [phone_ip]

The phone runs an MJPEG server on port 8080. This script connects to
http://<phone_ip>:8080/stream and publishes each frame as a ROS 2 topic.
No MTU limits — full 640x480 JPEG at quality 70.

Default phone IP is auto-discovered from /phone/gps/fix topic source,
or falls back to the first .1.x device responding on port 8080.
"""

import sys
import time
import urllib.request
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Bool


PHONE_PORT = 8080
BOUNDARY = b'rovac_frame'


class PhoneCameraBridge(Node):
    def __init__(self, phone_ip: str):
        super().__init__('phone_camera_bridge')
        self.phone_ip = phone_ip
        self.url = f'http://{phone_ip}:{PHONE_PORT}/stream'

        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )
        self.pub = self.create_publisher(
            CompressedImage, '/phone/camera/image_raw/http', qos)

        self.frame_count = 0

        # Flashlight control: subscribe to /phone/flashlight (std_msgs/Bool)
        self.create_subscription(Bool, '/phone/flashlight', self._torch_cb, 10)
        self.torch_url_on = f'http://{phone_ip}:{PHONE_PORT}/torch/on'
        self.torch_url_off = f'http://{phone_ip}:{PHONE_PORT}/torch/off'
        self.get_logger().info(f'Flashlight control: ros2 topic pub /phone/flashlight std_msgs/Bool "data: true"')

        self.get_logger().info(f'Connecting to MJPEG stream at {self.url}')

        # Start streaming in a timer to keep the node responsive
        self.create_timer(0.01, self._noop)  # keep spinning
        self.stream_thread = None
        self._start_stream()

    def _noop(self):
        pass

    def _torch_cb(self, msg: Bool):
        url = self.torch_url_on if msg.data else self.torch_url_off
        try:
            urllib.request.urlopen(url, timeout=2)
            self.get_logger().info(f'Flashlight {"ON" if msg.data else "OFF"}')
        except Exception as e:
            self.get_logger().warn(f'Torch control failed: {e}')

    def _start_stream(self):
        import threading
        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()

    def _stream_loop(self):
        while rclpy.ok():
            try:
                self.get_logger().info(f'Connecting to {self.url} ...')
                req = urllib.request.Request(self.url)
                resp = urllib.request.urlopen(req, timeout=10)

                self.get_logger().info(f'Connected! Streaming frames...')
                buf = b''
                while rclpy.ok():
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    buf += chunk

                    # Find JPEG frames between boundaries
                    while True:
                        # Find boundary
                        start_marker = buf.find(b'\xff\xd8')  # JPEG SOI
                        if start_marker < 0:
                            # Keep last 2 bytes in case SOI spans chunks
                            buf = buf[-2:] if len(buf) > 2 else buf
                            break

                        end_marker = buf.find(b'\xff\xd9', start_marker + 2)  # JPEG EOI
                        if end_marker < 0:
                            break  # incomplete frame, wait for more data

                        # Extract complete JPEG
                        jpeg = buf[start_marker:end_marker + 2]
                        buf = buf[end_marker + 2:]

                        # Publish
                        self._publish_frame(jpeg)

            except Exception as e:
                self.get_logger().warn(f'Stream error: {e}. Retrying in 3s...')
                time.sleep(3)

    def _publish_frame(self, jpeg: bytes):
        msg = CompressedImage()
        now = self.get_clock().now().to_msg()
        msg.header.stamp = now
        msg.header.frame_id = 'phone_camera'
        msg.format = 'jpeg'
        msg.data = jpeg

        self.pub.publish(msg)
        self.frame_count += 1
        if self.frame_count % 25 == 0:
            self.get_logger().info(
                f'Frame #{self.frame_count}: {len(jpeg)} bytes')


def main():
    # Default phone IP — can be overridden via command line
    phone_ip = sys.argv[1] if len(sys.argv) > 1 else '192.168.1.221'

    # Try to discover phone IP by scanning common addresses
    if len(sys.argv) <= 1:
        import socket
        for last_octet in range(100, 255):
            ip = f'192.168.1.{last_octet}'
            try:
                s = socket.create_connection((ip, PHONE_PORT), timeout=0.3)
                s.close()
                phone_ip = ip
                print(f'Found phone MJPEG server at {ip}:{PHONE_PORT}')
                break
            except (socket.timeout, ConnectionRefusedError, OSError):
                continue

    rclpy.init()
    node = PhoneCameraBridge(phone_ip)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
