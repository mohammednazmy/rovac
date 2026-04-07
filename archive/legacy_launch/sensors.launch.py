"""
Sensors Launch File - LIDAR, Super Sensor, IMU
Modular sensor stack for ROVAC robot.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Launch arguments
    lidar_port_arg = DeclareLaunchArgument(
        'lidar_port', default_value='/dev/ttyAMA0',
        description='Serial port for XV-11 LIDAR'
    )
    sensor_port_arg = DeclareLaunchArgument(
        'sensor_port', default_value='/dev/super_sensor',
        description='Serial port for Super Sensor'
    )

    # Vorwerk/XV-11 LIDAR Node
    lidar_node = Node(
        package='vorwerk_lidar',
        executable='vorwerk_lidar_node',
        name='vorwerk_lidar_node',
        output='screen',
        parameters=[{
            'serial_port': LaunchConfiguration('lidar_port'),
            'baud_rate': 115200,
            'frame_id': 'laser_frame',
            'scan_topic': '/scan',
        }],
        respawn=True,
        respawn_delay=3.0
    )

    # Super Sensor Node (4x ultrasonic)
    super_sensor_node = Node(
        package='tank_description',
        executable='super_sensor_ros2_node.py',
        name='super_sensor_node',
        output='screen',
        parameters=[{
            'port': LaunchConfiguration('sensor_port'),
            'publish_rate': 10.0,
            'obstacle_threshold': 30,
            'status_rate_divisor': 5,
        }],
        respawn=True,
        respawn_delay=3.0
    )

    return LaunchDescription([
        lidar_port_arg,
        sensor_port_arg,
        lidar_node,
        super_sensor_node,
    ])
