#!/usr/bin/env python3
"""
ROVAC Keyboard Teleop — Drive the robot with keyboard arrow keys / WASD.

By default, SSHes into the Pi and runs there for lowest latency.
Publishes to /cmd_vel_teleop (goes through the mux at highest priority).

Controls:
    ↑ / W   Forward         ↓ / S   Backward
    ← / A   Turn left       → / D   Turn right
    Q       Arc left         E       Arc right (forward + turn)
    + / =   Increase speed   - / _   Decrease speed
    SPACE   Stop             CTRL-C  Quit

Usage:
    # Default — auto-SSHes to Pi (lowest latency):
    python3 scripts/keyboard_teleop.py

    # Run locally on this machine (Mac or Pi):
    python3 scripts/keyboard_teleop.py --local
"""
import argparse
import os
import sys
import socket


# Pi connection settings
PI_HOST = "pi@192.168.1.200"
PI_SETUP = (
    "source /opt/ros/jazzy/setup.bash && "
    "source ~/robots/rovac/config/ros2_env.sh"
)
PI_SCRIPT = "~/robots/rovac/scripts/keyboard_teleop.py"


def ssh_to_pi(ramp_min=0.25, ramp_repeats=6, linear_accel=1.5, angular_accel=10.0):
    """Replace this process with an SSH session to the Pi running the teleop."""
    print(f"Connecting to Pi ({PI_HOST}) for lowest-latency control...")
    extra = ""
    if ramp_min != 0.25:
        extra += f" --ramp-min {ramp_min}"
    if ramp_repeats != 6:
        extra += f" --ramp-repeats {ramp_repeats}"
    if linear_accel != 1.5:
        extra += f" --linear-accel {linear_accel}"
    if angular_accel != 10.0:
        extra += f" --angular-accel {angular_accel}"
    cmd = f"{PI_SETUP} && python3 {PI_SCRIPT} --local{extra}"
    os.execvp("ssh", ["ssh", "-t", PI_HOST, cmd])
    # execvp replaces the process — never returns


def _kill_stale_cmd_vel_publishers():
    """Kill any stale processes publishing to cmd_vel_teleop.
    These ghost processes override real teleop commands and cause
    the robot to appear unresponsive."""
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ros2 topic pub.*cmd_vel_teleop"],
            capture_output=True, text=True, timeout=2)
        pids = result.stdout.strip().split('\n')
        my_pid = str(os.getpid())
        for pid in pids:
            pid = pid.strip()
            if pid and pid != my_pid:
                print(f"Killing stale cmd_vel_teleop publisher (PID {pid})")
                subprocess.run(["kill", pid], timeout=2)
    except Exception:
        pass  # Best-effort cleanup


def run_teleop(ramp_min=0.25, ramp_repeats=6, linear_accel=1.5, angular_accel=10.0):
    """Run the teleop node locally (on Pi or Mac)."""
    import time
    import math
    import curses

    _kill_stale_cmd_vel_publishers()

    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry

    # Speed presets — linear (m/s) and angular (rad/s) are coupled.
    # +/- changes both forward speed and turning speed together.
    # At max (0.50 m/s / 6.5 rad/s), wheels are near their calibrated limit.
    SPEED_STEPS = [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
    TURN_STEPS  = [1.0,  1.5,  2.0,  3.0,  4.0,  5.0,  6.5]
    DEFAULT_SPEED_IDX = 2  # 0.15 m/s, 2.0 rad/s

    # Arc turn scale — angular component when driving + turning (Q/E)
    ARC_ANG_SCALE = 2.0

    # Adaptive hold window (seconds):
    #   Terminals have ~300ms initial key-repeat delay, then ~30ms repeats.
    #   HOLD_INITIAL bridges that first 300ms gap so the motor doesn't stall.
    #   HOLD_REPEATING kicks in once repeats are flowing — gives fast stop.
    HOLD_INITIAL = 0.35
    HOLD_REPEATING = 0.08
    REPEAT_THRESHOLD = 2

    # Angular ramping — tap for fine turns, hold for full speed
    ANGULAR_RAMP_REPEATS = ramp_repeats
    ANGULAR_RAMP_MIN = ramp_min

    # Velocity smoothing — acceleration-limited ramping for smooth motion.
    # Output velocity moves toward target at these max rates (per second).
    # Deceleration uses DECEL_SCALE × accel for responsive stops.
    LINEAR_ACCEL = linear_accel    # m/s² — linear ramp rate
    ANGULAR_ACCEL = angular_accel  # rad/s² — angular ramp rate
    DECEL_SCALE = 2.5              # decel multiplier (faster stops)

    class KeyboardTeleop(Node):
        def __init__(self):
            super().__init__("keyboard_teleop")
            self.cmd_pub = self.create_publisher(Twist, "cmd_vel_teleop", 10)
            # best_effort subscriber works with both reliable and best_effort publishers
            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
            self.odom_sub = self.create_subscription(
                Odometry, "odom", self.odom_cb, qos)

            self.speed_idx = DEFAULT_SPEED_IDX
            self.linear_x = 0.0   # target (set by keys)
            self.angular_z = 0.0  # target (set by keys)
            self.smooth_lx = 0.0  # smoothed output (published)
            self.smooth_az = 0.0  # smoothed output (published)
            self._last_pub_time = 0.0

            self.odom_x = 0.0
            self.odom_y = 0.0
            self.odom_yaw = 0.0
            self.odom_vx = 0.0
            self.odom_wz = 0.0
            self.odom_count = 0
            self.odom_time = 0.0

        @property
        def max_linear(self):
            return SPEED_STEPS[self.speed_idx]

        @property
        def max_angular(self):
            return TURN_STEPS[self.speed_idx]

        def odom_cb(self, msg):
            self.odom_x = msg.pose.pose.position.x
            self.odom_y = msg.pose.pose.position.y
            q = msg.pose.pose.orientation
            siny = 2.0 * (q.w * q.z + q.x * q.y)
            cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
            self.odom_yaw = math.atan2(siny, cosy)
            self.odom_vx = msg.twist.twist.linear.x
            self.odom_wz = msg.twist.twist.angular.z
            self.odom_count += 1
            self.odom_time = time.time()

        @staticmethod
        def _step_toward(current, target, accel, dt):
            """Move current toward target at acceleration-limited rate."""
            diff = target - current
            # Decel faster when braking or reversing direction
            if abs(target) < abs(current) or target * current < 0:
                rate = accel * DECEL_SCALE
            else:
                rate = accel
            max_step = rate * dt
            if abs(diff) <= max_step:
                return target
            return current + math.copysign(max_step, diff)

        def publish_cmd(self):
            now = time.time()
            dt = now - self._last_pub_time if self._last_pub_time > 0 else 0.02
            self._last_pub_time = now
            dt = min(dt, 0.1)  # cap to prevent jumps after pauses

            self.smooth_lx = self._step_toward(
                self.smooth_lx, self.linear_x, LINEAR_ACCEL, dt)
            self.smooth_az = self._step_toward(
                self.smooth_az, self.angular_z, ANGULAR_ACCEL, dt)

            twist = Twist()
            twist.linear.x = self.smooth_lx
            twist.angular.z = self.smooth_az
            self.cmd_pub.publish(twist)

        def stop(self):
            self.linear_x = 0.0
            self.angular_z = 0.0
            self.smooth_lx = 0.0
            self.smooth_az = 0.0
            self.publish_cmd()

        def _process_key(self, key):
            """Returns True if this was a movement key."""
            if key == curses.KEY_UP or key == ord('w') or key == ord('W'):
                self.linear_x = self.max_linear
                self.angular_z = 0.0
            elif key == curses.KEY_DOWN or key == ord('s') or key == ord('S'):
                self.linear_x = -self.max_linear
                self.angular_z = 0.0
            elif key == curses.KEY_LEFT or key == ord('a') or key == ord('A'):
                self.linear_x = 0.0
                self.angular_z = self.max_angular
            elif key == curses.KEY_RIGHT or key == ord('d') or key == ord('D'):
                self.linear_x = 0.0
                self.angular_z = -self.max_angular
            elif key == ord('q') or key == ord('Q'):
                self.linear_x = self.max_linear
                self.angular_z = self.max_linear * ARC_ANG_SCALE
            elif key == ord('e') or key == ord('E'):
                self.linear_x = self.max_linear
                self.angular_z = -self.max_linear * ARC_ANG_SCALE
            else:
                return False
            return True

        def run(self, stdscr):
            curses.curs_set(0)
            stdscr.nodelay(True)
            stdscr.timeout(20)  # 20ms polling

            last_key_time = 0.0
            key_active = False
            repeat_count = 0
            last_spin = 0.0

            while rclpy.ok():
                now = time.time()

                # Process odom callbacks at ~10Hz
                if now - last_spin >= 0.1:
                    rclpy.spin_once(self, timeout_sec=0)
                    last_spin = now

                # Drain key buffer — use the LAST key pressed this frame
                last_key = -1
                while True:
                    try:
                        k = stdscr.getch()
                    except curses.error:
                        k = -1
                    if k == -1:
                        break
                    last_key = k
                key = last_key

                # Handle keys
                moved = False
                if key != -1:
                    if self._process_key(key):
                        key_active = True
                        last_key_time = now
                        repeat_count += 1
                        moved = True
                    elif key == ord(' '):
                        self.linear_x = 0.0
                        self.angular_z = 0.0
                        self.smooth_lx = 0.0  # instant stop
                        self.smooth_az = 0.0
                        key_active = False
                        repeat_count = 0
                    elif key == ord('+') or key == ord('='):
                        if self.speed_idx < len(SPEED_STEPS) - 1:
                            self.speed_idx += 1
                    elif key == ord('-') or key == ord('_'):
                        if self.speed_idx > 0:
                            self.speed_idx -= 1
                    elif key == 27:  # ESC sequence (arrow keys over SSH)
                        k2 = stdscr.getch()
                        if k2 == ord('['):
                            k3 = stdscr.getch()
                            esc_key = {ord('A'): curses.KEY_UP,
                                       ord('B'): curses.KEY_DOWN,
                                       ord('C'): curses.KEY_RIGHT,
                                       ord('D'): curses.KEY_LEFT}.get(k3)
                            if esc_key and self._process_key(esc_key):
                                key_active = True
                                last_key_time = now
                                repeat_count += 1
                                moved = True
                    elif key == 3:  # CTRL-C
                        break

                # Ramp angular velocity — gentle on first tap, full on sustained hold
                if moved and self.angular_z != 0.0:
                    ramp = max(ANGULAR_RAMP_MIN,
                               min(1.0, repeat_count / ANGULAR_RAMP_REPEATS))
                    self.angular_z *= ramp

                # Adaptive hold — long for first press, short once repeats flow
                hold_sec = (HOLD_REPEATING if repeat_count >= REPEAT_THRESHOLD
                            else HOLD_INITIAL)
                if key_active and (now - last_key_time) > hold_sec:
                    self.linear_x = 0.0
                    self.angular_z = 0.0
                    key_active = False
                    repeat_count = 0

                # Always publish (keeps ESP32 watchdog fed)
                self.publish_cmd()

                # Draw UI
                self._draw(stdscr, key_active)

            self.stop()

        def _draw(self, stdscr, key_active):
            try:
                stdscr.erase()

                host = socket.gethostname()
                stdscr.addstr(0, 0, f"ROVAC Keyboard Teleop [{host}]",
                              curses.A_BOLD)
                stdscr.addstr(0, 40,
                              f"Fwd: {self.max_linear:.2f} m/s  "
                              f"Turn: {self.max_angular:.1f} rad/s",
                              curses.A_BOLD)

                stdscr.addstr(2, 0, "Controls:  Arrow keys / WASD = drive")
                stdscr.addstr(3, 0, "           Q/E = arc    (tap=fine turn, hold=full)")
                stdscr.addstr(4, 0, "           +/- = speed up/down")
                stdscr.addstr(5, 0, "           SPACE = stop  CTRL-C = quit")

                lin_bar = ""
                for i, s in enumerate(SPEED_STEPS):
                    if i == self.speed_idx:
                        lin_bar += f"[{s:.2f}]"
                    else:
                        lin_bar += f" {s:.2f} "
                stdscr.addstr(7, 0, f"Fwd:   {lin_bar}")

                turn_bar = ""
                for i, t in enumerate(TURN_STEPS):
                    if i == self.speed_idx:
                        turn_bar += f"[{t:.1f}]"
                    else:
                        turn_bar += f" {t:.1f} "
                stdscr.addstr(8, 0, f"Turn:  {turn_bar}")

                state = "DRIVING" if key_active else "STOPPED"
                attr = curses.A_BOLD if key_active else curses.A_DIM
                stdscr.addstr(10, 0, f"State: {state}", attr)
                stdscr.addstr(11, 0,
                              f"Out:   linear={self.smooth_lx:+.3f} m/s  "
                              f"angular={self.smooth_az:+.3f} rad/s")
                stdscr.addstr(12, 0,
                              f"Tgt:   linear={self.linear_x:+.3f} m/s  "
                              f"angular={self.angular_z:+.3f} rad/s",
                              curses.A_DIM)

                if self.linear_x > 0 and self.angular_z == 0:
                    arrow = "    ^"
                elif self.linear_x < 0 and self.angular_z == 0:
                    arrow = "    v"
                elif self.angular_z > 0 and self.linear_x == 0:
                    arrow = "  <  "
                elif self.angular_z < 0 and self.linear_x == 0:
                    arrow = "    >"
                elif self.linear_x > 0 and self.angular_z > 0:
                    arrow = "  ^ /"
                elif self.linear_x > 0 and self.angular_z < 0:
                    arrow = "  \\ ^"
                else:
                    arrow = "  [ ]"
                stdscr.addstr(13, 0, f"Dir:   {arrow}")

                odom_age = time.time() - self.odom_time if self.odom_time > 0 else 999
                odom_status = "LIVE" if odom_age < 1.0 else "STALE"
                stdscr.addstr(15, 0, f"--- Odometry ({odom_status}, "
                              f"{self.odom_count} msgs) ---")
                stdscr.addstr(16, 0,
                              f"Pos:   x={self.odom_x:+.3f}  y={self.odom_y:+.3f}"
                              f"  yaw={math.degrees(self.odom_yaw):+.1f} deg")
                stdscr.addstr(17, 0,
                              f"Vel:   vx={self.odom_vx:+.3f} m/s  "
                              f"wz={self.odom_wz:+.3f} rad/s")

                stdscr.refresh()
            except curses.error:
                pass

    # --- Teleop main ---
    rclpy.init()
    node = KeyboardTeleop()

    print("Publishing to /cmd_vel_teleop (via mux)")
    print("Connecting to ROS2 topics...")

    # Wait for the mux to discover our publisher (DDS discovery).
    # Without this, the first 1-3 seconds of key presses are lost.
    print("  Waiting for mux subscriber...", end="", flush=True)
    deadline = time.time() + 8.0
    while node.cmd_pub.get_subscription_count() == 0 and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.2)
    if node.cmd_pub.get_subscription_count() > 0:
        print(f" connected ({node.cmd_pub.get_subscription_count()} sub)")
    else:
        print(" WARNING: mux not found (commands may not reach motors)")

    # Wait for odom feedback from motor driver
    print("  Waiting for odom...", end="", flush=True)
    deadline = time.time() + 5.0
    while node.odom_count == 0 and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.3)
    if node.odom_count > 0:
        print(f" connected ({node.odom_count} msgs)")
    else:
        print(" WARNING: no odom yet (may connect shortly)")

    print("Teleop ready!")

    sys.stdout.flush()
    sys.stderr.flush()
    time.sleep(0.2)

    saved_stderr_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)

    try:
        curses.wrapper(node.run)
    except KeyboardInterrupt:
        pass
    finally:
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stderr_fd)
        node.stop()
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description="ROVAC Keyboard Teleop")
    parser.add_argument("--local", action="store_true",
                        help="Run locally instead of SSHing to Pi")
    parser.add_argument("--ramp-min", type=float, default=0.25,
                        help="Min angular fraction on first tap (0.0-1.0, default: 0.25)")
    parser.add_argument("--ramp-repeats", type=int, default=6,
                        help="Key events to reach full angular speed (default: 6)")
    parser.add_argument("--linear-accel", type=float, default=1.5,
                        help="Linear acceleration limit in m/s² (default: 1.5)")
    parser.add_argument("--angular-accel", type=float, default=10.0,
                        help="Angular acceleration limit in rad/s² (default: 10.0)")
    args = parser.parse_args()

    kwargs = dict(ramp_min=args.ramp_min, ramp_repeats=args.ramp_repeats,
                  linear_accel=args.linear_accel, angular_accel=args.angular_accel)
    if args.local or socket.gethostname() == "rovac-pi":
        run_teleop(**kwargs)
    else:
        ssh_to_pi(**kwargs)


if __name__ == "__main__":
    main()
