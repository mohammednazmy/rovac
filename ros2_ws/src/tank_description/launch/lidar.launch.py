from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='vorwerk_lidar',
            executable='lidar_node',
            name='lidar_node',
            output='screen',
            parameters=[
                {'serial_port': '/dev/ttyAMA0'},
                {'baud_rate': 115200},
                {'frame_id': 'laser_frame'},
                {'scan_topic': 'scan'}
            ]
        ),
        # Optional: Static Transform Publisher if people want to visualize immediately relative to a base
        # Node(
        #     package='tf2_ros',
        #     executable='static_transform_publisher',
        #     arguments=['0', '0', '0', '0', '0', '0', 'base_link', 'laser_frame']
        # )
    ])
