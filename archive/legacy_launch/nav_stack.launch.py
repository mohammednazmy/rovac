import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    tank_desc_dir = get_package_share_directory('tank_description')
    
    params_file = LaunchConfiguration('params_file')
    use_sim_time = LaunchConfiguration('use_sim_time')
    
    declare_params = DeclareLaunchArgument(
        'params_file',
        default_value=os.path.join(tank_desc_dir, 'config', 'nav2_params.yaml'))
        
    declare_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='False')

    # Launch ONLY Navigation (Planner, Controller, Recoveries, BT)
    # Uses 'navigation_launch.py' to avoid conflicting with SLAM's map/localization
    nav_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'navigation_launch.py')
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'params_file': params_file,
            'autostart': 'True',
        }.items()
    )

    return LaunchDescription([
        declare_params,
        declare_sim_time,
        nav_launch
    ])
