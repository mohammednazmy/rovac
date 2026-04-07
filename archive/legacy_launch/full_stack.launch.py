"""
Full Stack Launch File - Complete ROVAC robot bringup
Combines sensors, locomotion, SLAM, and visualization.
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument, GroupAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    tank_desc_pkg = get_package_share_directory('tank_description')

    # Launch arguments
    enable_slam_arg = DeclareLaunchArgument(
        'enable_slam', default_value='true',
        description='Enable SLAM Toolbox'
    )
    enable_foxglove_arg = DeclareLaunchArgument(
        'enable_foxglove', default_value='true',
        description='Enable Foxglove Bridge'
    )

    # Include locomotion stack
    locomotion_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tank_desc_pkg, 'launch', 'locomotion.launch.py')
        )
    )

    # Include sensors stack
    sensors_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tank_desc_pkg, 'launch', 'sensors.launch.py')
        )
    )

    # Include SLAM (conditional could be added)
    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(tank_desc_pkg, 'launch', 'tank_slam.launch.py')
        )
    )

    # Foxglove Bridge
    foxglove_bridge = Node(
        package='foxglove_bridge',
        executable='foxglove_bridge',
        name='foxglove_bridge',
        output='screen',
        parameters=[{
            'port': 8765,
            'address': '0.0.0.0',
            'send_buffer_limit': 10000000,
        }],
        respawn=True,
        respawn_delay=2.0
    )

    # HTTP Bridge for cross-subnet control
    http_bridge = Node(
        package='tank_description',
        executable='http_bridge',
        name='http_bridge',
        output='screen',
        respawn=True,
        respawn_delay=2.0
    )

    # Health Monitor
    health_monitor = Node(
        package='tank_description',
        executable='health_monitor_node.py',
        name='health_monitor',
        output='screen',
        parameters=[{
            'check_interval': 2.0,
        }],
        respawn=True,
        respawn_delay=5.0
    )

    return LaunchDescription([
        enable_slam_arg,
        enable_foxglove_arg,
        locomotion_launch,
        sensors_launch,
        slam_launch,
        foxglove_bridge,
        http_bridge,
        health_monitor,
    ])
