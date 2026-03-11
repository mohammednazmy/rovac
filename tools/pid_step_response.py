#!/usr/bin/env python3
"""
PID Step Response Tester for ROVAC motor driver.

Sends a velocity step command via /cmd_vel_joy, records /odom velocity
for several seconds, then prints a CSV-formatted step response log.

Usage (on Pi):
  source /opt/ros/jazzy/setup.bash && source ~/robots/rovac/config/ros2_env.sh
  python3 ~/robots/rovac/tools/pid_step_response.py --target 0.15 --duration 5
  python3 ~/robots/rovac/tools/pid_step_response.py --target 0.30 --duration 5
  python3 ~/robots/rovac/tools/pid_step_response.py --target 0.50 --duration 5
"""

import argparse
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry


class StepResponseTester(Node):

    def __init__(self, target_vel, duration, settle_time):
        super().__init__("pid_step_response")

        self._target = target_vel
        self._duration = duration
        self._settle = settle_time

        self._log = []          # [(elapsed_s, v_linear, v_angular)]
        self._start_time = None
        self._phase = "settle"  # settle → step → coast → done

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST, depth=5)

        self._odom_sub = self.create_subscription(
            Odometry, "odom", self._odom_cb, sensor_qos)

        self._cmd_pub = self.create_publisher(
            Twist, "cmd_vel_joy",
            QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                       history=HistoryPolicy.KEEP_LAST, depth=1))

        self._timer = self.create_timer(0.05, self._tick)  # 20 Hz control
        self._start_time = time.monotonic()

        self.get_logger().info(
            f"Step response: target={target_vel} m/s, "
            f"duration={duration}s, settle={settle_time}s")

    def _odom_cb(self, msg: Odometry):
        if self._start_time is None:
            return
        elapsed = time.monotonic() - self._start_time
        vx = msg.twist.twist.linear.x
        wz = msg.twist.twist.angular.z
        self._log.append((elapsed, vx, wz))

    def _tick(self):
        elapsed = time.monotonic() - self._start_time

        if elapsed < self._settle:
            # Settle phase: send zero
            self._publish_vel(0.0)
            return

        step_elapsed = elapsed - self._settle

        if step_elapsed < self._duration:
            # Step phase: send target velocity
            self._publish_vel(self._target)
            return

        coast_elapsed = step_elapsed - self._duration

        if coast_elapsed < 2.0:
            # Coast phase: send zero, observe deceleration
            self._publish_vel(0.0)
            return

        # Done
        self._publish_vel(0.0)
        self._print_results()
        raise SystemExit(0)

    def _publish_vel(self, linear_x):
        msg = Twist()
        msg.linear.x = linear_x
        self._cmd_pub.publish(msg)

    def _print_results(self):
        print("\n# PID Step Response Data")
        print(f"# target_vel={self._target} m/s, duration={self._duration}s")
        print(f"# settle={self._settle}s")
        print("# elapsed_s,v_linear,v_angular,phase")

        for t, vx, wz in self._log:
            if t < self._settle:
                phase = "settle"
            elif t < self._settle + self._duration:
                phase = "step"
            else:
                phase = "coast"
            print(f"{t:.3f},{vx:.5f},{wz:.5f},{phase}")

        # Compute metrics from step phase
        step_data = [(t - self._settle, vx) for t, vx, _ in self._log
                     if self._settle <= t < self._settle + self._duration]

        if not step_data:
            print("\n# ERROR: No data during step phase!")
            return

        # Rise time: time to reach 90% of target
        threshold = 0.9 * self._target
        rise_time = None
        for t, vx in step_data:
            if vx >= threshold:
                rise_time = t
                break

        # Steady state: average of last 40% of step phase
        n_ss = max(1, len(step_data) * 2 // 5)
        ss_vals = [vx for _, vx in step_data[-n_ss:]]
        ss_mean = sum(ss_vals) / len(ss_vals)
        ss_error = abs(ss_mean - self._target) / max(abs(self._target), 1e-6) * 100

        # Overshoot
        peak = max(vx for _, vx in step_data)
        overshoot = max(0, (peak - self._target) / max(abs(self._target), 1e-6) * 100)

        # Oscillation: count zero-crossings of (vx - target)
        deviations = [vx - self._target for _, vx in step_data]
        crossings = sum(1 for i in range(1, len(deviations))
                       if deviations[i-1] * deviations[i] < 0)

        print(f"\n# --- Metrics ---")
        print(f"# Rise time (90%): {rise_time:.3f}s" if rise_time else "# Rise time: NEVER reached 90%")
        print(f"# Steady-state mean: {ss_mean:.4f} m/s (target: {self._target})")
        print(f"# Steady-state error: {ss_error:.1f}%")
        print(f"# Peak velocity: {peak:.4f} m/s")
        print(f"# Overshoot: {overshoot:.1f}%")
        print(f"# Zero-crossings (oscillation): {crossings}")
        print(f"# Data points: {len(step_data)}")


def main():
    parser = argparse.ArgumentParser(description="PID step response test")
    parser.add_argument("--target", type=float, default=0.15,
                       help="Target linear velocity (m/s)")
    parser.add_argument("--duration", type=float, default=5.0,
                       help="Duration of step command (s)")
    parser.add_argument("--settle", type=float, default=1.0,
                       help="Settle time before step (s)")
    args = parser.parse_args()

    rclpy.init()
    node = StepResponseTester(args.target, args.duration, args.settle)
    try:
        rclpy.spin(node)
    except (SystemExit, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
