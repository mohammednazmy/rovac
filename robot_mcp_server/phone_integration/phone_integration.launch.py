#!/usr/bin/env python3
"""
Phone Integration ROS2 Launch File
Launches all phone sensor and camera nodes for robot integration.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Launch arguments
    video_device_arg = DeclareLaunchArgument(
        'video_device', default_value='/dev/video10',
        description='V4L2 video device for phone camera')

    sensor_port_arg = DeclareLaunchArgument(
        'sensor_port', default_value='8080',
        description='SensorServer WebSocket port')

    camera_arg = DeclareLaunchArgument(
        'camera', default_value='back_main',
        description='Camera to use: back_main, front, back_ultrawide')

    enable_depth_arg = DeclareLaunchArgument(
        'enable_depth', default_value='false',
        description='Enable depth estimation (CPU intensive)')

    # Phone sensors node
    phone_sensors_node = Node(
        package='robot_mcp_server',
        executable='phone_sensors_node.py',
        name='phone_sensors',
        output='screen',
        parameters=[{
            'host': 'localhost',
            'port': LaunchConfiguration('sensor_port'),
            'frame_id': 'phone_link',
            'parent_frame': 'base_link',
            'phone_x': 0.05,
            'phone_y': 0.0,
            'phone_z': 0.12,
        }]
    )

    # Phone camera node
    phone_camera_node = Node(
        package='robot_mcp_server',
        executable='phone_camera_node.py',
        name='phone_camera',
        output='screen',
        parameters=[{
            'video_device': LaunchConfiguration('video_device'),
            'camera': LaunchConfiguration('camera'),
            'width': 1280,
            'height': 720,
            'fps': 30,
            'frame_id': 'phone_camera_link',
            'publish_raw': True,
            'publish_compressed': True,
            'jpeg_quality': 75,
        }]
    )

    # Static TF: phone_camera_link relative to phone_link
    phone_camera_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='phone_camera_tf',
        arguments=['0', '0', '0', '0', '0', '0', 'phone_link', 'phone_camera_link']
    )

    return LaunchDescription([
        video_device_arg,
        sensor_port_arg,
        camera_arg,
        enable_depth_arg,
        phone_sensors_node,
        phone_camera_node,
        phone_camera_tf,
    ])
