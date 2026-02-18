#!/usr/bin/env python3
"""
LIDAR + Camera Fusion Depth Node
Projects LIDAR points onto camera image to create depth information.

This approach uses your existing LIDAR data and fuses it with camera images
to create depth-enhanced visualization and sparse depth maps.

Published Topics:
    /phone/depth/lidar_projected   - sensor_msgs/Image (depth from LIDAR projection)
    /phone/depth/overlay           - sensor_msgs/Image (camera with LIDAR overlay)
    /phone/depth/points            - sensor_msgs/PointCloud2 (colored point cloud)

Subscribed Topics:
    /scan                          - sensor_msgs/LaserScan (LIDAR data)
    /phone/image_raw               - sensor_msgs/Image (camera image)
    /phone/camera_info             - sensor_msgs/CameraInfo (camera calibration)

TF Required:
    laser_frame -> phone_camera_link transform
"""

import math
import threading
from typing import Optional, Tuple
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, LaserScan, CameraInfo, PointCloud2, PointField
from std_msgs.msg import Header, Bool
from geometry_msgs.msg import TransformStamped
from tf2_ros import Buffer, TransformListener, TransformException

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("Warning: opencv not available")


class LidarCameraFusionNode(Node):
    """Fuses LIDAR data with camera images for depth perception"""

    def __init__(self):
        super().__init__('lidar_camera_fusion')

        # Parameters
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('image_topic', '/phone/image_raw')
        self.declare_parameter('camera_info_topic', '/phone/camera_info')
        self.declare_parameter('camera_frame', 'phone_camera_link')
        self.declare_parameter('laser_frame', 'laser_frame')
        self.declare_parameter('max_range', 10.0)  # meters
        self.declare_parameter('min_range', 0.1)
        self.declare_parameter('point_size', 3)
        self.declare_parameter('colormap', 'jet')  # jet, hot, rainbow

        self.scan_topic = self.get_parameter('scan_topic').value
        self.image_topic = self.get_parameter('image_topic').value
        self.camera_info_topic = self.get_parameter('camera_info_topic').value
        self.camera_frame = self.get_parameter('camera_frame').value
        self.laser_frame = self.get_parameter('laser_frame').value
        self.max_range = self.get_parameter('max_range').value
        self.min_range = self.get_parameter('min_range').value
        self.point_size = self.get_parameter('point_size').value
        self.colormap_name = self.get_parameter('colormap').value

        # QoS profiles
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Publishers
        self.pub_depth = self.create_publisher(Image, '/phone/depth/lidar_projected', sensor_qos)
        self.pub_overlay = self.create_publisher(Image, '/phone/depth/overlay', sensor_qos)
        self.pub_points = self.create_publisher(PointCloud2, '/phone/depth/points', sensor_qos)
        self.pub_status = self.create_publisher(Bool, '/phone/depth/fusion_active', 10)

        # Subscribers
        self.sub_scan = self.create_subscription(
            LaserScan, self.scan_topic, self.scan_callback, sensor_qos)
        self.sub_image = self.create_subscription(
            Image, self.image_topic, self.image_callback, sensor_qos)
        self.sub_camera_info = self.create_subscription(
            CameraInfo, self.camera_info_topic, self.camera_info_callback, sensor_qos)

        # TF
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # State
        self.latest_scan: Optional[LaserScan] = None
        self.latest_image: Optional[np.ndarray] = None
        self.camera_info: Optional[CameraInfo] = None
        self.camera_matrix: Optional[np.ndarray] = None
        self.image_size: Optional[Tuple[int, int]] = None

        # Colormap
        self.colormaps = {
            'jet': cv2.COLORMAP_JET,
            'hot': cv2.COLORMAP_HOT,
            'rainbow': cv2.COLORMAP_RAINBOW,
            'turbo': cv2.COLORMAP_TURBO,
        }
        self.colormap = self.colormaps.get(self.colormap_name, cv2.COLORMAP_JET)

        # Processing timer
        self.create_timer(0.1, self.process_fusion)  # 10 Hz
        self.create_timer(1.0, self.publish_status)

        self.get_logger().info('LIDAR-Camera fusion node started')

    def scan_callback(self, msg: LaserScan):
        """Store latest LIDAR scan"""
        self.latest_scan = msg

    def image_callback(self, msg: Image):
        """Convert and store latest camera image"""
        if not CV2_AVAILABLE:
            return

        try:
            # Convert ROS Image to OpenCV
            if msg.encoding == 'bgr8':
                self.latest_image = np.frombuffer(msg.data, dtype=np.uint8).reshape(
                    msg.height, msg.width, 3)
            elif msg.encoding == 'rgb8':
                img = np.frombuffer(msg.data, dtype=np.uint8).reshape(
                    msg.height, msg.width, 3)
                self.latest_image = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            else:
                self.get_logger().warn(f'Unsupported image encoding: {msg.encoding}')
        except Exception as e:
            self.get_logger().error(f'Image conversion error: {e}')

    def camera_info_callback(self, msg: CameraInfo):
        """Store camera calibration"""
        self.camera_info = msg
        self.image_size = (msg.width, msg.height)

        # Extract camera matrix
        self.camera_matrix = np.array([
            [msg.k[0], msg.k[1], msg.k[2]],
            [msg.k[3], msg.k[4], msg.k[5]],
            [msg.k[6], msg.k[7], msg.k[8]]
        ])

    def get_laser_to_camera_transform(self) -> Optional[np.ndarray]:
        """Get transformation matrix from laser frame to camera frame"""
        try:
            transform = self.tf_buffer.lookup_transform(
                self.camera_frame,
                self.laser_frame,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.1)
            )

            # Convert to 4x4 transformation matrix
            t = transform.transform.translation
            r = transform.transform.rotation

            # Quaternion to rotation matrix
            qw, qx, qy, qz = r.w, r.x, r.y, r.z

            rot_matrix = np.array([
                [1 - 2*(qy**2 + qz**2), 2*(qx*qy - qz*qw), 2*(qx*qz + qy*qw)],
                [2*(qx*qy + qz*qw), 1 - 2*(qx**2 + qz**2), 2*(qy*qz - qx*qw)],
                [2*(qx*qz - qy*qw), 2*(qy*qz + qx*qw), 1 - 2*(qx**2 + qy**2)]
            ])

            transform_matrix = np.eye(4)
            transform_matrix[:3, :3] = rot_matrix
            transform_matrix[:3, 3] = [t.x, t.y, t.z]

            return transform_matrix

        except TransformException as e:
            self.get_logger().debug(f'TF lookup failed: {e}')
            return None

    def scan_to_points(self, scan: LaserScan) -> np.ndarray:
        """Convert LaserScan to 3D points in laser frame"""
        angles = np.arange(scan.angle_min, scan.angle_max + scan.angle_increment,
                         scan.angle_increment)[:len(scan.ranges)]
        ranges = np.array(scan.ranges)

        # Filter invalid ranges
        valid = (ranges >= self.min_range) & (ranges <= self.max_range) & np.isfinite(ranges)
        angles = angles[valid]
        ranges = ranges[valid]

        # Convert to 3D (LIDAR is typically in XY plane at Z=0)
        x = ranges * np.cos(angles)
        y = ranges * np.sin(angles)
        z = np.zeros_like(x)

        points = np.vstack([x, y, z, np.ones_like(x)])  # 4xN homogeneous
        return points, ranges  # ranges already filtered above

    def project_points_to_image(self, points_3d: np.ndarray,
                                transform: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Project 3D points to image coordinates"""
        # Transform to camera frame
        points_camera = transform @ points_3d  # 4xN

        # Filter points behind camera (Z > 0 in camera frame)
        valid = points_camera[2, :] > 0.1
        points_camera = points_camera[:, valid]

        if points_camera.shape[1] == 0:
            return np.array([]), np.array([])

        # Project to image plane
        x = points_camera[0, :] / points_camera[2, :]
        y = points_camera[1, :] / points_camera[2, :]

        # Apply camera matrix
        fx, fy = self.camera_matrix[0, 0], self.camera_matrix[1, 1]
        cx, cy = self.camera_matrix[0, 2], self.camera_matrix[1, 2]

        u = fx * x + cx
        v = fy * y + cy

        # Filter points outside image
        w, h = self.image_size
        in_image = (u >= 0) & (u < w) & (v >= 0) & (v < h)

        return np.vstack([u[in_image], v[in_image]]).T, points_camera[2, in_image]

    def process_fusion(self):
        """Main fusion processing"""
        if not CV2_AVAILABLE:
            return

        if self.latest_scan is None or self.latest_image is None:
            return

        if self.camera_matrix is None or self.image_size is None:
            return

        # Get transform
        transform = self.get_laser_to_camera_transform()
        if transform is None:
            # Use default transform if TF not available
            # Assume LIDAR is mounted above and forward of camera
            transform = np.array([
                [1, 0, 0, 0],
                [0, 0, 1, 0],  # Y_cam = Z_laser
                [0, -1, 0, 0.1],  # Z_cam = -Y_laser, offset
                [0, 0, 0, 1]
            ])

        # Convert scan to points
        points_3d, depths = self.scan_to_points(self.latest_scan)
        if points_3d.shape[1] == 0:
            return

        # Project to image
        image_points, point_depths = self.project_points_to_image(points_3d, transform)
        if len(image_points) == 0:
            return

        # Create overlay image
        overlay = self.latest_image.copy()

        # Create depth image (sparse)
        depth_image = np.zeros((self.image_size[1], self.image_size[0]), dtype=np.float32)

        # Normalize depths for colormap
        depth_normalized = (point_depths - self.min_range) / (self.max_range - self.min_range)
        depth_normalized = np.clip(depth_normalized, 0, 1)

        # Draw points on overlay and depth image
        for i, (pt, d, d_norm) in enumerate(zip(image_points, point_depths, depth_normalized)):
            u, v = int(pt[0]), int(pt[1])

            # Color based on depth (near=red, far=blue for jet)
            color_idx = int((1 - d_norm) * 255)  # Invert so near is bright
            color_img = np.zeros((1, 1, 3), dtype=np.uint8)
            color_img[0, 0, 0] = color_idx
            colored = cv2.applyColorMap(color_img, self.colormap)
            color = tuple(int(c) for c in colored[0, 0])

            cv2.circle(overlay, (u, v), self.point_size, color, -1)
            depth_image[v, u] = d

        # Publish overlay
        self.publish_image(overlay, '/phone/depth/overlay', 'bgr8')

        # Publish depth (sparse)
        self.publish_depth_image(depth_image)

    def publish_image(self, image: np.ndarray, topic_suffix: str, encoding: str):
        """Publish OpenCV image as ROS message"""
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.camera_frame
        msg.height, msg.width = image.shape[:2]
        msg.encoding = encoding
        msg.is_bigendian = False
        msg.step = image.shape[1] * (3 if len(image.shape) == 3 else 1)
        msg.data = image.tobytes()
        self.pub_overlay.publish(msg)

    def publish_depth_image(self, depth: np.ndarray):
        """Publish depth image"""
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.camera_frame
        msg.height, msg.width = depth.shape
        msg.encoding = '32FC1'
        msg.is_bigendian = False
        msg.step = depth.shape[1] * 4
        msg.data = depth.tobytes()
        self.pub_depth.publish(msg)

    def publish_status(self):
        """Publish fusion status"""
        msg = Bool()
        msg.data = (self.latest_scan is not None and
                   self.latest_image is not None and
                   self.camera_matrix is not None)
        self.pub_status.publish(msg)

    def destroy_node(self):
        super().destroy_node()


def main(args=None):
    if not CV2_AVAILABLE:
        print("ERROR: OpenCV not available")
        return

    rclpy.init(args=args)
    node = LidarCameraFusionNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
