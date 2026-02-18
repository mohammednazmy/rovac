#!/usr/bin/env python3
"""
Launch file for enhanced ROVAC system with health monitoring, sensor fusion,
obstacle avoidance, frontier exploration, diagnostics collection, object recognition,
behavior tree framework, edge computing optimization, deep learning path planning,
predictive analytics, and thermal imaging.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    declare_enable_health_monitor = DeclareLaunchArgument(
        "enable_health_monitor",
        default_value="true",
        description="Enable system health monitoring",
    )

    declare_enable_sensor_fusion = DeclareLaunchArgument(
        "enable_sensor_fusion",
        default_value="true",
        description="Enable sensor fusion node",
    )

    declare_enable_obstacle_avoidance = DeclareLaunchArgument(
        "enable_obstacle_avoidance",
        default_value="true",
        description="Enable obstacle avoidance node",
    )

    declare_enable_frontier_exploration = DeclareLaunchArgument(
        "enable_frontier_exploration",
        default_value="false",
        description="Enable frontier exploration node",
    )

    declare_enable_diagnostics = DeclareLaunchArgument(
        "enable_diagnostics",
        default_value="true",
        description="Enable diagnostics collection",
    )

    declare_enable_object_recognition = DeclareLaunchArgument(
        "enable_object_recognition",
        default_value="true",
        description="Enable object recognition node",
    )

    declare_object_confidence_threshold = DeclareLaunchArgument(
        "object_confidence_threshold",
        default_value="0.5",
        description="Object detection confidence threshold",
    )

    declare_object_frame_skip = DeclareLaunchArgument(
        "object_frame_skip",
        default_value="5",
        description="Process every nth frame for object recognition",
    )

    declare_enable_behavior_tree = DeclareLaunchArgument(
        "enable_behavior_tree",
        default_value="true",
        description="Enable behavior tree framework",
    )

    declare_behavior_tree_tick_rate = DeclareLaunchArgument(
        "behavior_tree_tick_rate",
        default_value="10.0",
        description="Behavior tree tick rate (Hz)",
    )

    declare_enable_edge_optimization = DeclareLaunchArgument(
        "enable_edge_optimization",
        default_value="true",
        description="Enable edge computing optimization",
    )

    declare_process_on_pi = DeclareLaunchArgument(
        "process_on_pi",
        default_value="true",
        description="Process data on Raspberry Pi",
    )

    declare_compression_ratio = DeclareLaunchArgument(
        "compression_ratio",
        default_value="0.5",
        description="Data compression ratio (0.1-1.0)",
    )

    declare_batch_size = DeclareLaunchArgument(
        "processing_batch_size",
        default_value="10",
        description="Number of items to process in batch",
    )

    declare_enable_dl_planning = DeclareLaunchArgument(
        "enable_dl_planning",
        default_value="true",
        description="Enable deep learning path planning",
    )

    declare_model_path = DeclareLaunchArgument(
        "model_path",
        default_value="",
        description="Path to trained neural network model",
    )

    declare_publish_visualization = DeclareLaunchArgument(
        "publish_visualization",
        default_value="true",
        description="Publish path visualization markers",
    )

    declare_dl_update_rate = DeclareLaunchArgument(
        "dl_update_rate_hz",
        default_value="1.0",
        description="Deep learning path planning update rate (Hz)",
    )

    declare_enable_predictive_analytics = DeclareLaunchArgument(
        "enable_predictive_analytics",
        default_value="true",
        description="Enable predictive analytics and maintenance forecasting",
    )

    declare_data_collection_interval = DeclareLaunchArgument(
        "data_collection_interval",
        default_value="1.0",
        description="Data collection interval in seconds",
    )

    declare_report_generation_interval = DeclareLaunchArgument(
        "report_generation_interval",
        default_value="10.0",
        description="Report generation interval in seconds",
    )

    declare_enable_thermal_imaging = DeclareLaunchArgument(
        "enable_thermal_imaging",
        default_value="true",
        description="Enable thermal imaging node",
    )

    declare_use_emulation = DeclareLaunchArgument(
        "use_emulation",
        default_value="true",
        description="Use emulation mode instead of hardware camera",
    )

    declare_spi_device = DeclareLaunchArgument(
        "spi_device",
        default_value="/dev/spidev0.0",
        description="SPI device for FLIR Lepton camera",
    )

    declare_thermal_frame_rate = DeclareLaunchArgument(
        "thermal_frame_rate",
        default_value="9.0",
        description="Thermal camera frame rate (Hz)",
    )

    declare_thermal_detection_sensitivity = DeclareLaunchArgument(
        "thermal_detection_sensitivity",
        default_value="medium",
        description="Thermal detection sensitivity (high, medium, low)",
    )

    # Health Monitoring Node
    health_monitor_node = Node(
        package="rovac_enhanced",
        executable="system_health_monitor.py",
        name="system_health_monitor",
        output="screen",
        condition=IfCondition(LaunchConfiguration("enable_health_monitor")),
    )

    # Sensor Fusion Node
    sensor_fusion_node = Node(
        package="rovac_enhanced",
        executable="sensor_fusion_node.py",
        name="sensor_fusion_node",
        output="screen",
        parameters=[{"min_obstacle_distance": 0.3}, {"fusion_enabled": True}],
        condition=IfCondition(LaunchConfiguration("enable_sensor_fusion")),
    )

    # Obstacle Avoidance Node
    obstacle_avoidance_node = Node(
        package="rovac_enhanced",
        executable="obstacle_avoidance_node.py",
        name="obstacle_avoidance_node",
        output="screen",
        parameters=[
            {"min_distance": 0.4},
            {"max_linear_speed": 0.3},
            {"max_angular_speed": 1.0},
            {"enable_avoidance": True},
        ],
        condition=IfCondition(LaunchConfiguration("enable_obstacle_avoidance")),
    )

    # Frontier Exploration Node
    frontier_exploration_node = Node(
        package="rovac_enhanced",
        executable="frontier_exploration_node.py",
        name="frontier_exploration_node",
        output="screen",
        parameters=[
            {"exploration_rate": 0.5},
            {"frontier_min_size": 5},
            {"goal_distance_threshold": 0.5},
            {"enable_exploration": LaunchConfiguration("enable_frontier_exploration")},
        ],
        condition=IfCondition(LaunchConfiguration("enable_frontier_exploration")),
    )

    # Diagnostics Collector Node
    diagnostics_collector_node = Node(
        package="rovac_enhanced",
        executable="diagnostics_collector.py",
        name="diagnostics_collector",
        output="screen",
        parameters=[
            {"log_directory": "/tmp/rovac_logs"},
            {"collection_interval": 30.0},
            {"max_log_files": 10},
        ],
        condition=IfCondition(LaunchConfiguration("enable_diagnostics")),
    )

    # Object Recognition Node
    object_recognition_node = Node(
        package="rovac_enhanced",
        executable="object_recognition_node.py",
        name="object_recognition_node",
        output="screen",
        parameters=[
            {
                "confidence_threshold": LaunchConfiguration(
                    "object_confidence_threshold"
                )
            },
            {"frame_skip": LaunchConfiguration("object_frame_skip")},
        ],
        condition=IfCondition(LaunchConfiguration("enable_object_recognition")),
    )

    # Behavior Tree Node
    behavior_tree_node = Node(
        package="rovac_enhanced",
        executable="behavior_tree_node.py",
        name="behavior_tree_node",
        output="screen",
        parameters=[
            {
                "enable_behavior_tree": LaunchConfiguration("enable_behavior_tree"),
                "tick_rate": LaunchConfiguration("behavior_tree_tick_rate"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_behavior_tree")),
    )

    # Edge Optimization Node
    edge_optimization_node = Node(
        package="rovac_enhanced",
        executable="edge_optimization_node.py",
        name="edge_optimization_node",
        output="screen",
        parameters=[
            {
                "enable_edge_processing": LaunchConfiguration(
                    "enable_edge_optimization"
                ),
                "process_on_pi": LaunchConfiguration("process_on_pi"),
                "compression_ratio": LaunchConfiguration("compression_ratio"),
                "processing_batch_size": LaunchConfiguration("processing_batch_size"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_edge_optimization")),
    )

    # Deep Learning Path Planning Node
    dl_path_planning_node = Node(
        package="rovac_enhanced",
        executable="dl_path_planning_node.py",
        name="dl_path_planning_node",
        output="screen",
        parameters=[
            {
                "enable_dl_planning": LaunchConfiguration("enable_dl_planning"),
                "model_path": LaunchConfiguration("model_path"),
                "publish_visualization": LaunchConfiguration("publish_visualization"),
                "update_rate_hz": LaunchConfiguration("dl_update_rate_hz"),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_dl_planning")),
    )

    # Predictive Analytics Node
    predictive_analytics_node = Node(
        package="rovac_enhanced",
        executable="predictive_analytics_node.py",
        name="predictive_analytics_node",
        output="screen",
        parameters=[
            {
                "enable_predictive_analytics": LaunchConfiguration(
                    "enable_predictive_analytics"
                ),
                "data_collection_interval": LaunchConfiguration(
                    "data_collection_interval"
                ),
                "report_generation_interval": LaunchConfiguration(
                    "report_generation_interval"
                ),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_predictive_analytics")),
    )

    # Thermal Imaging Node
    thermal_imaging_node = Node(
        package="rovac_enhanced",
        executable="thermal_imaging_node.py",
        name="thermal_imaging_node",
        output="screen",
        parameters=[
            {
                "enable_thermal_imaging": LaunchConfiguration("enable_thermal_imaging"),
                "use_emulation": LaunchConfiguration("use_emulation"),
                "spi_device": LaunchConfiguration("spi_device"),
                "frame_rate": LaunchConfiguration("thermal_frame_rate"),
                "publish_visualization": LaunchConfiguration("publish_visualization"),
                "detection_sensitivity": LaunchConfiguration(
                    "thermal_detection_sensitivity"
                ),
            }
        ],
        condition=IfCondition(LaunchConfiguration("enable_thermal_imaging")),
    )

    # Create the launch description
    ld = LaunchDescription()

    # Add declarations
    ld.add_action(declare_enable_health_monitor)
    ld.add_action(declare_enable_sensor_fusion)
    ld.add_action(declare_enable_obstacle_avoidance)
    ld.add_action(declare_enable_frontier_exploration)
    ld.add_action(declare_enable_diagnostics)
    ld.add_action(declare_enable_object_recognition)
    ld.add_action(declare_object_confidence_threshold)
    ld.add_action(declare_object_frame_skip)
    ld.add_action(declare_enable_behavior_tree)
    ld.add_action(declare_behavior_tree_tick_rate)
    ld.add_action(declare_enable_edge_optimization)
    ld.add_action(declare_process_on_pi)
    ld.add_action(declare_compression_ratio)
    ld.add_action(declare_batch_size)
    ld.add_action(declare_enable_dl_planning)
    ld.add_action(declare_model_path)
    ld.add_action(declare_publish_visualization)
    ld.add_action(declare_dl_update_rate)
    ld.add_action(declare_enable_predictive_analytics)
    ld.add_action(declare_data_collection_interval)
    ld.add_action(declare_report_generation_interval)
    ld.add_action(declare_enable_thermal_imaging)
    ld.add_action(declare_use_emulation)
    ld.add_action(declare_spi_device)
    ld.add_action(declare_thermal_frame_rate)
    ld.add_action(declare_thermal_detection_sensitivity)

    # Add nodes
    ld.add_action(health_monitor_node)
    ld.add_action(sensor_fusion_node)
    ld.add_action(obstacle_avoidance_node)
    ld.add_action(frontier_exploration_node)
    ld.add_action(diagnostics_collector_node)
    ld.add_action(object_recognition_node)
    ld.add_action(behavior_tree_node)
    ld.add_action(edge_optimization_node)
    ld.add_action(dl_path_planning_node)
    ld.add_action(predictive_analytics_node)
    ld.add_action(thermal_imaging_node)

    return ld
