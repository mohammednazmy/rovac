from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('vorwerk_lidar')
    tank_desc_path = get_package_share_directory('tank_description')
    
    urdf_file = os.path.join(tank_desc_path, 'urdf', 'tank.urdf')
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    return LaunchDescription([
        # 1. Robot State Publisher (TF Tree)
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_desc}],
            arguments=[urdf_file]
        ),

        # 2. Lidar Node
        Node(
            package='vorwerk_lidar',
            executable='lidar_node',
            name='lidar_node',
            output='screen',
            parameters=[
                {'serial_port': '/dev/ttyAMA0'},
                {'baud_rate': 115200},
                {'frame_id': 'laser_frame'},
                {'scan_topic': '/scan'}  # Use absolute topic name
            ]
        ),

        # 3. Laser Odometry (RF2O)
        Node(
            package='rf2o_laser_odometry',
            executable='rf2o_laser_odometry_node',
            name='rf2o_laser_odometry',
            output='screen',
            parameters=[{
                'laser_scan_topic': '/scan',
                'odom_topic': '/odom',
                'publish_tf': True,
                'base_frame_id': 'base_link',
                'odom_frame_id': 'odom',
                'laser_frame_id': 'laser_frame',
                'init_pose_from_topic': '',
                'freq': 10.0
            }],
        ),

        # 4. SLAM Toolbox (Mapper)
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[{
                'use_sim_time': False,
                'odom_frame': 'odom',
                'map_frame': 'map',
                'base_frame': 'base_link',
                'scan_topic': '/scan',
                'mode': 'mapping', # mapping or localization
                'map_update_interval': 1.0,
                'max_laser_range': 6.0,
                'minimum_time_interval': 0.1
            }]
        ),

        Node(
            package='nav2_lifecycle_manager',
            executable='lifecycle_manager',
            name='lifecycle_manager_slam',
            output='screen',
            parameters=[{
                'use_sim_time': False,
                'autostart': True,
                'node_names': ['slam_toolbox'],
            }],
        ),
    ])
