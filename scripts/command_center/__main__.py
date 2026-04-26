#!/usr/bin/env python3
"""ROVAC Command Center — unified TUI for robot control and monitoring."""

import argparse
import os
import signal
import sys


def main():
    parser = argparse.ArgumentParser(description='ROVAC Command Center')
    parser.add_argument('--no-ros', action='store_true', help='Run without ROS2 (UI testing)')
    parser.add_argument('--pi-host', default='192.168.1.200', help='Pi edge IP')
    parser.add_argument('--pi-user', default='pi', help='Pi SSH user')
    args = parser.parse_args()

    # Check textual
    try:
        import textual  # noqa: F401
    except ImportError:
        print('textual not installed. Run: pip install textual')
        sys.exit(1)

    # Check rclpy
    if not args.no_ros:
        try:
            import rclpy  # noqa: F401
        except ImportError:
            print('Warning: rclpy not found. Source ROS2 environment first:')
            print('  conda activate ros_jazzy && source ~/robots/rovac/config/ros2_env.sh')
            print('Continuing in --no-ros mode...')
            args.no_ros = True

    from .app import RovacCommandCenter
    app = RovacCommandCenter(
        no_ros=args.no_ros,
        pi_host=args.pi_host,
        pi_user=args.pi_user,
    )

    # Last-resort Ctrl-C handler. Textual normally captures keystrokes
    # in raw mode (so the OS doesn't see Ctrl-C), but if the UI thread
    # is hung for any reason, this gives the user an escape hatch via
    # the controlling TTY's signal — we re-enable SIGINT to terminate
    # the process if Textual hasn't intercepted it.
    def _emergency_exit(_signum, _frame):
        try:
            app.exit()
        except Exception:
            pass
        # Force-exit if the UI didn't unwind
        os._exit(130)
    signal.signal(signal.SIGINT, _emergency_exit)
    signal.signal(signal.SIGTERM, _emergency_exit)

    app.run()


if __name__ == '__main__':
    main()
