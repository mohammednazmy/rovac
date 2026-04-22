#!/usr/bin/env python3
"""
Launch EKF sensor fusion for ROVAC.

EKF fuses wheel odometry (/odom) with onboard BNO055 IMU (/imu/data).

Usage:
    source config/ros2_env.sh
    ros2 launch scripts/ekf_launch.py
"""

import os
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config_dir = os.path.join(
        os.path.expanduser('~'), 'robots', 'rovac', 'config')

    return LaunchDescription([
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_node',
            output='screen',
            parameters=[os.path.join(config_dir, 'ekf_params.yaml')],
        ),
    ])
