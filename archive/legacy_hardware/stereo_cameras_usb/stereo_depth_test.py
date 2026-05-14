#!/usr/bin/env python3
"""
Quick stereo depth test for Logitech Brio 100 cameras.
Tests uncalibrated stereo matching to verify camera setup.

Usage:
    python stereo_depth_test.py

Press 'q' to quit, 's' to save current frame pair.
"""

import cv2
import numpy as np
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class StereoConfig:
    """Stereo camera configuration"""
    left_device: int = 0
    right_device: int = 1
    width: int = 1280
    height: int = 720
    fps: int = 30
    baseline_cm: float = 12.0  # Approximate baseline in cm
    rotate_90_cw: bool = True  # Rotate frames 90° clockwise (for vertical mounting)


class StereoCapture:
    """Synchronized stereo camera capture"""

    def __init__(self, config: StereoConfig):
        self.config = config
        self.left_frame: Optional[np.ndarray] = None
        self.right_frame: Optional[np.ndarray] = None
        self.left_cap: Optional[cv2.VideoCapture] = None
        self.right_cap: Optional[cv2.VideoCapture] = None
        self.running = False
        self.lock = threading.Lock()

    def start(self) -> bool:
        """Initialize and start capture"""
        # Open left camera
        self.left_cap = cv2.VideoCapture(self.config.left_device)
        if not self.left_cap.isOpened():
            print(f"Error: Cannot open left camera (device {self.config.left_device})")
            return False

        # Open right camera
        self.right_cap = cv2.VideoCapture(self.config.right_device)
        if not self.right_cap.isOpened():
            print(f"Error: Cannot open right camera (device {self.config.right_device})")
            self.left_cap.release()
            return False

        # Configure cameras
        for cap in [self.left_cap, self.right_cap]:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            cap.set(cv2.CAP_PROP_FPS, self.config.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency

        self.running = True

        # Start capture threads
        self.left_thread = threading.Thread(target=self._capture_left, daemon=True)
        self.right_thread = threading.Thread(target=self._capture_right, daemon=True)
        self.left_thread.start()
        self.right_thread.start()

        print(f"Stereo capture started: {self.config.width}x{self.config.height} @ {self.config.fps}fps")
        return True

    def _capture_left(self):
        """Capture thread for left camera"""
        while self.running:
            ret, frame = self.left_cap.read()
            if ret:
                with self.lock:
                    self.left_frame = frame

    def _capture_right(self):
        """Capture thread for right camera"""
        while self.running:
            ret, frame = self.right_cap.read()
            if ret:
                with self.lock:
                    self.right_frame = frame

    def get_frames(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Get current stereo frame pair"""
        with self.lock:
            left = self.left_frame.copy() if self.left_frame is not None else None
            right = self.right_frame.copy() if self.right_frame is not None else None

        # Apply rotation if configured (for vertical camera mounting)
        if self.config.rotate_90_cw:
            if left is not None:
                left = cv2.rotate(left, cv2.ROTATE_90_CLOCKWISE)
            if right is not None:
                right = cv2.rotate(right, cv2.ROTATE_90_CLOCKWISE)

        return left, right

    def stop(self):
        """Stop capture and release resources"""
        self.running = False
        time.sleep(0.1)
        if self.left_cap:
            self.left_cap.release()
        if self.right_cap:
            self.right_cap.release()


class StereoDepth:
    """Stereo depth computation using SGBM"""

    def __init__(self, config: StereoConfig):
        self.config = config

        # SGBM parameters (tuned for ~12cm baseline, indoor use)
        self.min_disparity = 0
        self.num_disparities = 128  # Must be divisible by 16
        self.block_size = 5

        self._rebuild_stereo()

    def _rebuild_stereo(self):
        """Rebuild stereo matcher with current parameters"""
        self.stereo = cv2.StereoSGBM_create(
            minDisparity=self.min_disparity,
            numDisparities=self.num_disparities,
            blockSize=self.block_size,
            P1=8 * 3 * self.block_size ** 2,
            P2=32 * 3 * self.block_size ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
            preFilterCap=63,
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
        )

        # WLS filter for smoother results
        self.right_matcher = cv2.ximgproc.createRightMatcher(self.stereo)
        self.wls_filter = cv2.ximgproc.createDisparityWLSFilter(self.stereo)
        self.wls_filter.setLambda(8000)
        self.wls_filter.setSigmaColor(1.5)

    def compute(self, left: np.ndarray, right: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute disparity and depth from stereo pair.
        Returns (disparity_colormap, depth_meters)
        """
        # Convert to grayscale
        left_gray = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
        right_gray = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)

        # Compute disparity
        left_disp = self.stereo.compute(left_gray, right_gray)
        right_disp = self.right_matcher.compute(right_gray, left_gray)

        # Apply WLS filter
        filtered_disp = self.wls_filter.filter(left_disp, left_gray, None, right_disp)

        # Normalize for display
        disp_vis = cv2.normalize(filtered_disp, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)

        # Convert to depth (approximate, needs calibration for accuracy)
        # depth = baseline * focal_length / disparity
        # Using rough estimates for uncalibrated setup
        focal_length_px = self.config.width * 0.8  # Approximate
        baseline_m = self.config.baseline_cm / 100.0

        # Avoid division by zero
        filtered_disp_float = filtered_disp.astype(np.float32) / 16.0  # SGBM uses fixed-point
        filtered_disp_float[filtered_disp_float <= 0] = 0.1

        depth = (baseline_m * focal_length_px) / filtered_disp_float
        depth[depth > 10.0] = 0  # Clip far values
        depth[depth < 0.1] = 0   # Clip near values

        return disp_color, depth


def main():
    print("=" * 60)
    print("STEREO DEPTH TEST")
    print("=" * 60)
    print("Controls:")
    print("  q     - Quit")
    print("  s     - Save current frames")
    print("  +/-   - Adjust num_disparities (depth range)")
    print("  [/]   - Adjust block_size (smoothness)")
    print("=" * 60)

    config = StereoConfig(
        left_device=1,   # Left Brio (physically on left)
        right_device=0,  # Right Brio (physically on right)
        width=1280,
        height=720,
        fps=30,
        baseline_cm=12.0,
        rotate_90_cw=True  # Vertical mounting
    )

    # Initialize capture
    capture = StereoCapture(config)
    if not capture.start():
        return

    # Initialize depth computation
    depth_computer = StereoDepth(config)

    # Wait for first frames
    time.sleep(0.5)

    frame_count = 0
    fps_start = time.time()
    fps = 0.0

    try:
        while True:
            left, right = capture.get_frames()

            if left is None or right is None:
                continue

            # Compute depth
            disp_color, depth = depth_computer.compute(left, right)

            # Calculate FPS
            frame_count += 1
            if frame_count % 30 == 0:
                fps = 30.0 / (time.time() - fps_start)
                fps_start = time.time()

            # Create display
            # Resize for display
            scale = 0.5
            left_small = cv2.resize(left, None, fx=scale, fy=scale)
            right_small = cv2.resize(right, None, fx=scale, fy=scale)
            disp_small = cv2.resize(disp_color, None, fx=scale, fy=scale)

            # Stack horizontally: left | right | disparity
            top_row = np.hstack([left_small, right_small])

            # Create depth info overlay
            center_depth = depth[depth.shape[0]//2, depth.shape[1]//2]
            cv2.putText(disp_small, f"Center: {center_depth:.2f}m", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(disp_small, f"FPS: {fps:.1f}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(disp_small, f"Disp: {depth_computer.num_disparities} Blk: {depth_computer.block_size}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Pad disparity to match width
            disp_padded = np.zeros_like(top_row)
            disp_padded[:, :disp_small.shape[1]] = disp_small

            display = np.vstack([top_row, disp_padded])

            cv2.imshow("Stereo Depth Test (Left | Right | Disparity)", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                timestamp = int(time.time())
                cv2.imwrite(f"/tmp/stereo_left_{timestamp}.jpg", left)
                cv2.imwrite(f"/tmp/stereo_right_{timestamp}.jpg", right)
                cv2.imwrite(f"/tmp/stereo_disp_{timestamp}.jpg", disp_color)
                print(f"Saved frames to /tmp/stereo_*_{timestamp}.jpg")
            elif key == ord('+') or key == ord('='):
                depth_computer.num_disparities = min(256, depth_computer.num_disparities + 16)
                depth_computer._rebuild_stereo()
                print(f"num_disparities: {depth_computer.num_disparities}")
            elif key == ord('-') or key == ord('_'):
                depth_computer.num_disparities = max(16, depth_computer.num_disparities - 16)
                depth_computer._rebuild_stereo()
                print(f"num_disparities: {depth_computer.num_disparities}")
            elif key == ord('['):
                depth_computer.block_size = max(3, depth_computer.block_size - 2)
                depth_computer._rebuild_stereo()
                print(f"block_size: {depth_computer.block_size}")
            elif key == ord(']'):
                depth_computer.block_size = min(21, depth_computer.block_size + 2)
                depth_computer._rebuild_stereo()
                print(f"block_size: {depth_computer.block_size}")

    except KeyboardInterrupt:
        pass
    finally:
        capture.stop()
        cv2.destroyAllWindows()
        print("Stereo depth test finished.")


if __name__ == "__main__":
    main()
