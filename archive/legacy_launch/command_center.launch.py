from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    tank_desc_pkg = get_package_share_directory('tank_description')
    
    # Include SLAM Stack (Robot State, Lidar, RF2O, SLAM Toolbox)
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

    # Tank Motor Driver
    motor_driver = Node(
        package='tank_description',
        executable='tank_motor_driver',
        name='tank_motor_driver',
        output='screen',
        respawn=True,
        respawn_delay=2.0
    )

    # cmd_vel Multiplexer - routes Nav2 (/cmd_vel_smoothed) and joystick (/cmd_vel_joy) to /cmd_vel
    cmd_vel_mux = Node(
        package='tank_description',
        executable='cmd_vel_mux',
        name='cmd_vel_mux',
        output='screen',
        respawn=True,
        respawn_delay=2.0
    )

    # HTTP Bridge - allows cross-subnet GameCube control via HTTP on port 5000
    http_bridge = Node(
        package='tank_description',
        executable='http_bridge',
        name='http_bridge',
        output='screen',
        respawn=True,
        respawn_delay=2.0
    )

    return LaunchDescription([
        slam_launch,
        foxglove_bridge,
        motor_driver,
        cmd_vel_mux,
        http_bridge
    ])
