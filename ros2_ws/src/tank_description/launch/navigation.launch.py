import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    # Directories
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    tank_desc_dir = get_package_share_directory('tank_description')
    
    # Configuration
    params_file = LaunchConfiguration('params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    
    declare_params_file_cmd = DeclareLaunchArgument(
        'params_file',
        default_value=os.path.join(tank_desc_dir, 'config', 'nav2_params.yaml'),
        description='Full path to the ROS2 parameters file to use for all launched nodes')

    declare_use_sim_time_cmd = DeclareLaunchArgument(
        'use_sim_time',
        default_value='False',
        description='Use simulation (Gazebo) clock if true')

    # Launch Nav2 Bringup
    # We use the 'bringup_launch.py' which launches map_server, amcl, bt_navigator, planner_server, controller_server, etc.
    bringup_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'params_file': params_file,
            'autostart': 'True',  # Auto-start the lifecycle nodes
            'map': '/tmp/my_map.yaml' # Placeholder, we will set this or use slam
        }.items())

    return LaunchDescription([
        declare_params_file_cmd,
        declare_use_sim_time_cmd,
        bringup_cmd
    ])
