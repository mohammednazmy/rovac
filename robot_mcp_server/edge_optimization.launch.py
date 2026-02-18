#!/usr/bin/env python3
"""
Launch file for edge optimization node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_edge_processing = DeclareLaunchArgument(
        "enable_edge_processing",
        default_value="true",
        description="Enable edge computing optimization",
    )

    declare_process_on_pi = DeclareLaunchArgument(
        "process_on_pi",
        default_value="true",
        description="Process data on Raspberry Pi",
    )

    declare_compression_ratio = DeclareLaunchArgument(
        "compression_ratio",
        default_value="0.5",
        description="Data compression ratio (0.1-1.0)",
    )

    declare_batch_size = DeclareLaunchArgument(
        "processing_batch_size",
        default_value="10",
        description="Number of items to process in batch",
    )

    # Edge Optimization Node
    edge_optimization_node = Node(
        package="rovac_enhanced",
        executable="edge_optimization_node.py",
        name="edge_optimization_node",
        output="screen",
        parameters=[
            {
                "enable_edge_processing": LaunchConfiguration("enable_edge_processing"),
                "process_on_pi": LaunchConfiguration("process_on_pi"),
                "compression_ratio": LaunchConfiguration("compression_ratio"),
                "processing_batch_size": LaunchConfiguration("processing_batch_size"),
            }
        ],
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_edge_processing)
    ld.add_action(declare_process_on_pi)
    ld.add_action(declare_compression_ratio)
    ld.add_action(declare_batch_size)

    # Add nodes
    ld.add_action(edge_optimization_node)

    return ld
