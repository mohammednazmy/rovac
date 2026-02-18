#!/usr/bin/env python3
"""
Object Recognition Node for ROVAC
Lightweight object detection using OpenCV DNN for edge computing
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage, LaserScan
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point
from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
import numpy as np
import time


class ObjectRecognitionNode(Node):
    def __init__(self):
        super().__init__("object_recognition_node")

        # Initialize CV bridge
        self.bridge = CvBridge()

        # Load MobileNet SSD model
        try:
            # Try to load model files
            model_path = (
                "~/robots/rovac/robot_mcp_server/models/MobileNetSSD_deploy.caffemodel"
            )
            config_path = (
                "~/robots/rovac/robot_mcp_server/models/MobileNetSSD_deploy.prototxt"
            )

            # Expand tilde
            import os

            model_path = os.path.expanduser(model_path)
            config_path = os.path.expanduser(config_path)

            if os.path.exists(model_path) and os.path.exists(config_path):
                self.net = cv2.dnn.readNetFromCaffe(config_path, model_path)
                self.get_logger().info("Loaded MobileNet SSD model")
            else:
                # Fallback to simpler approach using built-in OpenCV detectors
                self.net = None
                self.get_logger().warn(
                    "Model files not found, using fallback detection methods"
                )

        except Exception as e:
            self.get_logger().warn(f"Could not load DNN model: {e}")
            self.net = None

        # COCO class labels for MobileNet SSD
        self.class_labels = [
            "background",
            "aeroplane",
            "bicycle",
            "bird",
            "boat",
            "bottle",
            "bus",
            "car",
            "cat",
            "chair",
            "cow",
            "diningtable",
            "dog",
            "horse",
            "motorbike",
            "person",
            "pottedplant",
            "sheep",
            "sofa",
            "train",
            "tvmonitor",
        ]

        # Classes we're interested in for robot navigation
        self.target_classes = {
            "person": 15,
            "chair": 9,
            "sofa": 18,
            "diningtable": 11,
            "pottedplant": 16,
            "tvmonitor": 20,
        }

        # Confidence threshold
        self.confidence_threshold = 0.5

        # Frame processing parameters
        self.frame_skip = 5  # Process every 5th frame
        self.frame_counter = 0
        self.last_process_time = time.time()

        # Subscriptions
        self.image_subscription = self.create_subscription(
            Image, "/phone/image_raw", self.image_callback, 10
        )

        self.compressed_image_subscription = self.create_subscription(
            CompressedImage,
            "/phone/image_raw/compressed",
            self.compressed_image_callback,
            10,
        )

        # Publications
        self.object_markers_pub = self.create_publisher(
            MarkerArray, "/objects/markers", 10
        )

        self.detected_objects_pub = self.create_publisher(
            String, "/objects/detected", 10
        )

        self.enhanced_scan_pub = self.create_publisher(
            LaserScan, "/objects/filtered_scan", 10
        )

        self.get_logger().info("Object Recognition Node initialized")
        self.get_logger().info(
            "Subscribing to: /phone/image_raw, /phone/image_raw/compressed"
        )
        self.get_logger().info(
            "Publishing to: /objects/markers, /objects/detected, /objects/filtered_scan"
        )

    def image_callback(self, msg):
        """Process raw image messages"""
        if self.frame_counter % self.frame_skip != 0:
            self.frame_counter += 1
            return

        self.frame_counter += 1

        # Limit processing rate
        current_time = time.time()
        if current_time - self.last_process_time < 0.2:  # Max 5 FPS
            return

        self.last_process_time = current_time

        try:
            # Convert ROS Image to OpenCV
            cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            self.process_image(cv_image)
        except Exception as e:
            self.get_logger().error(f"Error processing image: {e}")

    def compressed_image_callback(self, msg):
        """Process compressed image messages (fallback)"""
        if self.frame_counter % self.frame_skip != 0:
            self.frame_counter += 1
            return

        self.frame_counter += 1

        # Limit processing rate
        current_time = time.time()
        if current_time - self.last_process_time < 0.2:  # Max 5 FPS
            return

        self.last_process_time = current_time

        try:
            # Convert compressed ROS Image to OpenCV
            np_arr = np.frombuffer(msg.data, np.uint8)
            cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            self.process_image(cv_image)
        except Exception as e:
            self.get_logger().error(f"Error processing compressed image: {e}")

    def process_image(self, cv_image):
        """Process image for object detection"""
        height, width = cv_image.shape[:2]

        # If we have a DNN model, use it
        if self.net is not None:
            detections = self.detect_objects_dnn(cv_image)
        else:
            # Fallback to simple color-based detection
            detections = self.detect_objects_simple(cv_image)

        # Process detections
        self.publish_detections(detections, width, height)

        # Log processing info
        if detections:
            self.get_logger().debug(f"Detected {len(detections)} objects")

    def detect_objects_dnn(self, cv_image):
        """Detect objects using DNN"""
        height, width = cv_image.shape[:2]

        # Prepare blob for DNN
        blob = cv2.dnn.blobFromImage(
            cv_image,
            0.007843,
            (300, 300),
            (127.5, 127.5, 127.5),
            swapRB=True,
            crop=False,
        )

        self.net.setInput(blob)
        detections = self.net.forward()

        # Parse detections
        objects = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]

            if confidence > self.confidence_threshold:
                class_id = int(detections[0, 0, i, 1])
                class_name = (
                    self.class_labels[class_id]
                    if class_id < len(self.class_labels)
                    else "unknown"
                )

                # Check if this is a target class
                if class_name in self.target_classes:
                    # Extract bounding box coordinates
                    box = detections[0, 0, i, 3:7] * np.array(
                        [width, height, width, height]
                    )
                    (x_min, y_min, x_max, y_max) = box.astype("int")

                    objects.append(
                        {
                            "class": class_name,
                            "confidence": float(confidence),
                            "bbox": (x_min, y_min, x_max, y_max),
                        }
                    )

        return objects

    def detect_objects_simple(self, cv_image):
        """Simple fallback detection using color and shape analysis"""
        # This is a placeholder for a simple detection method
        # In a real implementation, this would use techniques like:
        # - Color segmentation for specific objects
        # - HOG/SVM for person detection
        # - Haar cascades for face detection
        # - Motion detection for dynamic objects

        objects = []

        # Simple person detection using HOG
        try:
            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

            # Resize for faster processing
            resized = cv2.resize(cv_image, (320, 240))
            boxes, weights = hog.detectMultiScale(resized, winStride=(8, 8))

            for (x, y, w, h), weight in zip(boxes, weights):
                if weight > 0.5:  # Confidence threshold
                    # Scale back to original image size
                    scale_x = cv_image.shape[1] / 320.0
                    scale_y = cv_image.shape[0] / 240.0

                    x_min = int(x * scale_x)
                    y_min = int(y * scale_y)
                    x_max = int((x + w) * scale_x)
                    y_max = int((y + h) * scale_y)

                    objects.append(
                        {
                            "class": "person",
                            "confidence": float(weight),
                            "bbox": (x_min, y_min, x_max, y_max),
                        }
                    )
        except Exception as e:
            self.get_logger().debug(f"HOG detection failed: {e}")

        return objects

    def publish_detections(self, detections, image_width, image_height):
        """Publish detected objects"""
        if not detections:
            return

        # Publish detected objects as string
        objects_str = ", ".join(
            [f"{d['class']}({d['confidence']:.2f})" for d in detections]
        )
        objects_msg = String()
        objects_msg.data = objects_str
        self.detected_objects_pub.publish(objects_msg)

        # Create visualization markers
        marker_array = MarkerArray()

        for i, detection in enumerate(detections):
            # Create marker for visualization
            marker = Marker()
            marker.header.frame_id = "phone_camera_link"
            marker.header.stamp = self.get_clock().now().to_msg()
            marker.ns = "objects"
            marker.id = i
            marker.type = Marker.CUBE
            marker.action = Marker.ADD

            # Position (simplified - would need proper projection in real implementation)
            marker.pose.position.x = 1.0  # 1 meter in front (placeholder)
            marker.pose.position.y = (
                detection["bbox"][0] + detection["bbox"][2]
            ) / 2 / image_width - 0.5
            marker.pose.position.z = 0.5  # Half meter high (placeholder)

            # Orientation
            marker.pose.orientation.x = 0.0
            marker.pose.orientation.y = 0.0
            marker.pose.orientation.z = 0.0
            marker.pose.orientation.w = 1.0

            # Scale based on confidence and object type
            marker.scale.x = 0.3
            marker.scale.y = 0.3
            marker.scale.z = 0.3

            # Color based on object type
            colors = {
                "person": (1.0, 0.0, 0.0),  # Red
                "chair": (0.0, 1.0, 0.0),  # Green
                "sofa": (0.0, 0.0, 1.0),  # Blue
                "diningtable": (1.0, 1.0, 0.0),  # Yellow
                "pottedplant": (1.0, 0.0, 1.0),  # Magenta
                "tvmonitor": (0.0, 1.0, 1.0),  # Cyan
            }

            color = colors.get(detection["class"], (0.5, 0.5, 0.5))  # Gray default
            marker.color.r = color[0]
            marker.color.g = color[1]
            marker.color.b = color[2]
            marker.color.a = detection["confidence"]

            marker.lifetime.sec = 1
            marker.lifetime.nanosec = 0

            marker_array.markers.append(marker)

        # Publish markers
        self.object_markers_pub.publish(marker_array)


def main(args=None):
    rclpy.init(args=args)
    node = ObjectRecognitionNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
