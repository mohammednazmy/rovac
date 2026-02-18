#!/usr/bin/env python3
"""
Interactive Depth Correction Calibration

Uses on-screen controls instead of terminal input for easier calibration.
Place objects at known distances and use keyboard to record samples.

Controls:
    1-9     - Record sample at 0.1m to 0.9m actual distance
    0       - Record sample at 1.0m actual distance
    Shift+1-5 - Record sample at 1.1m to 1.5m (hold shift)
    c       - Record custom distance (shows input dialog)
    u       - Undo last sample
    q       - Quit and compute correction curve
    ESC     - Quit without saving
"""

import cv2
import numpy as np
import json
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass


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
    def __init__(self, config: StereoConfig):
        self.config = config
        self.load_calibration()
        self.num_disparities = 256
        self.block_size = 5
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

    def compute(self, left: np.ndarray, right: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        rect_left = cv2.remap(left, self.map_l1, self.map_l2, cv2.INTER_LINEAR)
        rect_right = cv2.remap(right, self.map_r1, self.map_r2, cv2.INTER_LINEAR)

        gray_l = cv2.cvtColor(rect_left, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(rect_right, cv2.COLOR_BGR2GRAY)

        disparity = self.stereo.compute(gray_l, gray_r)
        disp_float = disparity.astype(np.float32) / 16.0
        disp_float[disp_float <= 0] = 0.1

        depth = (self.baseline_mm * self.focal_length) / disp_float / 1000.0
        depth[depth > 10.0] = 0
        depth[depth < 0.05] = 0

        return rect_left, depth


def save_correction(calibration_dir: str, samples: List[Tuple[float, float]]):
    """Compute and save correction curve"""
    if len(samples) < 3:
        print("Need at least 3 samples")
        return False

    measured = np.array([s[0] for s in samples])
    actual = np.array([s[1] for s in samples])

    degree = min(2, len(samples) - 1)
    coefficients = np.polyfit(measured, actual, degree)

    predicted = np.polyval(coefficients, measured)
    rmse = np.sqrt(np.mean((predicted - actual) ** 2))

    correction_file = f"{calibration_dir}/depth_correction.json"
    with open(correction_file, 'w') as f:
        json.dump({
            'coefficients': coefficients.tolist(),
            'samples': samples,
            'rmse': rmse,
            'degree': degree
        }, f, indent=2)

    print(f"\n{'='*50}")
    print("CORRECTION SAVED")
    print(f"{'='*50}")
    print(f"File: {correction_file}")
    print(f"Samples: {len(samples)}")
    print(f"RMSE: {rmse:.4f}m")
    print(f"Coefficients: {coefficients}")
    print(f"\nSample comparison:")
    for meas, act in samples:
        corr = np.polyval(coefficients, meas)
        error = abs(corr - act)
        print(f"  {meas:.3f}m -> {corr:.3f}m (actual: {act:.3f}m, error: {error:.3f}m)")

    return True


def main():
    print("=" * 60)
    print("INTERACTIVE DEPTH CALIBRATION")
    print("=" * 60)
    print("\nPlace object at KNOWN distance, aim crosshair at it.")
    print("\nKEYBOARD SHORTCUTS:")
    print("  1-9    = Record at 0.1m - 0.9m")
    print("  0      = Record at 1.0m")
    print("  a-e    = Record at 1.1m - 1.5m")
    print("  f-j    = Record at 1.6m - 2.0m")
    print("  u      = Undo last sample")
    print("  q      = Save and quit")
    print("  ESC    = Quit without saving")
    print("=" * 60)

    config = StereoConfig()

    cam_left = ThreadedCamera(config.left_device, config.width, config.height)
    cam_right = ThreadedCamera(config.right_device, config.width, config.height)

    if not cam_left.start() or not cam_right.start():
        print("Error: Could not open cameras")
        return

    depth_computer = DepthComputer(config)
    samples: List[Tuple[float, float]] = []

    time.sleep(0.5)

    depth_buffer = []
    buffer_size = 15
    last_message = ""
    message_time = 0

    # Distance mapping for keys
    key_distances = {
        ord('1'): 0.1, ord('2'): 0.2, ord('3'): 0.3, ord('4'): 0.4, ord('5'): 0.5,
        ord('6'): 0.6, ord('7'): 0.7, ord('8'): 0.8, ord('9'): 0.9, ord('0'): 1.0,
        ord('a'): 1.1, ord('b'): 1.2, ord('c'): 1.3, ord('d'): 1.4, ord('e'): 1.5,
        ord('f'): 1.6, ord('g'): 1.7, ord('h'): 1.8, ord('i'): 1.9, ord('j'): 2.0,
    }

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

            # Get center depth
            h, w = depth.shape
            roi = depth[h//2-30:h//2+30, w//2-30:w//2+30]
            valid_depths = roi[roi > 0]
            valid_pct = 100 * len(valid_depths) / roi.size if roi.size > 0 else 0

            if len(valid_depths) > 0:
                center_depth = np.median(valid_depths)
                depth_buffer.append(center_depth)
                if len(depth_buffer) > buffer_size:
                    depth_buffer.pop(0)
            else:
                center_depth = 0

            smoothed_depth = np.median(depth_buffer) if depth_buffer else 0

            # Create display
            scale = 0.6
            display = cv2.resize(rect_left, None, fx=scale, fy=scale)
            h_disp, w_disp = display.shape[:2]

            # Draw crosshair
            cv2.line(display, (w_disp//2 - 40, h_disp//2), (w_disp//2 + 40, h_disp//2), (0, 255, 0), 2)
            cv2.line(display, (w_disp//2, h_disp//2 - 40), (w_disp//2, h_disp//2 + 40), (0, 255, 0), 2)
            cv2.rectangle(display, (w_disp//2 - 30, h_disp//2 - 30),
                         (w_disp//2 + 30, h_disp//2 + 30), (0, 255, 0), 1)

            # Info panel background
            cv2.rectangle(display, (5, 5), (280, 180), (0, 0, 0), -1)
            cv2.rectangle(display, (5, 5), (280, 180), (100, 100, 100), 1)

            # Depth reading
            depth_color = (0, 255, 255) if smoothed_depth > 0 else (0, 0, 255)
            cv2.putText(display, f"MEASURED: {smoothed_depth:.3f}m", (15, 35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, depth_color, 2)

            # ROI validity
            roi_color = (0, 255, 0) if valid_pct > 30 else (0, 165, 255) if valid_pct > 10 else (0, 0, 255)
            cv2.putText(display, f"ROI Valid: {valid_pct:.0f}%", (15, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, roi_color, 1)

            # Sample count
            cv2.putText(display, f"Samples: {len(samples)}", (15, 85),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Show last few samples
            y = 110
            for meas, act in samples[-4:]:
                cv2.putText(display, f"  {meas:.2f}m -> {act:.2f}m", (15, y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                y += 18

            # Show message if recent
            if time.time() - message_time < 2.0 and last_message:
                cv2.putText(display, last_message, (15, h_disp - 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Key hints at bottom
            cv2.putText(display, "Keys: 1-9=0.1-0.9m  0=1.0m  a-e=1.1-1.5m  f-j=1.6-2.0m",
                       (15, h_disp - 45), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)
            cv2.putText(display, "u=undo  q=save&quit  ESC=quit",
                       (15, h_disp - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)

            cv2.imshow("Depth Calibration", display)

            key = cv2.waitKey(1) & 0xFF

            if key == 27:  # ESC
                print("Cancelled without saving")
                break
            elif key == ord('q'):
                if len(samples) >= 3:
                    save_correction(config.calibration_dir, samples)
                else:
                    print(f"Only {len(samples)} samples. Need at least 3.")
                break
            elif key == ord('u'):
                if samples:
                    removed = samples.pop()
                    last_message = f"Removed: {removed[1]:.2f}m"
                    message_time = time.time()
                    print(f"Removed sample: {removed}")
            elif key in key_distances:
                if smoothed_depth > 0:
                    actual = key_distances[key]
                    samples.append((smoothed_depth, actual))
                    last_message = f"Added: {smoothed_depth:.2f}m -> {actual:.2f}m"
                    message_time = time.time()
                    print(f"Sample {len(samples)}: measured={smoothed_depth:.3f}m, actual={actual:.2f}m")
                else:
                    last_message = "No valid depth!"
                    message_time = time.time()

    except KeyboardInterrupt:
        pass
    finally:
        cam_left.stop()
        cam_right.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
