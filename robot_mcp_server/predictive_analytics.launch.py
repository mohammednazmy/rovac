#!/usr/bin/env python3
"""
Launch file for predictive analytics node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_predictive_analytics = DeclareLaunchArgument(
        "enable_predictive_analytics",
        default_value="true",
        description="Enable predictive analytics and maintenance forecasting",
    )

    declare_data_collection_interval = DeclareLaunchArgument(
        "data_collection_interval",
        default_value="1.0",
        description="Data collection interval in seconds",
    )

    declare_report_generation_interval = DeclareLaunchArgument(
        "report_generation_interval",
        default_value="10.0",
        description="Report generation interval in seconds",
    )

    # Predictive Analytics Node
    predictive_analytics_node = Node(
        package="rovac_enhanced",
        executable="predictive_analytics_node.py",
        name="predictive_analytics_node",
        output="screen",
        parameters=[
            {
                "enable_predictive_analytics": LaunchConfiguration(
                    "enable_predictive_analytics"
                ),
                "data_collection_interval": LaunchConfiguration(
                    "data_collection_interval"
                ),
                "report_generation_interval": LaunchConfiguration(
                    "report_generation_interval"
                ),
            }
        ],
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_predictive_analytics)
    ld.add_action(declare_data_collection_interval)
    ld.add_action(declare_report_generation_interval)

    # Add nodes
    ld.add_action(predictive_analytics_node)

    return ld
