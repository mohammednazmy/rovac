#!/usr/bin/env python3
"""
USB Webcam ROS2 Publisher

Publishes video from a USB webcam to ROS2 topics.
Supports MJPG for efficient USB bandwidth usage.

Topics:
    /webcam/image_raw           - Raw BGR8 image
    /webcam/image_raw/compressed - JPEG compressed image
    /webcam/camera_info         - Camera calibration info
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage, CameraInfo
from std_msgs.msg import Header
from cv_bridge import CvBridge
import cv2
import argparse
import sys


class WebcamPublisher(Node):
    def __init__(self, device: str = '/dev/video0', width: int = 640, 
                 height: int = 480, fps: float = 30.0, use_mjpg: bool = True):
        super().__init__('webcam_publisher')
        
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.bridge = CvBridge()
        
        # Publishers
        self.image_pub = self.create_publisher(Image, '/webcam/image_raw', 10)
        self.compressed_pub = self.create_publisher(
            CompressedImage, '/webcam/image_raw/compressed', 10)
        self.info_pub = self.create_publisher(CameraInfo, '/webcam/camera_info', 10)
        
        # Open video device
        self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.get_logger().error(f'Failed to open webcam at {device}')
            raise RuntimeError(f'Cannot open webcam at {device}')
        
        # Set format - prefer MJPG for better USB bandwidth
        if use_mjpg:
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        
        # Set resolution and frame rate
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        
        # Get actual settings
        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        self.width = actual_width
        self.height = actual_height
        
        self.get_logger().info(f'Webcam opened: {device}')
        self.get_logger().info(f'Resolution: {actual_width}x{actual_height} @ {actual_fps} fps')
        self.get_logger().info('Publishing to /webcam/image_raw')
        
        # Timer for frame capture
        self.timer = self.create_timer(1.0 / fps, self.capture_and_publish)
        
        # Frame counter
        self.frame_count = 0
        self.last_log_time = self.get_clock().now()
        
    def capture_and_publish(self):
        ret, frame = self.cap.read()
        if not ret:
            self.get_logger().warn('Failed to capture frame from webcam')
            return
        
        # Create header
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = 'webcam_optical_frame'
        
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
            compressed_msg.data = cv2.imencode(
                '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
            self.compressed_pub.publish(compressed_msg)
        except Exception as e:
            self.get_logger().warn(f'Failed to publish compressed image: {e}')
        
        # Publish camera info
        info_msg = CameraInfo()
        info_msg.header = header
        info_msg.width = self.width
        info_msg.height = self.height
        info_msg.distortion_model = 'plumb_bob'
        
        # Approximate camera matrix (uncalibrated)
        # Focal length estimate based on typical webcam FOV (~60-70 degrees)
        fx = fy = self.width * 1.2  # Approximate focal length
        cx, cy = self.width / 2, self.height / 2
        info_msg.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        info_msg.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        info_msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        self.info_pub.publish(info_msg)
        
        self.frame_count += 1
        
        # Log stats periodically
        now = self.get_clock().now()
        elapsed = (now - self.last_log_time).nanoseconds / 1e9
        if elapsed >= 10.0:
            actual_fps = self.frame_count / elapsed
            self.get_logger().info(f'Publishing at {actual_fps:.1f} fps')
            self.frame_count = 0
            self.last_log_time = now
    
    def destroy_node(self):
        if self.cap:
            self.cap.release()
        super().destroy_node()


def main():
    parser = argparse.ArgumentParser(description='USB Webcam ROS2 Publisher')
    parser.add_argument('--device', '-d', default='/dev/video0',
                        help='Video device path (default: /dev/video0)')
    parser.add_argument('--width', '-W', type=int, default=640,
                        help='Frame width (default: 640)')
    parser.add_argument('--height', '-H', type=int, default=480,
                        help='Frame height (default: 480)')
    parser.add_argument('--fps', '-f', type=float, default=30.0,
                        help='Frame rate (default: 30)')
    parser.add_argument('--no-mjpg', action='store_true',
                        help='Disable MJPG format (use YUYV)')
    
    args, ros_args = parser.parse_known_args()
    
    rclpy.init(args=ros_args)
    
    try:
        node = WebcamPublisher(
            device=args.device,
            width=args.width,
            height=args.height,
            fps=args.fps,
            use_mjpg=not args.no_mjpg
        )
        rclpy.spin(node)
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
