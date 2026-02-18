#!/usr/bin/env python3
"""
Advanced Navigation Node for ROVAC
ROS2 interface for deep learning path planning and predictive navigation
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

# Import our advanced navigation components
# Note: These would need to be implemented as separate modules
# For now, we'll define simplified versions


class NavigationState:
    """Navigation state for RL agents"""

    def __init__(
        self,
        x=0.0,
        y=0.0,
        theta=0.0,
        lidar_scan=None,
        ultrasonic_readings=None,
        imu_orientation=None,
        camera_features=None,
        thermal_data=None,
        goal_x=0.0,
        goal_y=0.0,
        battery_level=100.0,
        time_since_start=0.0,
        recent_collisions=0,
    ):
        self.x = x
        self.y = y
        self.theta = theta
        self.lidar_scan = lidar_scan or []
        self.ultrasonic_readings = ultrasonic_readings or []
        self.imu_orientation = imu_orientation or (0.0, 0.0, 0.0)
        self.camera_features = camera_features
        self.thermal_data = thermal_data
        self.goal_x = goal_x
        self.goal_y = goal_y
        self.battery_level = battery_level
        self.time_since_start = time_since_start
        self.recent_collisions = recent_collisions


class Obstacle:
    """Obstacle representation"""

    def __init__(
        self,
        x=0.0,
        y=0.0,
        radius=0.15,
        velocity_x=0.0,
        velocity_y=0.0,
        confidence=1.0,
        type="static",
    ):
        self.x = x
        self.y = y
        self.radius = radius
        self.velocity_x = velocity_x
        self.velocity_y = velocity_y
        self.confidence = confidence
        self.type = type


class RobotState:
    """Robot state for obstacle avoidance"""

    def __init__(
        self,
        x=0.0,
        y=0.0,
        theta=0.0,
        linear_velocity=0.0,
        angular_velocity=0.0,
        battery_level=100.0,
        timestamp=0.0,
    ):
        self.x = x
        self.y = y
        self.theta = theta
        self.linear_velocity = linear_velocity
        self.angular_velocity = angular_velocity
        self.battery_level = battery_level
        self.timestamp = timestamp


class RiskAssessment:
    """Risk assessment for collision avoidance"""

    def __init__(
        self,
        collision_probability=0.0,
        time_to_collision=float("inf"),
        risk_level="low",
        recommended_action="continue",
        collision_point=(0.0, 0.0),
        collision_time=0.0,
    ):
        self.collision_probability = collision_probability
        self.time_to_collision = time_to_collision
        self.risk_level = risk_level
        self.recommended_action = recommended_action
        self.collision_point = collision_point
        self.collision_time = collision_time


class DeepQLearningAgent:
    """Simplified Deep Q-Learning agent"""

    def __init__(self):
        self.epsilon = 1.0
        self.memory = []

    def act(self, state):
        """Choose action"""
        import random

        if random.random() < self.epsilon:
            return random.randint(0, 8)  # Discrete actions
        else:
            return 0  # Best action


class ActorCriticAgent:
    """Simplified Actor-Critic agent"""

    def __init__(self):
        pass

    def act(self, state):
        """Choose continuous action"""
        return 0.3, 0.0  # Linear and angular velocities


class AdaptiveEnvironmentalModel:
    """Simplified environmental model"""

    def __init__(self):
        self.features = {}
        self.cells = {}

    def update_with_lidar_scan(self, lidar_data, robot_pose, timestamp):
        """Update with LIDAR data"""
        pass


class PredictiveObstacleAvoidance:
    """Simplified obstacle avoidance"""

    def __init__(self):
        self.obstacles = []

    def update_robot_state(self, robot_state):
        """Update robot state"""
        pass

    def assess_collision_risk(self):
        """Assess collision risk"""
        return RiskAssessment()

    def execute_avoidance_action(self, risk_assessment):
        """Execute avoidance action"""
        return 0.0, 0.0  # Linear and angular velocities


class EnvironmentalContext:
    """Environmental context for path planning"""

    def __init__(
        self,
        occupancy_grid=None,
        temperature_map=None,
        feature_map=None,
        dynamic_obstacles=None,
        goal_position=(0.0, 0.0),
        robot_position=(0.0, 0.0, 0.0),
    ):
        self.occupancy_grid = occupancy_grid
        self.temperature_map = temperature_map
        self.feature_map = feature_map or {}
        self.dynamic_obstacles = dynamic_obstacles or []
        self.goal_position = goal_position
        self.robot_position = robot_position


class PathPoint:
    """Point in a planned path"""

    def __init__(
        self,
        x=0.0,
        y=0.0,
        theta=0.0,
        velocity=0.0,
        curvature=0.0,
        timestamp=0.0,
        cost=0.0,
    ):
        self.x = x
        self.y = y
        self.theta = theta
        self.velocity = velocity
        self.curvature = curvature
        self.timestamp = timestamp
        self.cost = cost


class NeuralPathPlan:
    """Neural network-generated path plan"""

    def __init__(
        self,
        path_points=None,
        total_cost=0.0,
        planning_time=0.0,
        confidence=1.0,
        optimization_level="basic",
    ):
        self.path_points = path_points or []
        self.total_cost = total_cost
        self.planning_time = planning_time
        self.confidence = confidence
        self.optimization_level = optimization_level


class NeuralPathPlanner:
    """Simplified neural path planner"""

    def __init__(self):
        pass

    def generate_path(self, context):
        """Generate path"""
        # Create dummy path
        path_points = []
        for i in range(10):
            point = PathPoint(
                x=i * 0.5,
                y=i * 0.2,
                theta=0.0,
                velocity=0.3,
                curvature=0.0,
                timestamp=time.time() + i * 0.1,
                cost=i * 0.1,
            )
            path_points.append(point)

        return NeuralPathPlan(
            path_points=path_points, total_cost=10.0, planning_time=0.5, confidence=0.9
        )


class AdvancedNavigationNode(Node):
    """ROS2 node for advanced AI/ML navigation"""

    def __init__(self):
        super().__init__("advanced_navigation_node")

        # ROS2 parameters
        self.declare_parameter("enable_rl_navigation", True)
        self.declare_parameter("enable_neural_planning", True)
        self.declare_parameter("enable_predictive_avoidance", True)
        self.declare_parameter("enable_environmental_modeling", True)
        self.declare_parameter("planning_frequency_hz", 1.0)
        self.declare_parameter("prediction_horizon_seconds", 5.0)
        self.declare_parameter("safety_margin_meters", 0.3)

        self.rl_enabled = self.get_parameter("enable_rl_navigation").value
        self.neural_enabled = self.get_parameter("enable_neural_planning").value
        self.avoidance_enabled = self.get_parameter("enable_predictive_avoidance").value
        self.modeling_enabled = self.get_parameter(
            "enable_environmental_modeling"
        ).value
        self.planning_freq = self.get_parameter("planning_frequency_hz").value
        self.prediction_horizon = self.get_parameter("prediction_horizon_seconds").value
        self.safety_margin = self.get_parameter("safety_margin_meters").value

        # Initialize navigation components
        self.rl_agent = DeepQLearningAgent() if self.rl_enabled else None
        self.actor_critic_agent = ActorCriticAgent() if self.rl_enabled else None
        self.neural_planner = NeuralPathPlanner() if self.neural_enabled else None
        self.environmental_model = (
            AdaptiveEnvironmentalModel() if self.modeling_enabled else None
        )
        self.obstacle_avoidance = (
            PredictiveObstacleAvoidance() if self.avoidance_enabled else None
        )

        # State tracking
        self.current_pose = (0.0, 0.0, 0.0)  # x, y, theta
        self.current_velocity = (0.0, 0.0)  # linear, angular
        self.goal_pose = None
        self.battery_level = 100.0
        self.lidar_data = []
        self.imu_data = (0.0, 0.0, 0.0)  # roll, pitch, yaw
        self.camera_features = []
        self.thermal_data = []
        self.dynamic_obstacles = []

        # Performance metrics
        self.navigation_stats = {
            "plans_generated": 0,
            "successful_navigations": 0,
            "collisions_averted": 0,
            "average_planning_time": 0.0,
            "rl_episodes": 0,
            "model_updates": 0,
        }

        # Subscriptions
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

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
        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel_advanced", 10)

        self.planned_path_publisher = self.create_publisher(
            Path, "/navigation/planned_path", 10
        )

        self.navigation_markers_publisher = self.create_publisher(
            MarkerArray, "/navigation/markers", 10
        )

        self.risk_assessment_publisher = self.create_publisher(
            String, "/navigation/risk_assessment", 10
        )

        self.navigation_stats_publisher = self.create_publisher(
            String, "/navigation/statistics", 10
        )

        # Timers
        self.planning_timer = self.create_timer(
            1.0 / self.planning_freq, self.planning_callback
        )

        self.stats_timer = self.create_timer(
            5.0,  # Every 5 seconds
            self.publish_statistics,
        )

        self.get_logger().info("Advanced Navigation Node initialized")
        self.get_logger().info(
            f"RL Navigation: {'Enabled' if self.rl_enabled else 'Disabled'}"
        )
        self.get_logger().info(
            f"Neural Planning: {'Enabled' if self.neural_enabled else 'Disabled'}"
        )
        self.get_logger().info(
            f"Predictive Avoidance: {'Enabled' if self.avoidance_enabled else 'Disabled'}"
        )
        self.get_logger().info(
            f"Environmental Modeling: {'Enabled' if self.modeling_enabled else 'Disabled'}"
        )
        self.get_logger().info(f"Planning Frequency: {self.planning_freq} Hz")

    def odom_callback(self, msg):
        """Handle odometry updates"""
        self.current_pose = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            self._quaternion_to_yaw(msg.pose.pose.orientation),
        )

        self.current_velocity = (msg.twist.twist.linear.x, msg.twist.twist.angular.z)

        # Update environmental model
        if self.environmental_model:
            robot_state = (
                msg.pose.pose.position.x,
                msg.pose.pose.position.y,
                self.current_pose[2],
            )
            # In practice, this would update the model with the robot's movement

    def lidar_callback(self, msg):
        """Handle LIDAR scan data"""
        self.lidar_data = list(msg.ranges)

        # Update environmental model with LIDAR data
        if self.environmental_model:
            robot_pose = self.current_pose
            timestamp = time.time()
            self.environmental_model.update_with_lidar_scan(
                self.lidar_data, robot_pose, timestamp
            )

        # Update obstacle avoidance with detected obstacles
        if self.obstacle_avoidance:
            obstacles = self._lidar_to_obstacles(self.lidar_data)
            self.obstacle_avoidance.update_obstacles(obstacles)

    def imu_callback(self, msg):
        """Handle IMU data"""
        # Convert quaternion to Euler angles
        roll, pitch, yaw = self._quaternion_to_euler(msg.orientation)
        self.imu_data = (roll, pitch, yaw)

    def battery_callback(self, msg):
        """Handle battery state updates"""
        self.battery_level = msg.percentage

    def goal_callback(self, msg):
        """Handle goal pose updates"""
        self.goal_pose = (msg.pose.position.x, msg.pose.position.y)
        self.get_logger().info(
            f"New navigation goal received: ({self.goal_pose[0]:.2f}, {self.goal_pose[1]:.2f})"
        )

        # Trigger immediate path planning
        self.trigger_path_planning()

    def camera_features_callback(self, msg):
        """Handle camera feature detections"""
        try:
            features_data = json.loads(msg.data)
            self.camera_features = features_data.get("features", [])

            # Update environmental model with camera features
            if self.environmental_model:
                robot_pose = self.current_pose
                timestamp = time.time()
                self.environmental_model.update_with_camera_features(
                    self.camera_features, robot_pose, timestamp
                )

        except Exception as e:
            self.get_logger().warn(f"Failed to parse camera features: {e}")

    def thermal_callback(self, msg):
        """Handle thermal signature detections"""
        try:
            thermal_data = json.loads(msg.data)
            self.thermal_data = thermal_data.get("signatures", [])

            # Update environmental model with thermal data
            if self.environmental_model:
                robot_pose = self.current_pose
                timestamp = time.time()
                # Convert thermal signatures to format expected by environmental model
                thermal_array = self._thermal_signatures_to_array(self.thermal_data)
                self.environmental_model.update_with_thermal_data(
                    thermal_array, robot_pose, timestamp
                )

        except Exception as e:
            self.get_logger().warn(f"Failed to parse thermal data: {e}")

    def _quaternion_to_yaw(self, orientation) -> float:
        """Convert quaternion to yaw angle"""
        # Simplified conversion - would use tf2 in practice
        return 2.0 * math.atan2(orientation.z, orientation.w)

    def _quaternion_to_euler(self, orientation) -> Tuple[float, float, float]:
        """Convert quaternion to Euler angles"""
        # Simplified conversion
        roll = 0.0
        pitch = 0.0
        yaw = 2.0 * math.atan2(orientation.z, orientation.w)
        return (roll, pitch, yaw)

    def _lidar_to_obstacles(self, lidar_data: List[float]) -> List[Obstacle]:
        """Convert LIDAR data to obstacle list"""
        obstacles = []
        robot_x, robot_y, robot_theta = self.current_pose

        # Process LIDAR data to find obstacles
        for angle_idx, distance in enumerate(lidar_data):
            if 0.1 < distance < 5.0:  # Valid readings within 5m
                angle_rad = math.radians(angle_idx)
                global_angle = robot_theta + angle_rad

                # Calculate obstacle position
                obstacle_x = robot_x + distance * math.cos(global_angle)
                obstacle_y = robot_y + distance * math.sin(global_angle)

                # Create obstacle
                obstacle = Obstacle(
                    x=obstacle_x,
                    y=obstacle_y,
                    radius=0.15,  # Typical obstacle size
                    velocity_x=0.0,
                    velocity_y=0.0,
                    confidence=min(1.0, distance / 5.0),  # Closer = higher confidence
                    type="static",
                )
                obstacles.append(obstacle)

        return obstacles

    def _thermal_signatures_to_array(
        self, signatures: List[Dict[str, Any]]
    ) -> np.ndarray:
        """Convert thermal signatures to array for environmental model"""
        thermal_array = []

        for signature in signatures:
            # Convert normalized coordinates to relative coordinates
            center_x = signature.get("center_x", 0.5)
            center_y = signature.get("center_y", 0.5)
            temperature = signature.get("temperature", 30.0)

            # Convert to relative coordinates (simplified)
            rel_x = (center_x - 0.5) * 5.0  # Assume 5m field of view
            rel_y = (center_y - 0.5) * 5.0

            thermal_array.extend([rel_x, rel_y, temperature])

        return np.array(thermal_array, dtype=np.float32)

    def trigger_path_planning(self):
        """Trigger immediate path planning"""
        if self.goal_pose:
            self.planning_callback()

    def planning_callback(self):
        """Main planning callback"""
        if not self.goal_pose:
            return

        start_time = time.time()

        # Create navigation state
        nav_state = self._create_navigation_state()

        # Generate path using neural planner
        if self.neural_enabled and self.neural_planner and self.environmental_model:
            try:
                # Create environmental context
                context = self._create_environmental_context()

                # Generate path
                path_plan = self.neural_planner.generate_path(context)

                # Update statistics
                self.navigation_stats["plans_generated"] += 1
                self.navigation_stats["average_planning_time"] = (
                    self.navigation_stats["average_planning_time"] * 0.9
                    + (time.time() - start_time) * 0.1
                )

                # Publish path
                self.publish_path(path_plan)

                # Execute path (simplified - would use more sophisticated control)
                self.execute_path(path_plan)

                self.get_logger().debug(
                    f"Neural path generated with {len(path_plan.path_points)} points"
                )

            except Exception as e:
                self.get_logger().error(f"Neural path planning failed: {e}")

        # Use RL agents for decision making
        if self.rl_enabled and self.rl_agent:
            try:
                # Get action from RL agent
                action = self.rl_agent.act(nav_state)

                # Convert action to velocity commands
                if self.actor_critic_agent:
                    linear_vel, angular_vel = self.actor_critic_agent.act(nav_state)
                else:
                    # Simple discrete action mapping
                    action_map = {
                        0: (0.3, 0.0),  # Forward
                        1: (0.0, 0.5),  # Left turn
                        2: (0.0, -0.5),  # Right turn
                        3: (0.0, 0.0),  # Stop
                        4: (-0.2, 0.0),  # Backward
                        5: (0.2, 0.3),  # Forward-left
                        6: (0.2, -0.3),  # Forward-right
                        7: (-0.1, 0.4),  # Backward-left
                        8: (-0.1, -0.4),  # Backward-right
                    }
                    linear_vel, angular_vel = action_map.get(action, (0.0, 0.0))

                # Send velocity command
                self.send_velocity_command(linear_vel, angular_vel)

                self.navigation_stats["rl_episodes"] += 1

            except Exception as e:
                self.get_logger().error(f"RL navigation failed: {e}")

        # Assess collision risk
        if self.avoidance_enabled and self.obstacle_avoidance:
            try:
                # Update robot state
                robot_state = RobotState(
                    x=self.current_pose[0],
                    y=self.current_pose[1],
                    theta=self.current_pose[2],
                    linear_velocity=self.current_velocity[0],
                    angular_velocity=self.current_velocity[1],
                    battery_level=self.battery_level,
                    timestamp=time.time(),
                )
                self.obstacle_avoidance.update_robot_state(robot_state)

                # Assess risk
                risk_assessment = self.obstacle_avoidance.assess_collision_risk()

                # Publish risk assessment
                self.publish_risk_assessment(risk_assessment)

                # Take avoidance action if needed
                if risk_assessment.collision_probability > 0.3:  # High risk threshold
                    linear_vel, angular_vel = (
                        self.obstacle_avoidance.execute_avoidance_action(
                            risk_assessment
                        )
                    )
                    self.send_velocity_command(linear_vel, angular_vel)
                    self.get_logger().info("Executing collision avoidance maneuver")

            except Exception as e:
                self.get_logger().error(f"Collision avoidance failed: {e}")

        # Update environmental model
        if self.modeling_enabled and self.environmental_model:
            try:
                # Learn from experience
                self.environmental_model.learn_from_experience()
                self.navigation_stats["model_updates"] += 1

            except Exception as e:
                self.get_logger().error(f"Environmental modeling failed: {e}")

    def _create_navigation_state(self) -> NavigationState:
        """Create navigation state for RL agents"""
        return NavigationState(
            x=self.current_pose[0],
            y=self.current_pose[1],
            theta=self.current_pose[2],
            lidar_scan=self.lidar_data,
            ultrasonic_readings=[0.0] * 4,  # Would subscribe to ultrasonic data
            imu_orientation=self.imu_data,
            camera_features=None,  # Would convert camera features
            thermal_data=None,  # Would convert thermal data
            goal_x=self.goal_pose[0] if self.goal_pose else 0.0,
            goal_y=self.goal_pose[1] if self.goal_pose else 0.0,
            battery_level=self.battery_level,
            time_since_start=time.time(),
            recent_collisions=0,  # Would track actual collisions
        )

    def _create_environmental_context(self) -> EnvironmentalContext:
        """Create environmental context for neural planner"""
        # Get occupancy grid from environmental model
        occupancy_grid = None
        temperature_map = None
        feature_map = {}
        dynamic_obstacles = []

        if self.environmental_model:
            # Simplified - would extract actual grid data
            occupancy_grid = np.zeros((200, 200))  # 20m x 20m with 0.1m resolution
            temperature_map = np.full((200, 200), 22.0)  # Base temperature

            # Convert dynamic obstacles
            for feature_id, feature in self.environmental_model.features.items():
                if feature.type == "dynamic_obstacle":
                    dynamic_obstacles.append(
                        (feature.x, feature.y, 0.0, 0.0)
                    )  # Simplified

        return EnvironmentalContext(
            occupancy_grid=occupancy_grid,
            temperature_map=temperature_map,
            feature_map=feature_map,
            dynamic_obstacles=dynamic_obstacles,
            goal_position=self.goal_pose if self.goal_pose else (0.0, 0.0),
            robot_position=self.current_pose,
        )

    def publish_path(self, path_plan: NeuralPathPlan):
        """Publish planned path"""
        if not path_plan.path_points:
            return

        # Create ROS2 Path message
        path_msg = Path()
        path_msg.header.stamp = self.get_clock().now().to_msg()
        path_msg.header.frame_id = "map"

        for point in path_plan.path_points:
            pose_stamped = PoseStamped()
            pose_stamped.header.stamp = path_msg.header.stamp
            pose_stamped.header.frame_id = path_msg.header.frame_id
            pose_stamped.pose.position.x = point.x
            pose_stamped.pose.position.y = point.y
            pose_stamped.pose.position.z = 0.0

            # Set orientation (simplified - would use actual theta)
            pose_stamped.pose.orientation.w = 1.0

            path_msg.poses.append(pose_stamped)

        self.planned_path_publisher.publish(path_msg)

        # Publish visualization markers
        self.publish_path_markers(path_plan)

    def publish_path_markers(self, path_plan: NeuralPathPlan):
        """Publish path visualization markers"""
        marker_array = MarkerArray()

        # Path line marker
        line_marker = Marker()
        line_marker.header.stamp = self.get_clock().now().to_msg()
        line_marker.header.frame_id = "map"
        line_marker.ns = "planned_path"
        line_marker.id = 0
        line_marker.type = Marker.LINE_STRIP
        line_marker.action = Marker.ADD
        line_marker.pose.orientation.w = 1.0
        line_marker.scale.x = 0.05  # Line width
        line_marker.color.r = 0.0
        line_marker.color.g = 1.0  # Green path
        line_marker.color.b = 0.0
        line_marker.color.a = 1.0

        # Add path points
        for point in path_plan.path_points:
            p = Point()
            p.x = point.x
            p.y = point.y
            p.z = 0.1  # Slightly above ground
            line_marker.points.append(p)

        marker_array.markers.append(line_marker)

        # Waypoint markers
        for i, point in enumerate(path_plan.path_points):
            waypoint_marker = Marker()
            waypoint_marker.header.stamp = self.get_clock().now().to_msg()
            waypoint_marker.header.frame_id = "map"
            waypoint_marker.ns = "path_waypoints"
            waypoint_marker.id = i + 1
            waypoint_marker.type = Marker.SPHERE
            waypoint_marker.action = Marker.ADD
            waypoint_marker.pose.position.x = point.x
            waypoint_marker.pose.position.y = point.y
            waypoint_marker.pose.position.z = 0.1
            waypoint_marker.pose.orientation.w = 1.0
            waypoint_marker.scale.x = 0.1
            waypoint_marker.scale.y = 0.1
            waypoint_marker.scale.z = 0.1
            waypoint_marker.color.r = 1.0  # Red waypoints
            waypoint_marker.color.g = 0.5
            waypoint_marker.color.b = 0.0
            waypoint_marker.color.a = 1.0
            marker_array.markers.append(waypoint_marker)

        self.navigation_markers_publisher.publish(marker_array)

    def execute_path(self, path_plan: NeuralPathPlan):
        """Execute planned path (simplified control)"""
        if not path_plan.path_points:
            return

        # For now, just send command to move toward first waypoint
        if path_plan.path_points:
            first_point = path_plan.path_points[0]
            robot_x, robot_y, robot_theta = self.current_pose

            # Calculate direction to waypoint
            dx = first_point.x - robot_x
            dy = first_point.y - robot_y
            distance = math.sqrt(dx * dx + dy * dy)

            if distance > 0.1:  # Not at waypoint yet
                target_angle = math.atan2(dy, dx)
                angle_diff = target_angle - robot_theta

                # Normalize angle difference
                while angle_diff > math.pi:
                    angle_diff -= 2 * math.pi
                while angle_diff < -math.pi:
                    angle_diff += 2 * math.pi

                # Simple proportional control
                linear_vel = min(0.3, distance * 0.5)  # Proportional to distance
                angular_vel = max(
                    -1.0, min(1.0, angle_diff * 2.0)
                )  # Proportional to angle error

                self.send_velocity_command(linear_vel, angular_vel)
            else:
                # At waypoint, send stop command
                self.send_velocity_command(0.0, 0.0)

    def send_velocity_command(self, linear_vel: float, angular_vel: float):
        """Send velocity command to robot"""
        twist_msg = Twist()
        twist_msg.linear.x = float(linear_vel)
        twist_msg.angular.z = float(angular_vel)
        self.cmd_vel_publisher.publish(twist_msg)

    def publish_risk_assessment(self, risk_assessment: RiskAssessment):
        """Publish risk assessment"""
        risk_msg = String()
        risk_msg.data = json.dumps(
            {
                "collision_probability": risk_assessment.collision_probability,
                "time_to_collision": risk_assessment.time_to_collision,
                "risk_level": risk_assessment.risk_level,
                "recommended_action": risk_assessment.recommended_action,
                "collision_point": risk_assessment.collision_point,
                "collision_time": risk_assessment.collision_time,
                "timestamp": time.time(),
            }
        )
        self.risk_assessment_publisher.publish(risk_msg)

    def publish_statistics(self):
        """Publish navigation statistics"""
        stats_msg = String()
        stats_msg.data = json.dumps(self.navigation_stats)
        self.navigation_stats_publisher.publish(stats_msg)

        # Log periodic stats
        self.get_logger().info(
            f"Navigation Stats - Plans: {self.navigation_stats['plans_generated']}, "
            f"Success Rate: {self.navigation_stats['successful_navigations']}, "
            f"Avg Time: {self.navigation_stats['average_planning_time']:.3f}s"
        )

    def destroy_node(self):
        """Clean up node resources"""
        # Save learned models if needed
        if self.rl_agent:
            # In a real implementation, this would save the model
            pass

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = AdvancedNavigationNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
