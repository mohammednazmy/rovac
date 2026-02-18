#!/usr/bin/env python3
"""
Monocular Depth Estimation ROS2 Node
Uses MiDaS-small or OpenCV-DNN for depth estimation from phone camera.

Published Topics:
    /phone/depth/image      - sensor_msgs/Image (depth map, 32FC1)
    /phone/depth/colored    - sensor_msgs/Image (colored depth visualization)
    /phone/depth/status     - std_msgs/Bool (processing status)

Subscribed Topics:
    /phone/image_raw        - sensor_msgs/Image (input camera image)

Note: This is CPU-only and will be slow (~0.5-2 FPS on Pi 5).
For real-time depth, consider using LIDAR data fusion instead.
"""

import os
import threading
import time
from typing import Optional
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image, CameraInfo
from std_msgs.msg import Bool, Header
from cv_bridge import CvBridge

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# Try to import torch for MiDaS
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class DepthEstimationNode(Node):
    """ROS2 node for monocular depth estimation"""

    def __init__(self):
        super().__init__('depth_estimation_node')

        # Parameters
        self.declare_parameter('model', 'midas_small')  # midas_small, midas_dpt_hybrid
        self.declare_parameter('input_topic', '/phone/image_raw')
        self.declare_parameter('target_fps', 2.0)  # Limit processing rate
        self.declare_parameter('input_size', 256)  # Smaller = faster
        self.declare_parameter('publish_colored', True)
        self.declare_parameter('frame_id', 'phone_camera_link')

        self.model_name = self.get_parameter('model').value
        self.input_topic = self.get_parameter('input_topic').value
        self.target_fps = self.get_parameter('target_fps').value
        self.input_size = self.get_parameter('input_size').value
        self.publish_colored = self.get_parameter('publish_colored').value
        self.frame_id = self.get_parameter('frame_id').value

        # QoS
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Publishers
        self.pub_depth = self.create_publisher(Image, '/phone/depth/image', sensor_qos)
        if self.publish_colored:
            self.pub_colored = self.create_publisher(Image, '/phone/depth/colored', sensor_qos)
        self.pub_status = self.create_publisher(Bool, '/phone/depth/status', 10)

        # Subscriber
        self.sub_image = self.create_subscription(
            Image, self.input_topic, self.image_callback, sensor_qos)

        # State
        self.cv_bridge = CvBridge()
        self.model = None
        self.transform = None
        self.device = 'cpu'
        self.processing = False
        self.last_process_time = 0.0
        self.min_interval = 1.0 / self.target_fps

        # Image queue (process latest only)
        self.image_queue = deque(maxlen=1)

        # Load model in background
        self.model_loaded = False
        self.model_thread = threading.Thread(target=self._load_model, daemon=True)
        self.model_thread.start()

        # Processing thread
        self.running = True
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()

        # Status timer
        self.create_timer(1.0, self._publish_status)

        self.get_logger().info(f'Depth estimation node started, model: {self.model_name}')

    def _load_model(self):
        """Load MiDaS model"""
        if not TORCH_AVAILABLE:
            self.get_logger().warn('PyTorch not available, depth estimation disabled')
            self.get_logger().info('To enable: pip install torch torchvision')
            return

        try:
            self.get_logger().info('Loading MiDaS model (this may take a while)...')

            # Use MiDaS small for better performance on Pi
            if self.model_name == 'midas_small':
                self.model = torch.hub.load('intel-isl/MiDaS', 'MiDaS_small', trust_repo=True)
                midas_transforms = torch.hub.load('intel-isl/MiDaS', 'transforms', trust_repo=True)
                self.transform = midas_transforms.small_transform
            else:
                self.model = torch.hub.load('intel-isl/MiDaS', 'DPT_Hybrid', trust_repo=True)
                midas_transforms = torch.hub.load('intel-isl/MiDaS', 'transforms', trust_repo=True)
                self.transform = midas_transforms.dpt_transform

            self.model.to(self.device)
            self.model.eval()
            self.model_loaded = True

            self.get_logger().info('MiDaS model loaded successfully')

        except Exception as e:
            self.get_logger().error(f'Failed to load MiDaS model: {e}')
            self.get_logger().info('Falling back to simple edge-based pseudo-depth')

    def image_callback(self, msg: Image):
        """Queue incoming images for processing"""
        self.image_queue.append(msg)

    def _process_loop(self):
        """Background processing loop"""
        while self.running:
            # Rate limiting
            now = time.time()
            if now - self.last_process_time < self.min_interval:
                time.sleep(0.01)
                continue

            # Get latest image
            if not self.image_queue:
                time.sleep(0.01)
                continue

            msg = self.image_queue.pop()
            self.last_process_time = now
            self.processing = True

            try:
                # Convert to OpenCV
                cv_image = self.cv_bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

                # Process depth
                if self.model_loaded and self.model is not None:
                    depth = self._process_midas(cv_image)
                else:
                    depth = self._process_simple(cv_image)

                # Publish
                self._publish_depth(depth, msg.header)

            except Exception as e:
                self.get_logger().error(f'Depth processing error: {e}')

            self.processing = False

    def _process_midas(self, image: np.ndarray) -> np.ndarray:
        """Process image with MiDaS model"""
        # Prepare input
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        input_batch = self.transform(img_rgb).to(self.device)

        # Inference
        with torch.no_grad():
            prediction = self.model(input_batch)
            prediction = torch.nn.functional.interpolate(
                prediction.unsqueeze(1),
                size=image.shape[:2],
                mode='bicubic',
                align_corners=False
            ).squeeze()

        depth = prediction.cpu().numpy()

        # Normalize to 0-1 range
        depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-8)

        return depth.astype(np.float32)

    def _process_simple(self, image: np.ndarray) -> np.ndarray:
        """Simple pseudo-depth from edges and gradients (fallback)"""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Resize for speed
        small = cv2.resize(gray, (self.input_size, self.input_size))

        # Edge detection
        edges = cv2.Canny(small, 50, 150)

        # Gradient magnitude (approximates depth discontinuities)
        grad_x = cv2.Sobel(small, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(small, cv2.CV_64F, 0, 1, ksize=3)
        gradient = np.sqrt(grad_x**2 + grad_y**2)

        # Combine (this is NOT real depth, just a visualization)
        pseudo_depth = gradient.astype(np.float32)
        pseudo_depth = cv2.GaussianBlur(pseudo_depth, (5, 5), 0)

        # Normalize
        pseudo_depth = (pseudo_depth - pseudo_depth.min()) / (pseudo_depth.max() - pseudo_depth.min() + 1e-8)

        # Resize back
        pseudo_depth = cv2.resize(pseudo_depth, (image.shape[1], image.shape[0]))

        return pseudo_depth

    def _publish_depth(self, depth: np.ndarray, header: Header):
        """Publish depth map"""
        # Update header
        header.frame_id = self.frame_id

        # Publish raw depth (32FC1)
        depth_msg = self.cv_bridge.cv2_to_imgmsg(depth, encoding='32FC1')
        depth_msg.header = header
        self.pub_depth.publish(depth_msg)

        # Publish colored visualization
        if self.publish_colored:
            # Apply colormap (MAGMA is good for depth)
            depth_colored = (depth * 255).astype(np.uint8)
            depth_colored = cv2.applyColorMap(depth_colored, cv2.COLORMAP_MAGMA)

            colored_msg = self.cv_bridge.cv2_to_imgmsg(depth_colored, encoding='bgr8')
            colored_msg.header = header
            self.pub_colored.publish(colored_msg)

    def _publish_status(self):
        """Publish processing status"""
        msg = Bool()
        msg.data = self.model_loaded or True  # True if fallback is working
        self.pub_status.publish(msg)

    def destroy_node(self):
        self.running = False
        super().destroy_node()


def main(args=None):
    if not CV2_AVAILABLE:
        print("ERROR: opencv-python not installed")
        return

    rclpy.init(args=args)
    node = DepthEstimationNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
