#!/usr/bin/env python3
"""
Predictive Obstacle Avoidance Node for ROVAC
ROS2 interface for anticipatory collision prevention
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String, Float32
from geometry_msgs.msg import Twist, PoseStamped, Point
from sensor_msgs.msg import LaserScan, Imu, BatteryState
from nav_msgs.msg import Odometry, Path
from visualization_msgs.msg import Marker, MarkerArray
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
import json
import time
import math
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from collections import deque
from predictive_obstacle_avoidance import (
    PredictiveObstacleAvoidance,
    Obstacle,
    RiskAssessment,
)


class PredictiveObstacleAvoidanceNode(Node):
    """ROS2 node for predictive obstacle avoidance"""

    def __init__(self):
        super().__init__("predictive_obstacle_avoidance_node")

        # ROS2 parameters
        self.declare_parameter("enable_predictive_avoidance", True)
        self.declare_parameter("prediction_horizon_seconds", 5.0)
        self.declare_parameter("risk_threshold", 0.3)
        self.declare_parameter("safety_margin_meters", 0.3)
        self.declare_parameter("reaction_time_seconds", 0.5)
        self.declare_parameter("learning_enabled", True)
        self.declare_parameter("publish_visualization", True)
        self.declare_parameter("max_prediction_age", 3.0)
        self.declare_parameter("update_frequency_hz", 10.0)
        self.declare_parameter("max_tracked_obstacles", 50)
        self.declare_parameter("kalman_process_noise", 0.1)
        self.declare_parameter("kalman_measurement_noise", 0.05)
        self.declare_parameter("collision_distance_threshold", 0.5)
        self.declare_parameter("publish_debug_info", False)

        self.enabled = self.get_parameter("enable_predictive_avoidance").value
        self.prediction_horizon = self.get_parameter("prediction_horizon_seconds").value
        self.risk_threshold = self.get_parameter("risk_threshold").value
        self.safety_margin = self.get_parameter("safety_margin_meters").value
        self.reaction_time = self.get_parameter("reaction_time_seconds").value
        self.learning_enabled = self.get_parameter("learning_enabled").value
        self.publish_viz = self.get_parameter("publish_visualization").value
        self.max_prediction_age = self.get_parameter("max_prediction_age").value
        self.update_freq = self.get_parameter("update_frequency_hz").value
        self.max_obstacles = self.get_parameter("max_tracked_obstacles").value
        self.kalman_process_noise = self.get_parameter("kalman_process_noise").value
        self.kalman_measurement_noise = self.get_parameter(
            "kalman_measurement_noise"
        ).value
        self.collision_threshold = self.get_parameter(
            "collision_distance_threshold"
        ).value
        self.publish_debug = self.get_parameter("publish_debug_info").value

        # Initialize predictive obstacle avoidance system
        self.obstacle_avoidance = PredictiveObstacleAvoidance(
            prediction_horizon=self.prediction_horizon,
            risk_threshold=self.risk_threshold,
            safety_margin=self.safety_margin,
            reaction_time=self.reaction_time,
            learning_enabled=self.learning_enabled,
            max_prediction_age=self.max_prediction_age,
            max_tracked_obstacles=self.max_obstacles,
            kalman_process_noise=self.kalman_process_noise,
            kalman_measurement_noise=self.kalman_measurement_noise,
            collision_distance_threshold=self.collision_threshold,
        )

        # State tracking
        self.current_pose = (0.0, 0.0, 0.0)  # x, y, theta
        self.current_velocity = (0.0, 0.0)  # linear, angular
        self.goal_pose = None
        self.battery_level = 100.0
        self.lidar_data = []
        self.imu_data = (0.0, 0.0, 0.0)  # roll, pitch, yaw
        self.ultrasonic_data = [0.0] * 4  # Four ultrasonic sensors
        self.camera_features = []
        self.thermal_data = []
        self.dynamic_obstacles = []
        self.recent_collisions = 0
        self.recent_obstacles = 0
        self.time_since_start = 0.0
        self.start_time = time.time()

        # Performance metrics
        self.avoidance_stats = {
            "obstacles_tracked": 0,
            "predictions_made": 0,
            "collisions_averted": 0,
            "false_positives": 0,
            "average_reaction_time_ms": 0.0,
            "prediction_accuracy": 0.0,
            "avoidance_success_rate": 0.0,
            "risk_assessments": 0,
            "avoidance_maneuvers": 0,
            "emergency_stops": 0,
        }

        # Experience tracking
        self.experience_buffer = deque(maxlen=10000)
        self.prediction_history = deque(maxlen=5000)
        self.avoidance_history = deque(maxlen=1000)

        if not self.enabled:
            self.get_logger().info("Predictive Obstacle Avoidance Node disabled")
            return

        # QoS profile
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # Subscriptions
        self.odom_subscription = self.create_subscription(
            Odometry, "/odom", self.odom_callback, qos_profile
        )

        self.lidar_subscription = self.create_subscription(
            LaserScan, "/scan", self.lidar_callback, qos_profile
        )

        self.imu_subscription = self.create_subscription(
            Imu, "/sensors/imu", self.imu_callback, qos_profile
        )

        self.battery_subscription = self.create_subscription(
            BatteryState, "/battery/state", self.battery_callback, qos_profile
        )

        self.goal_subscription = self.create_subscription(
            PoseStamped, "/goal_pose", self.goal_callback, qos_profile
        )

        self.ultrasonic_subscription = self.create_subscription(
            LaserScan,  # Using LaserScan for ultrasonic data
            "/sensors/ultrasonic/range",
            self.ultrasonic_callback,
            qos_profile,
        )

        self.camera_features_subscription = self.create_subscription(
            String,  # Simplified - would be custom message type in practice
            "/camera/features",
            self.camera_features_callback,
            qos_profile,
        )

        self.thermal_data_subscription = self.create_subscription(
            String,  # Simplified - would be custom message type
            "/thermal/signatures",
            self.thermal_callback,
            qos_profile,
        )

        # Publishers
        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel_predictive", 10)

        self.tracked_obstacles_publisher = self.create_publisher(
            String, "/predictive_obstacles/tracked", 10
        )

        self.predicted_obstacles_publisher = self.create_publisher(
            String, "/predictive_obstacles/predicted", 10
        )

        self.risk_assessment_publisher = self.create_publisher(
            String, "/predictive_obstacles/risk_assessment", 10
        )

        self.avoidance_command_publisher = self.create_publisher(
            Twist, "/predictive_obstacles/avoidance_command", 10
        )

        self.maneuvers_publisher = self.create_publisher(
            String, "/predictive_obstacles/maneuvers", 10
        )

        self.emergency_stop_publisher = self.create_publisher(
            String, "/predictive_obstacles/emergency_stop", 10
        )

        self.visualization_publisher = self.create_publisher(
            MarkerArray, "/predictive_obstacles/markers", 10
        )

        self.debug_info_publisher = self.create_publisher(
            String, "/predictive_obstacles/debug_info", 10
        )

        self.statistics_publisher = self.create_publisher(
            String, "/predictive_obstacles/statistics", 10
        )

        # Timers
        self.avoidance_timer = self.create_timer(
            1.0 / self.update_freq, self.avoidance_callback
        )

        self.stats_timer = self.create_timer(
            5.0,  # Every 5 seconds
            self.publish_statistics,
        )

        # Initialize obstacle avoidance parameters
        self.obstacle_avoidance.prediction_horizon = self.prediction_horizon
        self.obstacle_avoidance.risk_threshold = self.risk_threshold
        self.obstacle_avoidance.safety_margin = self.safety_margin
        self.obstacle_avoidance.reaction_time = self.reaction_time
        self.obstacle_avoidance.learning_enabled = self.learning_enabled
        self.obstacle_avoidance.max_prediction_age = self.max_prediction_age
        self.obstacle_avoidance.max_tracked_obstacles = self.max_obstacles
        self.obstacle_avoidance.kalman_process_noise = self.kalman_process_noise
        self.obstacle_avoidance.kalman_measurement_noise = self.kalman_measurement_noise
        self.obstacle_avoidance.collision_distance_threshold = self.collision_threshold

        self.get_logger().info("Predictive Obstacle Avoidance Node initialized")
        self.get_logger().info(f"Enabled: {'Yes' if self.enabled else 'No'}")
        self.get_logger().info(f"Prediction horizon: {self.prediction_horizon}s")
        self.get_logger().info(f"Risk threshold: {self.risk_threshold}")
        self.get_logger().info(f"Safety margin: {self.safety_margin}m")
        self.get_logger().info(f"Reaction time: {self.reaction_time}s")
        self.get_logger().info(
            f"Learning enabled: {'Yes' if self.learning_enabled else 'No'}"
        )
        self.get_logger().info(
            f"Publish visualization: {'Yes' if self.publish_viz else 'No'}"
        )
        self.get_logger().info(f"Max prediction age: {self.max_prediction_age}s")
        self.get_logger().info(f"Update frequency: {self.update_freq} Hz")
        self.get_logger().info(f"Max tracked obstacles: {self.max_obstacles}")
        self.get_logger().info(f"Kalman process noise: {self.kalman_process_noise}")
        self.get_logger().info(
            f"Kalman measurement noise: {self.kalman_measurement_noise}"
        )
        self.get_logger().info(f"Collision threshold: {self.collision_threshold}m")
        self.get_logger().info(
            f"Publish debug info: {'Yes' if self.publish_debug else 'No'}"
        )

    def odom_callback(self, msg):
        """Handle odometry updates"""
        self.current_pose = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            self._quaternion_to_yaw(msg.pose.pose.orientation),
        )

        self.current_velocity = (msg.twist.twist.linear.x, msg.twist.twist.angular.z)

        # Update time since start
        self.time_since_start = time.time() - self.start_time

        # Update obstacle avoidance with robot state
        if self.obstacle_avoidance:
            self.obstacle_avoidance.update_robot_state(
                x=self.current_pose[0],
                y=self.current_pose[1],
                theta=self.current_pose[2],
                linear_velocity=self.current_velocity[0],
                angular_velocity=self.current_velocity[1],
                battery_level=self.battery_level,
                timestamp=time.time(),
            )

    def lidar_callback(self, msg):
        """Handle LIDAR scan data"""
        self.lidar_data = list(msg.ranges)

        # Update obstacle avoidance with LIDAR data
        if self.obstacle_avoidance:
            self.obstacle_avoidance.update_with_lidar_scan(self.lidar_data)

        # Count obstacles
        self.recent_obstacles = sum(
            1 for distance in self.lidar_data if 0.1 < distance < 2.0
        )  # Obstacles within 2m

    def imu_callback(self, msg):
        """Handle IMU data"""
        # Convert quaternion to Euler angles
        roll, pitch, yaw = self._quaternion_to_euler(msg.orientation)
        self.imu_data = (roll, pitch, yaw)

        # Update obstacle avoidance with IMU data
        if self.obstacle_avoidance:
            self.obstacle_avoidance.update_with_imu_data(roll, pitch, yaw)

    def battery_callback(self, msg):
        """Handle battery state updates"""
        self.battery_level = msg.percentage

        # Update obstacle avoidance with battery data
        if self.obstacle_avoidance:
            self.obstacle_avoidance.update_with_battery_data(self.battery_level)

    def goal_callback(self, msg):
        """Handle goal pose updates"""
        self.goal_pose = (msg.pose.position.x, msg.pose.position.y)
        self.get_logger().info(
            f"New navigation goal received: ({self.goal_pose[0]:.2f}, {self.goal_pose[1]:.2f})"
        )

        # Update obstacle avoidance with goal
        if self.obstacle_avoidance and self.goal_pose:
            self.obstacle_avoidance.update_with_goal(
                self.goal_pose[0], self.goal_pose[1]
            )

    def ultrasonic_callback(self, msg):
        """Handle ultrasonic sensor data"""
        self.ultrasonic_data = list(msg.ranges)

        # Update obstacle avoidance with ultrasonic data
        if self.obstacle_avoidance:
            self.obstacle_avoidance.update_with_ultrasonic_data(self.ultrasonic_data)

    def camera_features_callback(self, msg):
        """Handle camera feature detections"""
        try:
            features_data = json.loads(msg.data)
            self.camera_features = features_data.get("features", [])

            # Update obstacle avoidance with camera features
            if self.obstacle_avoidance:
                self.obstacle_avoidance.update_with_camera_features(
                    self.camera_features
                )

        except Exception as e:
            self.get_logger().warn(f"Failed to parse camera features: {e}")

    def thermal_callback(self, msg):
        """Handle thermal signature detections"""
        try:
            thermal_data = json.loads(msg.data)
            self.thermal_data = thermal_data.get("signatures", [])

            # Update obstacle avoidance with thermal data
            if self.obstacle_avoidance:
                self.obstacle_avoidance.update_with_thermal_data(self.thermal_data)

        except Exception as e:
            self.get_logger().warn(f"Failed to parse thermal data: {e}")

    def _quaternion_to_yaw(self, orientation) -> float:
        """Convert quaternion to yaw angle"""
        # Simplified conversion
        return 2.0 * math.atan2(orientation.z, orientation.w)

    def _quaternion_to_euler(self, orientation) -> Tuple[float, float, float]:
        """Convert quaternion to Euler angles"""
        # Simplified conversion
        roll = 0.0
        pitch = 0.0
        yaw = 2.0 * math.atan2(orientation.z, orientation.w)
        return (roll, pitch, yaw)

    def avoidance_callback(self):
        """Main avoidance callback"""
        if not self.enabled:
            return

        # Check for collisions
        collision_occurred = self._check_collision()
        if collision_occurred:
            self._handle_collision()
            return

        # Assess collision risk
        risk_assessment = self.obstacle_avoidance.assess_collision_risk()

        # Update statistics
        self.avoidance_stats["risk_assessments"] += 1
        self.avoidance_stats["prediction_accuracy"] = (
            self.avoidance_stats["prediction_accuracy"] * 0.99
            + risk_assessment.accuracy * 0.01
        )

        # Publish risk assessment
        self.publish_risk_assessment(risk_assessment)

        # Take avoidance action if needed
        if risk_assessment.collision_probability > self.risk_threshold:
            linear_vel, angular_vel = self.obstacle_avoidance.execute_avoidance_action(
                risk_assessment
            )
            self.send_avoidance_command(linear_vel, angular_vel)
            self.get_logger().info("Executing collision avoidance maneuver")

            # Update statistics
            self.avoidance_stats["avoidance_maneuvers"] += 1
            self.avoidance_stats["collisions_averted"] += 1

            # Store avoidance experience
            if self.learning_enabled:
                experience = {
                    "timestamp": time.time(),
                    "risk_assessment": risk_assessment,
                    "avoidance_action": (linear_vel, angular_vel),
                    "collision_averted": True,
                    "battery_level": self.battery_level,
                    "obstacle_count": self.recent_obstacles,
                }
                self.experience_buffer.append(experience)
                self.avoidance_history.append(experience)

        # Update obstacle tracking
        tracked_obstacles = self.obstacle_avoidance.get_tracked_obstacles()
        self.avoidance_stats["obstacles_tracked"] = len(tracked_obstacles)

        # Publish tracked obstacles
        self.publish_tracked_obstacles(tracked_obstacles)

        # Publish predicted obstacles
        predicted_obstacles = self.obstacle_avoidance.get_predicted_obstacles()
        self.publish_predicted_obstacles(predicted_obstacles)

        # Publish visualization markers
        if self.publish_viz:
            self.publish_visualization(
                tracked_obstacles, predicted_obstacles, risk_assessment
            )

        # Publish debug information
        if self.publish_debug:
            self.publish_debug_info()

        # Learn from experience
        if self.learning_enabled and len(self.experience_buffer) >= 100:
            self._learn_from_experience()

    def _check_collision(self) -> bool:
        """Check for collision (simplified)"""
        if not self.lidar_data:
            return False

        # Check for very close obstacles
        min_distance = min([d for d in self.lidar_data if d > 0.01], default=10.0)
        return min_distance < self.safety_margin

    def _handle_collision(self):
        """Handle collision event"""
        self.get_logger().warn("💥 Collision detected!")

        # Send emergency stop command
        self.send_emergency_stop()

        # Update statistics
        self.avoidance_stats["collisions_averted"] += 1
        self.avoidance_stats["emergency_stops"] += 1

        # Store collision experience
        if self.learning_enabled:
            experience = {
                "timestamp": time.time(),
                "risk_assessment": None,
                "avoidance_action": (0.0, 0.0),  # Stop
                "collision_averted": False,
                "battery_level": self.battery_level,
                "obstacle_count": self.recent_obstacles,
            }
            self.experience_buffer.append(experience)
            self.avoidance_history.append(experience)

    def send_avoidance_command(self, linear_vel: float, angular_vel: float):
        """Send avoidance velocity command"""
        twist_msg = Twist()
        twist_msg.linear.x = float(linear_vel)
        twist_msg.angular.z = float(angular_vel)
        self.avoidance_command_publisher.publish(twist_msg)

        # Also publish to main command velocity topic
        self.cmd_vel_publisher.publish(twist_msg)

    def send_emergency_stop(self):
        """Send emergency stop command"""
        twist_msg = Twist()
        twist_msg.linear.x = 0.0
        twist_msg.angular.z = 0.0
        self.cmd_vel_publisher.publish(twist_msg)
        self.avoidance_command_publisher.publish(twist_msg)

        # Publish emergency stop notification
        stop_msg = String()
        stop_msg.data = json.dumps(
            {
                "timestamp": time.time(),
                "type": "emergency_stop",
                "reason": "collision_detected",
                "command": "stop_all_motors",
            }
        )
        self.emergency_stop_publisher.publish(stop_msg)

    def publish_tracked_obstacles(self, obstacles: List[Obstacle]):
        """Publish tracked obstacles"""
        obstacles_msg = String()
        obstacles_data = []

        for obstacle in obstacles:
            obstacles_data.append(
                {
                    "id": obstacle.id,
                    "x": obstacle.x,
                    "y": obstacle.y,
                    "vx": obstacle.vx,
                    "vy": obstacle.vy,
                    "radius": obstacle.radius,
                    "type": obstacle.type,
                    "confidence": obstacle.confidence,
                    "last_seen": obstacle.last_seen,
                    "prediction_horizon": obstacle.prediction_horizon,
                    "predicted_trajectory": obstacle.predicted_trajectory,
                }
            )

        obstacles_msg.data = json.dumps(
            {
                "timestamp": time.time(),
                "obstacles": obstacles_data,
                "count": len(obstacles),
            }
        )

        self.tracked_obstacles_publisher.publish(obstacles_msg)

    def publish_predicted_obstacles(self, obstacles: List[Obstacle]):
        """Publish predicted obstacles"""
        predicted_msg = String()
        predicted_data = []

        for obstacle in obstacles:
            predicted_data.append(
                {
                    "id": obstacle.id,
                    "x": obstacle.x,
                    "y": obstacle.y,
                    "predicted_x": obstacle.predicted_x
                    if hasattr(obstacle, "predicted_x")
                    else obstacle.x,
                    "predicted_y": obstacle.predicted_y
                    if hasattr(obstacle, "predicted_y")
                    else obstacle.y,
                    "prediction_time": obstacle.prediction_time
                    if hasattr(obstacle, "prediction_time")
                    else time.time(),
                    "confidence": obstacle.confidence,
                    "collision_probability": obstacle.collision_probability
                    if hasattr(obstacle, "collision_probability")
                    else 0.0,
                    "time_to_collision": obstacle.time_to_collision
                    if hasattr(obstacle, "time_to_collision")
                    else float("inf"),
                }
            )

        predicted_msg.data = json.dumps(
            {
                "timestamp": time.time(),
                "predicted_obstacles": predicted_data,
                "count": len(obstacles),
            }
        )

        self.predicted_obstacles_publisher.publish(predicted_msg)

    def publish_risk_assessment(self, risk_assessment: RiskAssessment):
        """Publish risk assessment"""
        risk_msg = String()
        risk_msg.data = json.dumps(
            {
                "timestamp": time.time(),
                "collision_probability": risk_assessment.collision_probability,
                "time_to_collision": risk_assessment.time_to_collision,
                "risk_level": risk_assessment.risk_level,
                "recommended_action": risk_assessment.recommended_action,
                "collision_point": risk_assessment.collision_point,
                "collision_time": risk_assessment.collision_time,
                "accuracy": risk_assessment.accuracy,
                "confidence": risk_assessment.confidence,
            }
        )

        self.risk_assessment_publisher.publish(risk_msg)

    def publish_visualization(
        self,
        tracked_obstacles: List[Obstacle],
        predicted_obstacles: List[Obstacle],
        risk_assessment: RiskAssessment,
    ):
        """Publish visualization markers"""
        marker_array = MarkerArray()

        # Tracked obstacles
        for i, obstacle in enumerate(tracked_obstacles):
            # Current position marker
            current_marker = Marker()
            current_marker.header.stamp = self.get_clock().now().to_msg()
            current_marker.header.frame_id = "map"
            current_marker.ns = "tracked_obstacles"
            current_marker.id = i * 2
            current_marker.type = Marker.SPHERE
            current_marker.action = Marker.ADD
            current_marker.pose.position.x = float(obstacle.x)
            current_marker.pose.position.y = float(obstacle.y)
            current_marker.pose.position.z = 0.1
            current_marker.pose.orientation.w = 1.0
            current_marker.scale.x = float(obstacle.radius * 2)
            current_marker.scale.y = float(obstacle.radius * 2)
            current_marker.scale.z = 0.2
            current_marker.color.r = 1.0  # Red for obstacles
            current_marker.color.g = 0.0
            current_marker.color.b = 0.0
            current_marker.color.a = float(obstacle.confidence)
            marker_array.markers.append(current_marker)

            # Velocity vector marker
            if abs(obstacle.vx) > 0.01 or abs(obstacle.vy) > 0.01:
                arrow_marker = Marker()
                arrow_marker.header.stamp = self.get_clock().now().to_msg()
                arrow_marker.header.frame_id = "map"
                arrow_marker.ns = "obstacle_velocities"
                arrow_marker.id = i * 2 + 1
                arrow_marker.type = Marker.ARROW
                arrow_marker.action = Marker.ADD
                arrow_marker.pose.position.x = float(obstacle.x)
                arrow_marker.pose.position.y = float(obstacle.y)
                arrow_marker.pose.position.z = 0.2

                # Set orientation based on velocity
                velocity_angle = math.atan2(obstacle.vy, obstacle.vx)
                arrow_marker.pose.orientation.z = math.sin(velocity_angle / 2.0)
                arrow_marker.pose.orientation.w = math.cos(velocity_angle / 2.0)

                arrow_marker.scale.x = (
                    math.sqrt(obstacle.vx**2 + obstacle.vy**2) * 2.0
                )  # Arrow length
                arrow_marker.scale.y = 0.05  # Arrow width
                arrow_marker.scale.z = 0.05  # Arrow height
                arrow_marker.color.r = 0.0
                arrow_marker.color.g = 1.0  # Green for velocity
                arrow_marker.color.b = 0.0
                arrow_marker.color.a = 0.7
                marker_array.markers.append(arrow_marker)

        # Predicted obstacles
        for i, obstacle in enumerate(predicted_obstacles):
            # Predicted position marker
            predicted_marker = Marker()
            predicted_marker.header.stamp = self.get_clock().now().to_msg()
            predicted_marker.header.frame_id = "map"
            predicted_marker.ns = "predicted_obstacles"
            predicted_marker.id = 1000 + i
            predicted_marker.type = Marker.SPHERE
            predicted_marker.action = Marker.ADD
            predicted_marker.pose.position.x = float(
                getattr(obstacle, "predicted_x", obstacle.x)
            )
            predicted_marker.pose.position.y = float(
                getattr(obstacle, "predicted_y", obstacle.y)
            )
            predicted_marker.pose.position.z = 0.15
            predicted_marker.pose.orientation.w = 1.0
            predicted_marker.scale.x = float(obstacle.radius * 2)
            predicted_marker.scale.y = float(obstacle.radius * 2)
            predicted_marker.scale.z = 0.1
            predicted_marker.color.r = 1.0  # Orange for predicted
            predicted_marker.color.g = 0.5
            predicted_marker.color.b = 0.0
            predicted_marker.color.a = float(
                getattr(obstacle, "collision_probability", 0.3)
            )
            marker_array.markers.append(predicted_marker)

        # Risk assessment visualization
        if risk_assessment.collision_probability > 0.1:
            # Collision risk zone
            risk_marker = Marker()
            risk_marker.header.stamp = self.get_clock().now().to_msg()
            risk_marker.header.frame_id = "map"
            risk_marker.ns = "collision_risk"
            risk_marker.id = 2000
            risk_marker.type = Marker.CYLINDER
            risk_marker.action = Marker.ADD
            risk_marker.pose.position.x = float(risk_assessment.collision_point[0])
            risk_marker.pose.position.y = float(risk_assessment.collision_point[1])
            risk_marker.pose.position.z = 0.05
            risk_marker.pose.orientation.w = 1.0
            risk_marker.scale.x = 0.5  # Diameter
            risk_marker.scale.y = 0.5  # Diameter
            risk_marker.scale.z = 0.1  # Height
            risk_marker.color.r = 1.0  # Red for high risk
            risk_marker.color.g = 0.0
            risk_marker.color.b = 0.0
            risk_marker.color.a = float(risk_assessment.collision_probability)
            marker_array.markers.append(risk_marker)

        # Robot position marker
        robot_marker = Marker()
        robot_marker.header.stamp = self.get_clock().now().to_msg()
        robot_marker.header.frame_id = "map"
        robot_marker.ns = "robot"
        robot_marker.id = 3000
        robot_marker.type = Marker.ARROW
        robot_marker.action = Marker.ADD
        robot_marker.pose.position.x = float(self.current_pose[0])
        robot_marker.pose.position.y = float(self.current_pose[1])
        robot_marker.pose.position.z = 0.1

        # Set orientation
        robot_marker.pose.orientation.z = math.sin(self.current_pose[2] / 2.0)
        robot_marker.pose.orientation.w = math.cos(self.current_pose[2] / 2.0)

        robot_marker.scale.x = 0.3  # Arrow length
        robot_marker.scale.y = 0.1  # Arrow width
        robot_marker.scale.z = 0.1  # Arrow height
        robot_marker.color.r = 0.0
        robot_marker.color.g = 1.0  # Green for robot
        robot_marker.color.b = 0.0
        robot_marker.color.a = 1.0
        marker_array.markers.append(robot_marker)

        self.visualization_publisher.publish(marker_array)

    def publish_debug_info(self):
        """Publish debug information"""
        debug_msg = String()
        debug_msg.data = json.dumps(
            {
                "timestamp": time.time(),
                "current_pose": self.current_pose,
                "current_velocity": self.current_velocity,
                "goal_pose": self.goal_pose,
                "battery_level": self.battery_level,
                "lidar_points": len(self.lidar_data),
                "ultrasonic_readings": self.ultrasonic_data,
                "imu_data": self.imu_data,
                "camera_features": len(self.camera_features),
                "thermal_signatures": len(self.thermal_data),
                "recent_obstacles": self.recent_obstacles,
                "recent_collisions": self.recent_collisions,
                "time_since_start": self.time_since_start,
                "prediction_horizon": self.prediction_horizon,
                "risk_threshold": self.risk_threshold,
                "safety_margin": self.safety_margin,
                "reaction_time": self.reaction_time,
                "learning_enabled": self.learning_enabled,
                "publish_visualization": self.publish_viz,
                "max_prediction_age": self.max_prediction_age,
                "update_frequency": self.update_freq,
                "max_tracked_obstacles": self.max_obstacles,
                "kalman_process_noise": self.kalman_process_noise,
                "kalman_measurement_noise": self.kalman_measurement_noise,
                "collision_threshold": self.collision_threshold,
                "publish_debug_info": self.publish_debug,
            }
        )

        self.debug_info_publisher.publish(debug_msg)

    def publish_statistics(self):
        """Publish avoidance statistics"""
        stats_msg = String()
        stats_msg.data = json.dumps(self.avoidance_stats)
        self.statistics_publisher.publish(stats_msg)

        # Log periodic stats
        self.get_logger().info(
            f"Predictive Avoidance Stats - "
            f"Tracked: {self.avoidance_stats['obstacles_tracked']}, "
            f"Predictions: {self.avoidance_stats['predictions_made']}, "
            f"Averted: {self.avoidance_stats['collisions_averted']}, "
            f"Accuracy: {self.avoidance_stats['prediction_accuracy']:.3f}"
        )

    def _learn_from_experience(self):
        """Learn from accumulated experience"""
        if not self.learning_enabled or len(self.experience_buffer) < 100:
            return

        # In a real implementation, this would train the prediction models
        # For simulation, we'll just update some statistics

        recent_experiences = list(self.experience_buffer)[-100:]
        successful_avoidances = sum(
            1 for exp in recent_experiences if exp.get("collision_averted", False)
        )
        total_attempts = len(recent_experiences)

        if total_attempts > 0:
            success_rate = successful_avoidances / total_attempts
            self.avoidance_stats["avoidance_success_rate"] = (
                self.avoidance_stats["avoidance_success_rate"] * 0.9
                + success_rate * 0.1
            )

        # Update prediction count
        self.avoidance_stats["predictions_made"] += len(recent_experiences)

        # Clear some experience to prevent buffer overflow
        while len(self.experience_buffer) > 5000:
            self.experience_buffer.popleft()

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        return self.avoidance_stats.copy()


def main(args=None):
    rclpy.init(args=args)
    node = PredictiveObstacleAvoidanceNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
