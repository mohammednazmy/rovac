#!/usr/bin/env python3
"""
Stereo Camera Recording Tool
Records stereo camera data (left/right images, depth, obstacles) to disk for later playback.

Usage:
    python3 stereo_record.py --output ~/stereo_capture/session1/
    python3 stereo_record.py --output ~/stereo_capture/session1/ --duration 60
    python3 stereo_record.py --output ~/stereo_capture/session1/ --topics depth,obstacles
"""

import os
import sys
import json
import time
import argparse
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import numpy as np

# ROS2 imports
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import Image, CompressedImage, CameraInfo
    from std_msgs.msg import Header
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False
    print("Warning: ROS2 not available, running in standalone mode")

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("Warning: OpenCV not available")


class StereoRecorder:
    """Records stereo camera data to disk"""

    def __init__(self, output_dir: str, topics: List[str] = None,
                 duration: float = None, max_frames: int = None):
        self.output_dir = Path(output_dir)
        self.duration = duration
        self.max_frames = max_frames
        self.topics = topics or ['left', 'right', 'depth', 'depth_color', 'obstacles']

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / 'left').mkdir(exist_ok=True)
        (self.output_dir / 'right').mkdir(exist_ok=True)
        (self.output_dir / 'depth').mkdir(exist_ok=True)
        (self.output_dir / 'depth_color').mkdir(exist_ok=True)

        # Recording state
        self.is_recording = False
        self.start_time = None
        self.frame_count = 0
        self.metadata = {
            'created': datetime.now().isoformat(),
            'topics': self.topics,
            'frames': [],
            'duration': None,
            'fps': None
        }

        # Thread safety
        self.lock = threading.Lock()

    def start(self):
        """Start recording"""
        self.is_recording = True
        self.start_time = time.time()
        self.frame_count = 0
        print(f"Recording started to {self.output_dir}")

    def stop(self):
        """Stop recording and save metadata"""
        self.is_recording = False
        elapsed = time.time() - self.start_time if self.start_time else 0

        self.metadata['duration'] = elapsed
        self.metadata['fps'] = self.frame_count / elapsed if elapsed > 0 else 0
        self.metadata['total_frames'] = self.frame_count

        # Save metadata
        metadata_path = self.output_dir / 'metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        print(f"\nRecording stopped")
        print(f"  Duration: {elapsed:.1f}s")
        print(f"  Frames: {self.frame_count}")
        print(f"  FPS: {self.metadata['fps']:.2f}")
        print(f"  Output: {self.output_dir}")

    def should_stop(self) -> bool:
        """Check if recording should stop"""
        if not self.is_recording:
            return True

        if self.duration and (time.time() - self.start_time) >= self.duration:
            return True

        if self.max_frames and self.frame_count >= self.max_frames:
            return True

        return False

    def record_frame(self, left: np.ndarray = None, right: np.ndarray = None,
                     depth: np.ndarray = None, depth_color: np.ndarray = None,
                     obstacles: Dict[str, Any] = None, timestamp: float = None):
        """Record a single frame of data"""
        if not self.is_recording:
            return

        with self.lock:
            ts = timestamp or time.time()
            frame_id = f"{self.frame_count:06d}"

            frame_meta = {
                'id': frame_id,
                'timestamp': ts,
                'relative_time': ts - self.start_time
            }

            # Save left image
            if left is not None and 'left' in self.topics:
                path = self.output_dir / 'left' / f'{frame_id}.png'
                cv2.imwrite(str(path), left)
                frame_meta['left'] = str(path.name)

            # Save right image
            if right is not None and 'right' in self.topics:
                path = self.output_dir / 'right' / f'{frame_id}.png'
                cv2.imwrite(str(path), right)
                frame_meta['right'] = str(path.name)

            # Save depth (as 16-bit PNG for precision)
            if depth is not None and 'depth' in self.topics:
                path = self.output_dir / 'depth' / f'{frame_id}.png'
                # Convert meters to millimeters and save as 16-bit
                depth_mm = (depth * 1000).astype(np.uint16)
                cv2.imwrite(str(path), depth_mm)
                frame_meta['depth'] = str(path.name)

            # Save colorized depth
            if depth_color is not None and 'depth_color' in self.topics:
                path = self.output_dir / 'depth_color' / f'{frame_id}.png'
                cv2.imwrite(str(path), depth_color)
                frame_meta['depth_color'] = str(path.name)

            # Save obstacles data
            if obstacles is not None and 'obstacles' in self.topics:
                frame_meta['obstacles'] = obstacles

            self.metadata['frames'].append(frame_meta)
            self.frame_count += 1

            # Print progress
            if self.frame_count % 10 == 0:
                elapsed = time.time() - self.start_time
                print(f"\rRecorded {self.frame_count} frames ({elapsed:.1f}s)", end='', flush=True)


# Only define ROS2 class if ROS2 is available
if HAS_ROS2:
    class ROS2StereoRecorder(Node):
        """ROS2 node for recording stereo camera topics"""

        def __init__(self, recorder: StereoRecorder):
            super().__init__('stereo_recorder')
            self.recorder = recorder

            # QoS for sensor data
            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1
            )

            # Buffers for synchronization
            self.left_image = None
            self.right_image = None
            self.depth_image = None
            self.depth_color = None
            self.obstacles = None
            self.last_sync_time = 0

            # Subscribe to topics
            self.left_sub = self.create_subscription(
                Image, '/stereo/left/image_raw',
                self.left_callback, sensor_qos
            )

            self.right_sub = self.create_subscription(
                Image, '/stereo/right/image_raw',
                self.right_callback, sensor_qos
            )

            self.depth_sub = self.create_subscription(
                Image, '/stereo/depth/image_raw',
                self.depth_callback, sensor_qos
            )

            self.depth_color_sub = self.create_subscription(
                Image, '/stereo/depth/image_color',
                self.depth_color_callback, sensor_qos
            )

            # Timer for synchronization
            self.sync_timer = self.create_timer(0.1, self.sync_callback)

            self.get_logger().info("Stereo recorder node started")

        def _image_to_numpy(self, msg: Image) -> np.ndarray:
            """Convert ROS Image to numpy array"""
            if msg.encoding == 'mono8':
                return np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width)
            elif msg.encoding == 'bgr8':
                return np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, 3)
            elif msg.encoding == 'rgb8':
                img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, 3)
                return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif msg.encoding == '32FC1':
                return np.frombuffer(msg.data, dtype=np.float32).reshape(msg.height, msg.width)
            elif msg.encoding == '16UC1':
                return np.frombuffer(msg.data, dtype=np.uint16).reshape(msg.height, msg.width)
            else:
                self.get_logger().warn(f"Unknown encoding: {msg.encoding}")
                return None

        def left_callback(self, msg: Image):
            self.left_image = self._image_to_numpy(msg)

        def right_callback(self, msg: Image):
            self.right_image = self._image_to_numpy(msg)

        def depth_callback(self, msg: Image):
            self.depth_image = self._image_to_numpy(msg)

        def depth_color_callback(self, msg: Image):
            self.depth_color = self._image_to_numpy(msg)

        def sync_callback(self):
            """Synchronize and record frames"""
            if not self.recorder.is_recording:
                return

            if self.recorder.should_stop():
                self.recorder.stop()
                rclpy.shutdown()
                return

            # Record if we have depth (minimum requirement)
            if self.depth_image is not None:
                self.recorder.record_frame(
                    left=self.left_image,
                    right=self.right_image,
                    depth=self.depth_image,
                    depth_color=self.depth_color,
                    timestamp=time.time()
                )

                # Clear buffers
                self.depth_image = None


def record_standalone(args):
    """Record in standalone mode (directly from cameras)"""
    print("Recording in standalone mode (direct camera access)")

    # Import stereo depth module
    from ros2_stereo_depth_node import StereoConfig, StereoDepthComputer, ThreadedCamera

    # Load config
    config_path = Path(__file__).parent.parent / 'config_pi.json'
    if config_path.exists():
        with open(config_path) as f:
            config_data = json.load(f)
        config = StereoConfig(**config_data)
    else:
        config = StereoConfig()

    # Initialize cameras
    left_cam = ThreadedCamera(config.left_camera_id, config.frame_width, config.frame_height)
    right_cam = ThreadedCamera(config.right_camera_id, config.frame_width, config.frame_height)

    if not left_cam.is_opened() or not right_cam.is_opened():
        print("Error: Could not open cameras")
        return 1

    # Initialize stereo computer
    stereo = StereoDepthComputer(config)

    # Load calibration
    calib_path = Path(__file__).parent.parent / config.calibration_file
    if calib_path.exists():
        stereo.load_calibration(str(calib_path))
    else:
        print(f"Warning: No calibration file at {calib_path}")

    # Create recorder
    recorder = StereoRecorder(
        args.output,
        topics=args.topics.split(',') if args.topics else None,
        duration=args.duration,
        max_frames=args.max_frames
    )

    recorder.start()

    try:
        while not recorder.should_stop():
            # Capture frames
            left = left_cam.read()
            right = right_cam.read()

            if left is None or right is None:
                continue

            # Compute depth
            depth = stereo.compute_depth(left, right)

            # Colorize depth
            depth_normalized = np.clip(depth / config.max_depth, 0, 1)
            depth_color = cv2.applyColorMap(
                (depth_normalized * 255).astype(np.uint8),
                cv2.COLORMAP_JET
            )

            # Record
            recorder.record_frame(
                left=left,
                right=right,
                depth=depth,
                depth_color=depth_color
            )

    except KeyboardInterrupt:
        print("\nInterrupted by user")

    finally:
        recorder.stop()
        left_cam.release()
        right_cam.release()

    return 0


def record_ros2(args):
    """Record from ROS2 topics"""
    print("Recording from ROS2 topics")

    if not rclpy.ok():
        rclpy.init()

    recorder = StereoRecorder(
        args.output,
        topics=args.topics.split(',') if args.topics else None,
        duration=args.duration,
        max_frames=args.max_frames
    )

    node = ROS2StereoRecorder(recorder)
    recorder.start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        if recorder.is_recording:
            recorder.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return 0


def main():
    parser = argparse.ArgumentParser(description='Record stereo camera data')
    parser.add_argument('--output', '-o', required=True,
                        help='Output directory for recorded data')
    parser.add_argument('--duration', '-d', type=float,
                        help='Recording duration in seconds')
    parser.add_argument('--max-frames', '-m', type=int,
                        help='Maximum number of frames to record')
    parser.add_argument('--topics', '-t',
                        help='Comma-separated list of topics to record (left,right,depth,depth_color,obstacles)')
    parser.add_argument('--standalone', '-s', action='store_true',
                        help='Record directly from cameras (no ROS2)')

    args = parser.parse_args()

    if not HAS_CV2:
        print("Error: OpenCV is required for recording")
        return 1

    if args.standalone or not HAS_ROS2:
        return record_standalone(args)
    else:
        return record_ros2(args)


if __name__ == '__main__':
    sys.exit(main())
