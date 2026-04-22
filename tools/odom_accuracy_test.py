#!/usr/bin/env python3
"""
odom_accuracy_test — Compare odometry pose claim to ground truth you measure.

Operator workflow:
  1. Mark the robot's starting pose on the floor (tape, sticky note).
  2. Run this tool — it reads `/odom` and shows live pose relative to a
     snapshot it takes at launch.
  3. Drive the robot a known distance (e.g. 1.00 m forward) via keyboard
     teleop in a separate terminal. Stop.
  4. Physically measure the actual distance traveled.
  5. Press ENTER in this tool — it prints odom-claimed delta vs. your
     measurement, revealing systematic bias (wheel_radius or
     wheel_separation error).

Supports two tests via `--test`:
  linear   — measure travel distance and report delta to expected
  yaw      — measure rotation angle and report delta to expected

REQUIRES:
  Motor driver service RUNNING (we only subscribe to /odom).
  Environment: `source /opt/ros/jazzy/setup.bash && source config/ros2_env.sh`

USAGE:
  python3 tools/odom_accuracy_test.py --test linear --expected 1.00
  python3 tools/odom_accuracy_test.py --test yaw --expected 180
"""

import argparse
import math
import sys
import time

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from nav_msgs.msg import Odometry
except ImportError:
    sys.exit("ERROR: rclpy / ROS 2 Jazzy environment not sourced. Run:\n"
             "  source /opt/ros/jazzy/setup.bash\n"
             "  source ~/robots/rovac/config/ros2_env.sh")


def quat_to_yaw(q) -> float:
    """Extract yaw from a ROS quaternion (ZYX convention, 2D mode)."""
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class OdomSnapshot(Node):
    def __init__(self):
        super().__init__("odom_accuracy")
        qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                         history=HistoryPolicy.KEEP_LAST, depth=5)
        self.sub = self.create_subscription(Odometry, "odom",
                                            self._cb, qos)
        self.latest = None

    def _cb(self, msg: Odometry):
        self.latest = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            quat_to_yaw(msg.pose.pose.orientation),
            time.monotonic(),
        )

    def wait_for_data(self, timeout=4.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.2)
            if self.latest is not None:
                return True
        return False


def main():
    ap = argparse.ArgumentParser(description="Odometry accuracy validation")
    ap.add_argument("--test", choices=("linear", "yaw"), required=True,
                    help="Which axis to test")
    ap.add_argument("--expected", type=float, required=True,
                    help="Expected ground-truth value (meters for linear, degrees for yaw)")
    args = ap.parse_args()

    rclpy.init()
    node = OdomSnapshot()
    try:
        if not node.wait_for_data():
            sys.exit("No /odom received in 4s. Is the motor driver running?")

        start = node.latest
        print("── Odometry Accuracy Test ──")
        print(f"Test type:     {args.test}")
        print(f"Expected:      {args.expected} "
              f"{'m' if args.test == 'linear' else 'deg'}")
        print(f"Start pose:    x={start[0]:+.3f} m, y={start[1]:+.3f} m, "
              f"yaw={math.degrees(start[2]):+.2f} deg")
        print()
        print("STEP: drive the robot to the end of your ground-truth marker,")
        print("      then press ENTER in this terminal.")
        print()
        try:
            input()
        except KeyboardInterrupt:
            print("\nCancelled.")
            return

        # Spin briefly so any in-flight odom updates land
        for _ in range(5):
            rclpy.spin_once(node, timeout_sec=0.1)
        end = node.latest

        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dyaw = end[2] - start[2]
        # Normalize yaw delta to [-pi, pi]
        dyaw = math.atan2(math.sin(dyaw), math.cos(dyaw))

        dist = math.hypot(dx, dy)
        yaw_deg = math.degrees(dyaw)

        print()
        print(f"End pose:      x={end[0]:+.3f} m, y={end[1]:+.3f} m, "
              f"yaw={math.degrees(end[2]):+.2f} deg")
        print(f"Pose delta:    dx={dx:+.3f} m, dy={dy:+.3f} m, "
              f"dyaw={yaw_deg:+.2f} deg")
        print()

        if args.test == "linear":
            claimed = dist
            units = "m"
            error = claimed - args.expected
            pct = 100.0 * error / args.expected if args.expected else 0.0
            print(f"Odom distance claimed: {claimed:.3f} m")
            print(f"Ground truth:          {args.expected:.3f} m")
            print(f"Error:                 {error:+.3f} m ({pct:+.2f}%)")
            if abs(pct) < 2.0:
                print("✓ Excellent accuracy (<2% error)")
            elif abs(pct) < 5.0:
                print("○ Good accuracy (2-5% error)")
            else:
                print("✗ Significant bias — check WHEEL_RADIUS in odometry.h")
                print("  If odom claims MORE than truth → wheel_radius too LARGE")
                print("  If odom claims LESS than truth → wheel_radius too SMALL")
        else:
            claimed = yaw_deg
            units = "deg"
            error = claimed - args.expected
            # Normalize: expected and claimed should both be same sign
            print(f"Odom yaw claimed:      {claimed:+.2f} deg")
            print(f"Ground truth:          {args.expected:+.2f} deg")
            print(f"Error:                 {error:+.2f} deg "
                  f"({100.0*error/args.expected:+.2f}%)")
            if abs(error) < 3.0:
                print("✓ Excellent accuracy (<3 deg error)")
            elif abs(error) < 10.0:
                print("○ Good accuracy (3-10 deg error)")
            else:
                print("✗ Significant bias — check WHEEL_SEPARATION in odometry.h")
                print("  If odom claims MORE rotation than truth → wheel_sep too SMALL")
                print("  If odom claims LESS rotation than truth → wheel_sep too LARGE")

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
