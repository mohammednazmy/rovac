#!/usr/bin/env python3
"""
Launch file for Deep Reinforcement Learning Navigation Node
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_deep_rl_navigation = DeclareLaunchArgument(
        "enable_deep_rl_navigation",
        default_value="true",
        description="Enable Deep Reinforcement Learning Navigation",
    )

    declare_navigation_mode = DeclareLaunchArgument(
        "navigation_mode",
        default_value="dqn",
        description="Navigation mode: dqn or actor_critic",
    )

    declare_learning_enabled = DeclareLaunchArgument(
        "learning_enabled",
        default_value="true",
        description="Enable learning and model training",
    )

    declare_exploration_rate = DeclareLaunchArgument(
        "exploration_rate",
        default_value="0.3",
        description="Initial exploration rate for RL agent (0.0-1.0)",
    )

    declare_update_frequency_hz = DeclareLaunchArgument(
        "update_frequency_hz",
        default_value="10.0",
        description="Navigation update frequency in Hz",
    )

    declare_goal_tolerance_meters = DeclareLaunchArgument(
        "goal_tolerance_meters",
        default_value="0.3",
        description="Goal reaching tolerance in meters",
    )

    declare_safety_margin_meters = DeclareLaunchArgument(
        "safety_margin_meters",
        default_value="0.3",
        description="Safety margin for obstacle avoidance in meters",
    )

    declare_max_linear_velocity = DeclareLaunchArgument(
        "max_linear_velocity",
        default_value="0.5",
        description="Maximum linear velocity in m/s",
    )

    declare_max_angular_velocity = DeclareLaunchArgument(
        "max_angular_velocity",
        default_value="1.5",
        description="Maximum angular velocity in rad/s",
    )

    declare_publish_visualization = DeclareLaunchArgument(
        "publish_visualization",
        default_value="true",
        description="Publish navigation visualization markers",
    )

    declare_log_training_data = DeclareLaunchArgument(
        "log_training_data",
        default_value="true",
        description="Log training data and statistics",
    )

    declare_robot_radius = DeclareLaunchArgument(
        "robot_radius", default_value="0.15", description="Robot radius in meters"
    )

    declare_prediction_horizon = DeclareLaunchArgument(
        "prediction_horizon",
        default_value="5.0",
        description="Prediction horizon in seconds",
    )

    declare_behavior_tree_tick_rate = DeclareLaunchArgument(
        "behavior_tree_tick_rate",
        default_value="10.0",
        description="Behavior tree tick rate in Hz",
    )

    declare_enable_predictive_avoidance = DeclareLaunchArgument(
        "enable_predictive_avoidance",
        default_value="true",
        description="Enable predictive obstacle avoidance",
    )

    declare_risk_tolerance = DeclareLaunchArgument(
        "risk_tolerance",
        default_value="0.1",
        description="Acceptable collision probability (0.0-1.0)",
    )

    declare_response_time = DeclareLaunchArgument(
        "response_time",
        default_value="0.5",
        description="Time to react to obstacles in seconds",
    )

    # Deep RL Navigation Node
    deep_rl_navigation_node = Node(
        package="rovac_enhanced",
        executable="deep_rl_navigation_node.py",
        name="deep_rl_navigation_node",
        output="screen",
        parameters=[
            {
                "enable_deep_rl_navigation": LaunchConfiguration(
                    "enable_deep_rl_navigation"
                ),
                "navigation_mode": LaunchConfiguration("navigation_mode"),
                "learning_enabled": LaunchConfiguration("learning_enabled"),
                "exploration_rate": LaunchConfiguration("exploration_rate"),
                "update_frequency_hz": LaunchConfiguration("update_frequency_hz"),
                "goal_tolerance_meters": LaunchConfiguration("goal_tolerance_meters"),
                "safety_margin_meters": LaunchConfiguration("safety_margin_meters"),
                "max_linear_velocity": LaunchConfiguration("max_linear_velocity"),
                "max_angular_velocity": LaunchConfiguration("max_angular_velocity"),
                "publish_visualization": LaunchConfiguration("publish_visualization"),
                "log_training_data": LaunchConfiguration("log_training_data"),
                "robot_radius": LaunchConfiguration("robot_radius"),
                "prediction_horizon": LaunchConfiguration("prediction_horizon"),
                "behavior_tree_tick_rate": LaunchConfiguration(
                    "behavior_tree_tick_rate"
                ),
                "enable_predictive_avoidance": LaunchConfiguration(
                    "enable_predictive_avoidance"
                ),
                "risk_tolerance": LaunchConfiguration("risk_tolerance"),
                "response_time": LaunchConfiguration("response_time"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_deep_rl_navigation")),
    )

    # Behavior Tree Node (Integrated with Deep RL)
    behavior_tree_node = Node(
        package="rovac_enhanced",
        executable="behavior_tree_node.py",
        name="behavior_tree_node",
        output="screen",
        parameters=[
            {
                "enable_behavior_tree": LaunchConfiguration(
                    "enable_deep_rl_navigation"
                ),
                "tick_rate": LaunchConfiguration("behavior_tree_tick_rate"),
                "navigation_mode": LaunchConfiguration("navigation_mode"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_deep_rl_navigation")),
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
                "risk_tolerance": LaunchConfiguration("risk_tolerance"),
                "response_time": LaunchConfiguration("response_time"),
                "prediction_horizon": LaunchConfiguration("prediction_horizon"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_predictive_avoidance")),
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_deep_rl_navigation)
    ld.add_action(declare_navigation_mode)
    ld.add_action(declare_learning_enabled)
    ld.add_action(declare_exploration_rate)
    ld.add_action(declare_update_frequency_hz)
    ld.add_action(declare_goal_tolerance_meters)
    ld.add_action(declare_safety_margin_meters)
    ld.add_action(declare_max_linear_velocity)
    ld.add_action(declare_max_angular_velocity)
    ld.add_action(declare_publish_visualization)
    ld.add_action(declare_log_training_data)
    ld.add_action(declare_robot_radius)
    ld.add_action(declare_prediction_horizon)
    ld.add_action(declare_behavior_tree_tick_rate)
    ld.add_action(declare_enable_predictive_avoidance)
    ld.add_action(declare_risk_tolerance)
    ld.add_action(declare_response_time)

    # Add nodes
    ld.add_action(deep_rl_navigation_node)
    ld.add_action(behavior_tree_node)
    ld.add_action(predictive_obstacle_avoidance_node)

    return ld
