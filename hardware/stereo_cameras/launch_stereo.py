#!/usr/bin/env python3
"""
Launch script for stereo depth and obstacle detection nodes.

Usage:
    python launch_stereo.py [--no-obstacles] [--pointcloud] [--display]

Options:
    --no-obstacles  Don't start obstacle detector
    --pointcloud    Enable point cloud publishing
    --display       Show local depth visualization
"""

import subprocess
import sys
import signal
import time
import argparse


def main():
    parser = argparse.ArgumentParser(description="Launch stereo depth system")
    parser.add_argument('--no-obstacles', action='store_true', help="Skip obstacle detector")
    parser.add_argument('--pointcloud', action='store_true', help="Enable point cloud")
    parser.add_argument('--display', action='store_true', help="Show local visualization")
    args = parser.parse_args()

    processes = []

    def cleanup(signum=None, frame=None):
        print("\nShutting down...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("=" * 50)
    print("STEREO DEPTH SYSTEM")
    print("=" * 50)

    # Build ROS2 run commands
    depth_cmd = [
        'python3', 'ros2_stereo_depth_node.py',
    ]
    if args.pointcloud:
        print("Point cloud: ENABLED")

    print("Starting stereo depth node...")
    p_depth = subprocess.Popen(depth_cmd)
    processes.append(p_depth)
    time.sleep(2)

    if not args.no_obstacles:
        print("Starting obstacle detector...")
        obstacle_cmd = ['python3', 'obstacle_detector.py']
        p_obstacle = subprocess.Popen(obstacle_cmd)
        processes.append(p_obstacle)

    if args.display:
        print("Starting local display...")
        display_cmd = ['python3', 'stereo_depth_calibrated.py']
        p_display = subprocess.Popen(display_cmd)
        processes.append(p_display)

    print("=" * 50)
    print("System running. Press Ctrl+C to stop.")
    print("=" * 50)
    print()
    print("Published topics:")
    print("  /stereo/depth/image_raw  - Depth image (32FC1)")
    print("  /stereo/left/image_rect  - Rectified left image")
    print("  /stereo/camera_info      - Camera parameters")
    if not args.no_obstacles:
        print("  /obstacles               - Obstacle detection JSON")
        print("  /obstacles/ranges        - Virtual laser scan")
        print("  /cmd_vel_obstacle        - Emergency stop commands")
    print()

    # Wait for processes
    try:
        while True:
            for p in processes:
                if p.poll() is not None:
                    print(f"Process {p.pid} exited")
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == '__main__':
    main()
