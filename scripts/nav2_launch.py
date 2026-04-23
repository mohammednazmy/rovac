"""
nav2_launch.py — Custom Nav2 bringup for ROVAC.

RoboStack/conda-forge does not package nav2_bringup for macOS (osx-arm64),
so we can't use nav2_bringup's canonical bringup_launch.py. All the
individual Nav2 components ARE packaged, so this launch file wires them
up the same way nav2_bringup would.

Starts:
  - nav2_map_server        → serves the static map (/map + /map_metadata)
  - nav2_amcl              → particle-filter localization (map ← → odom TF)
  - nav2_planner           → global path planner (/plan)
  - nav2_controller        → local controller (/cmd_vel_nav → /cmd_vel_smoothed via smoother)
  - nav2_behaviors         → recovery behaviors (backup, spin, wait)
  - nav2_bt_navigator      → behavior tree orchestrator (NavigateToPose action)
  - nav2_waypoint_follower → multi-goal NavigateThroughPoses
  - nav2_velocity_smoother → /cmd_vel_nav → /cmd_vel_smoothed
  - nav2_lifecycle_manager → brings the above up in order, manages activation

Usage (from mac_brain_launch.sh nav <map>):
  ros2 launch ~/robots/rovac/scripts/nav2_launch.py \\
       map:=/path/to/map.yaml \\
       params_file:=~/robots/rovac/config/nav2_params.yaml
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    map_arg = DeclareLaunchArgument(
        "map", description="Full path to the .yaml map file"
    )
    params_arg = DeclareLaunchArgument(
        "params_file",
        description="Full path to the Nav2 params yaml",
    )
    use_sim_time_arg = DeclareLaunchArgument(
        "use_sim_time", default_value="false"
    )

    map_yaml = LaunchConfiguration("map")
    params = LaunchConfiguration("params_file")
    use_sim_time = LaunchConfiguration("use_sim_time")

    # Lifecycle nodes managed by lifecycle_manager (order matters — map + amcl
    # first so TF map→odom exists before planners need it).
    lifecycle_nodes = [
        "map_server",
        "amcl",
        "controller_server",
        "planner_server",
        "behavior_server",
        "velocity_smoother",
        "waypoint_follower",
        "bt_navigator",
    ]

    # Remap velocity_smoother's input so controller_server's /cmd_vel flows
    # into the smoother, which then outputs /cmd_vel_smoothed consumed by our
    # priority mux on the Pi.
    smoother_remaps = [("cmd_vel", "cmd_vel_nav"),
                       ("cmd_vel_smoothed", "cmd_vel_smoothed")]

    # controller_server publishes to /cmd_vel by default; we want it to publish
    # to /cmd_vel_nav so the smoother can pick it up and emit /cmd_vel_smoothed.
    controller_remaps = [("cmd_vel", "cmd_vel_nav")]

    nodes = [
        Node(
            package="nav2_map_server",
            executable="map_server",
            name="map_server",
            output="screen",
            parameters=[
                params,
                {"use_sim_time": use_sim_time, "yaml_filename": map_yaml},
            ],
        ),
        Node(
            package="nav2_amcl",
            executable="amcl",
            name="amcl",
            output="screen",
            parameters=[params, {"use_sim_time": use_sim_time}],
        ),
        Node(
            package="nav2_controller",
            executable="controller_server",
            name="controller_server",
            output="screen",
            parameters=[params, {"use_sim_time": use_sim_time}],
            remappings=controller_remaps,
        ),
        Node(
            package="nav2_planner",
            executable="planner_server",
            name="planner_server",
            output="screen",
            parameters=[params, {"use_sim_time": use_sim_time}],
        ),
        Node(
            package="nav2_behaviors",
            executable="behavior_server",
            name="behavior_server",
            output="screen",
            parameters=[params, {"use_sim_time": use_sim_time}],
        ),
        Node(
            package="nav2_velocity_smoother",
            executable="velocity_smoother",
            name="velocity_smoother",
            output="screen",
            parameters=[params, {"use_sim_time": use_sim_time}],
            remappings=smoother_remaps,
        ),
        Node(
            package="nav2_waypoint_follower",
            executable="waypoint_follower",
            name="waypoint_follower",
            output="screen",
            parameters=[params, {"use_sim_time": use_sim_time}],
        ),
        Node(
            package="nav2_bt_navigator",
            executable="bt_navigator",
            name="bt_navigator",
            output="screen",
            parameters=[params, {"use_sim_time": use_sim_time}],
        ),
        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_navigation",
            output="screen",
            parameters=[
                {
                    "use_sim_time": use_sim_time,
                    "autostart": True,
                    "node_names": lifecycle_nodes,
                }
            ],
        ),
    ]

    return LaunchDescription(
        [map_arg, params_arg, use_sim_time_arg, *nodes]
    )
