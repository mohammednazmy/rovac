#!/usr/bin/env python3
"""
Depth Correction Calibration Tool

Measures actual vs reported depth at known distances to create a correction curve.
This compensates for systematic errors in stereo depth estimation.

Usage:
    python depth_correction.py calibrate  - Capture depth samples at known distances
    python depth_correction.py test       - Test correction with live view

Instructions:
    1. Place an object (flat surface works best) at a known distance
    2. Press 's' to save a sample, then enter the actual distance
    3. Repeat at 5-10 different distances (0.3m to 2m recommended)
    4. Press 'q' to finish and compute correction curve
"""

import cv2
import numpy as np
import json
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass
import sys


@dataclass
class StereoConfig:
    left_device: int = 1
    right_device: int = 0
    width: int = 1280
    height: int = 720
    rotate_90_cw: bool = True
    calibration_dir: str = "calibration_data"


class ThreadedCamera:
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


class DepthComputer:
    """Simplified depth computer for correction calibration"""

    def __init__(self, config: StereoConfig):
        self.config = config
        self.load_calibration()

        self.num_disparities = 256  # Reduced for better mid-range depth
        self.block_size = 5
        self.use_wls = False  # WLS can be too aggressive
        self._rebuild_stereo()

    def load_calibration(self):
        calib_file = f"{self.config.calibration_dir}/stereo_calibration.json"
        maps_file = f"{self.config.calibration_dir}/stereo_maps.npz"

        with open(calib_file, 'r') as f:
            self.calib = json.load(f)

        maps = np.load(maps_file)
        self.map_l1 = maps['map_l1']
        self.map_l2 = maps['map_l2']
        self.map_r1 = maps['map_r1']
        self.map_r2 = maps['map_r2']

        self.baseline_mm = self.calib['baseline_mm']
        self.focal_length = self.calib['projection_left'][0][0]

    def _rebuild_stereo(self):
        self.stereo = cv2.StereoSGBM_create(
            minDisparity=0,
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
        self.right_matcher = cv2.ximgproc.createRightMatcher(self.stereo)
        self.wls_filter = cv2.ximgproc.createDisparityWLSFilter(self.stereo)
        self.wls_filter.setLambda(8000)
        self.wls_filter.setSigmaColor(1.5)

    def compute(self, left: np.ndarray, right: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        rect_left = cv2.remap(left, self.map_l1, self.map_l2, cv2.INTER_LINEAR)
        rect_right = cv2.remap(right, self.map_r1, self.map_r2, cv2.INTER_LINEAR)

        gray_l = cv2.cvtColor(rect_left, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(rect_right, cv2.COLOR_BGR2GRAY)

        left_disp = self.stereo.compute(gray_l, gray_r)

        if self.use_wls:
            right_disp = self.right_matcher.compute(gray_r, gray_l)
            filtered_disp = self.wls_filter.filter(left_disp, gray_l, None, right_disp)
        else:
            filtered_disp = left_disp

        disp_float = filtered_disp.astype(np.float32) / 16.0
        disp_float[disp_float <= 0] = 0.1

        # Raw depth without correction
        depth = (self.baseline_mm * self.focal_length) / disp_float / 1000.0
        depth[depth > 10.0] = 0
        depth[depth < 0.05] = 0

        return rect_left, depth


class DepthCorrection:
    """Applies polynomial correction to depth measurements"""

    def __init__(self, calibration_dir: str = "calibration_data"):
        self.calibration_dir = calibration_dir
        self.coefficients = None
        self.load()

    def load(self) -> bool:
        """Load correction coefficients if they exist"""
        correction_file = f"{self.calibration_dir}/depth_correction.json"
        if Path(correction_file).exists():
            with open(correction_file, 'r') as f:
                data = json.load(f)
                self.coefficients = np.array(data['coefficients'])
                self.samples = data.get('samples', [])
                print(f"Loaded depth correction: {len(self.samples)} samples, degree {len(self.coefficients)-1}")
                return True
        return False

    def save(self, samples: List[Tuple[float, float]]):
        """Compute and save correction from samples"""
        if len(samples) < 3:
            print("Need at least 3 samples for correction curve")
            return False

        # Extract measured and actual depths
        measured = np.array([s[0] for s in samples])
        actual = np.array([s[1] for s in samples])

        # Fit polynomial (degree 2 usually works well)
        degree = min(2, len(samples) - 1)
        self.coefficients = np.polyfit(measured, actual, degree)

        # Compute fit quality
        predicted = np.polyval(self.coefficients, measured)
        rmse = np.sqrt(np.mean((predicted - actual) ** 2))

        correction_file = f"{self.calibration_dir}/depth_correction.json"
        with open(correction_file, 'w') as f:
            json.dump({
                'coefficients': self.coefficients.tolist(),
                'samples': samples,
                'rmse': rmse,
                'degree': degree
            }, f, indent=2)

        print(f"\nCorrection curve saved to {correction_file}")
        print(f"  Polynomial degree: {degree}")
        print(f"  RMSE: {rmse:.4f}m")
        print(f"  Coefficients: {self.coefficients}")

        return True

    def correct(self, depth: np.ndarray) -> np.ndarray:
        """Apply correction to depth array"""
        if self.coefficients is None:
            return depth

        corrected = np.polyval(self.coefficients, depth)
        corrected[depth <= 0] = 0  # Preserve invalid pixels
        return corrected

    def correct_single(self, depth: float) -> float:
        """Apply correction to single depth value"""
        if self.coefficients is None or depth <= 0:
            return depth
        return float(np.polyval(self.coefficients, depth))


def calibrate_correction(config: StereoConfig):
    """Interactive correction calibration"""
    print("=" * 60)
    print("DEPTH CORRECTION CALIBRATION")
    print("=" * 60)
    print("\nInstructions:")
    print("  1. Place a flat object at a KNOWN distance from cameras")
    print("  2. Aim center crosshair at the object")
    print("  3. Press 's' to capture, then type actual distance in meters")
    print("  4. Repeat at 5-10 different distances (0.3m to 2m)")
    print("  5. Press 'q' to finish and compute correction")
    print("\nControls:")
    print("  s - Save sample (prompts for actual distance)")
    print("  u - Undo last sample")
    print("  q - Quit and compute correction")
    print("=" * 60)

    cam_left = ThreadedCamera(config.left_device, config.width, config.height)
    cam_right = ThreadedCamera(config.right_device, config.width, config.height)

    if not cam_left.start() or not cam_right.start():
        print("Error: Could not open cameras")
        return

    depth_computer = DepthComputer(config)
    samples: List[Tuple[float, float]] = []  # (measured, actual)

    time.sleep(0.5)

    # For averaging multiple frames
    depth_buffer = []
    buffer_size = 10

    try:
        while True:
            frame_l = cam_left.get_frame()
            frame_r = cam_right.get_frame()

            if frame_l is None or frame_r is None:
                time.sleep(0.01)
                continue

            if config.rotate_90_cw:
                frame_l = cv2.rotate(frame_l, cv2.ROTATE_90_CLOCKWISE)
                frame_r = cv2.rotate(frame_r, cv2.ROTATE_90_CLOCKWISE)

            rect_left, depth = depth_computer.compute(frame_l, frame_r)

            # Get center depth (average over small region for stability)
            h, w = depth.shape
            roi = depth[h//2-30:h//2+30, w//2-30:w//2+30]  # Larger ROI
            valid_depths = roi[roi > 0]
            valid_pct = 100 * len(valid_depths) / roi.size if roi.size > 0 else 0
            if len(valid_depths) > 0:
                center_depth = np.median(valid_depths)
                depth_buffer.append(center_depth)
                if len(depth_buffer) > buffer_size:
                    depth_buffer.pop(0)
            else:
                center_depth = 0

            # Smoothed depth from buffer
            if depth_buffer:
                smoothed_depth = np.median(depth_buffer)
            else:
                smoothed_depth = 0

            # Create display
            scale = 0.5
            display = cv2.resize(rect_left, None, fx=scale, fy=scale)
            h_disp, w_disp = display.shape[:2]

            # Draw crosshair
            cv2.line(display, (w_disp//2 - 30, h_disp//2), (w_disp//2 + 30, h_disp//2), (0, 255, 0), 2)
            cv2.line(display, (w_disp//2, h_disp//2 - 30), (w_disp//2, h_disp//2 + 30), (0, 255, 0), 2)
            cv2.rectangle(display, (w_disp//2 - 20, h_disp//2 - 20),
                         (w_disp//2 + 20, h_disp//2 + 20), (0, 255, 0), 1)

            # Overlay info
            cv2.putText(display, f"Measured: {smoothed_depth:.3f}m", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(display, f"ROI valid: {valid_pct:.0f}%", (10, 55),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(display, f"Samples: {len(samples)}", (10, 80),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Show existing samples
            y_offset = 110
            for i, (meas, act) in enumerate(samples[-5:]):  # Show last 5
                cv2.putText(display, f"  {meas:.2f}m -> {act:.2f}m", (10, y_offset),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                y_offset += 20

            cv2.imshow("Depth Correction Calibration", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                if smoothed_depth > 0:
                    cv2.destroyAllWindows()
                    actual_str = input(f"\nMeasured depth: {smoothed_depth:.3f}m\nEnter ACTUAL distance in meters: ")
                    try:
                        actual = float(actual_str)
                        if 0.1 <= actual <= 10.0:
                            samples.append((smoothed_depth, actual))
                            print(f"Sample added: measured={smoothed_depth:.3f}m, actual={actual:.3f}m")
                        else:
                            print("Distance must be between 0.1 and 10.0 meters")
                    except ValueError:
                        print("Invalid input, sample not saved")
                    cv2.namedWindow("Depth Correction Calibration")
                else:
                    print("No valid depth reading at center")
            elif key == ord('u'):
                if samples:
                    removed = samples.pop()
                    print(f"Removed sample: {removed}")

    except KeyboardInterrupt:
        pass
    finally:
        cam_left.stop()
        cam_right.stop()
        cv2.destroyAllWindows()

    # Compute and save correction
    if len(samples) >= 3:
        print(f"\nComputing correction from {len(samples)} samples...")
        correction = DepthCorrection(config.calibration_dir)
        correction.save(samples)

        # Show comparison
        print("\nSample comparison (measured -> corrected vs actual):")
        for meas, act in samples:
            corr = correction.correct_single(meas)
            error = abs(corr - act)
            print(f"  {meas:.3f}m -> {corr:.3f}m (actual: {act:.3f}m, error: {error:.3f}m)")
    else:
        print(f"\nOnly {len(samples)} samples collected. Need at least 3 for correction curve.")


def test_correction(config: StereoConfig):
    """Test depth with correction applied"""
    print("=" * 60)
    print("TESTING DEPTH CORRECTION")
    print("=" * 60)

    correction = DepthCorrection(config.calibration_dir)
    if correction.coefficients is None:
        print("No correction data found. Run 'calibrate' first.")
        return

    cam_left = ThreadedCamera(config.left_device, config.width, config.height)
    cam_right = ThreadedCamera(config.right_device, config.width, config.height)

    if not cam_left.start() or not cam_right.start():
        print("Error: Could not open cameras")
        return

    depth_computer = DepthComputer(config)
    time.sleep(0.5)

    print("\nControls: q=quit, c=toggle correction")
    use_correction = True

    try:
        while True:
            frame_l = cam_left.get_frame()
            frame_r = cam_right.get_frame()

            if frame_l is None or frame_r is None:
                time.sleep(0.01)
                continue

            if config.rotate_90_cw:
                frame_l = cv2.rotate(frame_l, cv2.ROTATE_90_CLOCKWISE)
                frame_r = cv2.rotate(frame_r, cv2.ROTATE_90_CLOCKWISE)

            rect_left, depth_raw = depth_computer.compute(frame_l, frame_r)

            # Apply correction
            if use_correction:
                depth = correction.correct(depth_raw)
            else:
                depth = depth_raw

            # Get center depth
            h, w = depth.shape
            roi = depth[h//2-20:h//2+20, w//2-20:w//2+20]
            valid = roi[roi > 0]
            center_depth = np.median(valid) if len(valid) > 0 else 0

            roi_raw = depth_raw[h//2-20:h//2+20, w//2-20:w//2+20]
            valid_raw = roi_raw[roi_raw > 0]
            center_raw = np.median(valid_raw) if len(valid_raw) > 0 else 0

            # Create display
            scale = 0.5
            disp_vis = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
            disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)

            rect_small = cv2.resize(rect_left, None, fx=scale, fy=scale)
            disp_small = cv2.resize(disp_color, None, fx=scale, fy=scale)

            # Crosshair
            h_disp, w_disp = rect_small.shape[:2]
            cv2.line(rect_small, (w_disp//2 - 20, h_disp//2), (w_disp//2 + 20, h_disp//2), (0, 255, 0), 2)
            cv2.line(rect_small, (w_disp//2, h_disp//2 - 20), (w_disp//2, h_disp//2 + 20), (0, 255, 0), 2)

            # Info overlay
            status = "CORRECTED" if use_correction else "RAW"
            cv2.putText(disp_small, f"{status}: {center_depth:.2f}m", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(disp_small, f"Raw: {center_raw:.2f}m", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(disp_small, "Press 'c' to toggle correction", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

            display = np.hstack([rect_small, disp_small])
            cv2.imshow("Depth Correction Test", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('c'):
                use_correction = not use_correction
                print(f"Correction: {'ON' if use_correction else 'OFF'}")

    except KeyboardInterrupt:
        pass
    finally:
        cam_left.stop()
        cam_right.stop()
        cv2.destroyAllWindows()


def main():
    config = StereoConfig()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python depth_correction.py calibrate - Capture samples at known distances")
        print("  python depth_correction.py test      - Test with correction applied")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "calibrate":
        calibrate_correction(config)
    elif mode == "test":
        test_correction(config)
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
