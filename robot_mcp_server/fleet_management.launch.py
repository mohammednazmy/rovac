#!/usr/bin/env python3
"""
Launch file for ROVAC Fleet Management System
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_fleet_management = DeclareLaunchArgument(
        "enable_fleet_management",
        default_value="true",
        description="Enable fleet management system",
    )

    declare_robot_id = DeclareLaunchArgument(
        "robot_id",
        default_value="rovac_001",
        description="Unique identifier for this robot",
    )

    declare_robot_name = DeclareLaunchArgument(
        "robot_name",
        default_value="Primary_ROVAC",
        description="Human-readable name for this robot",
    )

    declare_fleet_topic_prefix = DeclareLaunchArgument(
        "fleet_topic_prefix",
        default_value="/fleet",
        description="Prefix for fleet communication topics",
    )

    declare_communication_frequency = DeclareLaunchArgument(
        "communication_frequency",
        default_value="1.0",
        description="Fleet communication frequency (Hz)",
    )

    declare_task_assignment_algorithm = DeclareLaunchArgument(
        "task_assignment_algorithm",
        default_value="greedy",
        description="Task assignment algorithm (greedy, round_robin)",
    )

    declare_enable_cooperative_mapping = DeclareLaunchArgument(
        "enable_cooperative_mapping",
        default_value="true",
        description="Enable cooperative mapping between robots",
    )

    declare_enable_task_sharing = DeclareLaunchArgument(
        "enable_task_sharing",
        default_value="true",
        description="Enable task sharing between robots",
    )

    declare_enable_behavior_tree = DeclareLaunchArgument(
        "enable_behavior_tree",
        default_value="true",
        description="Enable behavior tree framework",
    )

    declare_behavior_tree_tick_rate = DeclareLaunchArgument(
        "behavior_tree_tick_rate",
        default_value="10.0",
        description="Behavior tree tick rate (Hz)",
    )

    declare_enable_predictive_avoidance = DeclareLaunchArgument(
        "enable_predictive_avoidance",
        default_value="true",
        description="Enable predictive obstacle avoidance",
    )

    declare_prediction_horizon = DeclareLaunchArgument(
        "prediction_horizon",
        default_value="5.0",
        description="Prediction horizon for obstacle avoidance (seconds)",
    )

    # Fleet Management Node
    fleet_management_node = Node(
        package="rovac_enhanced",
        executable="fleet_management_node.py",
        name="fleet_management_node",
        output="screen",
        parameters=[
            {
                "robot_id": LaunchConfiguration("robot_id"),
                "robot_name": LaunchConfiguration("robot_name"),
                "fleet_topic_prefix": LaunchConfiguration("fleet_topic_prefix"),
                "communication_frequency": LaunchConfiguration(
                    "communication_frequency"
                ),
                "task_assignment_algorithm": LaunchConfiguration(
                    "task_assignment_algorithm"
                ),
                "enable_cooperative_mapping": LaunchConfiguration(
                    "enable_cooperative_mapping"
                ),
                "enable_task_sharing": LaunchConfiguration("enable_task_sharing"),
                "enable_behavior_tree": LaunchConfiguration("enable_behavior_tree"),
                "behavior_tree_tick_rate": LaunchConfiguration(
                    "behavior_tree_tick_rate"
                ),
                "enable_predictive_avoidance": LaunchConfiguration(
                    "enable_predictive_avoidance"
                ),
                "prediction_horizon": LaunchConfiguration("prediction_horizon"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_fleet_management")),
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_fleet_management)
    ld.add_action(declare_robot_id)
    ld.add_action(declare_robot_name)
    ld.add_action(declare_fleet_topic_prefix)
    ld.add_action(declare_communication_frequency)
    ld.add_action(declare_task_assignment_algorithm)
    ld.add_action(declare_enable_cooperative_mapping)
    ld.add_action(declare_enable_task_sharing)
    ld.add_action(declare_enable_behavior_tree)
    ld.add_action(declare_behavior_tree_tick_rate)
    ld.add_action(declare_enable_predictive_avoidance)
    ld.add_action(declare_prediction_horizon)

    # Add nodes
    ld.add_action(fleet_management_node)

    return ld
