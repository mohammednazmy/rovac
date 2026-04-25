#!/usr/bin/env python3
"""
coverage_tracker — Ground-truth "what did the vacuum pad actually touch?"

Independent of the coverage planner. Listens to TF and stamps every floor
cell that falls under the pad rectangle as it moves. Publishes the result
as an OccupancyGrid you can overlay on the SLAM map in Foxglove.

This separates **planning** from **verification**:
  - coverage_node.py decides where the pad SHOULD go.
  - coverage_tracker.py records where the pad ACTUALLY went.

Why both? Nav2 deviates from the plan (around obstacles, recoveries),
SLAM/EKF drifts a few cm, and inter-row turns sweep arcs the planner
doesn't model. Looking at /coverage/visited after a run is the only
honest way to know if the floor got vacuumed.

Subscribes:
  /map (OccupancyGrid, transient_local)  — defines grid extent + frame

Publishes:
  /coverage/visited (OccupancyGrid)   — same grid as /map; cells the pad
                                         passed over are 100, untouched -1
  /coverage/pad_polygon (PolygonStamped) — pad footprint at current pose

Looks up TF: <map.frame> → vacuum_pad_link

Parameters:
  pad_width, pad_depth   — pad dimensions (m). Defaults match URDF.
  update_hz              — rate at which we sample TF and stamp cells (Hz).
  publish_period_s       — how often we publish the visited grid (s).
"""
import math
import sys

import numpy as np

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.duration import Duration
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from nav_msgs.msg import OccupancyGrid
    from geometry_msgs.msg import PolygonStamped, Point32
    from tf2_ros import Buffer, TransformListener, TransformException
except ImportError as e:
    sys.exit(
        f"ERROR: ROS 2 Jazzy environment not sourced: {e}\n"
        "Run:  conda activate ros_jazzy && "
        "source ~/robots/rovac/config/ros2_env.sh"
    )


PAD_FRAME = "vacuum_pad_link"


class CoverageTracker(Node):
    def __init__(self):
        super().__init__("coverage_tracker")

        self.declare_parameter("pad_width", 0.10478)
        self.declare_parameter("pad_depth", 0.05398)
        self.declare_parameter("update_hz", 10.0)
        self.declare_parameter("publish_period_s", 1.0)

        self.pad_w = self.get_parameter("pad_width").value
        self.pad_d = self.get_parameter("pad_depth").value
        self.update_hz = self.get_parameter("update_hz").value
        self.publish_period = self.get_parameter("publish_period_s").value

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # map_msg: latest OccupancyGrid received on /map (or None pre-arrival).
        # visited: uint8 array same shape as map; 0=untouched, 1=pad-stamped.
        self.map_msg = None
        self.visited = None
        self.map_frame = "map"

        # /map is published transient_local (latched) by map_server / SLAM.
        map_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(OccupancyGrid, "/map", self._on_map, map_qos)

        # Publish coverage grid as transient_local so late subscribers
        # (Foxglove panel re-opens, etc.) get the latest snapshot.
        coverage_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.coverage_pub = self.create_publisher(
            OccupancyGrid, "/coverage/visited", coverage_qos
        )
        self.poly_pub = self.create_publisher(
            PolygonStamped, "/coverage/pad_polygon", 10
        )

        self.create_timer(1.0 / self.update_hz, self._stamp_pad)
        self.create_timer(self.publish_period, self._publish)

        self.get_logger().info(
            f"coverage_tracker up — pad {self.pad_d*1000:.0f}mm "
            f"(fore-aft) × {self.pad_w*1000:.0f}mm (lateral), "
            f"sampling {self.update_hz:.0f}Hz, publish every "
            f"{self.publish_period:.1f}s. Waiting for /map..."
        )

    # ---- Map handling -----------------------------------------------------

    def _on_map(self, msg):
        # If shape changed, reset coverage. Otherwise keep accumulated state.
        if (self.map_msg is None
                or msg.info.width != self.map_msg.info.width
                or msg.info.height != self.map_msg.info.height
                or msg.info.resolution != self.map_msg.info.resolution):
            self.visited = np.zeros((msg.info.height, msg.info.width),
                                    dtype=np.uint8)
            self.get_logger().info(
                f"Coverage grid initialized: {msg.info.width}×{msg.info.height} "
                f"at {msg.info.resolution:.3f} m/cell "
                f"({msg.info.width * msg.info.resolution:.2f}×"
                f"{msg.info.height * msg.info.resolution:.2f} m)"
            )
        self.map_msg = msg
        self.map_frame = msg.header.frame_id or "map"

    # ---- Pad sampling -----------------------------------------------------

    def _lookup_pad_pose(self):
        """Return (cx, cy, yaw) of pad in map frame, or None if unavailable."""
        try:
            tf = self.tf_buffer.lookup_transform(
                self.map_frame,
                PAD_FRAME,
                rclpy.time.Time(),
                timeout=Duration(seconds=0.05),
            )
        except TransformException:
            return None
        cx = tf.transform.translation.x
        cy = tf.transform.translation.y
        qz = tf.transform.rotation.z
        qw = tf.transform.rotation.w
        yaw = 2.0 * math.atan2(qz, qw)
        return (cx, cy, yaw)

    def _stamp_pad(self):
        if self.map_msg is None or self.visited is None:
            return
        pose = self._lookup_pad_pose()
        if pose is None:
            return
        cx, cy, yaw = pose

        info = self.map_msg.info
        res = info.resolution
        ox = info.origin.position.x
        oy = info.origin.position.y
        H, W = info.height, info.width

        # Axis-aligned bounding box of the rotated pad rectangle.
        # Use full diagonal for safety; the inside-rectangle check below
        # filters down to the actual rotated extent.
        half_diag = 0.5 * math.hypot(self.pad_d, self.pad_w)
        col_min = max(0, int(math.floor((cx - half_diag - ox) / res)))
        col_max = min(W - 1, int(math.ceil((cx + half_diag - ox) / res)))
        row_min = max(0, int(math.floor((cy - half_diag - oy) / res)))
        row_max = min(H - 1, int(math.ceil((cy + half_diag - oy) / res)))

        if col_max < col_min or row_max < row_min:
            return  # pad entirely off-map

        cols = np.arange(col_min, col_max + 1)
        rows = np.arange(row_min, row_max + 1)
        cc, rr = np.meshgrid(cols, rows)
        # World coords of cell centers, relative to pad center
        wx = ox + (cc + 0.5) * res - cx
        wy = oy + (rr + 0.5) * res - cy
        # Rotate into pad-local frame (inverse rotation by yaw)
        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        lx = cy_ * wx + sy_ * wy
        ly = -sy_ * wx + cy_ * wy
        inside = (np.abs(lx) <= self.pad_d / 2.0) & (np.abs(ly) <= self.pad_w / 2.0)

        if np.any(inside):
            self.visited[rr[inside], cc[inside]] = 1

    # ---- Publishing -------------------------------------------------------

    def _publish(self):
        if self.map_msg is None or self.visited is None:
            return

        grid = OccupancyGrid()
        grid.header.frame_id = self.map_frame
        grid.header.stamp = self.get_clock().now().to_msg()
        grid.info = self.map_msg.info
        # 100 = visited, -1 = untouched (renders transparent in most viewers)
        data = np.where(self.visited > 0, np.int8(100), np.int8(-1))
        grid.data = data.flatten().astype(np.int8).tolist()
        self.coverage_pub.publish(grid)

        # Coverage stats vs free cells in the SLAM map
        map_arr = np.array(self.map_msg.data, dtype=np.int8).reshape(
            self.map_msg.info.height, self.map_msg.info.width
        )
        free_mask = (map_arr == 0)
        total_free = int(free_mask.sum())
        covered_free = int(((self.visited > 0) & free_mask).sum())
        if total_free > 0:
            pct = 100.0 * covered_free / total_free
            self.get_logger().info(
                f"Coverage: {covered_free}/{total_free} free cells = {pct:.1f}%"
            )

        # Live pad polygon
        pose = self._lookup_pad_pose()
        if pose is None:
            return
        cx, cy, yaw = pose
        poly = PolygonStamped()
        poly.header.frame_id = self.map_frame
        poly.header.stamp = self.get_clock().now().to_msg()
        cy_, sy_ = math.cos(yaw), math.sin(yaw)
        corners_local = [
            (+self.pad_d / 2,  +self.pad_w / 2),
            (+self.pad_d / 2,  -self.pad_w / 2),
            (-self.pad_d / 2,  -self.pad_w / 2),
            (-self.pad_d / 2,  +self.pad_w / 2),
        ]
        for lx, ly in corners_local:
            wx = cx + cy_ * lx - sy_ * ly
            wy = cy + sy_ * lx + cy_ * ly
            p = Point32()
            p.x = float(wx)
            p.y = float(wy)
            p.z = 0.0
            poly.polygon.points.append(p)
        self.poly_pub.publish(poly)


def main():
    rclpy.init()
    node = CoverageTracker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
