#!/usr/bin/env python3
"""
ROS2 Stereo Depth Publisher Node

Publishes stereo depth data as ROS2 topics for Nav2/SLAM integration.

Published Topics:
    /stereo/depth/image_raw (sensor_msgs/Image) - Depth image (32FC1, meters)
    /stereo/left/image_rect (sensor_msgs/Image) - Rectified left camera image
    /stereo/camera_info (sensor_msgs/CameraInfo) - Camera intrinsics
    /stereo/depth/points (sensor_msgs/PointCloud2) - 3D point cloud (optional)

Parameters:
    ~publish_rate (float): Target publish rate in Hz (default: 10.0)
    ~publish_pointcloud (bool): Whether to publish point cloud (default: False)
    ~use_correction (bool): Apply depth correction (default: True)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo, PointCloud2, PointField
from std_msgs.msg import Header
# cv_bridge has NumPy 2.x compatibility issues - we'll create Image messages manually
# from cv_bridge import CvBridge
import cv2
import numpy as np
import json
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import struct


@dataclass
class StereoConfig:
    """Stereo camera configuration"""
    left_device: int = 1
    right_device: int = 0
    width: int = 1280
    height: int = 720
    rotate_90_cw: bool = True
    calibration_dir: str = "calibration_data"
    target_fps: float = 10.0

    @classmethod
    def from_file(cls, config_path: str) -> 'StereoConfig':
        """Load config from JSON file"""
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f)
                return cls(
                    left_device=data.get('left_device', 1),
                    right_device=data.get('right_device', 0),
                    width=data.get('width', 1280),
                    height=data.get('height', 720),
                    rotate_90_cw=data.get('rotate_90_cw', True),
                    calibration_dir=data.get('calibration_dir', 'calibration_data'),
                    target_fps=data.get('target_fps', 10.0)
                )
        return cls()


class ThreadedCamera:
    """Thread-safe camera capture"""

    def __init__(self, device_id: int, width: int, height: int):
        self.device_id = device_id
        self.width = width
        self.height = height
        self.frame: Optional[np.ndarray] = None
        self.running = False
        self.lock = threading.Lock()
        self.cap: Optional[cv2.VideoCapture] = None

    def start(self) -> bool:
        self.cap = cv2.VideoCapture(self.device_id)
        if not self.cap.isOpened():
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return True

    def _capture_loop(self):
        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.frame = frame
            time.sleep(0.001)

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
        time.sleep(0.1)
        if self.cap:
            self.cap.release()


class DepthCorrection:
    """Applies polynomial correction to depth measurements"""

    def __init__(self, calibration_dir: str):
        self.coefficients = None
        correction_file = Path(calibration_dir) / "depth_correction.json"
        if correction_file.exists():
            with open(correction_file, 'r') as f:
                data = json.load(f)
                self.coefficients = np.array(data['coefficients'])

    def correct(self, depth: np.ndarray) -> np.ndarray:
        if self.coefficients is None:
            return depth
        corrected = np.polyval(self.coefficients, depth)
        corrected[depth <= 0] = 0
        return corrected


class StereoDepthNode(Node):
    """ROS2 node for stereo depth processing and publishing"""

    def __init__(self):
        super().__init__('stereo_depth_node')

        # Declare parameters
        self.declare_parameter('publish_rate', 10.0)
        self.declare_parameter('publish_pointcloud', False)
        self.declare_parameter('use_correction', True)
        self.declare_parameter('calibration_dir', 'calibration_data')

        # Get parameters
        self.publish_rate = self.get_parameter('publish_rate').value
        self.publish_pointcloud = self.get_parameter('publish_pointcloud').value
        self.use_correction = self.get_parameter('use_correction').value
        calibration_dir = self.get_parameter('calibration_dir').value

        self.get_logger().info(f"Stereo Depth Node starting...")

        # Configuration - try to load from config_pi.json first
        script_dir = Path(__file__).parent
        config_file = script_dir / "config_pi.json"
        if config_file.exists():
            self.config = StereoConfig.from_file(str(config_file))
            self.get_logger().info(f"Loaded config from {config_file}")
        else:
            self.config = StereoConfig(calibration_dir=calibration_dir)
            self.get_logger().info("Using default config")

        self.get_logger().info(f"  Left camera: /dev/video{self.config.left_device}")
        self.get_logger().info(f"  Right camera: /dev/video{self.config.right_device}")
        self.get_logger().info(f"  Resolution: {self.config.width}x{self.config.height}")
        self.get_logger().info(f"  Publish rate: {self.publish_rate} Hz")

        # Load calibration
        self._load_calibration()

        # Depth correction
        if self.use_correction:
            self.depth_correction = DepthCorrection(calibration_dir)
            if self.depth_correction.coefficients is not None:
                self.get_logger().info("Depth correction loaded")
            else:
                self.get_logger().warn("No depth correction found")
        else:
            self.depth_correction = None

        # Initialize stereo matcher
        self._init_stereo_matcher()

        # Initialize cameras
        self.cam_left = ThreadedCamera(self.config.left_device,
                                        self.config.width,
                                        self.config.height)
        self.cam_right = ThreadedCamera(self.config.right_device,
                                         self.config.width,
                                         self.config.height)

        if not self.cam_left.start() or not self.cam_right.start():
            self.get_logger().error("Failed to open cameras!")
            raise RuntimeError("Camera initialization failed")

        self.get_logger().info("Cameras initialized")

        # QoS profile for sensor data
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Publishers
        self.depth_pub = self.create_publisher(Image, '/stereo/depth/image_raw', sensor_qos)
        self.left_pub = self.create_publisher(Image, '/stereo/left/image_rect', sensor_qos)
        self.left_raw_pub = self.create_publisher(Image, '/stereo/left/image_raw', sensor_qos)
        self.right_raw_pub = self.create_publisher(Image, '/stereo/right/image_raw', sensor_qos)
        self.depth_color_pub = self.create_publisher(Image, '/stereo/depth/image_color', sensor_qos)
        self.camera_info_pub = self.create_publisher(CameraInfo, '/stereo/camera_info', sensor_qos)

        if self.publish_pointcloud:
            self.pointcloud_pub = self.create_publisher(PointCloud2, '/stereo/depth/points', sensor_qos)

        # Timer for publishing
        timer_period = 1.0 / self.publish_rate
        self.timer = self.create_timer(timer_period, self._publish_callback)

        self.get_logger().info("Stereo Depth Node ready!")

    def _load_calibration(self):
        """Load stereo calibration data"""
        calib_file = Path(self.config.calibration_dir) / "stereo_calibration.json"
        maps_file = Path(self.config.calibration_dir) / "stereo_maps.npz"

        if not calib_file.exists() or not maps_file.exists():
            raise FileNotFoundError(f"Calibration files not found in {self.config.calibration_dir}")

        with open(calib_file, 'r') as f:
            self.calib = json.load(f)

        maps = np.load(maps_file)
        self.map_l1 = maps['map_l1']
        self.map_l2 = maps['map_l2']
        self.map_r1 = maps['map_r1']
        self.map_r2 = maps['map_r2']

        self.baseline_mm = self.calib['baseline_mm']
        self.focal_length = self.calib['projection_left'][0][0]

        # Camera matrix for CameraInfo
        self.camera_matrix = np.array(self.calib['projection_left'])[:3, :3]

        self.get_logger().info(f"Calibration loaded: baseline={self.baseline_mm:.1f}mm, focal={self.focal_length:.1f}px")

    def _init_stereo_matcher(self):
        """Initialize StereoSGBM matcher (optimized for Pi performance)"""
        # Reduced for faster computation on Pi
        self.num_disparities = 128  # Reduced from 256 (min depth ~1.3m)
        self.block_size = 7  # Larger block = faster but less detail

        # Use faster SGBM mode for Pi
        self.stereo = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=self.num_disparities,
            blockSize=self.block_size,
            P1=8 * 1 * self.block_size ** 2,  # Reduced multiplier
            P2=32 * 1 * self.block_size ** 2,
            disp12MaxDiff=2,  # More tolerant
            uniquenessRatio=5,  # Less strict
            speckleWindowSize=50,  # Smaller window
            speckleRange=16,  # Reduced
            preFilterCap=31,  # Reduced
            mode=cv2.STEREO_SGBM_MODE_HH  # Faster mode
        )

    def _compute_depth(self, left: np.ndarray, right: np.ndarray) -> tuple:
        """Compute depth from stereo pair (optimized for Pi with downsampling)"""
        # Rotate if configured
        if self.config.rotate_90_cw:
            left = cv2.rotate(left, cv2.ROTATE_90_CLOCKWISE)
            right = cv2.rotate(right, cv2.ROTATE_90_CLOCKWISE)

        # Rectify
        rect_left = cv2.remap(left, self.map_l1, self.map_l2, cv2.INTER_LINEAR)
        rect_right = cv2.remap(right, self.map_r1, self.map_r2, cv2.INTER_LINEAR)

        # Convert to grayscale
        gray_l = cv2.cvtColor(rect_left, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(rect_right, cv2.COLOR_BGR2GRAY)

        # Downsample by 2x for faster computation on Pi
        scale = 2
        h, w = gray_l.shape
        small_l = cv2.resize(gray_l, (w // scale, h // scale), interpolation=cv2.INTER_AREA)
        small_r = cv2.resize(gray_r, (w // scale, h // scale), interpolation=cv2.INTER_AREA)

        # Compute disparity on downscaled images
        disparity = self.stereo.compute(small_l, small_r)
        disp_float = disparity.astype(np.float32) / 16.0

        # Convert to depth (scale focal length for downsampled images)
        scaled_focal = self.focal_length / scale
        disp_float[disp_float <= 0] = 0.1
        depth_small = (self.baseline_mm * scaled_focal) / disp_float / 1000.0

        # Upscale depth back to original size
        depth = cv2.resize(depth_small, (w, h), interpolation=cv2.INTER_LINEAR)

        # Clip to valid range
        depth[depth > 10.0] = 0
        depth[depth < 0.1] = 0

        # Apply correction if enabled
        if self.depth_correction is not None and self.depth_correction.coefficients is not None:
            depth = self.depth_correction.correct(depth)

        return rect_left, depth

    def _create_camera_info(self, stamp) -> CameraInfo:
        """Create CameraInfo message"""
        msg = CameraInfo()
        msg.header.stamp = stamp
        msg.header.frame_id = "stereo_camera"

        h, w = self.map_l1.shape[:2]
        msg.height = h
        msg.width = w

        # Camera matrix (3x3)
        msg.k = self.camera_matrix.flatten().tolist()

        # Distortion (rectified, so zeros)
        msg.d = [0.0, 0.0, 0.0, 0.0, 0.0]

        # Rectification matrix (identity for rectified)
        msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]

        # Projection matrix
        msg.p = [
            self.focal_length, 0.0, w/2, 0.0,
            0.0, self.focal_length, h/2, 0.0,
            0.0, 0.0, 1.0, 0.0
        ]

        return msg

    def _create_pointcloud(self, depth: np.ndarray, image: np.ndarray, stamp) -> PointCloud2:
        """Create PointCloud2 message from depth"""
        h, w = depth.shape

        # Create mesh grid for pixel coordinates
        u = np.arange(w)
        v = np.arange(h)
        u, v = np.meshgrid(u, v)

        # Principal point (assume center)
        cx, cy = w / 2, h / 2
        fx = fy = self.focal_length

        # Back-project to 3D
        z = depth
        x = (u - cx) * z / fx
        y = (v - cy) * z / fy

        # Filter valid points
        valid = z > 0
        x = x[valid]
        y = y[valid]
        z = z[valid]

        # Get colors
        if len(image.shape) == 3:
            b = image[:, :, 0][valid]
            g = image[:, :, 1][valid]
            r = image[:, :, 2][valid]
        else:
            r = g = b = image[valid]

        # Pack RGB into single float
        rgb = np.zeros(len(x), dtype=np.uint32)
        rgb = (r.astype(np.uint32) << 16) | (g.astype(np.uint32) << 8) | b.astype(np.uint32)
        rgb_float = rgb.view(np.float32)

        # Create point cloud data
        points = np.zeros(len(x), dtype=[
            ('x', np.float32),
            ('y', np.float32),
            ('z', np.float32),
            ('rgb', np.float32)
        ])
        points['x'] = x
        points['y'] = y
        points['z'] = z
        points['rgb'] = rgb_float

        # Create message
        msg = PointCloud2()
        msg.header.stamp = stamp
        msg.header.frame_id = "stereo_camera"
        msg.height = 1
        msg.width = len(x)
        msg.is_dense = True
        msg.is_bigendian = False

        msg.fields = [
            PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
            PointField(name='rgb', offset=12, datatype=PointField.FLOAT32, count=1),
        ]
        msg.point_step = 16
        msg.row_step = msg.point_step * len(x)
        msg.data = points.tobytes()

        return msg

    def _numpy_to_image_msg(self, arr: np.ndarray, encoding: str) -> Image:
        """Convert numpy array to ROS Image message without cv_bridge"""
        msg = Image()
        msg.height = arr.shape[0]
        msg.width = arr.shape[1]
        msg.encoding = encoding

        if encoding == '32FC1':
            msg.step = arr.shape[1] * 4  # 4 bytes per float32
            msg.data = arr.astype(np.float32).tobytes()
        elif encoding == 'bgr8':
            msg.step = arr.shape[1] * 3  # 3 bytes per pixel
            msg.data = arr.astype(np.uint8).tobytes()
        elif encoding == 'mono8':
            msg.step = arr.shape[1]  # 1 byte per pixel
            msg.data = arr.astype(np.uint8).tobytes()
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")

        msg.is_bigendian = False
        return msg

    def _publish_callback(self):
        """Timer callback to publish depth data"""
        try:
            # Get frames
            frame_l = self.cam_left.get_frame()
            frame_r = self.cam_right.get_frame()

            if frame_l is None or frame_r is None:
                return

            # Compute depth
            rect_left, depth = self._compute_depth(frame_l, frame_r)

            # Get timestamp
            stamp = self.get_clock().now().to_msg()

            # Publish depth image (32FC1 - meters)
            depth_msg = self._numpy_to_image_msg(depth.astype(np.float32), '32FC1')
            depth_msg.header.stamp = stamp
            depth_msg.header.frame_id = "stereo_camera"
            self.depth_pub.publish(depth_msg)

            # Publish rectified left image
            left_msg = self._numpy_to_image_msg(rect_left, 'bgr8')
            left_msg.header.stamp = stamp
            left_msg.header.frame_id = "stereo_camera"
            self.left_pub.publish(left_msg)

            # Publish raw left image
            if hasattr(self, "left_raw_pub"):
                left_raw_msg = self._numpy_to_image_msg(frame_l, 'bgr8')
                left_raw_msg.header.stamp = stamp
                left_raw_msg.header.frame_id = "stereo_camera"
                self.left_raw_pub.publish(left_raw_msg)
            
            # Publish raw right image
            if hasattr(self, "right_raw_pub"):
                right_raw_msg = self._numpy_to_image_msg(frame_r, 'bgr8')
                right_raw_msg.header.stamp = stamp
                right_raw_msg.header.frame_id = "stereo_camera"
                self.right_raw_pub.publish(right_raw_msg)
            
            # Publish colorized depth image
            if hasattr(self, "depth_color_pub"):
                depth_normalized = (np.clip(depth, 0, 10) / 10.0 * 255).astype(np.uint8)
                depth_color = cv2.applyColorMap(depth_normalized, cv2.COLORMAP_JET)
                depth_color_msg = self._numpy_to_image_msg(depth_color, 'bgr8')
                depth_color_msg.header.stamp = stamp
                depth_color_msg.header.frame_id = "stereo_camera"
                self.depth_color_pub.publish(depth_color_msg)

            # Publish camera info
            camera_info_msg = self._create_camera_info(stamp)
            self.camera_info_pub.publish(camera_info_msg)

            # Publish point cloud if enabled
            if self.publish_pointcloud:
                pc_msg = self._create_pointcloud(depth, rect_left, stamp)
                self.pointcloud_pub.publish(pc_msg)

        except Exception as e:
            self.get_logger().error(f"Publish callback error: {e}")
            import traceback
            traceback.print_exc()

    def destroy_node(self):
        """Clean up on shutdown"""
        self.get_logger().info("Shutting down...")
        self.cam_left.stop()
        self.cam_right.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    try:
        node = StereoDepthNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
