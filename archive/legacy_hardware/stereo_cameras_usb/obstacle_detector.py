#!/usr/bin/env python3
"""
ROS2 Obstacle Detection Node

Subscribes to stereo depth and publishes obstacle information for navigation.

Subscribed Topics:
    /stereo/depth/image_raw (sensor_msgs/Image) - Depth image from stereo node

Published Topics:
    /obstacles (std_msgs/String) - JSON obstacle data
    /obstacles/ranges (sensor_msgs/LaserScan) - Virtual laser scan from depth
    /cmd_vel_obstacle (geometry_msgs/Twist) - Emergency stop commands

Parameters:
    ~danger_distance (float): Distance to trigger stop (default: 0.4m)
    ~warning_distance (float): Distance to trigger slow down (default: 0.8m)
    ~detection_width (float): Width of detection zone as fraction (default: 0.6)
    ~detection_height (float): Height of detection zone as fraction (default: 0.5)
    ~min_obstacle_pixels (int): Minimum pixels to confirm obstacle (default: 100)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, LaserScan
from geometry_msgs.msg import Twist
from std_msgs.msg import String
# cv_bridge has NumPy 2.x compatibility issues - we'll convert messages manually
# from cv_bridge import CvBridge
import cv2
import numpy as np
import json
from dataclasses import dataclass
from typing import Optional, Dict, List
import time


@dataclass
class ObstacleZone:
    """Defines a detection zone"""
    name: str
    x_start: float  # Fraction of image width (0-1)
    x_end: float
    y_start: float  # Fraction of image height (0-1)
    y_end: float
    weight: float = 1.0  # Importance weight


class ObstacleDetector(Node):
    """ROS2 node for obstacle detection from stereo depth"""

    def __init__(self):
        super().__init__('obstacle_detector')

        # Declare parameters
        self.declare_parameter('danger_distance', 0.4)
        self.declare_parameter('warning_distance', 0.8)
        self.declare_parameter('safe_distance', 1.2)
        self.declare_parameter('detection_width', 0.6)
        self.declare_parameter('detection_height', 0.5)
        self.declare_parameter('min_obstacle_pixels', 100)
        self.declare_parameter('publish_virtual_scan', True)
        self.declare_parameter('emergency_stop_enabled', True)

        # Get parameters
        self.danger_distance = self.get_parameter('danger_distance').value
        self.warning_distance = self.get_parameter('warning_distance').value
        self.safe_distance = self.get_parameter('safe_distance').value
        self.detection_width = self.get_parameter('detection_width').value
        self.detection_height = self.get_parameter('detection_height').value
        self.min_obstacle_pixels = self.get_parameter('min_obstacle_pixels').value
        self.publish_virtual_scan = self.get_parameter('publish_virtual_scan').value
        self.emergency_stop_enabled = self.get_parameter('emergency_stop_enabled').value

        self.get_logger().info("Obstacle Detector starting...")
        self.get_logger().info(f"  Danger distance: {self.danger_distance}m")
        self.get_logger().info(f"  Warning distance: {self.warning_distance}m")
        self.get_logger().info(f"  Detection zone: {self.detection_width*100:.0f}% x {self.detection_height*100:.0f}%")

        # Detection zones (can be customized)
        self.zones = self._create_detection_zones()

        # State
        self.current_status = "CLEAR"
        self.min_distance = float('inf')
        self.last_obstacle_time = 0
        self.obstacle_history: List[Dict] = []

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

        # Subscriber
        self.depth_sub = self.create_subscription(
            Image,
            '/stereo/depth/image_raw',
            self._depth_callback,
            sensor_qos
        )

        # Publishers
        self.obstacle_pub = self.create_publisher(String, '/obstacles', reliable_qos)
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel_obstacle', reliable_qos)

        if self.publish_virtual_scan:
            self.scan_pub = self.create_publisher(LaserScan, '/obstacles/ranges', sensor_qos)

        # Status timer (publish at 10Hz even without new depth)
        self.status_timer = self.create_timer(0.1, self._publish_status)

        self.get_logger().info("Obstacle Detector ready!")

    def _create_detection_zones(self) -> List[ObstacleZone]:
        """Create detection zones for different areas"""
        # Center zone - most important
        w = self.detection_width
        h = self.detection_height

        zones = [
            # Center (highest priority)
            ObstacleZone(
                name="center",
                x_start=(1 - w) / 2,
                x_end=(1 + w) / 2,
                y_start=(1 - h) / 2,
                y_end=(1 + h) / 2,
                weight=1.0
            ),
            # Left side
            ObstacleZone(
                name="left",
                x_start=0.05,
                x_end=0.35,
                y_start=0.3,
                y_end=0.7,
                weight=0.7
            ),
            # Right side
            ObstacleZone(
                name="right",
                x_start=0.65,
                x_end=0.95,
                y_start=0.3,
                y_end=0.7,
                weight=0.7
            ),
            # Bottom (ground obstacles)
            ObstacleZone(
                name="ground",
                x_start=0.2,
                x_end=0.8,
                y_start=0.7,
                y_end=0.95,
                weight=0.8
            ),
        ]
        return zones

    def _analyze_zone(self, depth: np.ndarray, zone: ObstacleZone) -> Dict:
        """Analyze a detection zone for obstacles"""
        h, w = depth.shape

        # Get zone boundaries in pixels
        x1 = int(zone.x_start * w)
        x2 = int(zone.x_end * w)
        y1 = int(zone.y_start * h)
        y2 = int(zone.y_end * h)

        # Extract zone
        zone_depth = depth[y1:y2, x1:x2]

        # Get valid depths (non-zero)
        valid_depths = zone_depth[zone_depth > 0]

        if len(valid_depths) < self.min_obstacle_pixels:
            return {
                "zone": zone.name,
                "status": "NO_DATA",
                "min_distance": float('inf'),
                "mean_distance": float('inf'),
                "obstacle_pixels": 0,
                "weight": zone.weight
            }

        # Calculate statistics
        min_dist = float(np.min(valid_depths))
        mean_dist = float(np.mean(valid_depths))

        # Count obstacle pixels
        danger_pixels = np.sum(valid_depths < self.danger_distance)
        warning_pixels = np.sum(valid_depths < self.warning_distance)

        # Determine status
        if danger_pixels > self.min_obstacle_pixels:
            status = "DANGER"
        elif warning_pixels > self.min_obstacle_pixels:
            status = "WARNING"
        else:
            status = "CLEAR"

        return {
            "zone": zone.name,
            "status": status,
            "min_distance": min_dist,
            "mean_distance": mean_dist,
            "danger_pixels": int(danger_pixels),
            "warning_pixels": int(warning_pixels),
            "valid_pixels": int(len(valid_depths)),
            "weight": zone.weight
        }

    def _create_virtual_scan(self, depth: np.ndarray) -> LaserScan:
        """Create a virtual LaserScan from depth image center row"""
        h, w = depth.shape

        # Use center horizontal slice
        center_row = depth[h // 2, :]

        # Subsample to reduce points
        num_points = 180
        indices = np.linspace(0, w - 1, num_points, dtype=int)
        ranges = center_row[indices]

        # Replace invalid with max range
        ranges[ranges <= 0] = 10.0

        # Create message
        msg = LaserScan()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "stereo_camera"

        # Configure scan parameters
        msg.angle_min = -0.5  # ~-30 degrees
        msg.angle_max = 0.5   # ~30 degrees
        msg.angle_increment = (msg.angle_max - msg.angle_min) / num_points
        msg.time_increment = 0.0
        msg.scan_time = 0.1
        msg.range_min = 0.1
        msg.range_max = 10.0
        msg.ranges = ranges.tolist()

        return msg

    def _image_msg_to_numpy(self, msg: Image) -> np.ndarray:
        """Convert ROS Image message to numpy array without cv_bridge"""
        if msg.encoding == '32FC1':
            # Float32 depth image
            depth = np.frombuffer(msg.data, dtype=np.float32)
            depth = depth.reshape((msg.height, msg.width))
            return depth
        elif msg.encoding == 'bgr8':
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            arr = arr.reshape((msg.height, msg.width, 3))
            return arr
        elif msg.encoding == 'mono8':
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            arr = arr.reshape((msg.height, msg.width))
            return arr
        else:
            raise ValueError(f"Unsupported encoding: {msg.encoding}")

    def _depth_callback(self, msg: Image):
        """Process incoming depth image"""
        try:
            # Convert to numpy (without cv_bridge to avoid NumPy 2.x issues)
            depth = self._image_msg_to_numpy(msg)
        except Exception as e:
            self.get_logger().error(f"Failed to convert depth image: {e}")
            return

        # Analyze each zone
        zone_results = []
        for zone in self.zones:
            result = self._analyze_zone(depth, zone)
            zone_results.append(result)

        # Determine overall status (worst case weighted)
        overall_status = "CLEAR"
        overall_min_distance = float('inf')

        for result in zone_results:
            if result["min_distance"] < overall_min_distance:
                overall_min_distance = result["min_distance"]

            if result["status"] == "DANGER" and result["weight"] > 0.5:
                overall_status = "DANGER"
            elif result["status"] == "WARNING" and overall_status != "DANGER":
                overall_status = "WARNING"

        self.current_status = overall_status
        self.min_distance = overall_min_distance

        # Publish obstacle data
        obstacle_data = {
            "timestamp": time.time(),
            "status": overall_status,
            "min_distance": overall_min_distance,
            "zones": zone_results
        }

        obstacle_msg = String()
        obstacle_msg.data = json.dumps(obstacle_data)
        self.obstacle_pub.publish(obstacle_msg)

        # Emergency stop if danger detected
        if self.emergency_stop_enabled and overall_status == "DANGER":
            self._send_emergency_stop()

        # Publish virtual scan
        if self.publish_virtual_scan:
            scan_msg = self._create_virtual_scan(depth)
            self.scan_pub.publish(scan_msg)

    def _send_emergency_stop(self):
        """Send emergency stop command"""
        stop_msg = Twist()
        stop_msg.linear.x = 0.0
        stop_msg.linear.y = 0.0
        stop_msg.linear.z = 0.0
        stop_msg.angular.x = 0.0
        stop_msg.angular.y = 0.0
        stop_msg.angular.z = 0.0
        self.cmd_vel_pub.publish(stop_msg)
        self.get_logger().warn(f"EMERGENCY STOP! Obstacle at {self.min_distance:.2f}m")

    def _publish_status(self):
        """Periodic status publication"""
        # Log status changes
        status_color = {
            "CLEAR": "\033[92m",    # Green
            "WARNING": "\033[93m",  # Yellow
            "DANGER": "\033[91m"    # Red
        }
        reset = "\033[0m"

        if self.min_distance < float('inf'):
            self.get_logger().debug(
                f"{status_color.get(self.current_status, '')}"
                f"Status: {self.current_status} | Min distance: {self.min_distance:.2f}m"
                f"{reset}"
            )


def main(args=None):
    rclpy.init(args=args)

    try:
        node = ObstacleDetector()
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
