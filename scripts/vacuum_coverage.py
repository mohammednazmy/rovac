#!/usr/bin/env python3
"""ROVAC Autonomous Vacuum Coverage Planner

Room-by-room boustrophedon coverage using Nav2.

Usage:
  1. Create a map:
       ./scripts/mac_brain_launch.sh slam
       # drive around, then in another terminal:
       mkdir -p ~/maps
       ros2 run nav2_map_server map_saver_cli -f ~/maps/house \\
           --ros-args -p map_subscribe_transient_local:=true

  2. Launch navigation:
       ./scripts/mac_brain_launch.sh nav ~/maps/house.yaml

  3. Run coverage:
       python3 scripts/vacuum_coverage.py ~/maps/house.yaml
"""

import math
import os
import sys
import time

import numpy as np
import yaml
from scipy import ndimage

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy

from nav2_msgs.action import FollowWaypoints
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import ColorRGBA
from visualization_msgs.msg import Marker, MarkerArray


# ── Room colors for visualization ────────────────────────────────────
ROOM_COLORS = [
    (0.2, 0.6, 1.0),   # blue
    (1.0, 0.4, 0.2),   # orange
    (0.2, 0.8, 0.4),   # green
    (0.8, 0.2, 0.8),   # purple
    (1.0, 0.8, 0.2),   # yellow
    (0.2, 0.8, 0.8),   # cyan
    (1.0, 0.4, 0.6),   # pink
    (0.6, 0.4, 0.2),   # brown
]


class VacuumCoverage(Node):
    def __init__(self, map_yaml_path):
        super().__init__('vacuum_coverage')

        # ── Tunable parameters ───────────────────────────────────────
        self.declare_parameter('robot_radius', 0.15)
        self.declare_parameter('sweep_width', 0.25)
        self.declare_parameter('wall_margin', 0.20)
        self.declare_parameter('doorway_width', 0.60)

        self.robot_radius = self.get_parameter('robot_radius').value
        self.sweep_width = self.get_parameter('sweep_width').value
        self.wall_margin = self.get_parameter('wall_margin').value
        self.doorway_width = self.get_parameter('doorway_width').value

        self.get_logger().info(
            f'Coverage params: radius={self.robot_radius}m, sweep={self.sweep_width}m, '
            f'margin={self.wall_margin}m, doorway={self.doorway_width}m'
        )

        # ── Load and process map ─────────────────────────────────────
        self.map_image, self.resolution, self.origin = self._load_map(map_yaml_path)
        self.get_logger().info(
            f'Map loaded: {self.map_image.shape[1]}x{self.map_image.shape[0]} '
            f'at {self.resolution}m/px, origin=({self.origin[0]:.2f}, {self.origin[1]:.2f})'
        )

        safe_map = self._erode_map(self.map_image)
        room_labels, num_rooms = self._segment_rooms(safe_map)

        # ── Plan coverage waypoints per room ─────────────────────────
        room_waypoints = []
        for room_id in range(1, num_rooms + 1):
            room_mask = (room_labels == room_id)
            wps = self._boustrophedon_sweep(room_mask)
            if wps:
                room_waypoints.append(wps)
                self.get_logger().info(
                    f'  Room {room_id}: {len(wps)} waypoints'
                )

        if not room_waypoints:
            self.get_logger().error('No rooms with navigable space found!')
            return

        # ── Order rooms by proximity ─────────────────────────────────
        ordered = self._order_rooms(room_waypoints)
        total_wps = sum(len(r) for r in ordered)
        self.get_logger().info(
            f'Coverage plan: {num_rooms} rooms, {total_wps} total waypoints'
        )

        # ── Visualization publisher ──────────────────────────────────
        self.marker_pub = self.create_publisher(
            MarkerArray, '/vacuum/coverage_plan', 10
        )
        self._publish_plan_markers(ordered)

        # ── Nav2 waypoint follower action client ─────────────────────
        self.wp_client = ActionClient(self, FollowWaypoints, 'follow_waypoints')
        self.current_room = 0
        self.rooms = ordered

        # Start execution after a short delay (let Foxglove see the plan)
        self.create_timer(3.0, self._start_coverage, callback_group=None)

    # ═════════════════════════════════════════════════════════════════
    #  MAP LOADING
    # ═════════════════════════════════════════════════════════════════

    def _load_map(self, yaml_path):
        """Load a Nav2 map_saver map (YAML + PGM)."""
        with open(yaml_path) as f:
            info = yaml.safe_load(f)

        pgm_path = info['image']
        if not os.path.isabs(pgm_path):
            pgm_path = os.path.join(os.path.dirname(yaml_path), pgm_path)

        # Read PGM as numpy array (white=free, black=occupied, gray=unknown)
        img = self._read_pgm(pgm_path)

        resolution = float(info['resolution'])
        origin = info.get('origin', [0.0, 0.0, 0.0])
        thresh = info.get('free_thresh', 0.196)

        # Binary free-space mask: pixel value > threshold means free
        # PGM values: 254=free, 205=unknown, 0=occupied
        free_threshold = int((1.0 - thresh) * 255)
        free_mask = (img >= free_threshold).astype(np.uint8)

        return free_mask, resolution, origin

    @staticmethod
    def _read_pgm(path):
        """Read a PGM file into a numpy array."""
        with open(path, 'rb') as f:
            magic = f.readline().strip()
            if magic not in (b'P5', b'P2'):
                raise ValueError(f'Not a PGM file: {magic}')
            # Skip comments
            line = f.readline()
            while line.startswith(b'#'):
                line = f.readline()
            width, height = map(int, line.split())
            maxval = int(f.readline().strip())
            if magic == b'P5':
                dtype = np.uint16 if maxval > 255 else np.uint8
                data = np.frombuffer(f.read(), dtype=dtype)
            else:
                data = np.array(f.read().split(), dtype=np.uint8)
        return data.reshape((height, width))

    # ═════════════════════════════════════════════════════════════════
    #  MAP PROCESSING
    # ═════════════════════════════════════════════════════════════════

    def _erode_map(self, free_mask):
        """Erode free space by wall_margin to create safe navigable area."""
        margin_px = max(1, int(self.wall_margin / self.resolution))
        y, x = np.ogrid[-margin_px:margin_px + 1, -margin_px:margin_px + 1]
        disk = (x * x + y * y <= margin_px * margin_px)
        eroded = ndimage.binary_erosion(free_mask, structure=disk)
        navigable_pct = eroded.sum() / max(free_mask.sum(), 1) * 100
        self.get_logger().info(
            f'Eroded by {self.wall_margin}m: {navigable_pct:.0f}% of free space navigable'
        )
        return eroded.astype(np.uint8)

    def _segment_rooms(self, safe_map):
        """Segment the map into rooms by detecting doorways.

        Strategy: morphologically open the safe map with a disk kernel
        sized to the doorway width. This "pinches off" narrow passages
        (doorways), splitting connected free space into separate rooms.
        Then expand room labels back to fill the original safe_map.
        """
        doorway_px = max(2, int(self.doorway_width / self.resolution))
        radius = doorway_px // 2

        # Create disk kernel for morphological opening
        y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
        disk = (x * x + y * y <= radius * radius)

        # Opening = erosion + dilation: removes features narrower than kernel
        opened = ndimage.binary_opening(safe_map, structure=disk)

        # Label connected components in the opened map
        labeled, num_rooms = ndimage.label(opened)

        if num_rooms == 0:
            # Fallback: treat entire safe map as one room
            self.get_logger().warn(
                'Room segmentation found 0 rooms — treating map as single room'
            )
            labeled = safe_map.copy()
            labeled[labeled > 0] = 1
            num_rooms = 1
        else:
            # Expand labels back to original safe_map extent.
            # Doorway pixels (safe but removed by opening) get assigned
            # to the nearest room via distance transform.
            unlabeled_safe = (safe_map > 0) & (labeled == 0)
            if unlabeled_safe.any():
                # For each room, compute distance from labeled pixels
                # Assign unlabeled pixels to nearest room
                distances = np.full(
                    (num_rooms, *safe_map.shape), np.inf, dtype=np.float32
                )
                for i in range(num_rooms):
                    room_mask = (labeled == (i + 1))
                    distances[i] = ndimage.distance_transform_edt(~room_mask)
                nearest_room = distances.argmin(axis=0) + 1
                labeled[unlabeled_safe] = nearest_room[unlabeled_safe]

        # Filter out tiny rooms (< 0.5 m^2)
        min_room_pixels = int(0.5 / (self.resolution ** 2))
        for room_id in range(1, num_rooms + 1):
            if (labeled == room_id).sum() < min_room_pixels:
                labeled[labeled == room_id] = 0

        # Re-label to remove gaps
        unique_ids = sorted(set(labeled[labeled > 0]))
        relabeled = np.zeros_like(labeled)
        for new_id, old_id in enumerate(unique_ids, 1):
            relabeled[labeled == old_id] = new_id

        final_count = len(unique_ids)
        self.get_logger().info(
            f'Room segmentation: {final_count} rooms '
            f'(doorway_width={self.doorway_width}m = {doorway_px}px)'
        )
        return relabeled, final_count

    # ═════════════════════════════════════════════════════════════════
    #  BOUSTROPHEDON SWEEP
    # ═════════════════════════════════════════════════════════════════

    def _boustrophedon_sweep(self, room_mask):
        """Generate zigzag sweep waypoints for a single room.

        Sweeps in horizontal rows (Y-axis), spacing rows by sweep_width.
        Each row produces a start and end waypoint at the leftmost and
        rightmost navigable pixel. Direction alternates each row.
        """
        rows_with_free = np.where(room_mask.any(axis=1))[0]
        if len(rows_with_free) == 0:
            return []

        min_row = rows_with_free[0]
        max_row = rows_with_free[-1]
        step = max(1, int(self.sweep_width / self.resolution))

        waypoints = []
        reverse = False

        for row in range(min_row, max_row + 1, step):
            # Find contiguous free segments in this row
            free_cols = np.where(room_mask[row])[0]
            if len(free_cols) == 0:
                continue

            # Handle non-contiguous segments (furniture gaps)
            segments = self._find_segments(free_cols)

            if reverse:
                segments = segments[::-1]
                for seg_start, seg_end in segments:
                    waypoints.append(self._pixel_to_pose(row, seg_end))
                    waypoints.append(self._pixel_to_pose(row, seg_start))
            else:
                for seg_start, seg_end in segments:
                    waypoints.append(self._pixel_to_pose(row, seg_start))
                    waypoints.append(self._pixel_to_pose(row, seg_end))

            reverse = not reverse

        return waypoints

    @staticmethod
    def _find_segments(free_cols):
        """Find contiguous runs of free pixels in a row.

        Returns list of (start_col, end_col) tuples.
        Skips segments shorter than 3 pixels (too narrow to navigate).
        """
        if len(free_cols) == 0:
            return []

        segments = []
        seg_start = free_cols[0]

        for i in range(1, len(free_cols)):
            if free_cols[i] - free_cols[i - 1] > 1:
                # Gap found — close current segment
                if free_cols[i - 1] - seg_start >= 3:
                    segments.append((seg_start, free_cols[i - 1]))
                seg_start = free_cols[i]

        # Close last segment
        if free_cols[-1] - seg_start >= 3:
            segments.append((seg_start, free_cols[-1]))

        return segments

    # ═════════════════════════════════════════════════════════════════
    #  ROOM ORDERING
    # ═════════════════════════════════════════════════════════════════

    def _order_rooms(self, room_waypoints):
        """Order rooms by nearest-neighbor greedy approach.

        Starts from the room whose first waypoint is closest to the
        map origin (assumed robot start position), then always picks
        the closest unvisited room.
        """
        if len(room_waypoints) <= 1:
            return room_waypoints

        def room_center(wps):
            cx = sum(w.pose.position.x for w in wps) / len(wps)
            cy = sum(w.pose.position.y for w in wps) / len(wps)
            return cx, cy

        def dist(a, b):
            return math.hypot(a[0] - b[0], a[1] - b[1])

        centers = [room_center(wps) for wps in room_waypoints]
        remaining = list(range(len(room_waypoints)))
        ordered = []

        # Start from room nearest to origin
        current_pos = (0.0, 0.0)
        while remaining:
            nearest_idx = min(remaining, key=lambda i: dist(current_pos, centers[i]))
            remaining.remove(nearest_idx)
            ordered.append(room_waypoints[nearest_idx])
            current_pos = centers[nearest_idx]

        return ordered

    # ═════════════════════════════════════════════════════════════════
    #  COORDINATE CONVERSION
    # ═════════════════════════════════════════════════════════════════

    def _pixel_to_pose(self, row, col, yaw=0.0):
        """Convert pixel (row, col) to a PoseStamped in the map frame.

        The occupancy grid's row 0 is the TOP of the image, but the
        map origin is at the BOTTOM-LEFT. So Y is flipped.
        """
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = self.origin[0] + col * self.resolution
        pose.pose.position.y = (
            self.origin[1]
            + (self.map_image.shape[0] - 1 - row) * self.resolution
        )
        pose.pose.position.z = 0.0
        # Compute orientation facing direction of travel
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose

    # ═════════════════════════════════════════════════════════════════
    #  VISUALIZATION
    # ═════════════════════════════════════════════════════════════════

    def _publish_plan_markers(self, ordered_rooms):
        """Publish coverage plan as RViz/Foxglove markers."""
        markers = MarkerArray()
        marker_id = 0

        for room_idx, wps in enumerate(ordered_rooms):
            color = ROOM_COLORS[room_idx % len(ROOM_COLORS)]

            # Line strip showing the sweep path
            path_marker = Marker()
            path_marker.header.frame_id = 'map'
            path_marker.header.stamp = self.get_clock().now().to_msg()
            path_marker.ns = f'room_{room_idx}'
            path_marker.id = marker_id
            path_marker.type = Marker.LINE_STRIP
            path_marker.action = Marker.ADD
            path_marker.scale.x = 0.03
            path_marker.color = ColorRGBA(
                r=color[0], g=color[1], b=color[2], a=0.7
            )
            path_marker.pose.orientation.w = 1.0

            for wp in wps:
                path_marker.points.append(wp.pose.position)

            markers.markers.append(path_marker)
            marker_id += 1

            # Room label
            if wps:
                label = Marker()
                label.header.frame_id = 'map'
                label.header.stamp = self.get_clock().now().to_msg()
                label.ns = 'room_labels'
                label.id = marker_id
                label.type = Marker.TEXT_VIEW_FACING
                label.action = Marker.ADD
                cx = sum(w.pose.position.x for w in wps) / len(wps)
                cy = sum(w.pose.position.y for w in wps) / len(wps)
                label.pose.position.x = cx
                label.pose.position.y = cy
                label.pose.position.z = 0.5
                label.pose.orientation.w = 1.0
                label.scale.z = 0.3
                label.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
                label.text = f'Room {room_idx + 1} ({len(wps)} pts)'
                markers.markers.append(label)
                marker_id += 1

        self.marker_pub.publish(markers)
        self.get_logger().info('Published coverage plan visualization to /vacuum/coverage_plan')

    # ═════════════════════════════════════════════════════════════════
    #  NAV2 EXECUTION
    # ═════════════════════════════════════════════════════════════════

    def _start_coverage(self):
        """Begin executing coverage room by room."""
        # Only fire once
        if hasattr(self, '_started'):
            return
        self._started = True

        self.get_logger().info('Waiting for Nav2 follow_waypoints action server...')
        if not self.wp_client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error(
                'Nav2 follow_waypoints not available! '
                'Is Nav2 running? (./scripts/mac_brain_launch.sh nav <map>)'
            )
            return

        self.get_logger().info('Nav2 connected. Starting coverage...')
        self._execute_next_room()

    def _execute_next_room(self):
        """Send the next room's waypoints to Nav2."""
        if self.current_room >= len(self.rooms):
            self.get_logger().info('Coverage COMPLETE! All rooms swept.')
            return

        room_wps = self.rooms[self.current_room]
        room_num = self.current_room + 1
        self.get_logger().info(
            f'Sweeping room {room_num}/{len(self.rooms)} '
            f'({len(room_wps)} waypoints)...'
        )

        goal = FollowWaypoints.Goal()
        goal.poses = room_wps

        future = self.wp_client.send_goal_async(
            goal, feedback_callback=self._waypoint_feedback
        )
        future.add_done_callback(self._goal_response)

    def _goal_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error(
                f'Room {self.current_room + 1} goal rejected by Nav2!'
            )
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._room_complete)

    def _waypoint_feedback(self, feedback_msg):
        current_wp = feedback_msg.feedback.current_waypoint
        total_wps = len(self.rooms[self.current_room])
        pct = (current_wp / max(total_wps, 1)) * 100
        self.get_logger().info(
            f'  Room {self.current_room + 1}: '
            f'waypoint {current_wp}/{total_wps} ({pct:.0f}%)'
        )

    def _room_complete(self, future):
        result = future.result()
        missed = result.result.missed_waypoints
        room_num = self.current_room + 1

        if missed:
            self.get_logger().warn(
                f'Room {room_num} done with {len(missed)} missed waypoints '
                f'(obstacles or nav failures)'
            )
        else:
            self.get_logger().info(f'Room {room_num} sweep complete!')

        self.current_room += 1
        self._execute_next_room()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    map_yaml = sys.argv[1]
    if not os.path.exists(map_yaml):
        print(f'Map file not found: {map_yaml}')
        sys.exit(1)

    rclpy.init()
    node = VacuumCoverage(map_yaml)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Coverage cancelled by user')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
