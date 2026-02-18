#!/usr/bin/env python3
"""
Launch file for object recognition node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_object_recognition = DeclareLaunchArgument(
        "enable_object_recognition",
        default_value="true",
        description="Enable object recognition node",
    )

    declare_confidence_threshold = DeclareLaunchArgument(
        "confidence_threshold",
        default_value="0.5",
        description="Detection confidence threshold",
    )

    declare_frame_skip = DeclareLaunchArgument(
        "frame_skip", default_value="5", description="Process every nth frame"
    )

    # Object Recognition Node
    object_recognition_node = Node(
        package="rovac_enhanced",
        executable="object_recognition_node.py",
        name="object_recognition_node",
        output="screen",
        parameters=[
            {
                "confidence_threshold": LaunchConfiguration("confidence_threshold"),
                "frame_skip": LaunchConfiguration("frame_skip"),
            }
        ],
        condition=DeclareLaunchArgument("enable_object_recognition").condition,
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_object_recognition)
    ld.add_action(declare_confidence_threshold)
    ld.add_action(declare_frame_skip)

    # Add nodes
    ld.add_action(object_recognition_node)

    return ld
