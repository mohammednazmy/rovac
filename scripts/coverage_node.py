#!/usr/bin/env python3
"""
coverage_node — Boustrophedon coverage planner for ROVAC.

Loads the current /map (occupancy grid), computes a safe back-and-forth
sweep path over the reachable free space, and dispatches the sequence
of waypoints to Nav2 via the NavigateThroughPoses action. Nav2 handles
the actual path execution (planner + controller + recovery) between
waypoints.

Philosophy: this is NOT a competitor to opennav_coverage / Fields2Cover
— those do much more sophisticated swath optimization and TSP-style
route planning. For a single indoor room with a ~30cm-wide robot, a
simple row-by-row boustrophedon over a grid covers 90%+ of floor with
a trivial fraction of the code.

Run:
  python3 scripts/coverage_node.py
  (requires: Nav2 stack running via mac_brain_launch.sh nav <map>)

Parameters:
  swath_width      : spacing between sweep rows (m). Default 0.30.
  robot_radius     : safety inflation around obstacles (m). Default 0.17.
                     Robot is 22x24.5cm, so half-diagonal ~16cm.
  min_span_length  : reject row sweeps shorter than this (m). Default 0.25.
  goal_tolerance   : hand this to Nav2 as waypoint acceptance radius (m).
                     Default 0.25 — generous, lets controller steer cleanly.
  preview_only     : if true, publish /coverage_path but don't dispatch.
                     Good for first dry run. Default false.
"""
import math
import sys

import numpy as np

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from nav_msgs.msg import OccupancyGrid, Path
    from geometry_msgs.msg import PoseStamped
    from nav2_msgs.action import NavigateThroughPoses
    from action_msgs.msg import GoalStatus
except ImportError as e:
    sys.exit(
        f"ERROR: ROS 2 Jazzy environment not sourced: {e}\n"
        "Run:  conda activate ros_jazzy && "
        "source ~/robots/rovac/config/ros2_env.sh"
    )


# ---- Helper: quaternion from yaw -------------------------------------------

def _yaw_to_quat(yaw: float):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


# ---- Main node -------------------------------------------------------------

class CoverageNode(Node):
    def __init__(self):
        super().__init__("coverage_node")

        self.declare_parameter("swath_width", 0.30)
        self.declare_parameter("robot_radius", 0.17)
        self.declare_parameter("min_span_length", 0.25)
        self.declare_parameter("goal_tolerance", 0.25)
        self.declare_parameter("preview_only", False)

        self.swath_width = self.get_parameter("swath_width").value
        self.robot_radius = self.get_parameter("robot_radius").value
        self.min_span_length = self.get_parameter("min_span_length").value
        self.goal_tolerance = self.get_parameter("goal_tolerance").value
        self.preview_only = self.get_parameter("preview_only").value

        self.map_msg: OccupancyGrid | None = None
        self.waypoints: list[tuple[float, float, float]] = []
        self._dispatched = False

        # /map is typically published as transient_local (latched). Subscribe
        # with matching QoS or we'll never receive it.
        map_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(OccupancyGrid, "/map", self._on_map, map_qos)

        # /coverage_path for Foxglove visualization
        self.path_pub = self.create_publisher(Path, "/coverage_path", 1)

        # Nav2 action client
        self.nav_client = ActionClient(self, NavigateThroughPoses,
                                       "navigate_through_poses")

        # Orchestration timer — fires until we've successfully dispatched
        self.create_timer(1.0, self._tick)

        self.get_logger().info(
            f"coverage_node up — swath_width={self.swath_width:.2f}m  "
            f"robot_radius={self.robot_radius:.2f}m  "
            f"preview_only={self.preview_only}"
        )
        self.get_logger().info("Waiting for /map and Nav2 action server...")

    # ---- Callbacks -----------------------------------------------------------

    def _on_map(self, msg: OccupancyGrid):
        if self.map_msg is not None:
            return  # one-shot — first map wins
        w, h = msg.info.width, msg.info.height
        res = msg.info.resolution
        self.get_logger().info(
            f"Got /map: {w}x{h} cells at {res:.3f} m/cell "
            f"({w * res:.2f}×{h * res:.2f} m total)"
        )
        self.map_msg = msg

    def _tick(self):
        if self._dispatched:
            return
        if self.map_msg is None:
            return
        if not self.nav_client.wait_for_server(timeout_sec=0.2):
            self.get_logger().info(
                "Nav2 action server /navigate_through_poses not ready — "
                "is nav2_launch.py running?"
            )
            return

        self.get_logger().info("Planning coverage path...")
        self.waypoints = self._plan_coverage()
        if not self.waypoints:
            self.get_logger().error("No waypoints produced — map empty or all inflated away")
            rclpy.shutdown()
            return

        self._publish_path()
        if self.preview_only:
            self.get_logger().info(
                f"preview_only=true — published {len(self.waypoints)} waypoints to "
                "/coverage_path. Not dispatching to Nav2. Shutting down."
            )
            self._dispatched = True
            rclpy.shutdown()
            return

        self._dispatch()
        self._dispatched = True

    # ---- Coverage planning --------------------------------------------------

    def _plan_coverage(self):
        """
        Returns a list of (x, y, yaw) in the map frame.

        Algorithm:
          1. Classify cells: free (0), occupied (>=65), unknown (-1).
             Treat unknown as obstacle for safety.
          2. Dilate obstacles by robot_radius / resolution cells.
          3. For each row (at swath_width spacing), find contiguous runs
             of safe-free cells. Skip runs shorter than min_span_length.
          4. For each run, emit two waypoints (left-to-right, then right-
             to-left on the next row — the boustrophedon pattern).
          5. Convert grid indices → map-frame coordinates using
             msg.info.origin and resolution.
        """
        info = self.map_msg.info
        res = info.resolution
        w, h = info.width, info.height
        data = np.array(self.map_msg.data, dtype=np.int8).reshape(h, w)

        free = data == 0
        # CONFIRMED obstacles only (walls). Do NOT treat unknown (-1) as an
        # obstacle for inflation — on a real SLAM map, unknown cells ring the
        # edges of every explored area, and inflating around them captures
        # most of the free floor. Nav2's local costmap + LIDAR watches for
        # actual obstacles during execution, so we don't need to pre-inflate
        # unknown space.
        confirmed_obstacle = data >= 65

        # Obstacle inflation — robot footprint safety margin.
        # Pure-numpy binary dilation with a square structuring element: shift
        # the mask by every (dy, dx) in the kernel radius and OR them together.
        # At inflate_cells=4 that's 81 OR ops of a small 2D array — trivial.
        # (Avoids a scipy.ndimage dependency that's been fragile in this conda
        # env due to LAPACK ABI shenanigans.)
        inflate_cells = max(1, int(math.ceil(self.robot_radius / res)))
        inflated_obstacle = _binary_dilate(confirmed_obstacle, inflate_cells)

        # Safe to traverse: confirmed-free AND not-too-close-to-a-wall.
        # Unknown cells stay OUT of safe (we don't plan waypoints there)
        # but they also don't infect the free cells via inflation.
        safe = free & ~inflated_obstacle
        n_safe = int(np.sum(safe))
        self.get_logger().info(
            f"Cells:  free={int(free.sum())}  "
            f"confirmed_obstacle={int(confirmed_obstacle.sum())}  "
            f"inflated_obstacle={int(inflated_obstacle.sum())}  "
            f"safe={n_safe} (inflation radius = {inflate_cells} cells = "
            f"{inflate_cells * res:.2f}m)"
        )

        if n_safe == 0:
            return []

        swath_cells = max(1, int(round(self.swath_width / res)))
        min_span_cells = max(1, int(round(self.min_span_length / res)))

        # Boustrophedon: iterate rows, alternate direction
        waypoints = []
        direction = 1  # +1 = left→right, -1 = right→left

        for row in range(0, h, swath_cells):
            runs = _contiguous_runs(safe[row])
            if not runs:
                continue
            # Keep only runs long enough to justify sweeping
            runs = [(a, b) for (a, b) in runs if (b - a + 1) >= min_span_cells]
            if not runs:
                continue

            # Order runs along the current sweep direction so adjacent runs in
            # this row are visited in a sensible sequence
            if direction == -1:
                runs = sorted(runs, key=lambda r: -r[0])
            else:
                runs = sorted(runs, key=lambda r: r[0])

            for a, b in runs:
                if direction == 1:
                    waypoints.append((a, row))
                    waypoints.append((b, row))
                else:
                    waypoints.append((b, row))
                    waypoints.append((a, row))

            direction = -direction

        # Grid → map frame
        origin_x = info.origin.position.x
        origin_y = info.origin.position.y
        map_wps: list[tuple[float, float, float]] = []
        for i, (col, row) in enumerate(waypoints):
            x = origin_x + (col + 0.5) * res
            y = origin_y + (row + 0.5) * res
            if i == 0:
                yaw = 0.0
            else:
                px, py, _ = map_wps[-1]
                yaw = math.atan2(y - py, x - px)
            map_wps.append((x, y, yaw))

        self.get_logger().info(
            f"Plan: {len(map_wps)} waypoints across "
            f"~{len([1 for i in range(0, h, swath_cells)])} rows"
        )
        return map_wps

    # ---- ROS wiring ----------------------------------------------------------

    def _publish_path(self):
        path = Path()
        path.header.frame_id = "map"
        path.header.stamp = self.get_clock().now().to_msg()
        for (x, y, yaw) in self.waypoints:
            pose = PoseStamped()
            pose.header = path.header
            pose.pose.position.x = float(x)
            pose.pose.position.y = float(y)
            qx, qy, qz, qw = _yaw_to_quat(yaw)
            pose.pose.orientation.x = qx
            pose.pose.orientation.y = qy
            pose.pose.orientation.z = qz
            pose.pose.orientation.w = qw
            path.poses.append(pose)
        self.path_pub.publish(path)
        self.get_logger().info(
            f"Published /coverage_path with {len(path.poses)} poses. "
            "View in Foxglove 3D panel, map frame."
        )

    def _dispatch(self):
        goal = NavigateThroughPoses.Goal()
        # Explicit BT path — belt-and-suspenders in case bt_navigator's
        # default_nav_through_poses_bt_xml param resolution is flaky.
        # The NavigateThroughPoses action has a `behavior_tree` field
        # that overrides the default.
        goal.behavior_tree = (
            "/opt/homebrew/Caskroom/miniforge/base/envs/ros_jazzy/"
            "share/nav2_bt_navigator/behavior_trees/"
            "navigate_through_poses_w_replanning_and_recovery.xml"
        )
        now = self.get_clock().now().to_msg()
        for (x, y, yaw) in self.waypoints:
            p = PoseStamped()
            p.header.frame_id = "map"
            p.header.stamp = now
            p.pose.position.x = float(x)
            p.pose.position.y = float(y)
            qx, qy, qz, qw = _yaw_to_quat(yaw)
            p.pose.orientation.x = qx
            p.pose.orientation.y = qy
            p.pose.orientation.z = qz
            p.pose.orientation.w = qw
            goal.poses.append(p)

        self.get_logger().info(
            f"Sending {len(goal.poses)} waypoints to Nav2 "
            "(NavigateThroughPoses)..."
        )
        send_future = self.nav_client.send_goal_async(
            goal, feedback_callback=self._on_feedback
        )
        send_future.add_done_callback(self._on_goal_response)

    def _on_feedback(self, fb_msg):
        fb = fb_msg.feedback
        # number_of_poses_remaining is the standard feedback field
        remaining = getattr(fb, "number_of_poses_remaining", None)
        if remaining is not None:
            self.get_logger().info(
                f"  progress: {remaining} waypoints remaining"
            )

    def _on_goal_response(self, future):
        handle = future.result()
        if not handle.accepted:
            self.get_logger().error("Nav2 REJECTED the goal. Stopping.")
            rclpy.shutdown()
            return
        self.get_logger().info("Nav2 accepted the coverage goal. Executing...")
        result_future = handle.get_result_async()
        result_future.add_done_callback(self._on_result)

    def _on_result(self, future):
        result_wrapper = future.result()
        status = result_wrapper.status
        status_str = {
            GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
            GoalStatus.STATUS_ABORTED: "ABORTED",
            GoalStatus.STATUS_CANCELED: "CANCELED",
        }.get(status, f"unknown({status})")
        self.get_logger().info(
            f"Coverage complete: status={status_str} "
            "— you can power-cycle the vacuum now."
        )
        rclpy.shutdown()


def _contiguous_runs(row: np.ndarray) -> list[tuple[int, int]]:
    """Find [start, end] indices of consecutive True runs in a 1D bool array."""
    if not np.any(row):
        return []
    padded = np.concatenate([[False], row, [False]])
    diff = np.diff(padded.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0] - 1
    return list(zip(starts.tolist(), ends.tolist()))


def _binary_dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """
    2D binary morphological dilation with a square (2*radius+1)^2 kernel.
    Equivalent to scipy.ndimage.binary_dilation(mask, structure=ones((N,N))).
    Pure numpy so we don't pull scipy into the conda env's LAPACK trap.
    """
    if radius <= 0:
        return mask.astype(bool, copy=False)
    mask = mask.astype(bool, copy=False)
    h, w = mask.shape
    # Pad with False on all sides so we can shift without wrapping
    padded = np.zeros((h + 2 * radius, w + 2 * radius), dtype=bool)
    padded[radius:radius + h, radius:radius + w] = mask
    out = np.zeros_like(mask)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out |= padded[radius + dy:radius + dy + h,
                          radius + dx:radius + dx + w]
    return out


def main():
    rclpy.init()
    node = CoverageNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Ctrl-C — canceling any active goal")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
