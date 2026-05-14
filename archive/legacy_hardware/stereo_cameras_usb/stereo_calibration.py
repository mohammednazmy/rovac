#!/usr/bin/env python3
"""
Stereo Camera Calibration Tool

Captures checkerboard images from both cameras and computes:
- Intrinsic parameters (focal length, principal point, distortion)
- Extrinsic parameters (relative position/rotation between cameras)
- Rectification transforms for stereo matching

Usage:
    1. Print a checkerboard pattern (9x6 inner corners recommended)
    2. Run: python stereo_calibration.py capture
    3. Hold checkerboard at various angles/distances, press 's' to save
    4. Capture 15-20 image pairs
    5. Run: python stereo_calibration.py calibrate

Controls during capture:
    s - Save current frame pair (if checkerboard detected in both)
    q - Quit and proceed to calibration
    c - Clear all captured images
"""

import cv2
import numpy as np
import glob
import os
import json
import sys
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CalibrationConfig:
    """Calibration configuration"""
    # Swapped: device 1 is physically on the left, device 0 is on the right
    left_device: int = 1
    right_device: int = 0
    width: int = 1280
    height: int = 720
    checkerboard_cols: int = 9  # Inner corners (not squares)
    checkerboard_rows: int = 6
    square_size_mm: float = 25.0  # Size of each square in mm
    rotate_90_cw: bool = True
    output_dir: str = "calibration_data"


class ThreadedCamera:
    """Threaded camera capture to prevent blocking/timeout issues"""

    def __init__(self, device_id: int, width: int, height: int):
        self.device_id = device_id
        self.width = width
        self.height = height
        self.frame: Optional[np.ndarray] = None
        self.running = False
        self.lock = threading.Lock()
        self.cap: Optional[cv2.VideoCapture] = None
        self.read_count = 0
        self.fail_count = 0
        self.last_frame_time = 0

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
        consecutive_fails = 0
        while self.running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    with self.lock:
                        self.frame = frame
                        self.last_frame_time = time.time()
                    self.read_count += 1
                    consecutive_fails = 0
                else:
                    self.fail_count += 1
                    consecutive_fails += 1
                    # Auto-recover if too many consecutive failures
                    if consecutive_fails > 30:
                        print(f"[Cam {self.device_id}] Recovering from {consecutive_fails} consecutive fails...")
                        self.cap.release()
                        time.sleep(0.3)
                        self.cap = cv2.VideoCapture(self.device_id)
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        consecutive_fails = 0
            time.sleep(0.001)  # Minimal delay

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def get_stats(self) -> str:
        age = time.time() - self.last_frame_time if self.last_frame_time > 0 else 0
        return f"r:{self.read_count} f:{self.fail_count} age:{age:.1f}s"

    def stop(self):
        self.running = False
        time.sleep(0.1)
        if self.cap:
            self.cap.release()


def ensure_dir(path: str):
    """Create directory if it doesn't exist"""
    Path(path).mkdir(parents=True, exist_ok=True)


class StereoCalibrationCapture:
    """Capture checkerboard images for calibration"""

    def __init__(self, config: CalibrationConfig):
        self.config = config
        self.output_dir = config.output_dir
        ensure_dir(self.output_dir)
        ensure_dir(f"{self.output_dir}/left")
        ensure_dir(f"{self.output_dir}/right")

        self.checkerboard_size = (config.checkerboard_cols, config.checkerboard_rows)
        self.criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    def capture(self):
        """Interactive capture of checkerboard images"""
        # Use threaded cameras to prevent blocking/timeout issues
        cam_left = ThreadedCamera(self.config.left_device, self.config.width, self.config.height)
        cam_right = ThreadedCamera(self.config.right_device, self.config.width, self.config.height)

        if not cam_left.start() or not cam_right.start():
            print("Error: Could not open cameras")
            return

        # Wait for cameras to initialize
        time.sleep(1.0)

        # Count existing images
        existing = len(glob.glob(f"{self.output_dir}/left/*.jpg"))
        img_count = existing

        print(f"\n{'='*60}")
        print("STEREO CALIBRATION CAPTURE")
        print(f"{'='*60}")
        print(f"Checkerboard: {self.config.checkerboard_cols}x{self.config.checkerboard_rows} inner corners")
        print(f"Existing images: {existing}")
        print(f"\nControls:")
        print(f"  s - Save frame pair (when checkerboard detected)")
        print(f"  q - Quit and calibrate")
        print(f"  c - Clear all captured images")
        print(f"{'='*60}\n")

        while True:
            frame_l = cam_left.get_frame()
            frame_r = cam_right.get_frame()

            if frame_l is None or frame_r is None:
                time.sleep(0.01)
                continue

            # Rotate if configured
            if self.config.rotate_90_cw:
                frame_l = cv2.rotate(frame_l, cv2.ROTATE_90_CLOCKWISE)
                frame_r = cv2.rotate(frame_r, cv2.ROTATE_90_CLOCKWISE)

            # Convert to grayscale for corner detection
            gray_l = cv2.cvtColor(frame_l, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(frame_r, cv2.COLOR_BGR2GRAY)

            # Find checkerboard corners
            found_l, corners_l = cv2.findChessboardCorners(gray_l, self.checkerboard_size, None)
            found_r, corners_r = cv2.findChessboardCorners(gray_r, self.checkerboard_size, None)

            # Draw corners on display frames
            display_l = frame_l.copy()
            display_r = frame_r.copy()

            if found_l:
                corners_l = cv2.cornerSubPix(gray_l, corners_l, (11, 11), (-1, -1), self.criteria)
                cv2.drawChessboardCorners(display_l, self.checkerboard_size, corners_l, found_l)

            if found_r:
                corners_r = cv2.cornerSubPix(gray_r, corners_r, (11, 11), (-1, -1), self.criteria)
                cv2.drawChessboardCorners(display_r, self.checkerboard_size, corners_r, found_r)

            # Status overlay
            status_l = "DETECTED" if found_l else "NOT FOUND"
            status_r = "DETECTED" if found_r else "NOT FOUND"
            color_l = (0, 255, 0) if found_l else (0, 0, 255)
            color_r = (0, 255, 0) if found_r else (0, 0, 255)

            cv2.putText(display_l, f"Left: {status_l}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_l, 2)
            cv2.putText(display_r, f"Right: {status_r}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_r, 2)
            cv2.putText(display_l, f"Captured: {img_count}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            # Show camera stats for debugging
            cv2.putText(display_l, f"L:{cam_left.get_stats()}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            cv2.putText(display_r, f"R:{cam_right.get_stats()}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            # Resize for display
            scale = 0.5
            display_l_small = cv2.resize(display_l, None, fx=scale, fy=scale)
            display_r_small = cv2.resize(display_r, None, fx=scale, fy=scale)
            display = np.hstack([display_l_small, display_r_small])

            cv2.imshow("Stereo Calibration (s=save, q=quit, c=clear)", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                if found_l and found_r:
                    # Save images
                    cv2.imwrite(f"{self.output_dir}/left/img_{img_count:03d}.jpg", frame_l)
                    cv2.imwrite(f"{self.output_dir}/right/img_{img_count:03d}.jpg", frame_r)
                    img_count += 1
                    print(f"Saved pair {img_count} - checkerboard detected in both cameras")
                else:
                    print(f"Cannot save: checkerboard not detected in both cameras (L:{found_l} R:{found_r})")
            elif key == ord('c'):
                # Clear all images
                for f in glob.glob(f"{self.output_dir}/left/*.jpg"):
                    os.remove(f)
                for f in glob.glob(f"{self.output_dir}/right/*.jpg"):
                    os.remove(f)
                img_count = 0
                print("Cleared all captured images")

        cam_left.stop()
        cam_right.stop()
        cv2.destroyAllWindows()

        print(f"\nCapture complete. {img_count} image pairs saved.")
        return img_count


class StereoCalibrator:
    """Compute stereo calibration from captured images"""

    def __init__(self, config: CalibrationConfig):
        self.config = config
        self.checkerboard_size = (config.checkerboard_cols, config.checkerboard_rows)
        self.criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

        # Prepare object points (0,0,0), (1,0,0), (2,0,0) ... scaled by square size
        self.objp = np.zeros((config.checkerboard_rows * config.checkerboard_cols, 3), np.float32)
        self.objp[:, :2] = np.mgrid[0:config.checkerboard_cols, 0:config.checkerboard_rows].T.reshape(-1, 2)
        self.objp *= config.square_size_mm

    def calibrate(self) -> dict:
        """Perform stereo calibration"""
        left_images = sorted(glob.glob(f"{self.config.output_dir}/left/*.jpg"))
        right_images = sorted(glob.glob(f"{self.config.output_dir}/right/*.jpg"))

        if len(left_images) == 0:
            print("Error: No calibration images found")
            return None

        if len(left_images) != len(right_images):
            print(f"Error: Mismatched image counts (left: {len(left_images)}, right: {len(right_images)})")
            return None

        print(f"\nCalibrating with {len(left_images)} image pairs...")

        obj_points = []  # 3D points in world space
        img_points_l = []  # 2D points in left image
        img_points_r = []  # 2D points in right image
        valid_pairs = []  # Track which pairs are valid

        img_size = None

        for i, (left_path, right_path) in enumerate(zip(left_images, right_images)):
            img_l = cv2.imread(left_path)
            img_r = cv2.imread(right_path)

            if img_l is None or img_r is None:
                print(f"  Skipping pair {i}: could not read images")
                continue

            gray_l = cv2.cvtColor(img_l, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(img_r, cv2.COLOR_BGR2GRAY)

            if img_size is None:
                img_size = gray_l.shape[::-1]

            # Find corners
            found_l, corners_l = cv2.findChessboardCorners(gray_l, self.checkerboard_size, None)
            found_r, corners_r = cv2.findChessboardCorners(gray_r, self.checkerboard_size, None)

            if found_l and found_r:
                corners_l = cv2.cornerSubPix(gray_l, corners_l, (11, 11), (-1, -1), self.criteria)
                corners_r = cv2.cornerSubPix(gray_r, corners_r, (11, 11), (-1, -1), self.criteria)

                obj_points.append(self.objp)
                img_points_l.append(corners_l)
                img_points_r.append(corners_r)
                valid_pairs.append(i)
                print(f"  Pair {i+1}: OK")
            else:
                print(f"  Pair {i+1}: Skipped (corners not found)")

        if len(obj_points) < 5:
            print(f"Error: Need at least 5 valid pairs, got {len(obj_points)}")
            return None

        print(f"\nUsing {len(obj_points)} valid pairs for calibration...")

        # Calibrate each camera individually first
        print("\n" + "="*50)
        print("INDIVIDUAL CAMERA CALIBRATION")
        print("="*50)

        print("\nCalibrating left camera...")
        ret_l, mtx_l, dist_l, rvecs_l, tvecs_l = cv2.calibrateCamera(
            obj_points, img_points_l, img_size, None, None)
        print(f"  RMS error: {ret_l:.4f}")

        # Validate left camera matrix
        cx_l, cy_l = mtx_l[0, 2], mtx_l[1, 2]
        fx_l, fy_l = mtx_l[0, 0], mtx_l[1, 1]
        print(f"  Focal length: fx={fx_l:.1f}, fy={fy_l:.1f}")
        print(f"  Principal point: cx={cx_l:.1f}, cy={cy_l:.1f}")
        print(f"  Distortion k1={dist_l[0,0]:.3f}, k2={dist_l[0,1]:.3f}")

        # Check for invalid calibration
        if cx_l < 0 or cy_l < 0 or cx_l > img_size[0] or cy_l > img_size[1]:
            print(f"  WARNING: Principal point outside image bounds!")
        if abs(dist_l[0,0]) > 1.0 or abs(dist_l[0,1]) > 5.0:
            print(f"  WARNING: Distortion coefficients are unusually large!")

        print("\nCalibrating right camera...")
        ret_r, mtx_r, dist_r, rvecs_r, tvecs_r = cv2.calibrateCamera(
            obj_points, img_points_r, img_size, None, None)
        print(f"  RMS error: {ret_r:.4f}")

        # Validate right camera matrix
        cx_r, cy_r = mtx_r[0, 2], mtx_r[1, 2]
        fx_r, fy_r = mtx_r[0, 0], mtx_r[1, 1]
        print(f"  Focal length: fx={fx_r:.1f}, fy={fy_r:.1f}")
        print(f"  Principal point: cx={cx_r:.1f}, cy={cy_r:.1f}")
        print(f"  Distortion k1={dist_r[0,0]:.3f}, k2={dist_r[0,1]:.3f}")

        if cx_r < 0 or cy_r < 0 or cx_r > img_size[0] or cy_r > img_size[1]:
            print(f"  WARNING: Principal point outside image bounds!")
        if abs(dist_r[0,0]) > 1.0 or abs(dist_r[0,1]) > 5.0:
            print(f"  WARNING: Distortion coefficients are unusually large!")

        # Compute per-image reprojection errors
        print("\nPer-image reprojection errors:")
        errors_l = []
        errors_r = []
        for i, (objp, imgp_l, imgp_r, rvec_l, tvec_l, rvec_r, tvec_r) in enumerate(
            zip(obj_points, img_points_l, img_points_r, rvecs_l, tvecs_l, rvecs_r, tvecs_r)):

            # Left camera error
            proj_l, _ = cv2.projectPoints(objp, rvec_l, tvec_l, mtx_l, dist_l)
            err_l = cv2.norm(imgp_l, proj_l, cv2.NORM_L2) / len(proj_l)
            errors_l.append(err_l)

            # Right camera error
            proj_r, _ = cv2.projectPoints(objp, rvec_r, tvec_r, mtx_r, dist_r)
            err_r = cv2.norm(imgp_r, proj_r, cv2.NORM_L2) / len(proj_r)
            errors_r.append(err_r)

            status = ""
            if err_l > 1.0 or err_r > 1.0:
                status = " <-- HIGH ERROR"
            print(f"  Pair {valid_pairs[i]+1}: L={err_l:.3f}, R={err_r:.3f}{status}")

        # Warn about high-error images
        high_error_pairs = [valid_pairs[i]+1 for i, (el, er) in enumerate(zip(errors_l, errors_r)) if el > 1.0 or er > 1.0]
        if high_error_pairs:
            print(f"\nWARNING: Pairs with high error (>1.0): {high_error_pairs}")
            print("Consider recapturing these images or removing them.")

        # Stereo calibration
        print("Performing stereo calibration...")
        flags = cv2.CALIB_FIX_INTRINSIC  # Use intrinsics from individual calibration

        ret_stereo, mtx_l, dist_l, mtx_r, dist_r, R, T, E, F = cv2.stereoCalibrate(
            obj_points, img_points_l, img_points_r,
            mtx_l, dist_l, mtx_r, dist_r, img_size,
            criteria=self.criteria, flags=flags)

        print(f"  Stereo RMS error: {ret_stereo:.4f}")

        # Compute rectification transforms
        print("Computing rectification transforms...")
        R1, R2, P1, P2, Q, roi_l, roi_r = cv2.stereoRectify(
            mtx_l, dist_l, mtx_r, dist_r, img_size, R, T,
            flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)

        # Compute rectification maps
        map_l1, map_l2 = cv2.initUndistortRectifyMap(mtx_l, dist_l, R1, P1, img_size, cv2.CV_32FC1)
        map_r1, map_r2 = cv2.initUndistortRectifyMap(mtx_r, dist_r, R2, P2, img_size, cv2.CV_32FC1)

        # Calculate baseline
        baseline_mm = np.linalg.norm(T)
        print(f"\nBaseline: {baseline_mm:.2f} mm ({baseline_mm/10:.2f} cm)")

        # Save calibration
        calibration = {
            'image_size': list(img_size),
            'left_camera_matrix': mtx_l.tolist(),
            'left_distortion': dist_l.tolist(),
            'right_camera_matrix': mtx_r.tolist(),
            'right_distortion': dist_r.tolist(),
            'rotation_matrix': R.tolist(),
            'translation_vector': T.tolist(),
            'essential_matrix': E.tolist(),
            'fundamental_matrix': F.tolist(),
            'rectification_left': R1.tolist(),
            'rectification_right': R2.tolist(),
            'projection_left': P1.tolist(),
            'projection_right': P2.tolist(),
            'disparity_to_depth': Q.tolist(),
            'roi_left': list(roi_l),
            'roi_right': list(roi_r),
            'baseline_mm': float(baseline_mm),
            'rms_error': float(ret_stereo),
            'num_images': len(obj_points),
            'checkerboard_size': list(self.checkerboard_size),
            'square_size_mm': self.config.square_size_mm,
        }

        # Save JSON
        calib_file = f"{self.config.output_dir}/stereo_calibration.json"
        with open(calib_file, 'w') as f:
            json.dump(calibration, f, indent=2)
        print(f"\nCalibration saved to: {calib_file}")

        # Save numpy maps for fast loading
        np.savez(f"{self.config.output_dir}/stereo_maps.npz",
                 map_l1=map_l1, map_l2=map_l2,
                 map_r1=map_r1, map_r2=map_r2,
                 Q=Q)
        print(f"Rectification maps saved to: {self.config.output_dir}/stereo_maps.npz")

        return calibration


def main():
    # IMPORTANT: Device mapping verified through testing:
    # - Device 1 = physically LEFT camera
    # - Device 0 = physically RIGHT camera
    config = CalibrationConfig(
        left_device=1,   # LEFT camera (verified)
        right_device=0,  # RIGHT camera (verified)
        width=1280,
        height=720,
        checkerboard_cols=9,  # Inner corners
        checkerboard_rows=6,
        square_size_mm=25.0,  # Adjust to your checkerboard!
        rotate_90_cw=True,
        output_dir="calibration_data"
    )

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python stereo_calibration.py capture   - Capture checkerboard images")
        print("  python stereo_calibration.py calibrate - Compute calibration from images")
        print("  python stereo_calibration.py verify    - Visually verify calibration quality")
        print("  python stereo_calibration.py both      - Capture then calibrate")
        print("  python stereo_calibration.py clear     - Clear all captured images")
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "capture":
        capturer = StereoCalibrationCapture(config)
        capturer.capture()

    elif mode == "calibrate":
        calibrator = StereoCalibrator(config)
        calibration = calibrator.calibrate()
        if calibration:
            print("\nCalibration complete!")
            print(f"  Baseline: {calibration['baseline_mm']:.1f} mm")
            print(f"  RMS Error: {calibration['rms_error']:.4f} (lower is better, <0.5 is good)")

    elif mode == "both":
        capturer = StereoCalibrationCapture(config)
        count = capturer.capture()
        if count >= 5:
            print("\nProceeding to calibration...")
            time.sleep(1)
            calibrator = StereoCalibrator(config)
            calibration = calibrator.calibrate()
            if calibration:
                print("\nCalibration complete!")
        else:
            print(f"\nNeed at least 5 image pairs for calibration, got {count}")

    elif mode == "verify":
        # Verify calibration quality visually
        verify_calibration(config)

    elif mode == "clear":
        # Clear all captured images and start fresh
        import shutil
        for subdir in ['left', 'right']:
            path = f"{config.output_dir}/{subdir}"
            if os.path.exists(path):
                for f in glob.glob(f"{path}/*.jpg"):
                    os.remove(f)
                print(f"Cleared {path}")
        print("Ready for fresh calibration capture.")

    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


def verify_calibration(config: CalibrationConfig):
    """Visually verify calibration quality by showing rectified images"""
    import json

    calib_file = f"{config.output_dir}/stereo_calibration.json"
    maps_file = f"{config.output_dir}/stereo_maps.npz"

    if not os.path.exists(calib_file) or not os.path.exists(maps_file):
        print("Error: Calibration files not found. Run 'calibrate' first.")
        return

    # Load calibration
    with open(calib_file, 'r') as f:
        calib = json.load(f)

    maps = np.load(maps_file)
    map_l1, map_l2 = maps['map_l1'], maps['map_l2']
    map_r1, map_r2 = maps['map_r1'], maps['map_r2']

    print(f"\n{'='*60}")
    print("CALIBRATION VERIFICATION")
    print(f"{'='*60}")
    print(f"Baseline: {calib['baseline_mm']:.1f} mm ({calib['baseline_mm']/10:.1f} cm)")
    print(f"RMS Error: {calib['rms_error']:.4f}")
    print(f"\nControls:")
    print(f"  n/p - Next/Previous image pair")
    print(f"  q   - Quit")
    print(f"{'='*60}\n")

    left_images = sorted(glob.glob(f"{config.output_dir}/left/*.jpg"))
    right_images = sorted(glob.glob(f"{config.output_dir}/right/*.jpg"))

    if not left_images:
        print("No images found to verify.")
        return

    idx = 0
    while True:
        img_l = cv2.imread(left_images[idx])
        img_r = cv2.imread(right_images[idx])

        # Rectify images
        rect_l = cv2.remap(img_l, map_l1, map_l2, cv2.INTER_LINEAR)
        rect_r = cv2.remap(img_r, map_r1, map_r2, cv2.INTER_LINEAR)

        # Draw horizontal lines to check alignment
        combined = np.hstack([rect_l, rect_r])
        h = combined.shape[0]
        for y in range(0, h, 50):
            cv2.line(combined, (0, y), (combined.shape[1], y), (0, 255, 0), 1)

        # Add info overlay
        cv2.putText(combined, f"Pair {idx+1}/{len(left_images)} - Check epipolar lines",
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(combined, "Features should align on green lines (same Y coord)",
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Resize for display
        scale = 0.4
        display = cv2.resize(combined, None, fx=scale, fy=scale)

        cv2.imshow("Calibration Verification (n=next, p=prev, q=quit)", display)

        key = cv2.waitKey(0) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('n'):
            idx = (idx + 1) % len(left_images)
        elif key == ord('p'):
            idx = (idx - 1) % len(left_images)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
