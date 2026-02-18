#!/usr/bin/env python3
"""
Deep Learning Path Planning Node for ROVAC
ROS2 interface for neural network-based navigation
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped, Twist, Point
from sensor_msgs.msg import LaserScan, Imu
from nav_msgs.msg import Path, OccupancyGrid
from visualization_msgs.msg import Marker, MarkerArray
import json
import time
from dl_path_planning import NeuralPathPlanner, EnvironmentState


class DLPathPlanningNode(Node):
    """ROS2 node for deep learning path planning"""

    def __init__(self):
        super().__init__("dl_path_planning_node")

        # ROS2 parameters
        self.declare_parameter("enable_dl_planning", True)
        self.declare_parameter("model_path", "")
        self.declare_parameter("publish_visualization", True)
        self.declare_parameter("update_rate_hz", 1.0)

        self.enabled = self.get_parameter("enable_dl_planning").value
        self.model_path = self.get_parameter("model_path").value
        self.publish_viz = self.get_parameter("publish_visualization").value
        self.update_rate = self.get_parameter("update_rate_hz").value

        # State variables
        self.current_pose = (0.0, 0.0, 0.0)  # x, y, theta
        self.goal_pose = None
        self.lidar_data = []
        self.imu_data = (0.0, 0.0, 0.0)  # roll, pitch, yaw
        self.battery_level = 100.0
        self.obstacles = []

        # Initialize path planner
        self.path_planner = NeuralPathPlanner(model_path=self.model_path)

        # Simulate training (in reality would load pre-trained model)
        self.path_planner.simulate_training(epochs=10)

        # Subscriptions
        self.lidar_subscription = self.create_subscription(
            LaserScan, "/scan", self.lidar_callback, 10
        )

        self.imu_subscription = self.create_subscription(
            Imu, "/sensors/imu", self.imu_callback, 10
        )

        self.goal_subscription = self.create_subscription(
            PoseStamped, "/goal_pose", self.goal_callback, 10
        )

        self.battery_subscription = self.create_subscription(
            String, "/system/battery_status", self.battery_callback, 10
        )

        # Publishers
        self.path_publisher = self.create_publisher(Path, "/dl/planned_path", 10)

        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel_dl", 10)

        self.visualization_publisher = self.create_publisher(
            MarkerArray, "/dl/path_visualization", 10
        )

        self.metrics_publisher = self.create_publisher(
            String, "/dl/performance_metrics", 10
        )

        # Timer for path planning updates
        self.timer = self.create_timer(1.0 / self.update_rate, self.plan_path_callback)

        self.get_logger().info("Deep Learning Path Planning Node initialized")
        self.get_logger().info(f"Update rate: {self.update_rate} Hz")
        self.get_logger().info(
            f"Visualization: {'Enabled' if self.publish_viz else 'Disabled'}"
        )

    def lidar_callback(self, msg):
        """Handle LIDAR scan data"""
        self.lidar_data = list(msg.ranges)

    def imu_callback(self, msg):
        """Handle IMU data"""
        # Extract orientation (simplified)
        orientation = msg.orientation
        # In a real implementation, would convert quaternion to Euler angles
        self.imu_data = (0.0, 0.0, 0.0)  # Placeholder

    def goal_callback(self, msg):
        """Handle goal pose updates"""
        self.goal_pose = (msg.pose.position.x, msg.pose.position.y)
        self.get_logger().info(
            f"New goal received: ({self.goal_pose[0]:.2f}, {self.goal_pose[1]:.2f})"
        )

    def battery_callback(self, msg):
        """Handle battery status updates"""
        try:
            data = json.loads(msg.data)
            self.battery_level = data.get("level", 100.0)
        except:
            pass

    def plan_path_callback(self):
        """Generate path using deep learning model"""
        if not self.enabled or not self.goal_pose:
            return

        # Create environment state
        env_state = EnvironmentState(
            lidar_data=self.lidar_data,
            ultrasonic_data=[],  # Would subscribe to ultrasonic data
            imu_orientation=self.imu_data,
            current_pose=self.current_pose,
            goal_pose=self.goal_pose,
            obstacles=self.obstacles,
            battery_level=self.battery_level,
        )

        # Generate path
        try:
            path_points = self.path_planner.generate_path(env_state)

            # Publish path
            self.publish_path(path_points)

            # Publish visualization
            if self.publish_viz:
                self.publish_visualization(path_points)

            # Publish performance metrics
            metrics = self.path_planner.get_performance_metrics()
            self.publish_metrics(metrics)

            self.get_logger().debug(f"Generated path with {len(path_points)} points")

        except Exception as e:
            self.get_logger().error(f"Path planning failed: {e}")

    def publish_path(self, path_points):
        """Publish planned path as ROS2 Path message"""
        path_msg = Path()
        path_msg.header.stamp = self.get_clock().now().to_msg()
        path_msg.header.frame_id = "map"

        for point in path_points:
            pose = PoseStamped()
            pose.header.stamp = path_msg.header.stamp
            pose.header.frame_id = path_msg.header.frame_id
            pose.pose.position.x = point.x
            pose.pose.position.y = point.y
            pose.pose.position.z = 0.0
            # In a real implementation, would set orientation based on theta
            path_msg.poses.append(pose)

        self.path_publisher.publish(path_msg)

    def publish_visualization(self, path_points):
        """Publish path visualization markers"""
        marker_array = MarkerArray()

        # Path line marker
        line_marker = Marker()
        line_marker.header.stamp = self.get_clock().now().to_msg()
        line_marker.header.frame_id = "map"
        line_marker.ns = "dl_path"
        line_marker.id = 0
        line_marker.type = Marker.LINE_STRIP
        line_marker.action = Marker.ADD
        line_marker.pose.orientation.w = 1.0
        line_marker.scale.x = 0.05  # Line width
        line_marker.color.r = 0.0
        line_marker.color.g = 1.0
        line_marker.color.b = 0.0
        line_marker.color.a = 1.0

        for point in path_points:
            p = Point()
            p.x = point.x
            p.y = point.y
            p.z = 0.1  # Slightly above ground
            line_marker.points.append(p)

        marker_array.markers.append(line_marker)

        # Path point markers
        for i, point in enumerate(path_points):
            point_marker = Marker()
            point_marker.header.stamp = self.get_clock().now().to_msg()
            point_marker.header.frame_id = "map"
            point_marker.ns = "dl_path_points"
            point_marker.id = i + 1
            point_marker.type = Marker.SPHERE
            point_marker.action = Marker.ADD
            point_marker.pose.position.x = point.x
            point_marker.pose.position.y = point.y
            point_marker.pose.position.z = 0.1
            point_marker.pose.orientation.w = 1.0
            point_marker.scale.x = 0.1
            point_marker.scale.y = 0.1
            point_marker.scale.z = 0.1
            point_marker.color.r = 1.0
            point_marker.color.g = 0.5
            point_marker.color.b = 0.0
            point_marker.color.a = 1.0
            marker_array.markers.append(point_marker)

        self.visualization_publisher.publish(marker_array)

    def publish_metrics(self, metrics):
        """Publish performance metrics"""
        metrics_msg = String()
        metrics_msg.data = json.dumps(metrics)
        self.metrics_publisher.publish(metrics_msg)


def main(args=None):
    rclpy.init(args=args)
    node = DLPathPlanningNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
