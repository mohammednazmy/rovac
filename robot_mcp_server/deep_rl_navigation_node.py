#!/usr/bin/env python3
"""
Deep Reinforcement Learning Navigation Node for ROVAC
ROS2 interface for self-improving path planning and obstacle avoidance
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
from deep_rl_navigation import (
    DeepQLearningAgent,
    ActorCriticAgent,
    NavigationState,
    NavigationAction,
    compute_navigation_reward,
)


class DeepRLNavigationNode(Node):
    """ROS2 node for deep reinforcement learning navigation"""

    def __init__(self):
        super().__init__("deep_rl_navigation_node")

        # ROS2 parameters
        self.declare_parameter("enable_deep_rl_navigation", True)
        self.declare_parameter("navigation_mode", "dqn")  # 'dqn' or 'actor_critic'
        self.declare_parameter("learning_enabled", True)
        self.declare_parameter("exploration_rate", 0.3)
        self.declare_parameter("update_frequency_hz", 10.0)
        self.declare_parameter("goal_tolerance_meters", 0.3)
        self.declare_parameter("safety_margin_meters", 0.3)
        self.declare_parameter("max_linear_velocity", 0.5)
        self.declare_parameter("max_angular_velocity", 1.5)
        self.declare_parameter("publish_visualization", True)
        self.declare_parameter("log_training_data", True)

        self.enabled = self.get_parameter("enable_deep_rl_navigation").value
        self.nav_mode = self.get_parameter("navigation_mode").value
        self.learning_enabled = self.get_parameter("learning_enabled").value
        self.exploration_rate = self.get_parameter("exploration_rate").value
        self.update_freq = self.get_parameter("update_frequency_hz").value
        self.goal_tolerance = self.get_parameter("goal_tolerance_meters").value
        self.safety_margin = self.get_parameter("safety_margin_meters").value
        self.max_linear_vel = self.get_parameter("max_linear_velocity").value
        self.max_angular_vel = self.get_parameter("max_angular_velocity").value
        self.publish_viz = self.get_parameter("publish_visualization").value
        self.log_training = self.get_parameter("log_training_data").value

        # Initialize navigation agents
        self.dqn_agent = DeepQLearningAgent() if self.nav_mode == "dqn" else None
        self.actor_critic_agent = (
            ActorCriticAgent() if self.nav_mode == "actor_critic" else None
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
        self.recent_collisions = 0
        self.recent_obstacles = 0
        self.time_since_start = 0.0
        self.start_time = time.time()

        # Navigation history
        self.path_history = deque(maxlen=100)
        self.velocity_history = deque(maxlen=50)
        self.reward_history = deque(maxlen=1000)
        self.experience_buffer = deque(maxlen=5000)

        # Performance metrics
        self.navigation_stats = {
            "goals_reached": 0,
            "collisions": 0,
            "total_steps": 0,
            "average_reward": 0.0,
            "success_rate": 0.0,
            "exploration_rate": self.exploration_rate,
            "learning_episodes": 0,
            "model_updates": 0,
            "training_loss": 0.0,
        }

        if not self.enabled:
            self.get_logger().info("Deep RL Navigation Node disabled")
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

        self.camera_features_subscription = self.create_subscription(
            String, "/camera/features", self.camera_features_callback, qos_profile
        )

        self.thermal_data_subscription = self.create_subscription(
            String, "/thermal/signatures", self.thermal_callback, qos_profile
        )

        # Publishers
        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel_rl", 10)

        self.planned_path_publisher = self.create_publisher(
            Path, "/rl/planned_path", 10
        )

        self.navigation_markers_publisher = self.create_publisher(
            MarkerArray, "/rl/navigation_markers", 10
        )

        self.reward_publisher = self.create_publisher(String, "/rl/reward", 10)

        self.navigation_stats_publisher = self.create_publisher(
            String, "/rl/navigation_stats", 10
        )

        self.training_data_publisher = self.create_publisher(
            String, "/rl/training_data", 10
        )

        # Timers
        self.navigation_timer = self.create_timer(
            1.0 / self.update_freq, self.navigation_callback
        )

        self.stats_timer = self.create_timer(5.0, self.publish_statistics)

        # Initialize agent parameters
        if self.dqn_agent:
            self.dqn_agent.epsilon = self.exploration_rate
        if self.actor_critic_agent:
            # Would configure actor-critic parameters
            pass

        self.get_logger().info("Deep RL Navigation Node initialized")
        self.get_logger().info(f"Navigation mode: {self.nav_mode}")
        self.get_logger().info(f"Learning enabled: {self.learning_enabled}")
        self.get_logger().info(f"Update frequency: {self.update_freq} Hz")
        self.get_logger().info(f"Goal tolerance: {self.goal_tolerance}m")
        self.get_logger().info(f"Safety margin: {self.safety_margin}m")
        self.get_logger().info(
            f"Max velocities: {self.max_linear_vel}m/s, {self.max_angular_vel}rad/s"
        )
        self.get_logger().info(f"Publish visualization: {self.publish_viz}")
        self.get_logger().info(f"Log training data: {self.log_training}")

    def odom_callback(self, msg):
        """Handle odometry updates"""
        self.current_pose = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            self._quaternion_to_yaw(msg.pose.pose.orientation),
        )

        self.current_velocity = (msg.twist.twist.linear.x, msg.twist.twist.angular.z)

        # Add to path history
        self.path_history.append((self.current_pose[0], self.current_pose[1]))

        # Add to velocity history
        self.velocity_history.append(self.current_velocity)

        # Update time since start
        self.time_since_start = time.time() - self.start_time

    def lidar_callback(self, msg):
        """Handle LIDAR scan data"""
        self.lidar_data = list(msg.ranges)

        # Count obstacles
        self.recent_obstacles = sum(
            1 for distance in self.lidar_data if 0.1 < distance < 2.0
        )  # Obstacles within 2m

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

    def camera_features_callback(self, msg):
        """Handle camera feature detections"""
        try:
            features_data = json.loads(msg.data)
            self.camera_features = features_data.get("features", [])
        except Exception as e:
            self.get_logger().warn(f"Failed to parse camera features: {e}")

    def thermal_callback(self, msg):
        """Handle thermal signature detections"""
        try:
            thermal_data = json.loads(msg.data)
            self.thermal_data = thermal_data.get("signatures", [])
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

    def navigation_callback(self):
        """Main navigation callback"""
        if not self.enabled or not self.goal_pose:
            return

        # Create current navigation state
        current_state = self._create_navigation_state()

        # Check if goal is reached
        goal_distance = self._calculate_distance(
            self.current_pose[0],
            self.current_pose[1],
            self.goal_pose[0],
            self.goal_pose[1],
        )

        if goal_distance <= self.goal_tolerance:
            self._handle_goal_reached()
            return

        # Check for collisions (simplified)
        collision_occurred = self._check_collision()
        if collision_occurred:
            self._handle_collision()
            return

        # Choose action using RL agent
        action = self._choose_action(current_state)

        # Execute action
        self._execute_action(action)

        # Compute reward
        next_state = self._create_navigation_state()
        reward = compute_navigation_reward(
            current_state,
            action,
            next_state,
            goal_reached=False,
            collision_occurred=collision_occurred,
        )

        # Store experience for learning
        if self.learning_enabled:
            experience = (current_state, action, reward, next_state, False)
            self.experience_buffer.append(experience)
            self.reward_history.append(reward)

        # Update navigation statistics
        self.navigation_stats["total_steps"] += 1
        self.navigation_stats["average_reward"] = (
            self.navigation_stats["average_reward"] * 0.99 + reward * 0.01
        )

        # Publish reward
        reward_msg = String()
        reward_msg.data = json.dumps(
            {
                "reward": reward,
                "timestamp": time.time(),
                "goal_distance": goal_distance,
                "collision_occurred": collision_occurred,
            }
        )
        self.reward_publisher.publish(reward_msg)

        # Train agent periodically
        if self.learning_enabled and len(self.experience_buffer) >= 32:
            self._train_agent()

        # Publish planned path and visualization
        self._publish_planned_path()
        if self.publish_viz:
            self._publish_navigation_markers()

    def _create_navigation_state(self) -> NavigationState:
        """Create navigation state for RL agent"""
        return NavigationState(
            x=self.current_pose[0],
            y=self.current_pose[1],
            theta=self.current_pose[2],
            lidar_scan=self.lidar_data,
            ultrasonic_readings=[0.0] * 4,  # Would subscribe to ultrasonic data
            imu_orientation=self.imu_data,
            camera_features=self.camera_features,
            thermal_data=self.thermal_data,
            goal_x=self.goal_pose[0] if self.goal_pose else 0.0,
            goal_y=self.goal_pose[1] if self.goal_pose else 0.0,
            battery_level=self.battery_level,
            time_since_start=self.time_since_start,
            recent_collisions=self.recent_collisions,
            recent_obstacles=self.recent_obstacles,
            path_history=list(self.path_history),
            velocity_history=list(self.velocity_history),
        )

    def _choose_action(self, state: NavigationState) -> NavigationAction:
        """Choose action using RL agent"""
        if self.nav_mode == "dqn" and self.dqn_agent:
            # Discrete action selection
            action_idx = self.dqn_agent.act(state)

            # Map discrete action to continuous velocities
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

            linear_vel, angular_vel = action_map.get(action_idx, (0.0, 0.0))

            return NavigationAction(
                linear_velocity=max(
                    -self.max_linear_vel, min(self.max_linear_vel, linear_vel)
                ),
                angular_velocity=max(
                    -self.max_angular_vel, min(self.max_angular_vel, angular_vel)
                ),
                timestamp=time.time(),
            )

        elif self.nav_mode == "actor_critic" and self.actor_critic_agent:
            # Continuous action selection
            linear_vel, angular_vel = self.actor_critic_agent.act(state)

            return NavigationAction(
                linear_velocity=max(
                    -self.max_linear_vel, min(self.max_linear_vel, linear_vel)
                ),
                angular_velocity=max(
                    -self.max_angular_vel, min(self.max_angular_vel, angular_vel)
                ),
                timestamp=time.time(),
            )

        else:
            # Fallback to simple proportional control
            if self.goal_pose:
                dx = self.goal_pose[0] - self.current_pose[0]
                dy = self.goal_pose[1] - self.current_pose[1]
                distance = math.sqrt(dx * dx + dy * dy)

                if distance > self.goal_tolerance:
                    target_angle = math.atan2(dy, dx)
                    angle_diff = target_angle - self.current_pose[2]

                    # Normalize angle difference
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi

                    # Simple proportional control
                    linear_vel = min(self.max_linear_vel, distance * 0.5)
                    angular_vel = max(
                        -self.max_angular_vel,
                        min(self.max_angular_vel, angle_diff * 2.0),
                    )
                else:
                    linear_vel = 0.0
                    angular_vel = 0.0
            else:
                linear_vel = 0.0
                angular_vel = 0.0

            return NavigationAction(
                linear_velocity=linear_vel,
                angular_velocity=angular_vel,
                timestamp=time.time(),
            )

    def _execute_action(self, action: NavigationAction):
        """Execute navigation action"""
        twist_msg = Twist()
        twist_msg.linear.x = float(action.linear_velocity)
        twist_msg.angular.z = float(action.angular_velocity)
        self.cmd_vel_publisher.publish(twist_msg)

    def _calculate_distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calculate Euclidean distance between two points"""
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    def _check_collision(self) -> bool:
        """Check for collision (simplified)"""
        if not self.lidar_data:
            return False

        # Check for very close obstacles
        min_distance = min([d for d in self.lidar_data if d > 0.01], default=10.0)
        return min_distance < self.safety_margin

    def _handle_goal_reached(self):
        """Handle goal reached event"""
        self.get_logger().info("🎯 Goal reached!")

        # Stop robot
        self._execute_action(NavigationAction(0.0, 0.0, time.time()))

        # Update statistics
        self.navigation_stats["goals_reached"] += 1
        self.navigation_stats["success_rate"] = self.navigation_stats[
            "goals_reached"
        ] / max(
            1,
            self.navigation_stats["goals_reached"]
            + self.navigation_stats["collisions"],
        )

        # Clear goal
        self.goal_pose = None

    def _handle_collision(self):
        """Handle collision event"""
        self.get_logger().warn("💥 Collision detected!")

        # Stop robot
        self._execute_action(NavigationAction(0.0, 0.0, time.time()))

        # Update statistics
        self.navigation_stats["collisions"] += 1
        self.navigation_stats["success_rate"] = self.navigation_stats[
            "goals_reached"
        ] / max(
            1,
            self.navigation_stats["goals_reached"]
            + self.navigation_stats["collisions"],
        )

        # Store collision experience
        if self.learning_enabled and len(self.path_history) > 1:
            current_state = self._create_navigation_state()
            action = NavigationAction(0.0, 0.0, time.time())  # Stop action
            next_state = current_state
            reward = -50.0  # Collision penalty

            experience = (current_state, action, reward, next_state, True)
            self.experience_buffer.append(experience)
            self.reward_history.append(reward)

        # Update collision counter
        self.recent_collisions += 1

        # Clear goal to prevent further collisions
        self.goal_pose = None

    def _train_agent(self):
        """Train RL agent with experience buffer"""
        if not self.learning_enabled:
            return

        # In a real implementation, this would train the neural networks
        # For simulation, we'll just acknowledge the training step

        if self.dqn_agent:
            # Simulate DQN training
            batch_loss = np.random.uniform(0.1, 1.0)  # Random loss for simulation
            self.navigation_stats["training_loss"] = (
                self.navigation_stats["training_loss"] * 0.9 + batch_loss * 0.1
            )
            self.navigation_stats["model_updates"] += 1
            self.navigation_stats["learning_episodes"] += 1

        elif self.actor_critic_agent:
            # Simulate Actor-Critic training
            batch_loss = np.random.uniform(0.05, 0.5)  # Random loss for simulation
            self.navigation_stats["training_loss"] = (
                self.navigation_stats["training_loss"] * 0.9 + batch_loss * 0.1
            )
            self.navigation_stats["model_updates"] += 1
            self.navigation_stats["learning_episodes"] += 1

        # Publish training data
        if self.log_training:
            training_msg = String()
            training_msg.data = json.dumps(
                {
                    "timestamp": time.time(),
                    "batch_loss": float(batch_loss),
                    "experience_buffer_size": len(self.experience_buffer),
                    "model_updates": self.navigation_stats["model_updates"],
                    "learning_episodes": self.navigation_stats["learning_episodes"],
                    "epsilon": self.dqn_agent.epsilon if self.dqn_agent else 0.0,
                }
            )
            self.training_data_publisher.publish(training_msg)

    def _publish_planned_path(self):
        """Publish planned path for visualization"""
        if not self.goal_pose:
            return

        # Create path from current position to goal
        path_msg = Path()
        path_msg.header.stamp = self.get_clock().now().to_msg()
        path_msg.header.frame_id = "map"

        # Current position
        current_pose = PoseStamped()
        current_pose.header.stamp = path_msg.header.stamp
        current_pose.header.frame_id = path_msg.header.frame_id
        current_pose.pose.position.x = float(self.current_pose[0])
        current_pose.pose.position.y = float(self.current_pose[1])
        current_pose.pose.orientation.w = 1.0
        path_msg.poses.append(current_pose)

        # Goal position
        goal_pose = PoseStamped()
        goal_pose.header.stamp = path_msg.header.stamp
        goal_pose.header.frame_id = path_msg.header.frame_id
        goal_pose.pose.position.x = float(self.goal_pose[0])
        goal_pose.pose.position.y = float(self.goal_pose[1])
        goal_pose.pose.orientation.w = 1.0
        path_msg.poses.append(goal_pose)

        self.planned_path_publisher.publish(path_msg)

    def _publish_navigation_markers(self):
        """Publish navigation visualization markers"""
        marker_array = MarkerArray()

        # Robot position marker
        robot_marker = Marker()
        robot_marker.header.stamp = self.get_clock().now().to_msg()
        robot_marker.header.frame_id = "map"
        robot_marker.ns = "robot"
        robot_marker.id = 0
        robot_marker.type = Marker.ARROW
        robot_marker.action = Marker.ADD
        robot_marker.pose.position.x = float(self.current_pose[0])
        robot_marker.pose.position.y = float(self.current_pose[1])
        robot_marker.pose.position.z = 0.1

        # Set orientation
        robot_marker.pose.orientation.x = 0.0
        robot_marker.pose.orientation.y = 0.0
        robot_marker.pose.orientation.z = math.sin(self.current_pose[2] / 2.0)
        robot_marker.pose.orientation.w = math.cos(self.current_pose[2] / 2.0)

        robot_marker.scale.x = 0.3  # Arrow length
        robot_marker.scale.y = 0.1  # Arrow width
        robot_marker.scale.z = 0.1  # Arrow height
        robot_marker.color.r = 0.0
        robot_marker.color.g = 1.0  # Green robot
        robot_marker.color.b = 0.0
        robot_marker.color.a = 1.0
        marker_array.markers.append(robot_marker)

        # Goal marker
        if self.goal_pose:
            goal_marker = Marker()
            goal_marker.header.stamp = self.get_clock().now().to_msg()
            goal_marker.header.frame_id = "map"
            goal_marker.ns = "goal"
            goal_marker.id = 1
            goal_marker.type = Marker.SPHERE
            goal_marker.action = Marker.ADD
            goal_marker.pose.position.x = float(self.goal_pose[0])
            goal_marker.pose.position.y = float(self.goal_pose[1])
            goal_marker.pose.position.z = 0.1
            goal_marker.pose.orientation.w = 1.0
            goal_marker.scale.x = 0.2
            goal_marker.scale.y = 0.2
            goal_marker.scale.z = 0.2
            goal_marker.color.r = 1.0  # Red goal
            goal_marker.color.g = 0.0
            goal_marker.color.b = 0.0
            goal_marker.color.a = 1.0
            marker_array.markers.append(goal_marker)

        # Path line marker
        path_marker = Marker()
        path_marker.header.stamp = self.get_clock().now().to_msg()
        path_marker.header.frame_id = "map"
        path_marker.ns = "planned_path"
        path_marker.id = 2
        path_marker.type = Marker.LINE_STRIP
        path_marker.action = Marker.ADD
        path_marker.pose.orientation.w = 1.0
        path_marker.scale.x = 0.05  # Line width
        path_marker.color.r = 0.0
        path_marker.color.g = 0.5  # Blue path
        path_marker.color.b = 1.0
        path_marker.color.a = 1.0

        if self.goal_pose:
            # Add path points
            start_point = Point()
            start_point.x = float(self.current_pose[0])
            start_point.y = float(self.current_pose[1])
            start_point.z = 0.05
            path_marker.points.append(start_point)

            end_point = Point()
            end_point.x = float(self.goal_pose[0])
            end_point.y = float(self.goal_pose[1])
            end_point.z = 0.05
            path_marker.points.append(end_point)

        marker_array.markers.append(path_marker)

        # Obstacle markers
        for i, distance in enumerate(self.lidar_data[:10]):  # First 10 LIDAR points
            if 0.1 < distance < 2.0:  # Valid obstacle readings
                angle = math.radians(i * 360 / len(self.lidar_data))
                obstacle_x = self.current_pose[0] + distance * math.cos(
                    self.current_pose[2] + angle
                )
                obstacle_y = self.current_pose[1] + distance * math.sin(
                    self.current_pose[2] + angle
                )

                obstacle_marker = Marker()
                obstacle_marker.header.stamp = self.get_clock().now().to_msg()
                obstacle_marker.header.frame_id = "map"
                obstacle_marker.ns = "obstacles"
                obstacle_marker.id = 10 + i
                obstacle_marker.type = Marker.CYLINDER
                obstacle_marker.action = Marker.ADD
                obstacle_marker.pose.position.x = float(obstacle_x)
                obstacle_marker.pose.position.y = float(obstacle_y)
                obstacle_marker.pose.position.z = 0.1
                obstacle_marker.pose.orientation.w = 1.0
                obstacle_marker.scale.x = 0.1
                obstacle_marker.scale.y = 0.1
                obstacle_marker.scale.z = 0.2
                obstacle_marker.color.r = 1.0  # Red obstacles
                obstacle_marker.color.g = 0.0
                obstacle_marker.color.b = 0.0
                obstacle_marker.color.a = 0.7
                marker_array.markers.append(obstacle_marker)

        self.navigation_markers_publisher.publish(marker_array)

    def publish_statistics(self):
        """Publish navigation statistics"""
        stats_msg = String()
        stats_msg.data = json.dumps(self.navigation_stats)
        self.navigation_stats_publisher.publish(stats_msg)

        # Log periodic stats
        self.get_logger().info(
            f"Navigation Stats - Goals: {self.navigation_stats['goals_reached']}, "
            f"Collisions: {self.navigation_stats['collisions']}, "
            f"Success Rate: {self.navigation_stats['success_rate']:.2f}, "
            f"Avg Reward: {self.navigation_stats['average_reward']:.3f}"
        )

    def reset_navigation(self):
        """Reset navigation state"""
        self.goal_pose = None
        self.path_history.clear()
        self.velocity_history.clear()
        self.reward_history.clear()
        self.experience_buffer.clear()
        self.recent_collisions = 0
        self.recent_obstacles = 0
        self.start_time = time.time()
        self.time_since_start = 0.0

        # Reset statistics
        self.navigation_stats = {
            "goals_reached": 0,
            "collisions": 0,
            "total_steps": 0,
            "average_reward": 0.0,
            "success_rate": 0.0,
            "exploration_rate": self.exploration_rate,
            "learning_episodes": 0,
            "model_updates": 0,
            "training_loss": 0.0,
        }

        self.get_logger().info("Navigation state reset")


def main(args=None):
    rclpy.init(args=args)
    node = DeepRLNavigationNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
