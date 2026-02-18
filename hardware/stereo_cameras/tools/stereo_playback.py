#!/usr/bin/env python3
"""
Stereo Camera Playback Tool
Replays recorded stereo camera data for debugging and analysis.

Usage:
    python3 stereo_playback.py ~/stereo_capture/session1/
    python3 stereo_playback.py ~/stereo_capture/session1/ --speed 0.5
    python3 stereo_playback.py ~/stereo_capture/session1/ --ros2
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List

import numpy as np

# ROS2 imports
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import Image
    from std_msgs.msg import Header
    from builtin_interfaces.msg import Time
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class StereoPlayback:
    """Plays back recorded stereo camera data"""

    def __init__(self, input_dir: str, speed: float = 1.0, loop: bool = False):
        self.input_dir = Path(input_dir)
        self.speed = speed
        self.loop = loop

        # Load metadata
        metadata_path = self.input_dir / 'metadata.json'
        if not metadata_path.exists():
            raise FileNotFoundError(f"No metadata.json in {input_dir}")

        with open(metadata_path) as f:
            self.metadata = json.load(f)

        self.frames = self.metadata.get('frames', [])
        self.total_frames = len(self.frames)
        self.current_frame = 0

        print(f"Loaded recording: {input_dir}")
        print(f"  Total frames: {self.total_frames}")
        print(f"  Duration: {self.metadata.get('duration', 0):.1f}s")
        print(f"  Original FPS: {self.metadata.get('fps', 0):.2f}")
        print(f"  Playback speed: {speed}x")

    def get_frame(self, index: int) -> Dict[str, Any]:
        """Get frame data at specified index"""
        if index >= self.total_frames:
            if self.loop:
                index = index % self.total_frames
            else:
                return None

        frame_meta = self.frames[index]
        result = {
            'id': frame_meta['id'],
            'timestamp': frame_meta['timestamp'],
            'relative_time': frame_meta['relative_time']
        }

        # Load left image
        if 'left' in frame_meta:
            path = self.input_dir / 'left' / frame_meta['left']
            if path.exists():
                result['left'] = cv2.imread(str(path))

        # Load right image
        if 'right' in frame_meta:
            path = self.input_dir / 'right' / frame_meta['right']
            if path.exists():
                result['right'] = cv2.imread(str(path))

        # Load depth (convert from mm back to meters)
        if 'depth' in frame_meta:
            path = self.input_dir / 'depth' / frame_meta['depth']
            if path.exists():
                depth_mm = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                result['depth'] = depth_mm.astype(np.float32) / 1000.0

        # Load colorized depth
        if 'depth_color' in frame_meta:
            path = self.input_dir / 'depth_color' / frame_meta['depth_color']
            if path.exists():
                result['depth_color'] = cv2.imread(str(path))

        # Load obstacles data
        if 'obstacles' in frame_meta:
            result['obstacles'] = frame_meta['obstacles']

        return result

    def next_frame(self) -> Optional[Dict[str, Any]]:
        """Get next frame in sequence"""
        frame = self.get_frame(self.current_frame)
        if frame is not None:
            self.current_frame += 1
        return frame

    def seek(self, frame_index: int):
        """Seek to specific frame"""
        self.current_frame = max(0, min(frame_index, self.total_frames - 1))

    def seek_time(self, time_sec: float):
        """Seek to specific time"""
        for i, frame in enumerate(self.frames):
            if frame['relative_time'] >= time_sec:
                self.current_frame = i
                return
        self.current_frame = self.total_frames - 1

    def reset(self):
        """Reset to beginning"""
        self.current_frame = 0

    def get_delay(self, prev_time: float, curr_time: float) -> float:
        """Calculate delay between frames based on playback speed"""
        return (curr_time - prev_time) / self.speed


# Only define ROS2 class if ROS2 is available
if HAS_ROS2:
    class ROS2StereoPlayback(Node):
        """ROS2 node for publishing recorded stereo data"""

        def __init__(self, playback: StereoPlayback):
            super().__init__('stereo_playback')
            self.playback = playback

            # QoS for sensor data
            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1
            )

            # Publishers
            self.left_pub = self.create_publisher(Image, '/stereo/left/image_raw', sensor_qos)
            self.right_pub = self.create_publisher(Image, '/stereo/right/image_raw', sensor_qos)
            self.depth_pub = self.create_publisher(Image, '/stereo/depth/image_raw', sensor_qos)
            self.depth_color_pub = self.create_publisher(Image, '/stereo/depth/image_color', sensor_qos)

            # Playback state
            self.prev_time = None

            # Timer will be set based on original FPS
            fps = self.playback.metadata.get('fps', 2.0) * self.playback.speed
            self.timer = self.create_timer(1.0 / fps, self.publish_frame)

            self.get_logger().info("Stereo playback node started")

        def _numpy_to_image_msg(self, img: np.ndarray, encoding: str) -> Image:
            """Convert numpy array to ROS Image message"""
            msg = Image()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'stereo_camera_link'
            msg.height = img.shape[0]
            msg.width = img.shape[1]
            msg.encoding = encoding

            if encoding == 'mono8':
                msg.step = img.shape[1]
            elif encoding == 'bgr8' or encoding == 'rgb8':
                msg.step = img.shape[1] * 3
            elif encoding == '32FC1':
                msg.step = img.shape[1] * 4

            msg.data = img.tobytes()
            return msg

        def publish_frame(self):
            """Publish next frame"""
            frame = self.playback.next_frame()
            if frame is None:
                self.get_logger().info("Playback finished")
                rclpy.shutdown()
                return

            # Publish left image
            if 'left' in frame:
                if len(frame['left'].shape) == 2:
                    msg = self._numpy_to_image_msg(frame['left'], 'mono8')
                else:
                    msg = self._numpy_to_image_msg(frame['left'], 'bgr8')
                self.left_pub.publish(msg)

            # Publish right image
            if 'right' in frame:
                if len(frame['right'].shape) == 2:
                    msg = self._numpy_to_image_msg(frame['right'], 'mono8')
                else:
                    msg = self._numpy_to_image_msg(frame['right'], 'bgr8')
                self.right_pub.publish(msg)

            # Publish depth
            if 'depth' in frame:
                msg = self._numpy_to_image_msg(frame['depth'], '32FC1')
                self.depth_pub.publish(msg)

            # Publish colorized depth
            if 'depth_color' in frame:
                msg = self._numpy_to_image_msg(frame['depth_color'], 'bgr8')
                self.depth_color_pub.publish(msg)

            # Progress
            progress = (self.playback.current_frame / self.playback.total_frames) * 100
            print(f"\rPlaying: {self.playback.current_frame}/{self.playback.total_frames} ({progress:.1f}%)", end='', flush=True)


def playback_gui(args):
    """Play back with GUI visualization"""
    playback = StereoPlayback(args.input, speed=args.speed, loop=args.loop)

    print("\nControls:")
    print("  Space: Pause/Resume")
    print("  Left/Right: Step frame")
    print("  +/-: Adjust speed")
    print("  R: Reset to beginning")
    print("  Q: Quit")

    paused = False
    prev_relative_time = 0

    while True:
        if not paused:
            frame = playback.next_frame()
            if frame is None:
                print("\nPlayback finished")
                break

            # Calculate delay
            curr_relative_time = frame['relative_time']
            if prev_relative_time > 0:
                delay = playback.get_delay(prev_relative_time, curr_relative_time)
                time.sleep(max(0, delay))
            prev_relative_time = curr_relative_time

        else:
            # When paused, just get current frame for display
            frame = playback.get_frame(playback.current_frame - 1)
            if frame is None:
                break

        # Create display
        display_images = []

        # Left image
        if 'left' in frame:
            left = frame['left']
            if len(left.shape) == 2:
                left = cv2.cvtColor(left, cv2.COLOR_GRAY2BGR)
            cv2.putText(left, 'Left', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            display_images.append(left)

        # Right image
        if 'right' in frame:
            right = frame['right']
            if len(right.shape) == 2:
                right = cv2.cvtColor(right, cv2.COLOR_GRAY2BGR)
            cv2.putText(right, 'Right', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            display_images.append(right)

        # Depth colorized
        if 'depth_color' in frame:
            depth_color = frame['depth_color'].copy()
            cv2.putText(depth_color, 'Depth', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            display_images.append(depth_color)

        # Combine images
        if display_images:
            # Resize all to same height
            target_height = 240
            resized = []
            for img in display_images:
                scale = target_height / img.shape[0]
                new_width = int(img.shape[1] * scale)
                resized.append(cv2.resize(img, (new_width, target_height)))

            combined = np.hstack(resized)

            # Add status bar
            status = f"Frame: {playback.current_frame}/{playback.total_frames} | "
            status += f"Time: {frame['relative_time']:.2f}s | "
            status += f"Speed: {playback.speed}x"
            if paused:
                status += " | PAUSED"

            cv2.putText(combined, status, (10, combined.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow('Stereo Playback', combined)

        # Handle keyboard input
        key = cv2.waitKey(1 if not paused else 100) & 0xFF

        if key == ord('q'):
            break
        elif key == ord(' '):
            paused = not paused
        elif key == ord('r'):
            playback.reset()
            prev_relative_time = 0
        elif key == 81 or key == 2:  # Left arrow
            playback.seek(playback.current_frame - 2)
            frame = playback.next_frame()
        elif key == 83 or key == 3:  # Right arrow
            frame = playback.next_frame()
        elif key == ord('+') or key == ord('='):
            playback.speed = min(4.0, playback.speed * 1.5)
            print(f"\nSpeed: {playback.speed}x")
        elif key == ord('-'):
            playback.speed = max(0.1, playback.speed / 1.5)
            print(f"\nSpeed: {playback.speed}x")

    cv2.destroyAllWindows()
    return 0


def playback_ros2(args):
    """Play back to ROS2 topics"""
    if not HAS_ROS2:
        print("Error: ROS2 not available")
        return 1

    playback = StereoPlayback(args.input, speed=args.speed, loop=args.loop)

    if not rclpy.ok():
        rclpy.init()

    node = ROS2StereoPlayback(playback)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    print()
    return 0


def main():
    parser = argparse.ArgumentParser(description='Play back recorded stereo camera data')
    parser.add_argument('input', help='Input directory with recorded data')
    parser.add_argument('--speed', '-s', type=float, default=1.0,
                        help='Playback speed multiplier (default: 1.0)')
    parser.add_argument('--loop', '-l', action='store_true',
                        help='Loop playback')
    parser.add_argument('--ros2', action='store_true',
                        help='Publish to ROS2 topics instead of GUI')
    parser.add_argument('--headless', action='store_true',
                        help='Run without GUI (just print stats)')

    args = parser.parse_args()

    if not HAS_CV2:
        print("Error: OpenCV is required for playback")
        return 1

    if not Path(args.input).exists():
        print(f"Error: Input directory not found: {args.input}")
        return 1

    if args.ros2:
        return playback_ros2(args)
    elif args.headless:
        # Just print metadata
        playback = StereoPlayback(args.input)
        print("\nMetadata:")
        for key, value in playback.metadata.items():
            if key != 'frames':
                print(f"  {key}: {value}")
        return 0
    else:
        return playback_gui(args)


if __name__ == '__main__':
    sys.exit(main())
