#!/usr/bin/env python3
"""
Stereo Depth Debug Tool

Shows raw disparity values and helps diagnose why depth readings fail.
"""

import cv2
import numpy as np
import json
import threading
import time
from pathlib import Path
from typing import Optional


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


def main():
    print("=" * 60)
    print("STEREO DEPTH DEBUG")
    print("=" * 60)
    print("Controls:")
    print("  q     - Quit")
    print("  w     - Swap left/right cameras")
    print("  +/-   - Adjust num_disparities")
    print("  r     - Toggle rectification")
    print("=" * 60)

    # Load calibration
    calib_dir = "calibration_data"
    calib_file = f"{calib_dir}/stereo_calibration.json"
    maps_file = f"{calib_dir}/stereo_maps.npz"

    if not Path(calib_file).exists():
        print(f"ERROR: No calibration found at {calib_file}")
        return

    with open(calib_file, 'r') as f:
        calib = json.load(f)

    maps = np.load(maps_file)
    map_l1 = maps['map_l1']
    map_l2 = maps['map_l2']
    map_r1 = maps['map_r1']
    map_r2 = maps['map_r2']

    baseline_mm = calib['baseline_mm']
    focal_length = calib['projection_left'][0][0]

    print(f"Baseline: {baseline_mm:.1f}mm, Focal: {focal_length:.1f}px")

    # Camera setup
    left_device = 1
    right_device = 0
    width, height = 1280, 720
    rotate = True
    use_rectification = True
    num_disparities = 256
    swapped = False

    cam_left = ThreadedCamera(left_device, width, height)
    cam_right = ThreadedCamera(right_device, width, height)

    if not cam_left.start() or not cam_right.start():
        print("Error: Could not open cameras")
        return

    time.sleep(0.5)

    def build_stereo(num_disp):
        return cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=num_disp,
            blockSize=5,
            P1=8 * 3 * 5 ** 2,
            P2=32 * 3 * 5 ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
            preFilterCap=63,
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
        )

    stereo = build_stereo(num_disparities)

    try:
        while True:
            frame_l = cam_left.get_frame()
            frame_r = cam_right.get_frame()

            if frame_l is None or frame_r is None:
                time.sleep(0.01)
                continue

            # Swap if requested
            if swapped:
                frame_l, frame_r = frame_r, frame_l

            # Rotate if needed
            if rotate:
                frame_l = cv2.rotate(frame_l, cv2.ROTATE_90_CLOCKWISE)
                frame_r = cv2.rotate(frame_r, cv2.ROTATE_90_CLOCKWISE)

            # Rectify if enabled
            if use_rectification:
                rect_l = cv2.remap(frame_l, map_l1, map_l2, cv2.INTER_LINEAR)
                rect_r = cv2.remap(frame_r, map_r1, map_r2, cv2.INTER_LINEAR)
            else:
                rect_l, rect_r = frame_l, frame_r

            # Convert to grayscale
            gray_l = cv2.cvtColor(rect_l, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(rect_r, cv2.COLOR_BGR2GRAY)

            # Compute disparity
            disparity = stereo.compute(gray_l, gray_r)
            disp_float = disparity.astype(np.float32) / 16.0

            # Get center region stats
            h, w = disp_float.shape
            roi = disp_float[h//2-30:h//2+30, w//2-30:w//2+30]

            center_disp = disp_float[h//2, w//2]
            roi_mean = np.mean(roi[roi > 0]) if np.any(roi > 0) else 0
            roi_valid = np.sum(roi > 0)
            roi_total = roi.size
            roi_pct = 100 * roi_valid / roi_total

            # Compute depth from disparity
            if center_disp > 0:
                center_depth = (baseline_mm * focal_length) / center_disp / 1000.0
            else:
                center_depth = 0

            # Min depth at current settings
            min_depth = baseline_mm * focal_length / num_disparities / 1000.0

            # Create visualization
            scale = 0.4

            # Normalize disparity for display
            disp_vis = cv2.normalize(disparity, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
            disp_color = cv2.applyColorMap(disp_vis, cv2.COLORMAP_JET)

            # Side by side: left, right, disparity
            left_small = cv2.resize(rect_l, None, fx=scale, fy=scale)
            right_small = cv2.resize(rect_r, None, fx=scale, fy=scale)
            disp_small = cv2.resize(disp_color, None, fx=scale, fy=scale)

            # Draw crosshairs
            for img in [left_small, right_small, disp_small]:
                ch, cw = img.shape[:2]
                cv2.line(img, (cw//2-15, ch//2), (cw//2+15, ch//2), (0, 255, 0), 1)
                cv2.line(img, (cw//2, ch//2-15), (cw//2, ch//2+15), (0, 255, 0), 1)

            # Add labels
            cv2.putText(left_small, "LEFT" + (" (swapped)" if swapped else ""), (10, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(right_small, "RIGHT" + (" (swapped)" if swapped else ""), (10, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(disp_small, f"DISPARITY", (10, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # Debug info on disparity
            y = 50
            info_color = (255, 255, 255)
            cv2.putText(disp_small, f"Center disp: {center_disp:.1f}px", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, info_color, 1)
            y += 20
            cv2.putText(disp_small, f"ROI valid: {roi_pct:.0f}% ({roi_valid}/{roi_total})", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, info_color, 1)
            y += 20
            cv2.putText(disp_small, f"ROI mean disp: {roi_mean:.1f}px", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, info_color, 1)
            y += 20

            depth_color = (0, 255, 255) if center_depth > 0 else (0, 0, 255)
            cv2.putText(disp_small, f"Depth: {center_depth:.2f}m", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, depth_color, 2)
            y += 25
            cv2.putText(disp_small, f"numDisp: {num_disparities} (min {min_depth:.2f}m)", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
            y += 18
            rect_status = "ON" if use_rectification else "OFF"
            cv2.putText(disp_small, f"Rectify: {rect_status}", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

            # Draw horizontal epipolar line across all three
            display = np.hstack([left_small, right_small, disp_small])
            ch = display.shape[0]
            cv2.line(display, (0, ch//2), (display.shape[1], ch//2), (0, 255, 255), 1)

            cv2.imshow("Stereo Debug", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('w'):
                swapped = not swapped
                print(f"Cameras {'SWAPPED' if swapped else 'NORMAL'}")
            elif key == ord('+') or key == ord('='):
                num_disparities = min(512, num_disparities + 16)
                stereo = build_stereo(num_disparities)
                print(f"num_disparities: {num_disparities} (min depth: {baseline_mm * focal_length / num_disparities / 1000:.2f}m)")
            elif key == ord('-') or key == ord('_'):
                num_disparities = max(16, num_disparities - 16)
                stereo = build_stereo(num_disparities)
                print(f"num_disparities: {num_disparities} (min depth: {baseline_mm * focal_length / num_disparities / 1000:.2f}m)")
            elif key == ord('r'):
                use_rectification = not use_rectification
                print(f"Rectification: {'ON' if use_rectification else 'OFF'}")

    except KeyboardInterrupt:
        pass
    finally:
        cam_left.stop()
        cam_right.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
