#!/usr/bin/env python3
"""
Simple Phone Camera ROS2 Node using FFmpeg
More reliable than OpenCV for v4l2loopback devices.
"""

import os
import subprocess
import threading
import time
import signal

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CompressedImage, CameraInfo
from std_msgs.msg import Bool, Header

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class PhoneCameraSimple(Node):
    """Simple phone camera node using FFmpeg for capture"""

    def __init__(self):
        super().__init__('phone_camera_simple')

        self.declare_parameter('video_device', '/dev/video10')
        self.declare_parameter('width', 1280)
        self.declare_parameter('height', 720)
        self.declare_parameter('fps', 15)
        self.declare_parameter('frame_id', 'phone_camera_link')
        self.declare_parameter('jpeg_quality', 75)

        self.video_device = self.get_parameter('video_device').value
        self.width = self.get_parameter('width').value
        self.height = self.get_parameter('height').value
        self.fps = self.get_parameter('fps').value
        self.frame_id = self.get_parameter('frame_id').value
        self.jpeg_quality = self.get_parameter('jpeg_quality').value

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        self.pub_image = self.create_publisher(Image, '/phone/image_raw', sensor_qos)
        self.pub_compressed = self.create_publisher(CompressedImage, '/phone/image_raw/compressed', sensor_qos)
        self.pub_camera_info = self.create_publisher(CameraInfo, '/phone/camera_info', sensor_qos)
        self.pub_connected = self.create_publisher(Bool, '/phone/camera_connected', 10)

        self.camera_info = self._create_camera_info()
        self.running = True
        self.connected = False
        self.ffmpeg_proc = None

        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

        self.create_timer(1.0, self._publish_status)
        self.get_logger().info(f'Phone camera simple node started, device: {self.video_device}')

    def _create_camera_info(self):
        info = CameraInfo()
        info.header.frame_id = self.frame_id
        info.width = self.width
        info.height = self.height
        info.distortion_model = 'plumb_bob'
        fx = fy = self.width * 0.9
        cx, cy = self.width / 2.0, self.height / 2.0
        info.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        info.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.d = [0.0, 0.0, 0.0, 0.0, 0.0]
        return info

    def _capture_loop(self):
        """Capture frames using FFmpeg"""
        frame_size = self.width * self.height * 3  # BGR24

        while self.running:
            try:
                # Start FFmpeg to read from v4l2 device and convert to BGR24
                cmd = [
                    'ffmpeg',
                    '-f', 'v4l2',
                    '-video_size', f'{self.width}x{self.height}',
                    '-framerate', str(self.fps),
                    '-input_format', 'yuv420p',
                    '-i', self.video_device,
                    '-vf', 'format=bgr24',
                    '-f', 'rawvideo',
                    '-'
                ]

                self.ffmpeg_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=frame_size * 2
                )

                self.get_logger().info('FFmpeg capture started')
                self.connected = True

                while self.running:
                    raw_frame = self.ffmpeg_proc.stdout.read(frame_size)
                    if len(raw_frame) != frame_size:
                        break

                    frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((self.height, self.width, 3))
                    self._publish_frame(frame)

            except Exception as e:
                self.get_logger().warn(f'Capture error: {e}')
                self.connected = False

            finally:
                if self.ffmpeg_proc:
                    self.ffmpeg_proc.terminate()
                    self.ffmpeg_proc = None

            time.sleep(2)

    def _publish_frame(self, frame):
        now = self.get_clock().now()
        header = Header()
        header.stamp = now.to_msg()
        header.frame_id = self.frame_id

        # Raw image
        img_msg = Image()
        img_msg.header = header
        img_msg.height = self.height
        img_msg.width = self.width
        img_msg.encoding = 'bgr8'
        img_msg.is_bigendian = False
        img_msg.step = self.width * 3
        img_msg.data = frame.tobytes()
        self.pub_image.publish(img_msg)

        # Compressed
        _, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        comp_msg = CompressedImage()
        comp_msg.header = header
        comp_msg.format = 'jpeg'
        comp_msg.data = encoded.tobytes()
        self.pub_compressed.publish(comp_msg)

        # Camera info
        self.camera_info.header = header
        self.pub_camera_info.publish(self.camera_info)

    def _publish_status(self):
        msg = Bool()
        msg.data = self.connected
        self.pub_connected.publish(msg)

    def destroy_node(self):
        self.running = False
        if self.ffmpeg_proc:
            self.ffmpeg_proc.terminate()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = PhoneCameraSimple()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
