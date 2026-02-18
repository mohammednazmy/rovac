"""
Locomotion Launch File - Motor control, odometry, TF
Core movement stack for ROVAC robot.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    tank_desc_pkg = get_package_share_directory('tank_description')
    urdf_file = os.path.join(tank_desc_pkg, 'urdf', 'tank.urdf')

    # Read URDF
    with open(urdf_file, 'r') as f:
        robot_description = f.read()

    # Robot State Publisher (TF tree from URDF)
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'publish_frequency': 30.0,
        }]
    )

    # cmd_vel Multiplexer
    cmd_vel_mux = Node(
        package='tank_description',
        executable='cmd_vel_mux',
        name='cmd_vel_mux',
        output='screen',
        respawn=True,
        respawn_delay=2.0
    )

    # Static TF: map -> odom (placeholder until SLAM provides this)
    static_tf_map_odom = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_map_odom',
        arguments=['0', '0', '0', '0', '0', '0', 'map', 'odom'],
        output='screen'
    )

    return LaunchDescription([
        robot_state_publisher,
        cmd_vel_mux,
        static_tf_map_odom,
    ])
