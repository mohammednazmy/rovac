#!/usr/bin/env python3
"""
Stereo Camera Visualizer
ROS2 node for visualizing stereo depth data with cursor distance readout.

Usage:
    python3 stereo_visualizer.py
    python3 stereo_visualizer.py --topic /stereo/depth/image_raw
"""

import sys
import argparse
import threading
from pathlib import Path

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import Image
    from diagnostic_msgs.msg import DiagnosticArray
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False


# Only define ROS2 class if ROS2 is available
if HAS_ROS2:
    class StereoVisualizer(Node):
        """ROS2 node for visualizing stereo depth"""

        def __init__(self, depth_topic: str, color_topic: str, max_depth: float):
            super().__init__('stereo_visualizer')
            self.max_depth = max_depth
            self.colormap = cv2.COLORMAP_JET

            self.depth_image = None
            self.depth_color = None
            self.diagnostics = {}
            self.lock = threading.Lock()
            self.mouse_x = -1
            self.mouse_y = -1

            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1
            )

            self.depth_sub = self.create_subscription(
                Image, depth_topic, self.depth_callback, sensor_qos)
            self.color_sub = self.create_subscription(
                Image, color_topic, self.color_callback, sensor_qos)
            self.diag_sub = self.create_subscription(
                DiagnosticArray, '/stereo/diagnostics', self.diag_callback, 10)

            self.window_name = 'Stereo Depth Visualizer'
            self.get_logger().info(f"Subscribing to {depth_topic}")

        def _to_numpy(self, msg):
            if msg.encoding == '32FC1':
                return np.frombuffer(msg.data, np.float32).reshape(msg.height, msg.width)
            elif msg.encoding == 'bgr8':
                return np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.width, 3)
            elif msg.encoding == 'rgb8':
                img = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.width, 3)
                return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            return None

        def depth_callback(self, msg):
            img = self._to_numpy(msg)
            if img is not None:
                with self.lock:
                    self.depth_image = img

        def color_callback(self, msg):
            img = self._to_numpy(msg)
            if img is not None:
                with self.lock:
                    self.depth_color = img

        def diag_callback(self, msg):
            diag = {}
            for s in msg.status:
                diag[s.name] = {kv.key: kv.value for kv in s.values}
            with self.lock:
                self.diagnostics = diag

        def mouse_cb(self, event, x, y, flags, param):
            self.mouse_x, self.mouse_y = x, y

        def get_display(self):
            with self.lock:
                depth = self.depth_image
                color = self.depth_color
                diag = self.diagnostics.copy()

            if color is not None:
                display = color.copy()
            elif depth is not None:
                norm = np.clip(depth / self.max_depth, 0, 1)
                display = cv2.applyColorMap((norm * 255).astype(np.uint8), self.colormap)
            else:
                display = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(display, "Waiting for data...", (180, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                return display

            h, w = display.shape[:2]

            # Crosshair and depth at cursor
            if 0 <= self.mouse_x < w and 0 <= self.mouse_y < h:
                cv2.line(display, (self.mouse_x-10, self.mouse_y),
                         (self.mouse_x+10, self.mouse_y), (255,255,255), 1)
                cv2.line(display, (self.mouse_x, self.mouse_y-10),
                         (self.mouse_x, self.mouse_y+10), (255,255,255), 1)
                if depth is not None:
                    d = depth[self.mouse_y, self.mouse_x]
                    txt = f"{d:.3f}m" if d > 0 else "N/A"
                    cv2.putText(display, txt, (self.mouse_x+15, self.mouse_y-5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)
                    cv2.putText(display, txt, (self.mouse_x+15, self.mouse_y-5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

            # Diagnostics overlay
            y = 25
            if 'stereo_depth' in diag:
                for k, v in diag['stereo_depth'].items():
                    cv2.putText(display, f"{k}: {v}", (10, y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
                    y += 20

            cv2.putText(display, "Q:Quit S:Screenshot C:Colormap", (10, h-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (128,128,128), 1)
            return display

        def run(self):
            cv2.namedWindow(self.window_name)
            cv2.setMouseCallback(self.window_name, self.mouse_cb)

            cmaps = [cv2.COLORMAP_JET, cv2.COLORMAP_TURBO, cv2.COLORMAP_VIRIDIS,
                     cv2.COLORMAP_PLASMA, cv2.COLORMAP_HOT]
            cmap_idx = 0
            shot = 0

            while rclpy.ok():
                rclpy.spin_once(self, timeout_sec=0.01)
                cv2.imshow(self.window_name, self.get_display())
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    cv2.imwrite(f"screenshot_{shot:04d}.png", self.get_display())
                    print(f"Saved screenshot_{shot:04d}.png")
                    shot += 1
                elif key == ord('c'):
                    cmap_idx = (cmap_idx + 1) % len(cmaps)
                    self.colormap = cmaps[cmap_idx]

            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--topic', default='/stereo/depth/image_raw')
    parser.add_argument('--color-topic', default='/stereo/depth/image_color')
    parser.add_argument('--max-depth', type=float, default=3.0)
    args = parser.parse_args()

    if not HAS_ROS2 or not HAS_CV2:
        print("Error: ROS2 and OpenCV required")
        return 1

    rclpy.init()
    try:
        viz = StereoVisualizer(args.topic, args.color_topic, args.max_depth)
        viz.run()
    finally:
        rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
