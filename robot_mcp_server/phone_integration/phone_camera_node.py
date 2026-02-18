#!/usr/bin/env python3
"""
Phone Camera ROS2 Node
Captures video from phone via scrcpy v4l2loopback and publishes to ROS2.

Requirements:
    - scrcpy 3.x installed (snap install scrcpy)
    - v4l2loopback module loaded
    - USB debugging enabled on phone

Published Topics:
    /phone/image_raw            - sensor_msgs/Image (raw BGR8)
    /phone/image_raw/compressed - sensor_msgs/CompressedImage (JPEG)
    /phone/camera_info          - sensor_msgs/CameraInfo
    /phone/camera_connected     - std_msgs/Bool

Services:
    /phone/camera/switch        - Switch between front/back camera
    /phone/camera/toggle_torch  - Toggle flashlight/torch
"""

import os
import re
import subprocess
import threading
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from rclpy.executors import MultiThreadedExecutor, ExternalShutdownException
from sensor_msgs.msg import Image, CompressedImage, CameraInfo
from std_msgs.msg import Bool, Header
from std_srvs.srv import Trigger, SetBool
from cv_bridge import CvBridge

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("Warning: opencv-python not installed")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def validate_video_device(device: str) -> bool:
    """Validate video device path to prevent injection"""
    # Must match /dev/video followed by digits only
    return bool(re.match(r'^/dev/video\d+$', device))


class PhoneCameraNode(Node):
    """ROS2 node for phone camera via scrcpy"""

    # Camera configurations
    CAMERAS = {
        'back_main': {'id': 0, 'resolution': (1280, 720), 'fps': 30},
        'front': {'id': 1, 'resolution': (1280, 720), 'fps': 30},
        'back_ultrawide': {'id': 2, 'resolution': (1280, 720), 'fps': 30},
    }

    def __init__(self):
        super().__init__('phone_camera_node')

        # Parameters
        self.declare_parameter('video_device', '/dev/video10')
        self.declare_parameter('camera', 'back_main')  # back_main, front, back_ultrawide
        self.declare_parameter('width', 1280)
        self.declare_parameter('height', 720)
        self.declare_parameter('fps', 30)
        self.declare_parameter('frame_id', 'phone_camera_link')
        self.declare_parameter('publish_raw', True)
        self.declare_parameter('publish_compressed', True)
        self.declare_parameter('jpeg_quality', 75)
        self.declare_parameter('auto_start_scrcpy', True)

        self.video_device = self.get_parameter('video_device').value
        self.camera_name = self.get_parameter('camera').value
        self.width = self.get_parameter('width').value
        self.height = self.get_parameter('height').value
        self.fps = self.get_parameter('fps').value
        self.frame_id = self.get_parameter('frame_id').value
        self.publish_raw = self.get_parameter('publish_raw').value
        self.publish_compressed = self.get_parameter('publish_compressed').value
        self.jpeg_quality = self.get_parameter('jpeg_quality').value
        self.auto_start_scrcpy = self.get_parameter('auto_start_scrcpy').value

        # QoS for camera
        camera_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Publishers
        if self.publish_raw:
            self.pub_image = self.create_publisher(Image, '/phone/image_raw', camera_qos)
        if self.publish_compressed:
            self.pub_compressed = self.create_publisher(
                CompressedImage, '/phone/image_raw/compressed', camera_qos)
        self.pub_camera_info = self.create_publisher(CameraInfo, '/phone/camera_info', camera_qos)
        self.pub_connected = self.create_publisher(Bool, '/phone/camera_connected', 10)

        # Services
        self.srv_switch = self.create_service(Trigger, '/phone/camera/switch', self.switch_camera_callback)
        self.srv_torch = self.create_service(SetBool, '/phone/camera/torch', self.torch_callback)

        # State
        self.cv_bridge = CvBridge()
        self.cap: Optional[cv2.VideoCapture] = None
        self.scrcpy_process: Optional[subprocess.Popen] = None
        self.running = True
        self.connected = False
        self.current_camera_id = self.CAMERAS.get(self.camera_name, {}).get('id', 0)
        self.torch_on = False

        # Camera info (approximate for phone camera)
        self.camera_info = self._create_camera_info()

        # Start capture thread
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()

        # Status timer
        self.create_timer(1.0, self._publish_status)

        self.get_logger().info(f'Phone camera node started, device: {self.video_device}')

    def _create_camera_info(self) -> CameraInfo:
        """Create approximate camera info for phone camera"""
        info = CameraInfo()
        info.header.frame_id = self.frame_id
        info.width = self.width
        info.height = self.height
        info.distortion_model = 'plumb_bob'

        # Approximate intrinsics for a typical phone camera
        # These should be calibrated for accurate depth estimation
        fx = fy = self.width * 0.9  # approximate focal length
        cx = self.width / 2.0
        cy = self.height / 2.0

        info.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        info.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.d = [0.0, 0.0, 0.0, 0.0, 0.0]  # assume no distortion

        return info

    def _start_scrcpy(self):
        """Start scrcpy to stream phone camera to v4l2loopback"""
        # Validate video device to prevent injection
        if not validate_video_device(self.video_device):
            self.get_logger().error(f'Invalid video device path: {self.video_device}')
            return False

        # Check if scrcpy is already running
        result = subprocess.run(['pgrep', '-f', 'scrcpy.*v4l2-sink'],
                               capture_output=True, timeout=5)
        if result.returncode == 0:
            self.get_logger().info('scrcpy already running')
            return True

        # Extract video number safely
        video_num = self.video_device.split("video")[-1]
        if not video_num.isdigit():
            self.get_logger().error(f'Invalid video number: {video_num}')
            return False

        # Ensure v4l2loopback is loaded with validated parameters
        try:
            subprocess.run(['sudo', 'modprobe', 'v4l2loopback', 'devices=1',
                           f'video_nr={video_num}',
                           'card_label=Phone_Camera', 'exclusive_caps=1'],
                          capture_output=True, timeout=10, check=False)
            subprocess.run(['sudo', 'chmod', '666', self.video_device],
                          capture_output=True, timeout=5, check=False)
        except subprocess.TimeoutExpired:
            self.get_logger().warn('v4l2loopback setup timed out')

        # Start scrcpy
        cmd = [
            '/snap/bin/scrcpy',
            '--video-source=camera',
            f'--camera-id={self.current_camera_id}',
            f'--camera-size={self.width}x{self.height}',
            '--no-playback',
            f'--v4l2-sink={self.video_device}',
            '--video-codec=h264',
        ]

        env = os.environ.copy()
        env['SNAP_LAUNCHER_NOTICE_ENABLED'] = 'false'

        try:
            self.scrcpy_process = subprocess.Popen(
                cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)  # Wait for scrcpy to start
            self.get_logger().info(f'Started scrcpy with camera {self.current_camera_id}')
            return True
        except Exception as e:
            self.get_logger().error(f'Failed to start scrcpy: {e}')
            return False

    def _stop_scrcpy(self):
        """Stop scrcpy process"""
        if self.scrcpy_process:
            self.scrcpy_process.terminate()
            self.scrcpy_process.wait(timeout=5)
            self.scrcpy_process = None
        subprocess.run(['pkill', '-f', 'scrcpy.*v4l2-sink'], capture_output=True)

    def _capture_loop(self):
        """Main capture loop with exponential backoff"""
        retry_count = 0
        max_retries = 10
        backoff_time = 0.5  # Initial backoff in seconds
        max_backoff = 30.0  # Maximum backoff time
        consecutive_errors = 0
        max_consecutive_errors = 50

        while self.running:
            try:
                # Start scrcpy if needed
                if self.auto_start_scrcpy and not self._is_scrcpy_running():
                    self._start_scrcpy()
                    time.sleep(2)

                # Open video capture
                if self.cap is None or not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(self.video_device, cv2.CAP_V4L2)
                    if not self.cap.isOpened():
                        self.get_logger().warn(f'Cannot open {self.video_device}, retrying... (attempt {retry_count + 1})')
                        # Exponential backoff
                        sleep_time = min(backoff_time * (1.5 ** retry_count), max_backoff)
                        time.sleep(sleep_time)
                        retry_count += 1
                        if retry_count > max_retries:
                            self.get_logger().warn(f'Max retries ({max_retries}) exceeded, restarting scrcpy')
                            retry_count = 0
                            backoff_time = 0.5  # Reset backoff
                            self._start_scrcpy()
                        continue

                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                    retry_count = 0
                    backoff_time = 0.5  # Reset backoff on success
                    consecutive_errors = 0

                # Read frame
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    self.connected = False
                    consecutive_errors += 1
                    if consecutive_errors > max_consecutive_errors:
                        self.get_logger().warn(f'Too many consecutive read errors, resetting capture')
                        if self.cap:
                            self.cap.release()
                            self.cap = None
                        consecutive_errors = 0
                    time.sleep(0.1)
                    continue

                self.connected = True
                consecutive_errors = 0
                self._publish_frame(frame)

            except Exception as e:
                self.get_logger().error(f'Capture error: {e}')
                self.connected = False
                consecutive_errors += 1
                if self.cap:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self.cap = None
                # Exponential backoff on errors
                sleep_time = min(backoff_time * (1.5 ** min(consecutive_errors, 10)), max_backoff)
                time.sleep(sleep_time)

    def _is_scrcpy_running(self) -> bool:
        """Check if scrcpy is running"""
        result = subprocess.run(['pgrep', '-f', 'scrcpy.*v4l2-sink'], capture_output=True)
        return result.returncode == 0

    def _publish_frame(self, frame):
        """Publish frame to ROS2 topics"""
        now = self.get_clock().now()
        header = Header()
        header.stamp = now.to_msg()
        header.frame_id = self.frame_id

        # Publish raw image
        if self.publish_raw:
            img_msg = self.cv_bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            img_msg.header = header
            self.pub_image.publish(img_msg)

        # Publish compressed image
        if self.publish_compressed:
            comp_msg = CompressedImage()
            comp_msg.header = header
            comp_msg.format = 'jpeg'
            _, encoded = cv2.imencode('.jpg', frame,
                                     [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            comp_msg.data = encoded.tobytes()
            self.pub_compressed.publish(comp_msg)

        # Publish camera info
        self.camera_info.header = header
        self.pub_camera_info.publish(self.camera_info)

    def _publish_status(self):
        """Publish connection status"""
        msg = Bool()
        msg.data = self.connected
        self.pub_connected.publish(msg)

    def switch_camera_callback(self, request, response):
        """Switch between front and back camera"""
        # Cycle through cameras
        camera_list = list(self.CAMERAS.keys())
        current_idx = camera_list.index(self.camera_name) if self.camera_name in camera_list else 0
        next_idx = (current_idx + 1) % len(camera_list)
        self.camera_name = camera_list[next_idx]
        self.current_camera_id = self.CAMERAS[self.camera_name]['id']

        # Restart scrcpy with new camera
        self._stop_scrcpy()
        if self.cap:
            self.cap.release()
            self.cap = None
        time.sleep(1)
        self._start_scrcpy()

        response.success = True
        response.message = f'Switched to {self.camera_name} (camera {self.current_camera_id})'
        self.get_logger().info(response.message)
        return response

    def torch_callback(self, request, response):
        """Toggle phone flashlight/torch"""
        try:
            # Use ADB to control torch
            state = '1' if request.data else '0'
            subprocess.run([
                'adb', 'shell',
                f'cmd statusbar expand-settings && sleep 0.5 && cmd statusbar collapse'
            ], capture_output=True, timeout=5)

            self.torch_on = request.data
            response.success = True
            response.message = f'Torch {"on" if self.torch_on else "off"}'
        except Exception as e:
            response.success = False
            response.message = f'Failed to toggle torch: {e}'

        return response

    def destroy_node(self):
        """Clean shutdown"""
        self.running = False
        if self.cap:
            self.cap.release()
        self._stop_scrcpy()
        super().destroy_node()


def main(args=None):
    if not CV2_AVAILABLE:
        print("ERROR: opencv-python not installed. Run: pip install opencv-python")
        return

    rclpy.init(args=args)
    node = PhoneCameraNode()

    # Use MultiThreadedExecutor for better handling of blocking operations
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)

    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
