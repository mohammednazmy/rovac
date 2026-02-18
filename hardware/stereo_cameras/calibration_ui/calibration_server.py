#!/usr/bin/env python3
"""
Interactive Stereo Camera Calibration UI
Web-based interface for stereo camera calibration.

Usage:
    python3 calibration_server.py                    # Start on port 8081
    python3 calibration_server.py --port 9000        # Custom port
    python3 calibration_server.py --cameras 0 2      # Specify camera IDs
"""

import os
import sys
import json
import time
import base64
import asyncio
import argparse
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import numpy as np

# Web framework
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    print("Warning: FastAPI not available")

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

SCRIPT_DIR = Path(__file__).parent


class StereoCalibrator:
    """Handles stereo camera calibration"""

    def __init__(self, left_camera_id: int = 0, right_camera_id: int = 2,
                 width: int = 640, height: int = 480):
        self.left_camera_id = left_camera_id
        self.right_camera_id = right_camera_id
        self.width = width
        self.height = height

        # Calibration parameters
        self.pattern_size = (9, 6)  # Checkerboard inner corners
        self.square_size = 25.0  # mm

        # Captured images
        self.left_images: List[np.ndarray] = []
        self.right_images: List[np.ndarray] = []
        self.image_points_left: List[np.ndarray] = []
        self.image_points_right: List[np.ndarray] = []

        # Calibration results
        self.calibration_data: Dict[str, Any] = {}
        self.is_calibrated = False
        self.rms_error = None

        # Camera handles
        self.left_cam = None
        self.right_cam = None
        self.cameras_open = False

        # State
        self.lock = threading.Lock()
        self.last_left_frame = None
        self.last_right_frame = None
        self.last_corners_left = None
        self.last_corners_right = None

    def open_cameras(self) -> bool:
        """Open both cameras"""
        try:
            self.left_cam = cv2.VideoCapture(self.left_camera_id)
            self.left_cam.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.left_cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            self.right_cam = cv2.VideoCapture(self.right_camera_id)
            self.right_cam.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.right_cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            if not self.left_cam.isOpened() or not self.right_cam.isOpened():
                return False

            self.cameras_open = True
            return True
        except Exception as e:
            print(f"Error opening cameras: {e}")
            return False

    def close_cameras(self):
        """Close cameras"""
        if self.left_cam:
            self.left_cam.release()
        if self.right_cam:
            self.right_cam.release()
        self.cameras_open = False

    def capture_frame(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Capture a frame from both cameras"""
        if not self.cameras_open:
            return None, None

        ret_l, left = self.left_cam.read()
        ret_r, right = self.right_cam.read()

        if ret_l and ret_r:
            with self.lock:
                self.last_left_frame = left
                self.last_right_frame = right
            return left, right
        return None, None

    def detect_pattern(self, image: np.ndarray) -> Tuple[bool, Optional[np.ndarray]]:
        """Detect checkerboard pattern in image"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

        # Find checkerboard corners
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
        ret, corners = cv2.findChessboardCorners(gray, self.pattern_size, flags)

        if ret:
            # Refine corners
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            return True, corners

        return False, None

    def capture_calibration_pair(self) -> Dict[str, Any]:
        """Capture a stereo pair for calibration"""
        left, right = self.capture_frame()
        if left is None or right is None:
            return {'success': False, 'error': 'Failed to capture frames'}

        # Detect pattern in both images
        found_left, corners_left = self.detect_pattern(left)
        found_right, corners_right = self.detect_pattern(right)

        with self.lock:
            self.last_corners_left = corners_left if found_left else None
            self.last_corners_right = corners_right if found_right else None

        if found_left and found_right:
            self.left_images.append(left.copy())
            self.right_images.append(right.copy())
            self.image_points_left.append(corners_left)
            self.image_points_right.append(corners_right)

            return {
                'success': True,
                'pair_count': len(self.left_images),
                'message': f'Captured pair {len(self.left_images)}'
            }
        else:
            missing = []
            if not found_left:
                missing.append('left')
            if not found_right:
                missing.append('right')
            return {
                'success': False,
                'error': f'Pattern not found in: {", ".join(missing)}'
            }

    def run_calibration(self) -> Dict[str, Any]:
        """Run stereo calibration"""
        if len(self.left_images) < 10:
            return {
                'success': False,
                'error': f'Need at least 10 image pairs, have {len(self.left_images)}'
            }

        # Prepare object points
        objp = np.zeros((self.pattern_size[0] * self.pattern_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:self.pattern_size[0], 0:self.pattern_size[1]].T.reshape(-1, 2)
        objp *= self.square_size

        object_points = [objp] * len(self.left_images)
        image_size = (self.width, self.height)

        try:
            # Calibrate individual cameras first
            ret_l, K1, D1, rvecs_l, tvecs_l = cv2.calibrateCamera(
                object_points, self.image_points_left, image_size, None, None
            )
            ret_r, K2, D2, rvecs_r, tvecs_r = cv2.calibrateCamera(
                object_points, self.image_points_right, image_size, None, None
            )

            # Stereo calibration
            flags = (cv2.CALIB_FIX_INTRINSIC +
                     cv2.CALIB_USE_INTRINSIC_GUESS +
                     cv2.CALIB_FIX_FOCAL_LENGTH)

            criteria = (cv2.TERM_CRITERIA_MAX_ITER + cv2.TERM_CRITERIA_EPS, 100, 1e-6)

            ret, K1, D1, K2, D2, R, T, E, F = cv2.stereoCalibrate(
                object_points,
                self.image_points_left,
                self.image_points_right,
                K1, D1, K2, D2,
                image_size,
                criteria=criteria,
                flags=flags
            )

            # Compute rectification transforms
            R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
                K1, D1, K2, D2, image_size, R, T,
                flags=cv2.CALIB_ZERO_DISPARITY,
                alpha=0
            )

            # Compute baseline
            baseline = np.linalg.norm(T)

            # Store calibration data
            self.calibration_data = {
                'image_size': list(image_size),
                'pattern_size': list(self.pattern_size),
                'square_size': self.square_size,
                'num_images': len(self.left_images),
                'rms_error': float(ret),
                'baseline_mm': float(baseline),
                'left_camera_matrix': K1.tolist(),
                'left_distortion': D1.tolist(),
                'right_camera_matrix': K2.tolist(),
                'right_distortion': D2.tolist(),
                'rotation_matrix': R.tolist(),
                'translation_vector': T.tolist(),
                'essential_matrix': E.tolist(),
                'fundamental_matrix': F.tolist(),
                'R1': R1.tolist(),
                'R2': R2.tolist(),
                'P1': P1.tolist(),
                'P2': P2.tolist(),
                'Q': Q.tolist(),
                'roi_left': list(roi1),
                'roi_right': list(roi2),
                'calibration_date': datetime.now().isoformat()
            }

            self.is_calibrated = True
            self.rms_error = ret

            return {
                'success': True,
                'rms_error': ret,
                'baseline_mm': baseline,
                'message': f'Calibration complete! RMS error: {ret:.4f}'
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Calibration failed: {str(e)}'
            }

    def save_calibration(self, filepath: str) -> bool:
        """Save calibration to file"""
        if not self.is_calibrated:
            return False

        try:
            with open(filepath, 'w') as f:
                json.dump(self.calibration_data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving calibration: {e}")
            return False

    def load_calibration(self, filepath: str) -> bool:
        """Load calibration from file"""
        try:
            with open(filepath) as f:
                self.calibration_data = json.load(f)
            self.is_calibrated = True
            self.rms_error = self.calibration_data.get('rms_error')
            return True
        except Exception as e:
            print(f"Error loading calibration: {e}")
            return False

    def clear_captures(self):
        """Clear all captured images"""
        self.left_images = []
        self.right_images = []
        self.image_points_left = []
        self.image_points_right = []

    def get_preview_with_overlay(self) -> Tuple[Optional[bytes], Optional[bytes]]:
        """Get preview images with pattern overlay"""
        with self.lock:
            left = self.last_left_frame
            right = self.last_right_frame
            corners_l = self.last_corners_left
            corners_r = self.last_corners_right

        if left is None or right is None:
            return None, None

        left_display = left.copy()
        right_display = right.copy()

        # Draw corners if detected
        if corners_l is not None:
            cv2.drawChessboardCorners(left_display, self.pattern_size, corners_l, True)
        if corners_r is not None:
            cv2.drawChessboardCorners(right_display, self.pattern_size, corners_r, True)

        # Add status text
        status_l = "Pattern: FOUND" if corners_l is not None else "Pattern: NOT FOUND"
        status_r = "Pattern: FOUND" if corners_r is not None else "Pattern: NOT FOUND"
        color_l = (0, 255, 0) if corners_l is not None else (0, 0, 255)
        color_r = (0, 255, 0) if corners_r is not None else (0, 0, 255)

        cv2.putText(left_display, status_l, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_l, 2)
        cv2.putText(right_display, status_r, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_r, 2)

        # Encode to JPEG
        _, left_jpeg = cv2.imencode('.jpg', left_display, [cv2.IMWRITE_JPEG_QUALITY, 70])
        _, right_jpeg = cv2.imencode('.jpg', right_display, [cv2.IMWRITE_JPEG_QUALITY, 70])

        return left_jpeg.tobytes(), right_jpeg.tobytes()

    def get_status(self) -> Dict[str, Any]:
        """Get current calibration status"""
        with self.lock:
            has_pattern_l = self.last_corners_left is not None
            has_pattern_r = self.last_corners_right is not None

        return {
            'cameras_open': self.cameras_open,
            'pattern_detected_left': has_pattern_l,
            'pattern_detected_right': has_pattern_r,
            'captured_pairs': len(self.left_images),
            'is_calibrated': self.is_calibrated,
            'rms_error': self.rms_error,
            'pattern_size': list(self.pattern_size),
            'square_size': self.square_size
        }


# Create FastAPI app
app = FastAPI(title="Stereo Calibration UI")
calibrator: Optional[StereoCalibrator] = None


@app.get("/", response_class=HTMLResponse)
async def get_calibration_ui():
    """Serve the calibration UI HTML"""
    return get_calibration_html()


@app.get("/api/status")
async def get_status():
    """Get calibration status"""
    if calibrator:
        return calibrator.get_status()
    return {"error": "Calibrator not initialized"}


@app.post("/api/capture")
async def capture_pair():
    """Capture a calibration pair"""
    if calibrator:
        return calibrator.capture_calibration_pair()
    return {"error": "Calibrator not initialized"}


@app.post("/api/calibrate")
async def run_calibration():
    """Run stereo calibration"""
    if calibrator:
        return calibrator.run_calibration()
    return {"error": "Calibrator not initialized"}


@app.post("/api/clear")
async def clear_captures():
    """Clear all captured images"""
    if calibrator:
        calibrator.clear_captures()
        return {"success": True, "message": "Captures cleared"}
    return {"error": "Calibrator not initialized"}


@app.post("/api/save")
async def save_calibration():
    """Save calibration to default location"""
    if calibrator and calibrator.is_calibrated:
        default_path = Path(__file__).parent.parent / 'stereo_calibration.json'
        if calibrator.save_calibration(str(default_path)):
            return {"success": True, "path": str(default_path)}
        return {"success": False, "error": "Failed to save"}
    return {"error": "Not calibrated"}


@app.get("/api/calibration")
async def get_calibration_data():
    """Get calibration data"""
    if calibrator and calibrator.is_calibrated:
        return calibrator.calibration_data
    return {"error": "Not calibrated"}


@app.post("/api/settings")
async def update_settings(settings: dict):
    """Update calibration settings"""
    if calibrator:
        if 'pattern_size' in settings:
            calibrator.pattern_size = tuple(settings['pattern_size'])
        if 'square_size' in settings:
            calibrator.square_size = float(settings['square_size'])
        return {"success": True}
    return {"error": "Calibrator not initialized"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for live preview"""
    await websocket.accept()

    try:
        while True:
            if calibrator and calibrator.cameras_open:
                # Capture and detect
                calibrator.capture_frame()
                _, corners_l = calibrator.detect_pattern(calibrator.last_left_frame) if calibrator.last_left_frame is not None else (False, None)
                _, corners_r = calibrator.detect_pattern(calibrator.last_right_frame) if calibrator.last_right_frame is not None else (False, None)

                with calibrator.lock:
                    calibrator.last_corners_left = corners_l
                    calibrator.last_corners_right = corners_r

                # Get preview images
                left_jpeg, right_jpeg = calibrator.get_preview_with_overlay()

                if left_jpeg and right_jpeg:
                    message = {
                        'type': 'preview',
                        'left': base64.b64encode(left_jpeg).decode(),
                        'right': base64.b64encode(right_jpeg).decode(),
                        'status': calibrator.get_status()
                    }
                    await websocket.send_json(message)

            await asyncio.sleep(0.1)  # ~10 FPS preview

    except WebSocketDisconnect:
        pass


def get_calibration_html():
    """Return calibration UI HTML"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stereo Calibration</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 1.8em;
            color: #e94560;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
        }
        .panel {
            background: rgba(22, 33, 62, 0.8);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        }
        .panel-title {
            font-size: 1.1em;
            color: #e94560;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .camera-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        .camera-view {
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            position: relative;
        }
        .camera-view img {
            width: 100%;
            height: auto;
            display: block;
        }
        .camera-label {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0, 0, 0, 0.7);
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 0.9em;
        }
        .status-indicator {
            position: absolute;
            top: 10px;
            right: 10px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }
        .status-indicator.found { background: #2ecc71; }
        .status-indicator.not-found { background: #e74c3c; }
        .controls {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .btn {
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 500;
            transition: all 0.2s;
            text-align: center;
        }
        .btn-primary {
            background: #e94560;
            color: white;
        }
        .btn-primary:hover { background: #d63850; }
        .btn-primary:disabled {
            background: #666;
            cursor: not-allowed;
        }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            color: #eee;
        }
        .btn-secondary:hover { background: rgba(255, 255, 255, 0.2); }
        .btn-success {
            background: #2ecc71;
            color: white;
        }
        .btn-success:hover { background: #27ae60; }
        .progress-container {
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            padding: 15px;
        }
        .progress-bar {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 5px;
            height: 10px;
            margin-top: 10px;
            overflow: hidden;
        }
        .progress-fill {
            background: linear-gradient(90deg, #e94560, #f39c12);
            height: 100%;
            border-radius: 5px;
            transition: width 0.3s;
        }
        .progress-text {
            display: flex;
            justify-content: space-between;
            font-size: 0.9em;
            color: #888;
        }
        .settings-group {
            margin-bottom: 15px;
        }
        .settings-group label {
            display: block;
            margin-bottom: 5px;
            font-size: 0.9em;
            color: #aaa;
        }
        .settings-group input {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 6px;
            background: rgba(0, 0, 0, 0.3);
            color: #eee;
            font-size: 1em;
        }
        .result-box {
            background: rgba(46, 204, 113, 0.1);
            border: 1px solid #2ecc71;
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
            display: none;
        }
        .result-box.show { display: block; }
        .result-box h3 {
            color: #2ecc71;
            margin-bottom: 10px;
        }
        .result-item {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .instructions {
            background: rgba(52, 152, 219, 0.1);
            border: 1px solid #3498db;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .instructions h4 {
            color: #3498db;
            margin-bottom: 10px;
        }
        .instructions ol {
            margin-left: 20px;
            font-size: 0.9em;
            color: #aaa;
        }
        .instructions li {
            margin-bottom: 5px;
        }
        .log {
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            padding: 10px;
            max-height: 150px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 0.85em;
        }
        .log-entry { padding: 3px 0; color: #aaa; }
        .log-entry.success { color: #2ecc71; }
        .log-entry.error { color: #e74c3c; }
        @media (max-width: 900px) {
            .container { grid-template-columns: 1fr; }
            .camera-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 Stereo Camera Calibration</h1>
        <p style="color: #888; margin-top: 5px;">Capture checkerboard images to calibrate stereo cameras</p>
    </div>

    <div class="container">
        <div class="main-content">
            <div class="panel">
                <h2 class="panel-title">Camera Preview</h2>
                <div class="camera-grid">
                    <div class="camera-view">
                        <img id="left-preview" src="" alt="Left Camera">
                        <span class="camera-label">Left Camera</span>
                        <span class="status-indicator not-found" id="status-left"></span>
                    </div>
                    <div class="camera-view">
                        <img id="right-preview" src="" alt="Right Camera">
                        <span class="camera-label">Right Camera</span>
                        <span class="status-indicator not-found" id="status-right"></span>
                    </div>
                </div>
            </div>

            <div class="panel" style="margin-top: 20px;">
                <h2 class="panel-title">Calibration Log</h2>
                <div class="log" id="log"></div>
            </div>
        </div>

        <div class="sidebar">
            <div class="panel">
                <div class="instructions">
                    <h4>📋 Instructions</h4>
                    <ol>
                        <li>Print a checkerboard pattern (9x6 inner corners)</li>
                        <li>Hold the board so both cameras can see it</li>
                        <li>Click "Capture" when pattern is detected (green indicators)</li>
                        <li>Capture at least 15-20 pairs from different angles</li>
                        <li>Click "Calibrate" when ready</li>
                    </ol>
                </div>
            </div>

            <div class="panel" style="margin-top: 15px;">
                <h2 class="panel-title">Settings</h2>
                <div class="settings-group">
                    <label>Pattern Size (columns x rows)</label>
                    <div style="display: flex; gap: 10px;">
                        <input type="number" id="pattern-cols" value="9" min="3" max="20">
                        <input type="number" id="pattern-rows" value="6" min="3" max="20">
                    </div>
                </div>
                <div class="settings-group">
                    <label>Square Size (mm)</label>
                    <input type="number" id="square-size" value="25" min="1" max="100" step="0.1">
                </div>
                <button class="btn btn-secondary" onclick="updateSettings()" style="width: 100%;">
                    Update Settings
                </button>
            </div>

            <div class="panel" style="margin-top: 15px;">
                <h2 class="panel-title">Progress</h2>
                <div class="progress-container">
                    <div class="progress-text">
                        <span>Captured Pairs</span>
                        <span id="capture-count">0 / 15</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="progress-fill" style="width: 0%"></div>
                    </div>
                </div>
            </div>

            <div class="panel controls" style="margin-top: 15px;">
                <button class="btn btn-primary" id="capture-btn" onclick="captureImage()" disabled>
                    📸 Capture Pair
                </button>
                <button class="btn btn-success" id="calibrate-btn" onclick="runCalibration()" disabled>
                    ⚙️ Run Calibration
                </button>
                <button class="btn btn-secondary" onclick="clearCaptures()">
                    🗑️ Clear All
                </button>
                <button class="btn btn-secondary" id="save-btn" onclick="saveCalibration()" disabled>
                    💾 Save Calibration
                </button>
            </div>

            <div class="panel result-box" id="result-box">
                <h3>✅ Calibration Complete!</h3>
                <div class="result-item">
                    <span>RMS Error</span>
                    <span id="rms-error">--</span>
                </div>
                <div class="result-item">
                    <span>Baseline</span>
                    <span id="baseline">--</span>
                </div>
                <div class="result-item">
                    <span>Image Pairs</span>
                    <span id="num-pairs">--</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        const minCaptures = 15;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = function() {
                addLog('Connected to server', 'success');
            };

            ws.onclose = function() {
                addLog('Disconnected from server', 'error');
                setTimeout(connect, 2000);
            };

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handlePreview(data);
            };
        }

        function handlePreview(data) {
            if (data.type === 'preview') {
                // Update preview images
                if (data.left) {
                    document.getElementById('left-preview').src = 'data:image/jpeg;base64,' + data.left;
                }
                if (data.right) {
                    document.getElementById('right-preview').src = 'data:image/jpeg;base64,' + data.right;
                }

                // Update status indicators
                const statusLeft = document.getElementById('status-left');
                const statusRight = document.getElementById('status-right');
                const captureBtn = document.getElementById('capture-btn');
                const calibrateBtn = document.getElementById('calibrate-btn');

                statusLeft.className = 'status-indicator ' + (data.status.pattern_detected_left ? 'found' : 'not-found');
                statusRight.className = 'status-indicator ' + (data.status.pattern_detected_right ? 'found' : 'not-found');

                // Enable capture button if both patterns detected
                captureBtn.disabled = !(data.status.pattern_detected_left && data.status.pattern_detected_right);

                // Enable calibrate button if enough captures
                calibrateBtn.disabled = data.status.captured_pairs < minCaptures;

                // Update progress
                const count = data.status.captured_pairs;
                document.getElementById('capture-count').textContent = `${count} / ${minCaptures}`;
                document.getElementById('progress-fill').style.width = Math.min(100, (count / minCaptures) * 100) + '%';
            }
        }

        async function captureImage() {
            const response = await fetch('/api/capture', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                addLog(`Captured pair ${result.pair_count}`, 'success');
            } else {
                addLog(result.error, 'error');
            }
        }

        async function runCalibration() {
            addLog('Running calibration...', 'info');
            document.getElementById('calibrate-btn').disabled = true;

            const response = await fetch('/api/calibrate', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                addLog(`Calibration complete! RMS: ${result.rms_error.toFixed(4)}`, 'success');

                // Show results
                document.getElementById('result-box').classList.add('show');
                document.getElementById('rms-error').textContent = result.rms_error.toFixed(4);
                document.getElementById('baseline').textContent = result.baseline_mm.toFixed(2) + ' mm';
                document.getElementById('num-pairs').textContent = document.getElementById('capture-count').textContent.split(' ')[0];
                document.getElementById('save-btn').disabled = false;
            } else {
                addLog(result.error, 'error');
            }

            document.getElementById('calibrate-btn').disabled = false;
        }

        async function clearCaptures() {
            await fetch('/api/clear', { method: 'POST' });
            addLog('Captures cleared', 'info');
            document.getElementById('result-box').classList.remove('show');
            document.getElementById('save-btn').disabled = true;
        }

        async function saveCalibration() {
            const response = await fetch('/api/save', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                addLog(`Saved to ${result.path}`, 'success');
            } else {
                addLog(result.error || 'Failed to save', 'error');
            }
        }

        async function updateSettings() {
            const cols = parseInt(document.getElementById('pattern-cols').value);
            const rows = parseInt(document.getElementById('pattern-rows').value);
            const squareSize = parseFloat(document.getElementById('square-size').value);

            const response = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pattern_size: [cols, rows],
                    square_size: squareSize
                })
            });

            if (response.ok) {
                addLog(`Settings updated: ${cols}x${rows}, ${squareSize}mm`, 'success');
            }
        }

        function addLog(message, type = 'info') {
            const log = document.getElementById('log');
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + type;
            const time = new Date().toLocaleTimeString();
            entry.textContent = `[${time}] ${message}`;
            log.insertBefore(entry, log.firstChild);

            while (log.children.length > 30) {
                log.removeChild(log.lastChild);
            }
        }

        // Start connection
        connect();
        addLog('Calibration UI initialized');
    </script>
</body>
</html>
"""


async def main_async(args):
    """Main async entry point"""
    global calibrator

    # Initialize calibrator
    calibrator = StereoCalibrator(
        left_camera_id=args.left_camera,
        right_camera_id=args.right_camera,
        width=args.width,
        height=args.height
    )

    if not calibrator.open_cameras():
        print("Warning: Could not open cameras. Running in demo mode.")
    else:
        print(f"Cameras opened: left={args.left_camera}, right={args.right_camera}")

    # Run server
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


def main():
    parser = argparse.ArgumentParser(description='Stereo Calibration UI')
    parser.add_argument('--port', '-p', type=int, default=8081,
                        help='Server port (default: 8081)')
    parser.add_argument('--host', '-H', default='0.0.0.0',
                        help='Server host (default: 0.0.0.0)')
    parser.add_argument('--left-camera', '-l', type=int, default=0,
                        help='Left camera ID (default: 0)')
    parser.add_argument('--right-camera', '-r', type=int, default=2,
                        help='Right camera ID (default: 2)')
    parser.add_argument('--width', type=int, default=640,
                        help='Camera width (default: 640)')
    parser.add_argument('--height', type=int, default=480,
                        help='Camera height (default: 480)')

    args = parser.parse_args()

    if not HAS_FASTAPI:
        print("Error: FastAPI required. Install with: pip install fastapi uvicorn")
        return 1

    if not HAS_CV2:
        print("Error: OpenCV required")
        return 1

    print(f"Starting Stereo Calibration UI on http://{args.host}:{args.port}")

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nShutdown requested")
        if calibrator:
            calibrator.close_cameras()

    return 0


if __name__ == '__main__':
    sys.exit(main())
