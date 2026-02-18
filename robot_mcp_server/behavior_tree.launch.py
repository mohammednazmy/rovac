#!/usr/bin/env python3
"""
Launch file for behavior tree node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_behavior_tree = DeclareLaunchArgument(
        "enable_behavior_tree",
        default_value="true",
        description="Enable behavior tree node",
    )

    declare_tick_rate = DeclareLaunchArgument(
        "tick_rate", default_value="10.0", description="Behavior tree tick rate (Hz)"
    )

    # Behavior Tree Node
    behavior_tree_node = Node(
        package="rovac_enhanced",
        executable="behavior_tree_node.py",
        name="behavior_tree_node",
        output="screen",
        parameters=[
            {
                "enable_behavior_tree": LaunchConfiguration("enable_behavior_tree"),
                "tick_rate": LaunchConfiguration("tick_rate"),
            }
        ],
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_behavior_tree)
    ld.add_action(declare_tick_rate)

    # Add nodes
    ld.add_action(behavior_tree_node)

    return ld
