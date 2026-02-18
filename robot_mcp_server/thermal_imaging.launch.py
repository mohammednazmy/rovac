#!/usr/bin/env python3
"""
Launch file for thermal imaging node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_thermal_imaging = DeclareLaunchArgument(
        "enable_thermal_imaging",
        default_value="true",
        description="Enable thermal imaging node",
    )

    declare_use_emulation = DeclareLaunchArgument(
        "use_emulation",
        default_value="true",
        description="Use emulation mode instead of hardware camera",
    )

    declare_spi_device = DeclareLaunchArgument(
        "spi_device",
        default_value="/dev/spidev0.0",
        description="SPI device for FLIR Lepton camera",
    )

    declare_frame_rate = DeclareLaunchArgument(
        "frame_rate", default_value="9.0", description="Thermal camera frame rate (Hz)"
    )

    declare_publish_visualization = DeclareLaunchArgument(
        "publish_visualization",
        default_value="true",
        description="Publish visualization markers for detected signatures",
    )

    declare_detection_sensitivity = DeclareLaunchArgument(
        "detection_sensitivity",
        default_value="medium",
        description="Detection sensitivity (high, medium, low)",
    )

    # Thermal Imaging Node
    thermal_imaging_node = Node(
        package="rovac_enhanced",
        executable="thermal_imaging_node.py",
        name="thermal_imaging_node",
        output="screen",
        parameters=[
            {
                "enable_thermal_imaging": LaunchConfiguration("enable_thermal_imaging"),
                "use_emulation": LaunchConfiguration("use_emulation"),
                "spi_device": LaunchConfiguration("spi_device"),
                "frame_rate": LaunchConfiguration("frame_rate"),
                "publish_visualization": LaunchConfiguration("publish_visualization"),
                "detection_sensitivity": LaunchConfiguration("detection_sensitivity"),
            }
        ],
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_thermal_imaging)
    ld.add_action(declare_use_emulation)
    ld.add_action(declare_spi_device)
    ld.add_action(declare_frame_rate)
    ld.add_action(declare_publish_visualization)
    ld.add_action(declare_detection_sensitivity)

    # Add nodes
    ld.add_action(thermal_imaging_node)

    return ld
