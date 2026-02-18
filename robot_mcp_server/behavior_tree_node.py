#!/usr/bin/env python3
"""
Behavior Tree Node for ROVAC
ROS2 interface for behavior tree execution
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from geometry_msgs.msg import Twist
from sensor_msgs.msg import LaserScan
import json
import time
from behavior_tree_framework import *


class ROVACBehaviorTreeNode(Node):
    """ROS2 node for behavior tree execution"""

    def __init__(self):
        super().__init__("behavior_tree_node")

        # ROS2 parameters
        self.declare_parameter("tick_rate", 10.0)
        self.declare_parameter("enable_behavior_tree", True)

        self.tick_rate = self.get_parameter("tick_rate").value
        self.enabled = self.get_parameter("enable_behavior_tree").value

        # State variables
        self.obstacle_detected = False
        self.battery_level = 100.0
        self.current_pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
        self.mission_active = False
        self.mission_goal = None

        # Subscriptions
        self.scan_subscription = self.create_subscription(
            LaserScan, "/scan", self.scan_callback, 10
        )

        self.battery_subscription = self.create_subscription(
            String, "/system/battery_status", self.battery_callback, 10
        )

        # Publishers
        self.cmd_vel_publisher = self.create_publisher(Twist, "/cmd_vel_bt", 10)

        self.status_publisher = self.create_publisher(
            String, "/behavior_tree/status", 10
        )

        self.mission_publisher = self.create_publisher(
            String, "/behavior_tree/mission_status", 10
        )

        # Services/Actions would go here for mission planning

        # Create behavior tree
        self.behavior_tree = self.create_mission_behavior_tree()

        # Timer for behavior tree execution
        self.timer = self.create_timer(1.0 / self.tick_rate, self.execute_behavior_tree)

        self.get_logger().info("Behavior Tree Node initialized")
        self.get_logger().info(f"Tick rate: {self.tick_rate} Hz")

    def scan_callback(self, msg):
        """Handle LIDAR scan data"""
        # Check for obstacles in front
        front_ranges = msg.ranges[len(msg.ranges) // 2 - 10 : len(msg.ranges) // 2 + 10]
        min_distance = min([r for r in front_ranges if r > 0], default=10.0)
        self.obstacle_detected = min_distance < 0.5  # 50cm threshold

    def battery_callback(self, msg):
        """Handle battery status updates"""
        try:
            data = json.loads(msg.data)
            self.battery_level = data.get("level", 100.0)
        except:
            pass  # Ignore invalid data

    def execute_behavior_tree(self):
        """Execute one tick of the behavior tree"""
        if not self.enabled:
            return

        if self.behavior_tree:
            status = self.behavior_tree.tick()

            # Publish status
            status_msg = String()
            status_msg.data = json.dumps(
                {"status": status.value, "timestamp": time.time()}
            )
            self.status_publisher.publish(status_msg)

    def create_mission_behavior_tree(self):
        """Create the main mission behavior tree"""

        # Root selector for different mission modes
        root = SelectorNode("Mission_Root")

        # Autonomous exploration sequence
        exploration_sequence = SequenceNode("Exploration_Sequence")

        # Check battery level
        battery_check = ConditionNode("Battery_Check", self.check_battery_level)
        exploration_sequence.add_child(battery_check)

        # Check for obstacles
        obstacle_check = ConditionNode("Obstacle_Check", self.check_no_obstacles)
        exploration_sequence.add_child(obstacle_check)

        # Move forward action
        move_forward = ActionNode("Move_Forward", self.move_forward_action)
        exploration_sequence.add_child(move_forward)

        # Obstacle avoidance sequence
        avoidance_sequence = SequenceNode("Avoidance_Sequence")

        # Check if obstacle detected
        obstacle_detected = ConditionNode(
            "Obstacle_Detected", self.check_obstacle_detected
        )
        avoidance_sequence.add_child(obstacle_detected)

        # Turn away from obstacle
        turn_action = ActionNode("Turn_From_Obstacle", self.turn_away_action)
        avoidance_sequence.add_child(turn_action)

        # Low battery sequence
        low_battery_sequence = SequenceNode("Low_Battery_Sequence")

        # Check if battery is low
        low_battery_check = ConditionNode("Low_Battery_Check", self.check_low_battery)
        low_battery_sequence.add_child(low_battery_check)

        # Return to charging station
        return_home = ActionNode("Return_Home", self.return_home_action)
        low_battery_sequence.add_child(return_home)

        # Add all sequences to root
        root.add_child(low_battery_sequence)
        root.add_child(avoidance_sequence)
        root.add_child(exploration_sequence)

        return BehaviorTree(root)

    # Condition functions
    def check_battery_level(self):
        """Check if battery level is sufficient"""
        return self.battery_level > 20.0

    def check_no_obstacles(self):
        """Check if no obstacles are detected"""
        return not self.obstacle_detected

    def check_obstacle_detected(self):
        """Check if obstacle is detected"""
        return self.obstacle_detected

    def check_low_battery(self):
        """Check if battery is low"""
        return self.battery_level < 30.0

    # Action functions
    def move_forward_action(self):
        """Move robot forward"""
        cmd_vel = Twist()
        cmd_vel.linear.x = 0.3  # 0.3 m/s forward
        self.cmd_vel_publisher.publish(cmd_vel)
        self.get_logger().info("Moving forward")
        return True

    def turn_away_action(self):
        """Turn away from obstacle"""
        cmd_vel = Twist()
        cmd_vel.angular.z = 1.0  # 1 rad/s turn
        self.cmd_vel_publisher.publish(cmd_vel)
        time.sleep(1.0)  # Turn for 1 second
        # Stop
        cmd_vel.angular.z = 0.0
        self.cmd_vel_publisher.publish(cmd_vel)
        self.get_logger().info("Turning away from obstacle")
        return True

    def return_home_action(self):
        """Return to charging station"""
        self.get_logger().info("Returning to charging station")
        # In a real implementation, this would navigate to home position
        return True


def main(args=None):
    rclpy.init(args=args)
    node = ROVACBehaviorTreeNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
