#!/usr/bin/env python3
"""
Calibrated Stereo Depth Pipeline

Uses stereo calibration data to produce accurate depth measurements.
Applies rectification, computes disparity, and converts to metric depth.

Usage:
    python stereo_depth_calibrated.py

Controls:
    q     - Quit
    s     - Save current depth frame
    +/-   - Adjust num_disparities
    [/]   - Adjust block_size
    r     - Toggle raw vs filtered disparity
    d     - Show depth at mouse position (click to measure)
"""

import cv2
import numpy as np
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

# Import depth correction if available
try:
    from depth_correction import DepthCorrection
    HAS_CORRECTION = True
except ImportError:
    HAS_CORRECTION = False


@dataclass
class StereoConfig:
    """Stereo camera configuration"""
    left_device: int = 1    # Physically LEFT camera
    right_device: int = 0   # Physically RIGHT camera
    width: int = 1280
    height: int = 720
    fps: int = 30
    rotate_90_cw: bool = True
    calibration_dir: str = "calibration_data"


class ThreadedCamera:
    """Threaded camera capture for reliable multi-camera operation"""

    def __init__(self, device_id: int, width: int, height: int):
        self.device_id = device_id
        self.width = width
        self.height = height
        self.frame: Optional[np.ndarray] = None
        self.running = False
        self.lock = threading.Lock()
        self.cap: Optional[cv2.VideoCapture] = None

    def start(self) -> bool:
        self.cap = cv2.VideoCapture(self.device_id)
        if not self.cap.isOpened():
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        return True

    def _capture_loop(self):
        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.frame = frame
            time.sleep(0.001)

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False
        time.sleep(0.1)
        if self.cap:
            self.cap.release()


class CalibratedStereoDepth:
    """Calibrated stereo depth computation"""

    def __init__(self, config: StereoConfig):
        self.config = config
        self.load_calibration()

        # SGBM parameters
        self.min_disparity = 0
        self.num_disparities = 256  # Must be divisible by 16 (256 for close objects)
        self.block_size = 5
        self.use_wls_filter = True

        self._rebuild_stereo()

    def load_calibration(self):
        """Load calibration data"""
        calib_file = f"{self.config.calibration_dir}/stereo_calibration.json"
        maps_file = f"{self.config.calibration_dir}/stereo_maps.npz"

        if not Path(calib_file).exists() or not Path(maps_file).exists():
            raise FileNotFoundError(f"Calibration files not found in {self.config.calibration_dir}")

        # Load calibration parameters
        with open(calib_file, 'r') as f:
            self.calib = json.load(f)

        # Load rectification maps
        maps = np.load(maps_file)
        self.map_l1 = maps['map_l1']
        self.map_l2 = maps['map_l2']
        self.map_r1 = maps['map_r1']
        self.map_r2 = maps['map_r2']
        self.Q = maps['Q']

        self.baseline_mm = self.calib['baseline_mm']
        self.focal_length = self.calib['projection_left'][0][0]  # fx from P1

        print(f"Loaded calibration: baseline={self.baseline_mm:.1f}mm, f={self.focal_length:.1f}px")

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

        # WLS filter for smoother results (reduced lambda for better edge preservation)
        self.right_matcher = cv2.ximgproc.createRightMatcher(self.stereo)
        self.wls_filter = cv2.ximgproc.createDisparityWLSFilter(self.stereo)
        self.wls_filter.setLambda(4000)  # Reduced from 8000 for less aggressive filtering
        self.wls_filter.setSigmaColor(1.2)

    def rectify(self, left: np.ndarray, right: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Apply rectification to stereo pair"""
        rect_left = cv2.remap(left, self.map_l1, self.map_l2, cv2.INTER_LINEAR)
        rect_right = cv2.remap(right, self.map_r1, self.map_r2, cv2.INTER_LINEAR)
        return rect_left, rect_right

    def compute(self, left: np.ndarray, right: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute disparity and depth from stereo pair.
        Returns (rectified_left, disparity_colormap, depth_meters)
        """
        # Rectify images
        rect_left, rect_right = self.rectify(left, right)

        # Convert to grayscale
        gray_l = cv2.cvtColor(rect_left, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(rect_right, cv2.COLOR_BGR2GRAY)

        # Compute disparity
        left_disp = self.stereo.compute(gray_l, gray_r)

        if self.use_wls_filter:
            right_disp = self.right_matcher.compute(gray_r, gray_l)
            filtered_disp = self.wls_filter.filter(left_disp, gray_l, None, right_disp)
        else:
            filtered_disp = left_disp

        # Convert to float (SGBM uses fixed-point with 4 fractional bits)
        disp_float = filtered_disp.astype(np.float32) / 16.0

        # Compute depth: Z = baseline * focal_length / disparity
        # Avoid division by zero
        disp_float[disp_float <= 0] = 0.1
        depth = (self.baseline_mm * self.focal_length) / disp_float / 1000.0  # Convert to meters

        # Clip unreasonable values
        depth[depth > 10.0] = 0  # Max 10m
        depth[depth < 0.1] = 0   # Min 10cm

        # Create visualization
        disp_vis = cv2.normalize(filtered_disp, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)

        return rect_left, disp_color, depth


def main():
    print("=" * 60)
    print("CALIBRATED STEREO DEPTH")
    print("=" * 60)
    print("Controls:")
    print("  q     - Quit")
    print("  s     - Save current frame")
    print("  +/-   - Adjust num_disparities")
    print("  [/]   - Adjust block_size")
    print("  f     - Toggle WLS filter")
    print("  Click - Measure depth at point")
    print("=" * 60)

    config = StereoConfig(
        left_device=1,
        right_device=0,
        width=1280,
        height=720,
        fps=30,
        rotate_90_cw=True,
        calibration_dir="calibration_data"
    )

    # Initialize cameras
    cam_left = ThreadedCamera(config.left_device, config.width, config.height)
    cam_right = ThreadedCamera(config.right_device, config.width, config.height)

    if not cam_left.start() or not cam_right.start():
        print("Error: Could not open cameras")
        return

    # Initialize depth computation
    try:
        depth_computer = CalibratedStereoDepth(config)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Run 'python stereo_calibration.py calibrate' first.")
        cam_left.stop()
        cam_right.stop()
        return

    # Load depth correction if available
    depth_correction = None
    use_correction = False
    if HAS_CORRECTION:
        depth_correction = DepthCorrection(config.calibration_dir)
        if depth_correction.coefficients is not None:
            use_correction = True
            print("Depth correction loaded and enabled (press 'c' to toggle)")
        else:
            print("No depth correction found. Run 'python depth_correction.py calibrate' to create one.")

    # Wait for cameras
    time.sleep(0.5)

    # Mouse callback for depth measurement
    mouse_state = {'x': 0, 'y': 0, 'clicked': False, 'click_x': 0, 'click_y': 0, 'click_depth': 0.0}

    def mouse_callback(event, x, y, flags, param):
        mouse_state['x'] = x
        mouse_state['y'] = y
        if event == cv2.EVENT_LBUTTONDOWN:
            mouse_state['clicked'] = True
            mouse_state['click_x'] = x
            mouse_state['click_y'] = y

    cv2.namedWindow("Calibrated Stereo Depth")
    cv2.setMouseCallback("Calibrated Stereo Depth", mouse_callback)

    frame_count = 0
    fps_start = time.time()
    fps = 0.0

    try:
        while True:
            frame_l = cam_left.get_frame()
            frame_r = cam_right.get_frame()

            if frame_l is None or frame_r is None:
                time.sleep(0.01)
                continue

            # Rotate if configured
            if config.rotate_90_cw:
                frame_l = cv2.rotate(frame_l, cv2.ROTATE_90_CLOCKWISE)
                frame_r = cv2.rotate(frame_r, cv2.ROTATE_90_CLOCKWISE)

            # Compute depth
            rect_left, disp_color, depth_raw = depth_computer.compute(frame_l, frame_r)

            # Apply correction if enabled
            if use_correction and depth_correction is not None:
                depth = depth_correction.correct(depth_raw)
            else:
                depth = depth_raw

            # FPS calculation
            frame_count += 1
            if frame_count % 30 == 0:
                fps = 30.0 / (time.time() - fps_start)
                fps_start = time.time()

            # Get depth at center
            h, w = depth.shape
            center_depth = depth[h // 2, w // 2]

            # Create display
            scale = 0.5
            rect_small = cv2.resize(rect_left, None, fx=scale, fy=scale)
            disp_small = cv2.resize(disp_color, None, fx=scale, fy=scale)

            # Draw crosshair on center
            ch, cw = rect_small.shape[:2]
            cv2.line(rect_small, (cw//2 - 20, ch//2), (cw//2 + 20, ch//2), (0, 255, 0), 1)
            cv2.line(rect_small, (cw//2, ch//2 - 20), (cw//2, ch//2 + 20), (0, 255, 0), 1)

            # Add overlays
            cv2.putText(disp_small, f"Center: {center_depth:.2f}m", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(disp_small, f"FPS: {fps:.1f}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            # Calculate min measurable depth
            min_depth = depth_computer.baseline_mm * depth_computer.focal_length / depth_computer.num_disparities / 1000
            corr_status = "CORR" if use_correction else "RAW"
            cv2.putText(disp_small, f"Disp:{depth_computer.num_disparities} Blk:{depth_computer.block_size} [{corr_status}]",
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(disp_small, f"Range: {min_depth:.2f}m - 10.0m",
                       (10, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Handle click measurement
            disp_small_w = disp_small.shape[1]
            rect_small_w = rect_small.shape[1]

            if mouse_state['clicked']:
                cx, cy = mouse_state['click_x'], mouse_state['click_y']
                # Check if click is on depth map (right side of display)
                if cx >= rect_small_w:
                    # Convert display coords to depth array coords
                    depth_x = int((cx - rect_small_w) / scale)
                    depth_y = int(cy / scale)
                    if 0 <= depth_y < depth.shape[0] and 0 <= depth_x < depth.shape[1]:
                        mouse_state['click_depth'] = depth[depth_y, depth_x]
                        print(f"Clicked at ({depth_x}, {depth_y}): {mouse_state['click_depth']:.3f}m")
                mouse_state['clicked'] = False

            # Show click depth and marker
            if mouse_state['click_depth'] > 0:
                cv2.putText(disp_small, f"Click: {mouse_state['click_depth']:.2f}m", (10, 140),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                # Draw marker at click position on depth map
                marker_x = mouse_state['click_x'] - rect_small_w
                marker_y = mouse_state['click_y']
                if 0 <= marker_x < disp_small_w and 0 <= marker_y < disp_small.shape[0]:
                    cv2.circle(disp_small, (marker_x, marker_y), 8, (0, 255, 255), 2)
                    cv2.line(disp_small, (marker_x - 12, marker_y), (marker_x + 12, marker_y), (0, 255, 255), 1)
                    cv2.line(disp_small, (marker_x, marker_y - 12), (marker_x, marker_y + 12), (0, 255, 255), 1)

            # Show live depth at mouse position (hover)
            mx, my = mouse_state['x'], mouse_state['y']
            if mx >= rect_small_w:
                hover_x = int((mx - rect_small_w) / scale)
                hover_y = int(my / scale)
                if 0 <= hover_y < depth.shape[0] and 0 <= hover_x < depth.shape[1]:
                    hover_depth = depth[hover_y, hover_x]
                    cv2.putText(disp_small, f"Hover: {hover_depth:.2f}m", (10, 165),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

            # Combine views
            display = np.hstack([rect_small, disp_small])

            # Draw horizontal line at mouse position (epipolar reference)
            if 0 <= my < display.shape[0]:
                cv2.line(display, (0, my), (display.shape[1], my), (0, 255, 0), 1)

            cv2.imshow("Calibrated Stereo Depth", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                timestamp = int(time.time())
                cv2.imwrite(f"/tmp/stereo_rect_{timestamp}.jpg", rect_left)
                cv2.imwrite(f"/tmp/stereo_disp_{timestamp}.jpg", disp_color)
                np.save(f"/tmp/stereo_depth_{timestamp}.npy", depth)
                print(f"Saved to /tmp/stereo_*_{timestamp}.*")
            elif key == ord('+') or key == ord('='):
                depth_computer.num_disparities = min(512, depth_computer.num_disparities + 16)
                depth_computer._rebuild_stereo()
                print(f"num_disparities: {depth_computer.num_disparities} (min depth: {depth_computer.baseline_mm * depth_computer.focal_length / depth_computer.num_disparities / 1000:.2f}m)")
            elif key == ord('-') or key == ord('_'):
                depth_computer.num_disparities = max(16, depth_computer.num_disparities - 16)
                depth_computer._rebuild_stereo()
                print(f"num_disparities: {depth_computer.num_disparities} (min depth: {depth_computer.baseline_mm * depth_computer.focal_length / depth_computer.num_disparities / 1000:.2f}m)")
            elif key == ord('['):
                depth_computer.block_size = max(3, depth_computer.block_size - 2)
                depth_computer._rebuild_stereo()
                print(f"block_size: {depth_computer.block_size}")
            elif key == ord(']'):
                depth_computer.block_size = min(21, depth_computer.block_size + 2)
                depth_computer._rebuild_stereo()
                print(f"block_size: {depth_computer.block_size}")
            elif key == ord('f'):
                depth_computer.use_wls_filter = not depth_computer.use_wls_filter
                print(f"WLS filter: {'on' if depth_computer.use_wls_filter else 'off'}")
            elif key == ord('c'):
                if depth_correction is not None and depth_correction.coefficients is not None:
                    use_correction = not use_correction
                    print(f"Depth correction: {'ON' if use_correction else 'OFF'}")
                else:
                    print("No depth correction available. Run 'python depth_correction.py calibrate' first.")

    except KeyboardInterrupt:
        pass
    finally:
        cam_left.stop()
        cam_right.stop()
        cv2.destroyAllWindows()
        print("Calibrated stereo depth finished.")


if __name__ == "__main__":
    main()
