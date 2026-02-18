#!/usr/bin/env python3
"""
Thermal Imaging Node for ROVAC
ROS2 interface for FLIR Lepton thermal camera and heat signature detection
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import Image
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point
import json
import time
import numpy as np
from cv_bridge import CvBridge
import cv2
from typing import List

# Import our thermal imaging components
from thermal_camera_driver import FLIRLeptonDriver, ThermalFrame
from heat_signature_detector import (
    HeatSignatureDetector,
    HeatSignature,
    DetectionConfig,
)


class ThermalImagingNode(Node):
    """ROS2 node for thermal imaging and heat signature detection"""

    def __init__(self):
        super().__init__("thermal_imaging_node")

        # ROS2 parameters
        self.declare_parameter("enable_thermal_imaging", True)
        self.declare_parameter("use_emulation", True)
        self.declare_parameter("spi_device", "/dev/spidev0.0")
        self.declare_parameter("frame_rate", 9.0)
        self.declare_parameter("publish_visualization", True)
        self.declare_parameter("detection_sensitivity", "medium")

        self.enabled = self.get_parameter("enable_thermal_imaging").value
        self.use_emulation = self.get_parameter("use_emulation").value
        self.spi_device = self.get_parameter("spi_device").value
        self.frame_rate = self.get_parameter("frame_rate").value
        self.publish_viz = self.get_parameter("publish_visualization").value
        self.sensitivity = self.get_parameter("detection_sensitivity").value

        # Initialize components
        self.driver = FLIRLeptonDriver(
            spi_device=self.spi_device, use_emulation=self.use_emulation
        )

        # Configure detection sensitivity
        config = self._create_detection_config()
        self.detector = HeatSignatureDetector(config=config)

        # CV Bridge for image conversion
        self.cv_bridge = CvBridge()

        # State variables
        self.current_frame = None
        self.last_detection_time = 0.0
        self.detection_stats = {
            "frames_processed": 0,
            "signatures_detected": 0,
            "persons_found": 0,
            "fires_found": 0,
            "animals_found": 0,
        }

        if self.enabled:
            # Connect to thermal camera
            if self.driver.connect():
                self.get_logger().info("✅ Connected to thermal camera")

                # Publishers
                self.thermal_image_publisher = self.create_publisher(
                    Image, "/thermal/image_raw", 10
                )

                self.thermal_compressed_publisher = self.create_publisher(
                    Image, "/thermal/image_raw/compressed", 10
                )

                self.signatures_publisher = self.create_publisher(
                    String, "/thermal/signatures", 10
                )

                self.visualization_publisher = self.create_publisher(
                    MarkerArray, "/thermal/signature_markers", 10
                )

                self.stats_publisher = self.create_publisher(
                    String, "/thermal/statistics", 10
                )

                # Start streaming
                self.driver.start_streaming(callback=self.frame_callback)
                self.get_logger().info("🎥 Started thermal camera streaming")

            else:
                self.get_logger().error("❌ Failed to connect to thermal camera")
                self.enabled = False
        else:
            self.get_logger().info("⏸️ Thermal imaging disabled")

        # Timer for periodic tasks
        self.timer = self.create_timer(1.0, self.publish_statistics)

        self.get_logger().info("🔥 Thermal Imaging Node initialized")
        self.get_logger().info(
            f"   Emulation mode: {'Enabled' if self.use_emulation else 'Disabled'}"
        )
        self.get_logger().info(f"   Detection sensitivity: {self.sensitivity}")
        self.get_logger().info(
            f"   Visualization: {'Enabled' if self.publish_viz else 'Disabled'}"
        )

    def _create_detection_config(self) -> DetectionConfig:
        """Create detection configuration based on sensitivity setting"""
        config = DetectionConfig()

        if self.sensitivity == "high":
            config.confidence_threshold = 0.3
            config.min_person_pixels = 20
            config.persistence_threshold = 0.4
        elif self.sensitivity == "low":
            config.confidence_threshold = 0.7
            config.min_person_pixels = 100
            config.persistence_threshold = 0.8
        else:  # medium (default)
            config.confidence_threshold = 0.5
            config.min_person_pixels = 50
            config.persistence_threshold = 0.6

        return config

    def frame_callback(self, frame: ThermalFrame):
        """Handle incoming thermal frames"""
        if not self.enabled:
            return

        self.current_frame = frame
        self.detection_stats["frames_processed"] += 1

        # Process frame
        self.process_frame(frame)

        # Publish thermal image
        self.publish_thermal_image(frame)

    def process_frame(self, frame: ThermalFrame):
        """Process thermal frame for heat signatures"""
        try:
            # Detect heat signatures
            signatures = self.detector.detect_signatures(frame)

            # Update statistics
            self.detection_stats["signatures_detected"] += len(signatures)

            # Count by type
            for signature in signatures:
                if signature.signature_type == "person":
                    self.detection_stats["persons_found"] += 1
                elif signature.signature_type == "fire":
                    self.detection_stats["fires_found"] += 1
                elif signature.signature_type == "animal":
                    self.detection_stats["animals_found"] += 1

            # Publish detections
            self.publish_signatures(signatures)

            # Publish visualization markers
            if self.publish_viz and signatures:
                self.publish_visualization(signatures)

            # Update last detection time
            if signatures:
                self.last_detection_time = time.time()

        except Exception as e:
            self.get_logger().error(f"❌ Frame processing failed: {e}")

    def publish_thermal_image(self, frame: ThermalFrame):
        """Publish thermal image as ROS2 message"""
        try:
            # Normalize temperature data for visualization
            temp_data = frame.temperature_data
            temp_min = temp_data.min()
            temp_max = temp_data.max()

            if temp_max > temp_min:
                # Convert to 8-bit for publishing
                normalized = (
                    (temp_data - temp_min) / (temp_max - temp_min) * 255
                ).astype(np.uint8)
            else:
                normalized = np.zeros_like(temp_data, dtype=np.uint8)

            # Create colorized thermal image (pseudo-color)
            colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)

            # Convert to ROS Image message
            image_msg = self.cv_bridge.cv2_to_imgmsg(colored, encoding="bgr8")
            image_msg.header.stamp = self.get_clock().now().to_msg()
            image_msg.header.frame_id = "thermal_camera_link"

            # Publish raw image
            self.thermal_image_publisher.publish(image_msg)

            # Also publish compressed version
            compressed_msg = self.cv_bridge.cv2_to_compressed_imgmsg(colored)
            compressed_msg.format = "jpeg"
            compressed_msg.header = image_msg.header
            self.thermal_compressed_publisher.publish(compressed_msg)

        except Exception as e:
            self.get_logger().error(f"❌ Thermal image publishing failed: {e}")

    def publish_signatures(self, signatures: List[HeatSignature]):
        """Publish detected heat signatures"""
        try:
            # Convert signatures to JSON
            signature_data = []
            for sig in signatures:
                signature_data.append(
                    {
                        "center_x": sig.center_x,
                        "center_y": sig.center_y,
                        "temperature": sig.temperature,
                        "area_pixels": sig.area_pixels,
                        "signature_type": sig.signature_type,
                        "confidence": sig.confidence,
                    }
                )

            signatures_msg = String()
            signatures_msg.data = json.dumps(
                {
                    "timestamp": time.time(),
                    "signatures": signature_data,
                    "count": len(signatures),
                }
            )

            self.signatures_publisher.publish(signatures_msg)

        except Exception as e:
            self.get_logger().error(f"❌ Signature publishing failed: {e}")

    def publish_visualization(self, signatures: List[HeatSignature]):
        """Publish visualization markers for detected signatures"""
        try:
            marker_array = MarkerArray()

            for i, signature in enumerate(signatures):
                # Create marker for visualization
                marker = Marker()
                marker.header.stamp = self.get_clock().now().to_msg()
                marker.header.frame_id = "thermal_camera_link"
                marker.ns = "thermal_signatures"
                marker.id = i
                marker.type = Marker.SPHERE
                marker.action = Marker.ADD

                # Position (convert normalized to meters - assuming 5m max range)
                marker.pose.position.x = signature.center_x * 5.0
                marker.pose.position.y = (
                    signature.center_y - 0.5
                ) * 5.0  # Center Y at 0
                marker.pose.position.z = (
                    signature.temperature / 50.0
                )  # Height based on temperature

                # Orientation
                marker.pose.orientation.w = 1.0

                # Scale based on confidence and temperature
                scale_factor = 0.1 + (signature.confidence * 0.2)
                marker.scale.x = scale_factor
                marker.scale.y = scale_factor
                marker.scale.z = scale_factor * (signature.temperature / 100.0)

                # Color based on signature type
                if signature.signature_type == "person":
                    marker.color.r = 0.0
                    marker.color.g = 1.0
                    marker.color.b = 0.0
                elif signature.signature_type == "fire":
                    marker.color.r = 1.0
                    marker.color.g = 0.0
                    marker.color.b = 0.0
                elif signature.signature_type == "animal":
                    marker.color.r = 0.0
                    marker.color.g = 1.0
                    marker.color.b = 1.0
                else:
                    marker.color.r = 1.0
                    marker.color.g = 1.0
                    marker.color.b = 0.0

                marker.color.a = signature.confidence

                # Lifetime
                marker.lifetime.sec = 1
                marker.lifetime.nanosec = 0

                marker_array.markers.append(marker)

            self.visualization_publisher.publish(marker_array)

        except Exception as e:
            self.get_logger().error(f"❌ Visualization publishing failed: {e}")

    def publish_statistics(self):
        """Publish thermal imaging statistics"""
        if not self.enabled:
            return

        try:
            stats_msg = String()
            stats_msg.data = json.dumps(self.detection_stats)
            self.stats_publisher.publish(stats_msg)

            # Log periodic info
            if self.detection_stats["frames_processed"] % 30 == 0:
                self.get_logger().info(
                    f"📊 Stats - Frames: {self.detection_stats['frames_processed']}, "
                    f"Persons: {self.detection_stats['persons_found']}, "
                    f"Fires: {self.detection_stats['fires_found']}"
                )

        except Exception as e:
            self.get_logger().error(f"❌ Statistics publishing failed: {e}")

    def add_test_signature(self, x: int, y: int, temp: float = 37.0, size: int = 15):
        """Add test signature for demonstration/testing"""
        if self.driver:
            self.driver.add_emulated_object(x, y, temp, size)
            self.get_logger().info(f"➕ Added test signature at ({x},{y}), {temp}°C")

    def clear_test_signatures(self):
        """Clear test signatures"""
        if self.driver:
            self.driver.clear_emulated_objects()
            self.get_logger().info("🧹 Cleared test signatures")


def main(args=None):
    rclpy.init(args=args)
    node = ThermalImagingNode()

    try:
        # Add some test signatures for demonstration
        if node.use_emulation:
            node.add_test_signature(80, 60, temp=37.0, size=15)  # Person-like
            node.add_test_signature(120, 40, temp=150.0, size=8)  # Fire-like

        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.enabled:
            node.driver.stop_streaming()
            node.driver.disconnect()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
