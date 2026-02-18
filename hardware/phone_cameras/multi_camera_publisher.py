#!/usr/bin/env python3
"""
Multi-Camera ROS2 Publisher

Publishes video from a v4l2 device (phone camera via scrcpy) to ROS2 topics.
Supports multiple instances for multiple cameras.

Usage:
    python3 multi_camera_publisher.py --camera-name back --device /dev/video10
    python3 multi_camera_publisher.py --camera-name front --device /dev/video11
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage, CameraInfo
from std_msgs.msg import Header
from cv_bridge import CvBridge
import cv2
import argparse
import sys


class CameraPublisher(Node):
    def __init__(self, camera_name: str, device: str, fps: float = 15.0):
        super().__init__(f'phone_camera_{camera_name}_publisher')

        self.camera_name = camera_name
        self.device = device
        self.fps = fps
        self.bridge = CvBridge()

        # Topic names based on camera name
        base_topic = f'/phone/camera/{camera_name}'

        # Publishers
        self.image_pub = self.create_publisher(Image, f'{base_topic}/image_raw', 10)
        self.compressed_pub = self.create_publisher(CompressedImage, f'{base_topic}/image_raw/compressed', 10)
        self.info_pub = self.create_publisher(CameraInfo, f'{base_topic}/camera_info', 10)

        # Open video device
        self.cap = cv2.VideoCapture(device)
        if not self.cap.isOpened():
            self.get_logger().error(f'Failed to open {device}')
            raise RuntimeError(f'Cannot open {device}')

        # Get actual resolution
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.get_logger().info(f'Camera [{camera_name}]: {device} @ {self.width}x{self.height}')
        self.get_logger().info(f'Publishing to {base_topic}/image_raw')

        # Timer for frame capture
        self.timer = self.create_timer(1.0 / fps, self.capture_and_publish)

        # Frame counter for camera_info
        self.frame_count = 0

    def capture_and_publish(self):
        ret, frame = self.cap.read()
        if not ret:
            self.get_logger().warn(f'Failed to capture frame from {self.device}')
            return

        # Create header
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = f'phone_camera_{self.camera_name}_optical_frame'

        # Publish raw image
        try:
            img_msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            img_msg.header = header
            self.image_pub.publish(img_msg)
        except Exception as e:
            self.get_logger().error(f'Failed to publish raw image: {e}')
            return

        # Publish compressed image
        try:
            compressed_msg = CompressedImage()
            compressed_msg.header = header
            compressed_msg.format = 'jpeg'
            compressed_msg.data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
            self.compressed_pub.publish(compressed_msg)
        except Exception as e:
            self.get_logger().warn(f'Failed to publish compressed image: {e}')

        # Publish camera info
        info_msg = CameraInfo()
        info_msg.header = header
        info_msg.width = self.width
        info_msg.height = self.height
        info_msg.distortion_model = 'plumb_bob'
        # Default camera matrix (approximate)
        fx = fy = self.width  # Approximate focal length
        cx, cy = self.width / 2, self.height / 2
        info_msg.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        info_msg.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        info_msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        self.info_pub.publish(info_msg)

        self.frame_count += 1

    def destroy_node(self):
        if self.cap:
            self.cap.release()
        super().destroy_node()


def main():
    parser = argparse.ArgumentParser(description='Phone Camera ROS2 Publisher')
    parser.add_argument('--camera-name', '-n', required=True,
                        help='Camera name (e.g., back, front, wide)')
    parser.add_argument('--device', '-d', required=True,
                        help='V4L2 device path (e.g., /dev/video10)')
    parser.add_argument('--fps', '-f', type=float, default=15.0,
                        help='Frame rate (default: 15)')

    # Parse known args to allow ROS args to pass through
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)

    try:
        node = CameraPublisher(args.camera_name, args.device, args.fps)
        rclpy.spin(node)
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
