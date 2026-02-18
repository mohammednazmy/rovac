#!/usr/bin/env python3
"""
Launch file for Predictive Obstacle Avoidance Node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_predictive_avoidance = DeclareLaunchArgument(
        "enable_predictive_avoidance",
        default_value="true",
        description="Enable predictive obstacle avoidance",
    )

    declare_prediction_horizon_seconds = DeclareLaunchArgument(
        "prediction_horizon_seconds",
        default_value="5.0",
        description="Obstacle prediction time horizon in seconds",
    )

    declare_risk_threshold = DeclareLaunchArgument(
        "risk_threshold",
        default_value="0.3",
        description="Collision probability threshold for avoidance action",
    )

    declare_safety_margin_meters = DeclareLaunchArgument(
        "safety_margin_meters",
        default_value="0.3",
        description="Safety margin around robot in meters",
    )

    declare_reaction_time_seconds = DeclareLaunchArgument(
        "reaction_time_seconds",
        default_value="0.5",
        description="Time to react to obstacles in seconds",
    )

    declare_learning_enabled = DeclareLaunchArgument(
        "learning_enabled",
        default_value="true",
        description="Enable experience-based learning",
    )

    declare_publish_visualization = DeclareLaunchArgument(
        "publish_visualization",
        default_value="true",
        description="Publish visualization markers",
    )

    declare_max_prediction_age = DeclareLaunchArgument(
        "max_prediction_age",
        default_value="3.0",
        description="Maximum age for predictions in seconds",
    )

    declare_update_frequency_hz = DeclareLaunchArgument(
        "update_frequency_hz",
        default_value="10.0",
        description="Avoidance update frequency in Hz",
    )

    declare_max_tracked_obstacles = DeclareLaunchArgument(
        "max_tracked_obstacles",
        default_value="50",
        description="Maximum number of tracked obstacles",
    )

    declare_kalman_process_noise = DeclareLaunchArgument(
        "kalman_process_noise",
        default_value="0.1",
        description="Kalman filter process noise",
    )

    declare_kalman_measurement_noise = DeclareLaunchArgument(
        "kalman_measurement_noise",
        default_value="0.05",
        description="Kalman filter measurement noise",
    )

    declare_collision_distance_threshold = DeclareLaunchArgument(
        "collision_distance_threshold",
        default_value="0.5",
        description="Distance threshold for collision detection",
    )

    declare_publish_debug_info = DeclareLaunchArgument(
        "publish_debug_info",
        default_value="false",
        description="Publish debug information",
    )

    declare_model_path = DeclareLaunchArgument(
        "model_path",
        default_value="",
        description="Path to trained neural network model",
    )

    declare_goal_tolerance_meters = DeclareLaunchArgument(
        "goal_tolerance_meters",
        default_value="0.3",
        description="Goal reaching tolerance in meters",
    )

    declare_enable_adaptive_thresholds = DeclareLaunchArgument(
        "enable_adaptive_thresholds",
        default_value="true",
        description="Enable adaptive risk thresholds",
    )

    declare_adaptive_learning_rate = DeclareLaunchArgument(
        "adaptive_learning_rate",
        default_value="0.01",
        description="Adaptive learning rate for experience-based improvement",
    )

    declare_enable_multi_sensor_fusion = DeclareLaunchArgument(
        "enable_multi_sensor_fusion",
        default_value="true",
        description="Enable fusion of multiple sensor types",
    )

    declare_sensor_fusion_weight_lidar = DeclareLaunchArgument(
        "sensor_fusion_weight_lidar",
        default_value="0.4",
        description="Weight for LIDAR data in sensor fusion",
    )

    declare_sensor_fusion_weight_ultrasonic = DeclareLaunchArgument(
        "sensor_fusion_weight_ultrasonic",
        default_value="0.3",
        description="Weight for ultrasonic data in sensor fusion",
    )

    declare_sensor_fusion_weight_camera = DeclareLaunchArgument(
        "sensor_fusion_weight_camera",
        default_value="0.2",
        description="Weight for camera data in sensor fusion",
    )

    declare_sensor_fusion_weight_imu = DeclareLaunchArgument(
        "sensor_fusion_weight_imu",
        default_value="0.1",
        description="Weight for IMU data in sensor fusion",
    )

    # Predictive Obstacle Avoidance Node
    predictive_obstacle_avoidance_node = Node(
        package="rovac_enhanced",
        executable="predictive_obstacle_avoidance_node.py",
        name="predictive_obstacle_avoidance_node",
        output="screen",
        parameters=[
            {
                "enable_predictive_avoidance": LaunchConfiguration(
                    "enable_predictive_avoidance"
                ),
                "prediction_horizon_seconds": LaunchConfiguration(
                    "prediction_horizon_seconds"
                ),
                "risk_threshold": LaunchConfiguration("risk_threshold"),
                "safety_margin_meters": LaunchConfiguration("safety_margin_meters"),
                "reaction_time_seconds": LaunchConfiguration("reaction_time_seconds"),
                "learning_enabled": LaunchConfiguration("learning_enabled"),
                "publish_visualization": LaunchConfiguration("publish_visualization"),
                "max_prediction_age": LaunchConfiguration("max_prediction_age"),
                "update_frequency_hz": LaunchConfiguration("update_frequency_hz"),
                "max_tracked_obstacles": LaunchConfiguration("max_tracked_obstacles"),
                "kalman_process_noise": LaunchConfiguration("kalman_process_noise"),
                "kalman_measurement_noise": LaunchConfiguration(
                    "kalman_measurement_noise"
                ),
                "collision_distance_threshold": LaunchConfiguration(
                    "collision_distance_threshold"
                ),
                "publish_debug_info": LaunchConfiguration("publish_debug_info"),
                "model_path": LaunchConfiguration("model_path"),
                "goal_tolerance_meters": LaunchConfiguration("goal_tolerance_meters"),
                "enable_adaptive_thresholds": LaunchConfiguration(
                    "enable_adaptive_thresholds"
                ),
                "adaptive_learning_rate": LaunchConfiguration("adaptive_learning_rate"),
                "enable_multi_sensor_fusion": LaunchConfiguration(
                    "enable_multi_sensor_fusion"
                ),
                "sensor_fusion_weight_lidar": LaunchConfiguration(
                    "sensor_fusion_weight_lidar"
                ),
                "sensor_fusion_weight_ultrasonic": LaunchConfiguration(
                    "sensor_fusion_weight_ultrasonic"
                ),
                "sensor_fusion_weight_camera": LaunchConfiguration(
                    "sensor_fusion_weight_camera"
                ),
                "sensor_fusion_weight_imu": LaunchConfiguration(
                    "sensor_fusion_weight_imu"
                ),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_predictive_avoidance")),
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_predictive_avoidance)
    ld.add_action(declare_prediction_horizon_seconds)
    ld.add_action(declare_risk_threshold)
    ld.add_action(declare_safety_margin_meters)
    ld.add_action(declare_reaction_time_seconds)
    ld.add_action(declare_learning_enabled)
    ld.add_action(declare_publish_visualization)
    ld.add_action(declare_max_prediction_age)
    ld.add_action(declare_update_frequency_hz)
    ld.add_action(declare_max_tracked_obstacles)
    ld.add_action(declare_kalman_process_noise)
    ld.add_action(declare_kalman_measurement_noise)
    ld.add_action(declare_collision_distance_threshold)
    ld.add_action(declare_publish_debug_info)
    ld.add_action(declare_model_path)
    ld.add_action(declare_goal_tolerance_meters)
    ld.add_action(declare_enable_adaptive_thresholds)
    ld.add_action(declare_adaptive_learning_rate)
    ld.add_action(declare_enable_multi_sensor_fusion)
    ld.add_action(declare_sensor_fusion_weight_lidar)
    ld.add_action(declare_sensor_fusion_weight_ultrasonic)
    ld.add_action(declare_sensor_fusion_weight_camera)
    ld.add_action(declare_sensor_fusion_weight_imu)

    # Add nodes
    ld.add_action(predictive_obstacle_avoidance_node)

    return ld
