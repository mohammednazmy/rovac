#!/usr/bin/env python3
"""
Launch file for Advanced Navigation Node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_advanced_navigation = DeclareLaunchArgument(
        "enable_advanced_navigation",
        default_value="true",
        description="Enable advanced navigation node",
    )

    declare_navigation_mode = DeclareLaunchArgument(
        "navigation_mode",
        default_value="hybrid",
        description="Navigation mode: basic, advanced, hybrid",
    )

    declare_path_planning_algorithm = DeclareLaunchArgument(
        "path_planning_algorithm",
        default_value="dl_neural",
        description="Path planning algorithm: dijkstra, astar, dl_neural, hybrid",
    )

    declare_obstacle_avoidance_algorithm = DeclareLaunchArgument(
        "obstacle_avoidance_algorithm",
        default_value="predictive",
        description="Obstacle avoidance algorithm: basic, advanced, predictive",
    )

    declare_enable_sensor_fusion = DeclareLaunchArgument(
        "enable_sensor_fusion",
        default_value="true",
        description="Enable sensor fusion for navigation",
    )

    declare_enable_predictive_avoidance = DeclareLaunchArgument(
        "enable_predictive_avoidance",
        default_value="true",
        description="Enable predictive obstacle avoidance",
    )

    declare_enable_behavior_tree = DeclareLaunchArgument(
        "enable_behavior_tree",
        default_value="true",
        description="Enable behavior tree integration",
    )

    declare_enable_edge_optimization = DeclareLaunchArgument(
        "enable_edge_optimization",
        default_value="true",
        description="Enable edge computing optimization",
    )

    declare_update_frequency_hz = DeclareLaunchArgument(
        "update_frequency_hz",
        default_value="10.0",
        description="Navigation update frequency (Hz)",
    )

    declare_goal_tolerance_meters = DeclareLaunchArgument(
        "goal_tolerance_meters",
        default_value="0.3",
        description="Goal reaching tolerance (meters)",
    )

    declare_safety_margin_meters = DeclareLaunchArgument(
        "safety_margin_meters",
        default_value="0.3",
        description="Safety margin for obstacle avoidance (meters)",
    )

    declare_max_linear_velocity = DeclareLaunchArgument(
        "max_linear_velocity",
        default_value="0.5",
        description="Maximum linear velocity (m/s)",
    )

    declare_max_angular_velocity = DeclareLaunchArgument(
        "max_angular_velocity",
        default_value="1.5",
        description="Maximum angular velocity (rad/s)",
    )

    declare_publish_visualization = DeclareLaunchArgument(
        "publish_visualization",
        default_value="true",
        description="Publish navigation visualization markers",
    )

    declare_log_navigation_data = DeclareLaunchArgument(
        "log_navigation_data",
        default_value="true",
        description="Log navigation data and statistics",
    )

    declare_enable_adaptive_planning = DeclareLaunchArgument(
        "enable_adaptive_planning",
        default_value="true",
        description="Enable adaptive path planning",
    )

    declare_planning_horizon_seconds = DeclareLaunchArgument(
        "planning_horizon_seconds",
        default_value="5.0",
        description="Path planning horizon (seconds)",
    )

    declare_enable_dynamic_obstacle_tracking = DeclareLaunchArgument(
        "enable_dynamic_obstacle_tracking",
        default_value="true",
        description="Enable dynamic obstacle tracking",
    )

    declare_obstacle_prediction_horizon = DeclareLaunchArgument(
        "obstacle_prediction_horizon",
        default_value="3.0",
        description="Obstacle prediction horizon (seconds)",
    )

    declare_enable_thermal_navigation = DeclareLaunchArgument(
        "enable_thermal_navigation",
        default_value="false",
        description="Enable thermal imaging for navigation",
    )

    declare_enable_multi_modal_fusion = DeclareLaunchArgument(
        "enable_multi_modal_fusion",
        default_value="true",
        description="Enable multi-modal sensor fusion",
    )

    declare_fusion_weight_lidar = DeclareLaunchArgument(
        "fusion_weight_lidar",
        default_value="0.4",
        description="Weight for LIDAR data in fusion",
    )

    declare_fusion_weight_ultrasonic = DeclareLaunchArgument(
        "fusion_weight_ultrasonic",
        default_value="0.3",
        description="Weight for ultrasonic data in fusion",
    )

    declare_fusion_weight_imu = DeclareLaunchArgument(
        "fusion_weight_imu",
        default_value="0.2",
        description="Weight for IMU data in fusion",
    )

    declare_fusion_weight_camera = DeclareLaunchArgument(
        "fusion_weight_camera",
        default_value="0.1",
        description="Weight for camera data in fusion",
    )

    # Advanced Navigation Node
    advanced_navigation_node = Node(
        package="rovac_enhanced",
        executable="advanced_navigation_node.py",
        name="advanced_navigation_node",
        output="screen",
        parameters=[
            {
                "enable_advanced_navigation": LaunchConfiguration(
                    "enable_advanced_navigation"
                ),
                "navigation_mode": LaunchConfiguration("navigation_mode"),
                "path_planning_algorithm": LaunchConfiguration(
                    "path_planning_algorithm"
                ),
                "obstacle_avoidance_algorithm": LaunchConfiguration(
                    "obstacle_avoidance_algorithm"
                ),
                "enable_sensor_fusion": LaunchConfiguration("enable_sensor_fusion"),
                "enable_predictive_avoidance": LaunchConfiguration(
                    "enable_predictive_avoidance"
                ),
                "enable_behavior_tree": LaunchConfiguration("enable_behavior_tree"),
                "enable_edge_optimization": LaunchConfiguration(
                    "enable_edge_optimization"
                ),
                "update_frequency_hz": LaunchConfiguration("update_frequency_hz"),
                "goal_tolerance_meters": LaunchConfiguration("goal_tolerance_meters"),
                "safety_margin_meters": LaunchConfiguration("safety_margin_meters"),
                "max_linear_velocity": LaunchConfiguration("max_linear_velocity"),
                "max_angular_velocity": LaunchConfiguration("max_angular_velocity"),
                "publish_visualization": LaunchConfiguration("publish_visualization"),
                "log_navigation_data": LaunchConfiguration("log_navigation_data"),
                "enable_adaptive_planning": LaunchConfiguration(
                    "enable_adaptive_planning"
                ),
                "planning_horizon_seconds": LaunchConfiguration(
                    "planning_horizon_seconds"
                ),
                "enable_dynamic_obstacle_tracking": LaunchConfiguration(
                    "enable_dynamic_obstacle_tracking"
                ),
                "obstacle_prediction_horizon": LaunchConfiguration(
                    "obstacle_prediction_horizon"
                ),
                "enable_thermal_navigation": LaunchConfiguration(
                    "enable_thermal_navigation"
                ),
                "enable_multi_modal_fusion": LaunchConfiguration(
                    "enable_multi_modal_fusion"
                ),
                "fusion_weight_lidar": LaunchConfiguration("fusion_weight_lidar"),
                "fusion_weight_ultrasonic": LaunchConfiguration(
                    "fusion_weight_ultrasonic"
                ),
                "fusion_weight_imu": LaunchConfiguration("fusion_weight_imu"),
                "fusion_weight_camera": LaunchConfiguration("fusion_weight_camera"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_advanced_navigation")),
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_advanced_navigation)
    ld.add_action(declare_navigation_mode)
    ld.add_action(declare_path_planning_algorithm)
    ld.add_action(declare_obstacle_avoidance_algorithm)
    ld.add_action(declare_enable_sensor_fusion)
    ld.add_action(declare_enable_predictive_avoidance)
    ld.add_action(declare_enable_behavior_tree)
    ld.add_action(declare_enable_edge_optimization)
    ld.add_action(declare_update_frequency_hz)
    ld.add_action(declare_goal_tolerance_meters)
    ld.add_action(declare_safety_margin_meters)
    ld.add_action(declare_max_linear_velocity)
    ld.add_action(declare_max_angular_velocity)
    ld.add_action(declare_publish_visualization)
    ld.add_action(declare_log_navigation_data)
    ld.add_action(declare_enable_adaptive_planning)
    ld.add_action(declare_planning_horizon_seconds)
    ld.add_action(declare_enable_dynamic_obstacle_tracking)
    ld.add_action(declare_obstacle_prediction_horizon)
    ld.add_action(declare_enable_thermal_navigation)
    ld.add_action(declare_enable_multi_modal_fusion)
    ld.add_action(declare_fusion_weight_lidar)
    ld.add_action(declare_fusion_weight_ultrasonic)
    ld.add_action(declare_fusion_weight_imu)
    ld.add_action(declare_fusion_weight_camera)

    # Add nodes
    ld.add_action(advanced_navigation_node)

    return ld
