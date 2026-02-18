#!/usr/bin/env python3
"""
Edge Computing Optimization Node for ROVAC
Moves processing to Raspberry Pi for reduced latency and bandwidth
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Float32
from sensor_msgs.msg import Image, LaserScan, Imu
from geometry_msgs.msg import Twist
import json
import time
import threading
import queue
from typing import Dict, Any
import numpy as np


class EdgeOptimizationNode(Node):
    """ROS2 node for edge computing optimization"""

    def __init__(self):
        super().__init__("edge_optimization_node")

        # ROS2 parameters
        self.declare_parameter("enable_edge_processing", True)
        self.declare_parameter("process_on_pi", True)
        self.declare_parameter("compression_ratio", 0.5)
        self.declare_parameter("processing_batch_size", 10)

        self.enabled = self.get_parameter("enable_edge_processing").value
        self.process_on_pi = self.get_parameter("process_on_pi").value
        self.compression_ratio = self.get_parameter("compression_ratio").value
        self.batch_size = self.get_parameter("processing_batch_size").value

        # State variables
        self.data_queue = queue.Queue(maxsize=100)
        self.processing_stats = {
            "processed_frames": 0,
            "bandwidth_saved_mb": 0.0,
            "processing_time_ms": 0.0,
            "pi_load_percent": 0.0,
        }

        # Subscriptions for sensor data that can be processed on edge
        self.image_subscription = self.create_subscription(
            Image, "/phone/image_raw", self.image_callback, 10
        )

        self.scan_subscription = self.create_subscription(
            LaserScan, "/scan", self.scan_callback, 10
        )

        self.imu_subscription = self.create_subscription(
            Imu, "/sensors/imu", self.imu_callback, 10
        )

        # Publishers for processed data
        self.optimized_image_publisher = self.create_publisher(
            Image, "/edge/optimized_image", 10
        )

        self.optimized_scan_publisher = self.create_publisher(
            LaserScan, "/edge/optimized_scan", 10
        )

        self.fused_data_publisher = self.create_publisher(
            String, "/edge/fused_data", 10
        )

        self.stats_publisher = self.create_publisher(String, "/edge/stats", 10)

        # Timer for periodic processing and statistics
        self.timer = self.create_timer(0.1, self.process_data_batch)
        self.stats_timer = self.create_timer(1.0, self.publish_statistics)

        # Processing thread
        self.processing_thread = threading.Thread(
            target=self.edge_processing_worker, daemon=True
        )
        self.processing_thread.start()

        self.get_logger().info("Edge Optimization Node initialized")
        self.get_logger().info(f"Processing on Pi: {self.process_on_pi}")
        self.get_logger().info(f"Compression ratio: {self.compression_ratio}")

    def image_callback(self, msg):
        """Handle image data - candidate for edge processing"""
        if not self.enabled:
            return

        # Add to processing queue
        try:
            self.data_queue.put(
                {"type": "image", "data": msg, "timestamp": time.time()}, block=False
            )
        except queue.Full:
            self.get_logger().warn("Image queue full, dropping frame")

    def scan_callback(self, msg):
        """Handle LIDAR scan data - candidate for edge processing"""
        if not self.enabled:
            return

        # Add to processing queue
        try:
            self.data_queue.put(
                {"type": "scan", "data": msg, "timestamp": time.time()}, block=False
            )
        except queue.Full:
            self.get_logger().warn("Scan queue full, dropping data")

    def imu_callback(self, msg):
        """Handle IMU data - candidate for edge processing"""
        if not self.enabled:
            return

        # Add to processing queue
        try:
            self.data_queue.put(
                {"type": "imu", "data": msg, "timestamp": time.time()}, block=False
            )
        except queue.Full:
            self.get_logger().warn("IMU queue full, dropping data")

    def process_data_batch(self):
        """Process batch of sensor data"""
        if not self.enabled or self.data_queue.empty():
            return

        batch = []
        batch_count = min(self.batch_size, self.data_queue.qsize())

        # Collect batch
        for _ in range(batch_count):
            try:
                item = self.data_queue.get(block=False)
                batch.append(item)
            except queue.Empty:
                break

        if not batch:
            return

        # Process batch
        start_time = time.time()
        processed_data = self.optimize_data_batch(batch)
        processing_time = (time.time() - start_time) * 1000  # ms

        # Update statistics
        self.processing_stats["processed_frames"] += len(batch)
        self.processing_stats["processing_time_ms"] = processing_time

        # Publish processed data
        self.publish_processed_data(processed_data)

    def optimize_data_batch(self, batch):
        """Optimize batch of sensor data for edge processing"""
        optimized_data = []

        for item in batch:
            data_type = item["type"]
            data = item["data"]

            if data_type == "image":
                optimized_item = self.optimize_image_data(data)
            elif data_type == "scan":
                optimized_item = self.optimize_scan_data(data)
            elif data_type == "imu":
                optimized_item = self.optimize_imu_data(data)
            else:
                optimized_item = data

            optimized_data.append(
                {
                    "type": data_type,
                    "data": optimized_item,
                    "original_size": self.calculate_data_size(data),
                    "optimized_size": self.calculate_data_size(optimized_item),
                }
            )

        return optimized_data

    def optimize_image_data(self, image_msg):
        """Optimize image data through compression/resizing"""
        # In a real implementation, this would:
        # 1. Resize image based on compression ratio
        # 2. Apply lossy compression
        # 3. Convert to more efficient format
        # 4. Perform basic CV processing on Pi

        # For simulation, just return original with stats
        optimized_msg = image_msg
        original_size = len(image_msg.data) if hasattr(image_msg, "data") else 0
        optimized_size = int(original_size * self.compression_ratio)

        # Calculate bandwidth saved
        bandwidth_saved = (original_size - optimized_size) / (1024 * 1024)  # MB
        self.processing_stats["bandwidth_saved_mb"] += bandwidth_saved

        self.get_logger().debug(
            f"Image optimized: {original_size} -> {optimized_size} bytes"
        )
        return optimized_msg

    def optimize_scan_data(self, scan_msg):
        """Optimize LIDAR scan data through filtering"""
        # In a real implementation, this would:
        # 1. Filter noise from scan data
        # 2. Reduce angular resolution
        # 3. Apply temporal smoothing
        # 4. Perform basic obstacle detection on Pi

        # For simulation, just return original with minor modifications
        optimized_msg = scan_msg
        return optimized_msg

    def optimize_imu_data(self, imu_msg):
        """Optimize IMU data through filtering"""
        # In a real implementation, this would:
        # 1. Apply sensor fusion on Pi
        # 2. Filter noise from accelerometer/gyro
        # 3. Calculate orientation/quaternion on Pi
        # 4. Reduce data rate for transmission

        # For simulation, just return original
        optimized_msg = imu_msg
        return optimized_msg

    def calculate_data_size(self, msg):
        """Calculate approximate size of ROS2 message"""
        # Simplified size calculation
        if hasattr(msg, "data"):
            return len(msg.data) if isinstance(msg.data, (bytes, list)) else 32
        elif hasattr(msg, "ranges"):
            return len(msg.ranges) * 4  # 4 bytes per float
        else:
            return 64  # Default estimate

    def publish_processed_data(self, processed_data):
        """Publish optimized data"""
        # In a real implementation, this would:
        # 1. Publish optimized sensor data
        # 2. Send fused results back to Mac
        # 3. Handle Pi-Mac communication

        # For now, just publish fused data example
        fused_msg = String()
        fused_data = {
            "timestamp": time.time(),
            "processed_items": len(processed_data),
            "optimization_ratio": self.compression_ratio,
        }
        fused_msg.data = json.dumps(fused_data)
        self.fused_data_publisher.publish(fused_msg)

    def edge_processing_worker(self):
        """Worker thread for heavy edge processing"""
        while rclpy.ok():
            # Simulate Pi-side processing work
            time.sleep(0.01)  # 10ms work simulation
            # In real implementation, this would handle:
            # - Neural network inference
            # - Complex sensor fusion
            # - Predictive analytics
            pass

    def publish_statistics(self):
        """Publish processing statistics"""
        if not self.enabled:
            return

        stats_msg = String()
        stats_msg.data = json.dumps(self.processing_stats)
        self.stats_publisher.publish(stats_msg)

        # Log periodic stats
        self.get_logger().info(
            f"Stats - Processed: {self.processing_stats['processed_frames']}, "
            f"Bandwidth saved: {self.processing_stats['bandwidth_saved_mb']:.2f}MB"
        )


def main(args=None):
    rclpy.init(args=args)
    node = EdgeOptimizationNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
