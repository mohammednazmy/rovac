#!/usr/bin/env python3
"""ROVAC Command Center — unified TUI for robot control and monitoring."""

import sys
import argparse


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
    ros_available = True
    if not args.no_ros:
        try:
            import rclpy  # noqa: F401
        except ImportError:
            print('Warning: rclpy not found. Source ROS2 environment first:')
            print('  conda activate ros_jazzy && source ~/robots/rovac/config/ros2_env.sh')
            print('Continuing in --no-ros mode...')
            ros_available = False
            args.no_ros = True

    from .app import RovacCommandCenter
    app = RovacCommandCenter(
        no_ros=args.no_ros,
        pi_host=args.pi_host,
        pi_user=args.pi_user,
    )
    app.run()


if __name__ == '__main__':
    main()
