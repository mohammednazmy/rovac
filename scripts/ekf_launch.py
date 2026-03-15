#!/usr/bin/env python3
"""
Launch EKF sensor fusion + optional GPS navigation for ROVAC.

EKF fuses wheel odometry (/odom) with phone IMU (/phone/imu).
navsat_transform converts phone GPS to local coordinates.

Usage:
    source config/ros2_env.sh
    ros2 launch scripts/ekf_launch.py              # EKF only
    ros2 launch scripts/ekf_launch.py gps:=true    # EKF + GPS
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    config_dir = os.path.join(
        os.path.expanduser('~'), 'robots', 'rovac', 'config')

    return LaunchDescription([
        DeclareLaunchArgument('gps', default_value='false',
                              description='Enable GPS navigation'),

        # EKF node — fuses wheel odom + phone IMU
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'ekf_params.yaml')],
        ),

        # navsat_transform — converts GPS to local odom frame
        Node(
            package='robot_localization',
            executable='navsat_transform_node',
            name='navsat_transform',
            output='screen',
            parameters=[os.path.join(config_dir, 'navsat_params.yaml')],
            remappings=[
                ('gps/fix', '/phone/gps/fix'),
                ('imu/data', '/phone/imu'),
                ('odometry/filtered', '/odometry/filtered'),
            ],
            condition=IfCondition(LaunchConfiguration('gps')),
        ),
    ])
