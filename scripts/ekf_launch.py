#!/usr/bin/env python3
"""
Launch EKF sensor fusion for ROVAC.

Fuses wheel odometry (/odom) with phone IMU (/phone/imu/relay)
to produce /odometry/filtered with improved localization.

Usage:
    source config/ros2_env.sh
    ros2 launch scripts/ekf_launch.py

Requires: ros-jazzy-robot-localization, phone sensor relay running.
"""

import os
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    config_dir = os.path.join(
        os.path.expanduser('~'), 'robots', 'rovac', 'config')

    ekf_config = os.path.join(config_dir, 'ekf_params.yaml')

    return LaunchDescription([
        # EKF node — fuses wheel odom + phone IMU
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_node',
            output='screen',
            parameters=[ekf_config],
            remappings=[
                ('odometry/filtered', '/odometry/filtered'),
            ],
        ),
    ])
