#!/usr/bin/env python3
"""
Launch file for deep learning path planning node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_dl_planning = DeclareLaunchArgument(
        "enable_dl_planning",
        default_value="true",
        description="Enable deep learning path planning",
    )

    declare_model_path = DeclareLaunchArgument(
        "model_path",
        default_value="",
        description="Path to trained neural network model",
    )

    declare_publish_visualization = DeclareLaunchArgument(
        "publish_visualization",
        default_value="true",
        description="Publish path visualization markers",
    )

    declare_update_rate = DeclareLaunchArgument(
        "update_rate_hz",
        default_value="1.0",
        description="Path planning update rate (Hz)",
    )

    # Deep Learning Path Planning Node
    dl_path_planning_node = Node(
        package="rovac_enhanced",
        executable="dl_path_planning_node.py",
        name="dl_path_planning_node",
        output="screen",
        parameters=[
            {
                "enable_dl_planning": LaunchConfiguration("enable_dl_planning"),
                "model_path": LaunchConfiguration("model_path"),
                "publish_visualization": LaunchConfiguration("publish_visualization"),
                "update_rate_hz": LaunchConfiguration("update_rate_hz"),
            }
        ],
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_dl_planning)
    ld.add_action(declare_model_path)
    ld.add_action(declare_publish_visualization)
    ld.add_action(declare_update_rate)

    # Add nodes
    ld.add_action(dl_path_planning_node)

    return ld
