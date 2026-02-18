#!/usr/bin/env python3
"""
Frontier Exploration Node for ROVAC Robot
Implements autonomous exploration for SLAM map building
"""

import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid, Odometry
from geometry_msgs.msg import PoseStamped, Twist, Point
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool
import numpy as np
import cv2
import math
from collections import deque


class FrontierExplorationNode(Node):
    def __init__(self):
        super().__init__("frontier_exploration_node")

        # Parameters
        self.declare_parameter("exploration_rate", 0.5)
        self.declare_parameter("frontier_min_size", 5)
        self.declare_parameter("goal_distance_threshold", 0.5)
        self.declare_parameter("enable_exploration", True)

        self.exploration_rate = self.get_parameter("exploration_rate").value
        self.frontier_min_size = self.get_parameter("frontier_min_size").value
        self.goal_distance_threshold = self.get_parameter(
            "goal_distance_threshold"
        ).value
        self.enable_exploration = self.get_parameter("enable_exploration").value

        # State variables
        self.map_data = None
        self.robot_pose = None
        self.current_goal = None
        self.exploring = False
        self.frontiers = []

        # Publishers
        self.goal_pub = self.create_publisher(PoseStamped, "/move_base_simple/goal", 10)
        self.cmd_vel_pub = self.create_publisher(Twist, "/cmd_vel_exploration", 10)
        self.exploration_status_pub = self.create_publisher(
            Bool, "/system/exploration_active", 10
        )

        # Subscribers
        self.map_sub = self.create_subscription(
            OccupancyGrid, "/map", self.map_callback, 10
        )
        self.odom_sub = self.create_subscription(
            Odometry, "/odom", self.odom_callback, 10
        )

        # Timer for exploration updates
        self.timer = self.create_timer(self.exploration_rate, self.explore_frontiers)

        self.get_logger().info("Frontier Exploration Node initialized")

    def map_callback(self, msg):
        """Callback for occupancy grid map data"""
        self.map_data = msg

    def odom_callback(self, msg):
        """Callback for robot odometry"""
        self.robot_pose = msg.pose.pose

    def find_frontiers(self, occupancy_grid):
        """Find frontiers (unknown-free boundaries) in the occupancy grid"""
        if occupancy_grid is None:
            return []

        # Convert occupancy grid to numpy array
        width = occupancy_grid.info.width
        height = occupancy_grid.info.height
        map_array = np.array(occupancy_grid.data, dtype=np.int8).reshape(
            (height, width)
        )

        # Define frontier points
        frontiers = []
        visited = np.zeros_like(map_array, dtype=bool)

        # Directions for 8-connectivity
        directions = [
            (-1, -1),
            (-1, 0),
            (-1, 1),
            (0, -1),
            (0, 1),
            (1, -1),
            (1, 0),
            (1, 1),
        ]

        # Iterate through the map
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                # Skip if already visited or not free space
                if visited[y, x] or map_array[y, x] != 0:
                    continue

                # Check if this free cell is adjacent to unknown space
                is_frontier = False
                for dy, dx in directions:
                    ny, nx = y + dy, x + dx
                    if (
                        0 <= ny < height and 0 <= nx < width and map_array[ny, nx] == -1
                    ):  # -1 indicates unknown
                        is_frontier = True
                        break

                if is_frontier:
                    # Flood fill to find connected frontier region
                    frontier_region = self.flood_fill_frontier(
                        map_array, visited, x, y, directions
                    )
                    if len(frontier_region) >= self.frontier_min_size:
                        frontiers.append(frontier_region)

        return frontiers

    def flood_fill_frontier(self, map_array, visited, start_x, start_y, directions):
        """Flood fill to find connected frontier regions"""
        frontier_points = []
        queue = deque([(start_x, start_y)])
        visited[start_y, start_x] = True

        while queue:
            x, y = queue.popleft()
            frontier_points.append((x, y))

            # Check 8-connected neighbors
            for dy, dx in directions:
                nx, ny = x + dx, y + dy
                if (
                    0 <= ny < map_array.shape[0]
                    and 0 <= nx < map_array.shape[1]
                    and not visited[ny, nx]
                    and map_array[ny, nx] == 0
                ):
                    # Check if this neighbor is adjacent to unknown space
                    is_adjacent_to_unknown = False
                    for ddy, ddx in directions:
                        nnx, nny = nx + ddx, ny + ddy
                        if (
                            0 <= nny < map_array.shape[0]
                            and 0 <= nnx < map_array.shape[1]
                            and map_array[nny, nnx] == -1
                        ):
                            is_adjacent_to_unknown = True
                            break

                    if is_adjacent_to_unknown:
                        visited[ny, nx] = True
                        queue.append((nx, ny))

        return frontier_points

    def select_best_frontier(self, frontiers, robot_pose, map_info):
        """Select the best frontier to explore based on criteria"""
        if not frontiers or robot_pose is None:
            return None

        best_frontier = None
        best_score = float("-inf")

        # Get robot position in map coordinates
        robot_x = int(
            (robot_pose.position.x - map_info.origin.position.x) / map_info.resolution
        )
        robot_y = int(
            (robot_pose.position.y - map_info.origin.position.y) / map_info.resolution
        )

        for frontier in frontiers:
            # Calculate centroid of frontier
            centroid_x = sum(point[0] for point in frontier) / len(frontier)
            centroid_y = sum(point[1] for point in frontier) / len(frontier)

            # Convert to world coordinates
            world_x = centroid_x * map_info.resolution + map_info.origin.position.x
            world_y = centroid_y * map_info.resolution + map_info.origin.position.y

            # Calculate distance from robot
            distance = math.sqrt(
                (world_x - robot_pose.position.x) ** 2
                + (world_y - robot_pose.position.y) ** 2
            )

            # Calculate information gain (size of frontier)
            info_gain = len(frontier)

            # Score based on distance and information gain
            # Prefer closer frontiers with higher information gain
            score = info_gain / (distance + 1.0)

            if score > best_score:
                best_score = score
                best_frontier = {
                    "centroid": (world_x, world_y),
                    "points": frontier,
                    "score": score,
                }

        return best_frontier

    def create_navigation_goal(self, frontier_centroid):
        """Create a navigation goal pose for the selected frontier"""
        goal_pose = PoseStamped()
        goal_pose.header.stamp = self.get_clock().now().to_msg()
        goal_pose.header.frame_id = "map"

        # Set position
        goal_pose.pose.position.x = frontier_centroid[0]
        goal_pose.pose.position.y = frontier_centroid[1]
        goal_pose.pose.position.z = 0.0

        # Set orientation (face toward the frontier)
        goal_pose.pose.orientation.x = 0.0
        goal_pose.pose.orientation.y = 0.0
        goal_pose.pose.orientation.z = 0.0
        goal_pose.pose.orientation.w = 1.0

        return goal_pose

    def explore_frontiers(self):
        """Main exploration function"""
        if (
            not self.enable_exploration
            or self.map_data is None
            or self.robot_pose is None
        ):
            return

        # Find frontiers in the current map
        self.frontiers = self.find_frontiers(self.map_data)

        if not self.frontiers:
            # No frontiers found, exploration complete or map fully explored
            self.exploring = False
            self.get_logger().info("No frontiers found. Exploration may be complete.")
            return

        # Select best frontier to explore
        best_frontier = self.select_best_frontier(
            self.frontiers, self.robot_pose, self.map_data.info
        )

        if best_frontier is None:
            self.exploring = False
            return

        # Check if we've reached the current goal
        if self.current_goal is not None:
            distance_to_goal = math.sqrt(
                (self.robot_pose.position.x - self.current_goal.pose.position.x) ** 2
                + (self.robot_pose.position.y - self.current_goal.pose.position.y) ** 2
            )

            if distance_to_goal < self.goal_distance_threshold:
                self.get_logger().info(
                    "Reached frontier goal. Finding next frontier..."
                )
                # Goal reached, will select new frontier on next iteration

        # Set new goal if needed
        if (
            self.current_goal is None
            or self.distance_to_pose(self.current_goal.pose)
            > self.goal_distance_threshold
        ):
            self.current_goal = self.create_navigation_goal(best_frontier["centroid"])
            self.goal_pub.publish(self.current_goal)
            self.exploring = True
            self.get_logger().info(
                f"Setting new exploration goal at ({best_frontier['centroid'][0]:.2f}, {best_frontier['centroid'][1]:.2f})"
            )

        # Publish exploration status
        status_msg = Bool()
        status_msg.data = self.exploring
        self.exploration_status_pub.publish(status_msg)

    def distance_to_pose(self, pose):
        """Calculate distance from robot to a given pose"""
        if self.robot_pose is None:
            return float("inf")

        return math.sqrt(
            (self.robot_pose.position.x - pose.position.x) ** 2
            + (self.robot_pose.position.y - pose.position.y) ** 2
        )


def main(args=None):
    rclpy.init(args=args)
    node = FrontierExplorationNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
