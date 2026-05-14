#!/usr/bin/env python3
"""
Enhanced ROS2 Stereo Depth Publisher Node

Includes:
- TF Integration (static transforms for camera frames)
- Diagnostic Topics (health, performance metrics)
- Depth Filtering (temporal, spatial, confidence)
- Foxglove Integration (colorized depth, compressed images)
- Debug visualization topics

Published Topics:
    /stereo/depth/image_raw (sensor_msgs/Image) - Depth image (32FC1, meters)
    /stereo/depth/image_color (sensor_msgs/Image) - Colorized depth (BGR8)
    /stereo/depth/compressed (sensor_msgs/CompressedImage) - Compressed depth
    /stereo/left/image_rect (sensor_msgs/Image) - Rectified left camera image
    /stereo/camera_info (sensor_msgs/CameraInfo) - Camera intrinsics
    /stereo/depth/points (sensor_msgs/PointCloud2) - 3D point cloud (optional)
    /stereo/depth/filtered (sensor_msgs/Image) - Filtered depth (optional)
    /stereo/depth/confidence (sensor_msgs/Image) - Match confidence map
    /stereo/diagnostics (diagnostic_msgs/DiagnosticArray) - System diagnostics

TF Frames:
    base_link -> stereo_camera_link
    stereo_camera_link -> stereo_left_optical_frame
    stereo_camera_link -> stereo_right_optical_frame
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import Image, CameraInfo, PointCloud2, PointField, CompressedImage
from std_msgs.msg import Header
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from geometry_msgs.msg import TransformStamped
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
import cv2
import numpy as np
import json
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from collections import deque
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

    # TF Configuration
    camera_x: float = 0.1  # meters from base_link
    camera_y: float = 0.0
    camera_z: float = 0.15
    camera_roll: float = 0.0  # radians
    camera_pitch: float = 0.0
    camera_yaw: float = 0.0

    # Filtering Configuration
    enable_temporal_filter: bool = True
    temporal_alpha: float = 0.4  # Smoothing factor (0-1, higher = more responsive)
    enable_spatial_filter: bool = True
    spatial_sigma: float = 0.8
    enable_hole_filling: bool = True
    hole_fill_radius: int = 3
    confidence_threshold: float = 0.5

    # Visualization Configuration
    publish_colorized: bool = True
    publish_compressed: bool = True
    publish_confidence: bool = True
    colormap: int = cv2.COLORMAP_JET
    depth_min_display: float = 0.3  # meters
    depth_max_display: float = 5.0  # meters
    jpeg_quality: int = 80

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
                    target_fps=data.get('target_fps', 10.0),
                    camera_x=data.get('camera_x', 0.1),
                    camera_y=data.get('camera_y', 0.0),
                    camera_z=data.get('camera_z', 0.15),
                    camera_roll=data.get('camera_roll', 0.0),
                    camera_pitch=data.get('camera_pitch', 0.0),
                    camera_yaw=data.get('camera_yaw', 0.0),
                    enable_temporal_filter=data.get('enable_temporal_filter', True),
                    temporal_alpha=data.get('temporal_alpha', 0.4),
                    enable_spatial_filter=data.get('enable_spatial_filter', True),
                    spatial_sigma=data.get('spatial_sigma', 0.8),
                    enable_hole_filling=data.get('enable_hole_filling', True),
                    hole_fill_radius=data.get('hole_fill_radius', 3),
                    confidence_threshold=data.get('confidence_threshold', 0.5),
                    publish_colorized=data.get('publish_colorized', True),
                    publish_compressed=data.get('publish_compressed', True),
                    publish_confidence=data.get('publish_confidence', True),
                    colormap=data.get('colormap', cv2.COLORMAP_JET),
                    depth_min_display=data.get('depth_min_display', 0.3),
                    depth_max_display=data.get('depth_max_display', 5.0),
                    jpeg_quality=data.get('jpeg_quality', 80)
                )
        return cls()


class ThreadedCamera:
    """Thread-safe camera capture with statistics"""

    def __init__(self, device_id: int, width: int, height: int):
        self.device_id = device_id
        self.width = width
        self.height = height
        self.frame: Optional[np.ndarray] = None
        self.running = False
        self.lock = threading.Lock()
        self.cap: Optional[cv2.VideoCapture] = None

        # Statistics
        self.frame_count = 0
        self.drop_count = 0
        self.last_capture_time = 0
        self.capture_times = deque(maxlen=100)

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
                start = time.time()
                ret, frame = self.cap.read()
                capture_time = time.time() - start

                if ret and frame is not None:
                    with self.lock:
                        self.frame = frame
                        self.frame_count += 1
                        self.last_capture_time = time.time()
                        self.capture_times.append(capture_time)
                else:
                    self.drop_count += 1
            time.sleep(0.001)

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def get_stats(self) -> Dict:
        """Get camera statistics"""
        with self.lock:
            avg_capture = np.mean(self.capture_times) if self.capture_times else 0
            return {
                'frame_count': self.frame_count,
                'drop_count': self.drop_count,
                'drop_rate': self.drop_count / max(1, self.frame_count + self.drop_count),
                'avg_capture_ms': avg_capture * 1000,
                'last_capture_age': time.time() - self.last_capture_time if self.last_capture_time else -1
            }

    def stop(self):
        self.running = False
        time.sleep(0.1)
        if self.cap:
            self.cap.release()


class DepthFilter:
    """Advanced depth filtering with temporal and spatial processing"""

    def __init__(self, config: StereoConfig):
        self.config = config
        self.prev_depth = None
        self.confidence = None

    def apply(self, depth: np.ndarray, disparity: np.ndarray = None) -> tuple:
        """Apply all configured filters and return (filtered_depth, confidence)"""
        filtered = depth.copy()

        # Calculate confidence from disparity if available
        if disparity is not None:
            self.confidence = self._calculate_confidence(disparity)
        else:
            self.confidence = np.ones_like(depth)

        # Apply temporal filter (smooths over time)
        if self.config.enable_temporal_filter:
            filtered = self._temporal_filter(filtered)

        # Apply spatial filter (smooths spatially)
        if self.config.enable_spatial_filter:
            filtered = self._spatial_filter(filtered)

        # Apply hole filling
        if self.config.enable_hole_filling:
            filtered = self._hole_fill(filtered)

        return filtered, self.confidence

    def _calculate_confidence(self, disparity: np.ndarray) -> np.ndarray:
        """Calculate confidence from disparity smoothness"""
        # Higher confidence where disparity is smooth
        grad_x = cv2.Sobel(disparity, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(disparity, cv2.CV_32F, 0, 1, ksize=3)
        gradient_mag = np.sqrt(grad_x**2 + grad_y**2)

        # Normalize to 0-1 (lower gradient = higher confidence)
        max_grad = np.percentile(gradient_mag[gradient_mag > 0], 95) if np.any(gradient_mag > 0) else 1.0
        confidence = 1.0 - np.clip(gradient_mag / max_grad, 0, 1)

        # Zero confidence where no depth
        confidence[disparity <= 0] = 0

        return confidence.astype(np.float32)

    def _temporal_filter(self, depth: np.ndarray) -> np.ndarray:
        """Exponential moving average over time"""
        if self.prev_depth is None:
            self.prev_depth = depth.copy()
            return depth

        alpha = self.config.temporal_alpha

        # Only filter where both frames have valid depth
        valid_curr = depth > 0
        valid_prev = self.prev_depth > 0
        both_valid = valid_curr & valid_prev

        filtered = depth.copy()
        filtered[both_valid] = (alpha * depth[both_valid] +
                                (1 - alpha) * self.prev_depth[both_valid])

        self.prev_depth = filtered.copy()
        return filtered

    def _spatial_filter(self, depth: np.ndarray) -> np.ndarray:
        """Bilateral filter preserving edges"""
        # Create mask of valid depth
        valid = depth > 0

        # Apply bilateral filter (edge-preserving smoothing)
        depth_8bit = np.clip(depth * 25, 0, 255).astype(np.uint8)
        filtered_8bit = cv2.bilateralFilter(depth_8bit, 5,
                                             self.config.spatial_sigma * 50,
                                             self.config.spatial_sigma * 50)
        filtered = filtered_8bit.astype(np.float32) / 25.0

        # Restore invalid regions
        filtered[~valid] = 0

        return filtered

    def _hole_fill(self, depth: np.ndarray) -> np.ndarray:
        """Fill small holes with nearby valid values"""
        radius = self.config.hole_fill_radius

        # Find holes (zero depth)
        holes = depth <= 0

        if not np.any(holes):
            return depth

        # Dilate valid depth to fill holes
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                            (radius * 2 + 1, radius * 2 + 1))

        # Use morphological closing to fill small holes
        filled = depth.copy()
        valid_mask = (depth > 0).astype(np.uint8)
        dilated_mask = cv2.dilate(valid_mask, kernel)

        # Inpaint small holes
        small_holes = (dilated_mask > 0) & (depth <= 0)
        if np.any(small_holes):
            # Use inpainting for small regions
            depth_8bit = np.clip(depth * 25, 0, 255).astype(np.uint8)
            inpaint_mask = small_holes.astype(np.uint8) * 255
            inpainted = cv2.inpaint(depth_8bit, inpaint_mask, radius, cv2.INPAINT_NS)
            filled[small_holes] = inpainted[small_holes].astype(np.float32) / 25.0

        return filled


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


class PerformanceTracker:
    """Track performance metrics"""

    def __init__(self, window_size: int = 100):
        self.compute_times = deque(maxlen=window_size)
        self.publish_times = deque(maxlen=window_size)
        self.frame_intervals = deque(maxlen=window_size)
        self.last_frame_time = None
        self.total_frames = 0
        self.start_time = time.time()

    def record_compute(self, duration: float):
        self.compute_times.append(duration)

    def record_publish(self, duration: float):
        self.publish_times.append(duration)

    def record_frame(self):
        now = time.time()
        if self.last_frame_time is not None:
            self.frame_intervals.append(now - self.last_frame_time)
        self.last_frame_time = now
        self.total_frames += 1

    def get_stats(self) -> Dict:
        runtime = time.time() - self.start_time
        return {
            'total_frames': self.total_frames,
            'runtime_sec': runtime,
            'avg_fps': self.total_frames / max(1, runtime),
            'current_fps': 1.0 / np.mean(self.frame_intervals) if self.frame_intervals else 0,
            'avg_compute_ms': np.mean(self.compute_times) * 1000 if self.compute_times else 0,
            'avg_publish_ms': np.mean(self.publish_times) * 1000 if self.publish_times else 0,
            'max_compute_ms': max(self.compute_times) * 1000 if self.compute_times else 0,
        }


class StereoDepthEnhancedNode(Node):
    """Enhanced ROS2 node for stereo depth with TF, diagnostics, filtering, and visualization"""

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

        self.get_logger().info(f"Enhanced Stereo Depth Node starting...")

        # Configuration - try to load from config file
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
        self.get_logger().info(f"  Filtering: temporal={self.config.enable_temporal_filter}, spatial={self.config.enable_spatial_filter}")

        # Load calibration
        self._load_calibration()

        # Depth correction
        if self.use_correction:
            self.depth_correction = DepthCorrection(calibration_dir)
            if self.depth_correction.coefficients is not None:
                self.get_logger().info("Depth correction loaded")
        else:
            self.depth_correction = None

        # Initialize depth filter
        self.depth_filter = DepthFilter(self.config)

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

        # Performance tracking
        self.perf = PerformanceTracker()

        # Store latest disparity for confidence calculation
        self.latest_disparity = None

        # QoS profiles
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        reliable_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # Core Publishers
        self.depth_pub = self.create_publisher(Image, '/stereo/depth/image_raw', sensor_qos)
        self.left_pub = self.create_publisher(Image, '/stereo/left/image_rect', sensor_qos)
        self.camera_info_pub = self.create_publisher(CameraInfo, '/stereo/camera_info', sensor_qos)

        # Enhanced Publishers
        if self.config.publish_colorized:
            self.depth_color_pub = self.create_publisher(Image, '/stereo/depth/image_color', sensor_qos)

        if self.config.publish_compressed:
            self.depth_compressed_pub = self.create_publisher(CompressedImage, '/stereo/depth/compressed', sensor_qos)
            self.left_compressed_pub = self.create_publisher(CompressedImage, '/stereo/left/compressed', sensor_qos)

        if self.config.publish_confidence:
            self.confidence_pub = self.create_publisher(Image, '/stereo/depth/confidence', sensor_qos)

        # Filtered depth publisher
        self.filtered_depth_pub = self.create_publisher(Image, '/stereo/depth/filtered', sensor_qos)

        if self.publish_pointcloud:
            self.pointcloud_pub = self.create_publisher(PointCloud2, '/stereo/depth/points', sensor_qos)

        # Diagnostics publisher
        self.diag_pub = self.create_publisher(DiagnosticArray, '/stereo/diagnostics', reliable_qos)

        # TF Broadcasters
        self.tf_static_broadcaster = StaticTransformBroadcaster(self)
        self._publish_static_transforms()

        # Timers
        timer_period = 1.0 / self.publish_rate
        self.timer = self.create_timer(timer_period, self._publish_callback)
        self.diag_timer = self.create_timer(1.0, self._publish_diagnostics)  # 1 Hz

        self.get_logger().info("Enhanced Stereo Depth Node ready!")
        self.get_logger().info(f"  Publishing colorized: {self.config.publish_colorized}")
        self.get_logger().info(f"  Publishing compressed: {self.config.publish_compressed}")
        self.get_logger().info(f"  Publishing confidence: {self.config.publish_confidence}")

    def _publish_static_transforms(self):
        """Publish static TF transforms for camera frames"""
        transforms = []
        stamp = self.get_clock().now().to_msg()

        # base_link -> stereo_camera_link
        t1 = TransformStamped()
        t1.header.stamp = stamp
        t1.header.frame_id = 'base_link'
        t1.child_frame_id = 'stereo_camera_link'
        t1.transform.translation.x = self.config.camera_x
        t1.transform.translation.y = self.config.camera_y
        t1.transform.translation.z = self.config.camera_z

        # Convert RPY to quaternion
        quat = self._euler_to_quaternion(self.config.camera_roll,
                                          self.config.camera_pitch,
                                          self.config.camera_yaw)
        t1.transform.rotation.x = quat[0]
        t1.transform.rotation.y = quat[1]
        t1.transform.rotation.z = quat[2]
        t1.transform.rotation.w = quat[3]
        transforms.append(t1)

        # stereo_camera_link -> stereo_left_optical_frame
        t2 = TransformStamped()
        t2.header.stamp = stamp
        t2.header.frame_id = 'stereo_camera_link'
        t2.child_frame_id = 'stereo_left_optical_frame'
        t2.transform.translation.x = 0.0
        t2.transform.translation.y = 0.0
        t2.transform.translation.z = 0.0
        # Optical frame rotation (Z forward, X right, Y down)
        quat_opt = self._euler_to_quaternion(-np.pi/2, 0, -np.pi/2)
        t2.transform.rotation.x = quat_opt[0]
        t2.transform.rotation.y = quat_opt[1]
        t2.transform.rotation.z = quat_opt[2]
        t2.transform.rotation.w = quat_opt[3]
        transforms.append(t2)

        # stereo_camera_link -> stereo_right_optical_frame
        t3 = TransformStamped()
        t3.header.stamp = stamp
        t3.header.frame_id = 'stereo_camera_link'
        t3.child_frame_id = 'stereo_right_optical_frame'
        t3.transform.translation.x = 0.0
        t3.transform.translation.y = -self.baseline_mm / 1000.0  # baseline in meters
        t3.transform.translation.z = 0.0
        t3.transform.rotation.x = quat_opt[0]
        t3.transform.rotation.y = quat_opt[1]
        t3.transform.rotation.z = quat_opt[2]
        t3.transform.rotation.w = quat_opt[3]
        transforms.append(t3)

        # Alias: stereo_camera -> stereo_left_optical_frame (for backward compatibility)
        t4 = TransformStamped()
        t4.header.stamp = stamp
        t4.header.frame_id = 'stereo_left_optical_frame'
        t4.child_frame_id = 'stereo_camera'
        t4.transform.translation.x = 0.0
        t4.transform.translation.y = 0.0
        t4.transform.translation.z = 0.0
        t4.transform.rotation.x = 0.0
        t4.transform.rotation.y = 0.0
        t4.transform.rotation.z = 0.0
        t4.transform.rotation.w = 1.0
        transforms.append(t4)

        self.tf_static_broadcaster.sendTransform(transforms)
        self.get_logger().info(f"Published static TF transforms: base_link -> stereo_camera_link -> optical frames")

    def _euler_to_quaternion(self, roll: float, pitch: float, yaw: float) -> tuple:
        """Convert Euler angles to quaternion"""
        cy = np.cos(yaw * 0.5)
        sy = np.sin(yaw * 0.5)
        cp = np.cos(pitch * 0.5)
        sp = np.sin(pitch * 0.5)
        cr = np.cos(roll * 0.5)
        sr = np.sin(roll * 0.5)

        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy
        qw = cr * cp * cy + sr * sp * sy

        return (qx, qy, qz, qw)

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
        self.camera_matrix = np.array(self.calib['projection_left'])[:3, :3]

        self.get_logger().info(f"Calibration loaded: baseline={self.baseline_mm:.1f}mm, focal={self.focal_length:.1f}px")

    def _init_stereo_matcher(self):
        """Initialize StereoSGBM matcher"""
        self.num_disparities = 128
        self.block_size = 7

        self.stereo = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=self.num_disparities,
            blockSize=self.block_size,
            P1=8 * 1 * self.block_size ** 2,
            P2=32 * 1 * self.block_size ** 2,
            disp12MaxDiff=2,
            uniquenessRatio=5,
            speckleWindowSize=50,
            speckleRange=16,
            preFilterCap=31,
            mode=cv2.STEREO_SGBM_MODE_HH
        )

    def _compute_depth(self, left: np.ndarray, right: np.ndarray) -> tuple:
        """Compute depth from stereo pair with disparity output"""
        if self.config.rotate_90_cw:
            left = cv2.rotate(left, cv2.ROTATE_90_CLOCKWISE)
            right = cv2.rotate(right, cv2.ROTATE_90_CLOCKWISE)

        rect_left = cv2.remap(left, self.map_l1, self.map_l2, cv2.INTER_LINEAR)
        rect_right = cv2.remap(right, self.map_r1, self.map_r2, cv2.INTER_LINEAR)

        gray_l = cv2.cvtColor(rect_left, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(rect_right, cv2.COLOR_BGR2GRAY)

        # Downsample
        scale = 2
        h, w = gray_l.shape
        small_l = cv2.resize(gray_l, (w // scale, h // scale), interpolation=cv2.INTER_AREA)
        small_r = cv2.resize(gray_r, (w // scale, h // scale), interpolation=cv2.INTER_AREA)

        # Compute disparity
        disparity = self.stereo.compute(small_l, small_r)
        disp_float = disparity.astype(np.float32) / 16.0

        # Store for confidence calculation
        self.latest_disparity = cv2.resize(disp_float, (w, h), interpolation=cv2.INTER_LINEAR)

        # Convert to depth
        scaled_focal = self.focal_length / scale
        disp_float[disp_float <= 0] = 0.1
        depth_small = (self.baseline_mm * scaled_focal) / disp_float / 1000.0

        depth = cv2.resize(depth_small, (w, h), interpolation=cv2.INTER_LINEAR)
        depth[depth > 10.0] = 0
        depth[depth < 0.1] = 0

        if self.depth_correction is not None and self.depth_correction.coefficients is not None:
            depth = self.depth_correction.correct(depth)

        return rect_left, depth

    def _colorize_depth(self, depth: np.ndarray) -> np.ndarray:
        """Convert depth to colorized visualization"""
        # Normalize to display range
        depth_display = np.clip(depth, self.config.depth_min_display, self.config.depth_max_display)
        depth_normalized = (depth_display - self.config.depth_min_display) / (
            self.config.depth_max_display - self.config.depth_min_display)
        depth_8bit = (depth_normalized * 255).astype(np.uint8)

        # Apply colormap (invert so closer = warmer)
        depth_8bit = 255 - depth_8bit
        colored = cv2.applyColorMap(depth_8bit, self.config.colormap)

        # Mask invalid depth as black
        colored[depth <= 0] = [0, 0, 0]

        return colored

    def _create_camera_info(self, stamp) -> CameraInfo:
        """Create CameraInfo message"""
        msg = CameraInfo()
        msg.header.stamp = stamp
        msg.header.frame_id = "stereo_left_optical_frame"

        h, w = self.map_l1.shape[:2]
        msg.height = h
        msg.width = w
        msg.k = self.camera_matrix.flatten().tolist()
        msg.d = [0.0, 0.0, 0.0, 0.0, 0.0]
        msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        msg.p = [
            self.focal_length, 0.0, w/2, 0.0,
            0.0, self.focal_length, h/2, 0.0,
            0.0, 0.0, 1.0, 0.0
        ]

        return msg

    def _create_pointcloud(self, depth: np.ndarray, image: np.ndarray, stamp) -> PointCloud2:
        """Create PointCloud2 message from depth"""
        h, w = depth.shape
        u = np.arange(w)
        v = np.arange(h)
        u, v = np.meshgrid(u, v)
        cx, cy = w / 2, h / 2
        fx = fy = self.focal_length
        z = depth
        x = (u - cx) * z / fx
        y = (v - cy) * z / fy
        valid = z > 0
        x, y, z = x[valid], y[valid], z[valid]

        if len(image.shape) == 3:
            b, g, r = image[:,:,0][valid], image[:,:,1][valid], image[:,:,2][valid]
        else:
            r = g = b = image[valid]

        rgb = (r.astype(np.uint32) << 16) | (g.astype(np.uint32) << 8) | b.astype(np.uint32)
        rgb_float = rgb.view(np.float32)

        points = np.zeros(len(x), dtype=[
            ('x', np.float32), ('y', np.float32), ('z', np.float32), ('rgb', np.float32)
        ])
        points['x'], points['y'], points['z'], points['rgb'] = x, y, z, rgb_float

        msg = PointCloud2()
        msg.header.stamp = stamp
        msg.header.frame_id = "stereo_left_optical_frame"
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

    def _numpy_to_image_msg(self, arr: np.ndarray, encoding: str, frame_id: str = "stereo_left_optical_frame") -> Image:
        """Convert numpy array to ROS Image message"""
        msg = Image()
        msg.header.frame_id = frame_id
        msg.height = arr.shape[0]
        msg.width = arr.shape[1]
        msg.encoding = encoding

        if encoding == '32FC1':
            msg.step = arr.shape[1] * 4
            msg.data = arr.astype(np.float32).tobytes()
        elif encoding == 'bgr8':
            msg.step = arr.shape[1] * 3
            msg.data = arr.astype(np.uint8).tobytes()
        elif encoding == 'mono8':
            msg.step = arr.shape[1]
            msg.data = arr.astype(np.uint8).tobytes()
        else:
            raise ValueError(f"Unsupported encoding: {encoding}")

        msg.is_bigendian = False
        return msg

    def _create_compressed_image(self, image: np.ndarray, format: str = 'jpeg') -> CompressedImage:
        """Create compressed image message"""
        msg = CompressedImage()
        msg.header.frame_id = "stereo_left_optical_frame"
        msg.format = format

        if format == 'jpeg':
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.config.jpeg_quality]
            _, encoded = cv2.imencode('.jpg', image, encode_param)
        else:
            _, encoded = cv2.imencode('.png', image)

        msg.data = encoded.tobytes()
        return msg

    def _publish_callback(self):
        """Timer callback to publish depth data"""
        try:
            frame_l = self.cam_left.get_frame()
            frame_r = self.cam_right.get_frame()

            if frame_l is None or frame_r is None:
                return

            # Compute depth
            compute_start = time.time()
            rect_left, depth = self._compute_depth(frame_l, frame_r)
            compute_time = time.time() - compute_start
            self.perf.record_compute(compute_time)

            # Apply filtering
            filtered_depth, confidence = self.depth_filter.apply(depth, self.latest_disparity)

            publish_start = time.time()
            stamp = self.get_clock().now().to_msg()

            # Publish raw depth
            depth_msg = self._numpy_to_image_msg(depth.astype(np.float32), '32FC1')
            depth_msg.header.stamp = stamp
            self.depth_pub.publish(depth_msg)

            # Publish filtered depth
            filtered_msg = self._numpy_to_image_msg(filtered_depth.astype(np.float32), '32FC1')
            filtered_msg.header.stamp = stamp
            self.filtered_depth_pub.publish(filtered_msg)

            # Publish rectified left image
            left_msg = self._numpy_to_image_msg(rect_left, 'bgr8')
            left_msg.header.stamp = stamp
            self.left_pub.publish(left_msg)

            # Publish colorized depth
            if self.config.publish_colorized:
                depth_color = self._colorize_depth(filtered_depth)
                color_msg = self._numpy_to_image_msg(depth_color, 'bgr8')
                color_msg.header.stamp = stamp
                self.depth_color_pub.publish(color_msg)

            # Publish compressed images
            if self.config.publish_compressed:
                # Compress colorized depth
                depth_color = self._colorize_depth(filtered_depth) if not self.config.publish_colorized else depth_color
                comp_depth = self._create_compressed_image(depth_color)
                comp_depth.header.stamp = stamp
                self.depth_compressed_pub.publish(comp_depth)

                # Compress left image
                comp_left = self._create_compressed_image(rect_left)
                comp_left.header.stamp = stamp
                self.left_compressed_pub.publish(comp_left)

            # Publish confidence
            if self.config.publish_confidence:
                conf_8bit = (confidence * 255).astype(np.uint8)
                conf_msg = self._numpy_to_image_msg(conf_8bit, 'mono8')
                conf_msg.header.stamp = stamp
                self.confidence_pub.publish(conf_msg)

            # Publish camera info
            camera_info_msg = self._create_camera_info(stamp)
            self.camera_info_pub.publish(camera_info_msg)

            # Publish point cloud
            if self.publish_pointcloud:
                pc_msg = self._create_pointcloud(filtered_depth, rect_left, stamp)
                self.pointcloud_pub.publish(pc_msg)

            publish_time = time.time() - publish_start
            self.perf.record_publish(publish_time)
            self.perf.record_frame()

        except Exception as e:
            self.get_logger().error(f"Publish callback error: {e}")
            import traceback
            traceback.print_exc()

    def _publish_diagnostics(self):
        """Publish diagnostic information"""
        diag_msg = DiagnosticArray()
        diag_msg.header.stamp = self.get_clock().now().to_msg()

        # Overall status
        status = DiagnosticStatus()
        status.name = "stereo_depth_node"
        status.hardware_id = "stereo_cameras"

        perf_stats = self.perf.get_stats()
        left_stats = self.cam_left.get_stats()
        right_stats = self.cam_right.get_stats()

        # Determine overall health
        fps = perf_stats['current_fps']
        if fps >= self.publish_rate * 0.8:
            status.level = DiagnosticStatus.OK
            status.message = f"Running at {fps:.1f} FPS"
        elif fps >= self.publish_rate * 0.5:
            status.level = DiagnosticStatus.WARN
            status.message = f"Low frame rate: {fps:.1f} FPS"
        else:
            status.level = DiagnosticStatus.ERROR
            status.message = f"Critical: {fps:.1f} FPS"

        status.values = [
            KeyValue(key='fps', value=f"{fps:.2f}"),
            KeyValue(key='target_fps', value=f"{self.publish_rate:.1f}"),
            KeyValue(key='total_frames', value=str(perf_stats['total_frames'])),
            KeyValue(key='compute_time_ms', value=f"{perf_stats['avg_compute_ms']:.1f}"),
            KeyValue(key='publish_time_ms', value=f"{perf_stats['avg_publish_ms']:.1f}"),
            KeyValue(key='max_compute_ms', value=f"{perf_stats['max_compute_ms']:.1f}"),
            KeyValue(key='left_camera_drops', value=str(left_stats['drop_count'])),
            KeyValue(key='right_camera_drops', value=str(right_stats['drop_count'])),
            KeyValue(key='left_capture_ms', value=f"{left_stats['avg_capture_ms']:.1f}"),
            KeyValue(key='right_capture_ms', value=f"{right_stats['avg_capture_ms']:.1f}"),
            KeyValue(key='temporal_filter', value=str(self.config.enable_temporal_filter)),
            KeyValue(key='spatial_filter', value=str(self.config.enable_spatial_filter)),
            KeyValue(key='hole_filling', value=str(self.config.enable_hole_filling)),
        ]

        diag_msg.status.append(status)
        self.diag_pub.publish(diag_msg)

    def destroy_node(self):
        """Clean up on shutdown"""
        self.get_logger().info("Shutting down...")
        self.cam_left.stop()
        self.cam_right.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    try:
        node = StereoDepthEnhancedNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()
