#!/usr/bin/env python3
"""
Stereo Camera Real-time Visualization Dashboard
Web-based dashboard for monitoring stereo camera output.

Usage:
    python3 server.py                    # Start dashboard on port 8080
    python3 server.py --port 9000        # Custom port
    python3 server.py --ros2             # Connect to ROS2 topics
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
from typing import Optional, Dict, Any, List, Set

import numpy as np

# Web framework
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import HTMLResponse, FileResponse
    from fastapi.templating import Jinja2Templates
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    print("Warning: FastAPI not available, install with: pip install fastapi uvicorn jinja2")

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# ROS2 imports
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
    from sensor_msgs.msg import Image, CompressedImage
    from diagnostic_msgs.msg import DiagnosticArray
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        print(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        print(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


class StereoDataSource:
    """Base class for stereo data sources"""

    def __init__(self):
        self.depth_image = None
        self.depth_color = None
        self.left_image = None
        self.right_image = None
        self.obstacles = None
        self.diagnostics = {}
        self.last_update = 0
        self.frame_count = 0
        self.lock = threading.Lock()

    def get_depth_jpeg(self, quality: int = 70) -> Optional[bytes]:
        """Get depth color image as JPEG bytes"""
        with self.lock:
            if self.depth_color is None:
                return None
            _, buffer = cv2.imencode('.jpg', self.depth_color,
                                      [cv2.IMWRITE_JPEG_QUALITY, quality])
            return buffer.tobytes()

    def get_left_jpeg(self, quality: int = 70) -> Optional[bytes]:
        """Get left camera image as JPEG bytes"""
        with self.lock:
            if self.left_image is None:
                return None
            img = self.left_image
            if len(img.shape) == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            _, buffer = cv2.imencode('.jpg', img,
                                      [cv2.IMWRITE_JPEG_QUALITY, quality])
            return buffer.tobytes()

    def get_status(self) -> dict:
        """Get current status"""
        with self.lock:
            return {
                'timestamp': self.last_update,
                'frame_count': self.frame_count,
                'has_depth': self.depth_color is not None or self.depth_image is not None,
                'has_left': self.left_image is not None,
                'has_right': self.right_image is not None,
                'diagnostics': self.diagnostics,
                'obstacles': self.obstacles
            }


# Only define ROS2 class if ROS2 is available
if HAS_ROS2:
    class ROS2DataSource(StereoDataSource, Node):
        """ROS2-based data source"""

        def __init__(self):
            StereoDataSource.__init__(self)
            Node.__init__(self, 'stereo_dashboard')

            # QoS for sensor data
            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1
            )

            # Subscribe to topics
            self.depth_color_sub = self.create_subscription(
                Image, '/stereo/depth/image_color',
                self.depth_color_callback, sensor_qos
            )

            self.depth_sub = self.create_subscription(
                Image, '/stereo/depth/image_raw',
                self.depth_callback, sensor_qos
            )

            self.left_sub = self.create_subscription(
                Image, '/stereo/left/image_raw',
                self.left_callback, sensor_qos
            )

            self.right_sub = self.create_subscription(
                Image, '/stereo/right/image_raw',
                self.right_callback, sensor_qos
            )

            self.diag_sub = self.create_subscription(
                DiagnosticArray, '/stereo/diagnostics',
                self.diagnostics_callback, 10
            )

            self.get_logger().info("ROS2 data source initialized")

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
            return None

        def depth_color_callback(self, msg: Image):
            img = self._image_to_numpy(msg)
            if img is not None:
                with self.lock:
                    self.depth_color = img
                    self._has_depth_color_topic = True
                    self.last_update = time.time()
                    self.frame_count += 1

        def depth_callback(self, msg: Image):
            img = self._image_to_numpy(msg)
            if img is not None:
                with self.lock:
                    self.depth_image = img
                    # Update frame count if we're not receiving depth_color from topic
                    if not getattr(self, '_has_depth_color_topic', False):
                        self.last_update = time.time()
                        self.frame_count += 1
                        # Generate colorized depth from raw depth
                        if HAS_CV2:
                            max_depth = 3.0
                            depth_norm = np.clip(img / max_depth, 0, 1)
                            self.depth_color = cv2.applyColorMap(
                                (depth_norm * 255).astype(np.uint8),
                                cv2.COLORMAP_JET
                            )

        def left_callback(self, msg: Image):
            img = self._image_to_numpy(msg)
            if img is not None:
                with self.lock:
                    self.left_image = img

        def right_callback(self, msg: Image):
            img = self._image_to_numpy(msg)
            if img is not None:
                with self.lock:
                    self.right_image = img

        def diagnostics_callback(self, msg: DiagnosticArray):
            diag = {}
            for status in msg.status:
                values = {}
                for kv in status.values:
                    values[kv.key] = kv.value
                diag[status.name] = {
                    'level': status.level,
                    'message': status.message,
                    'values': values
                }
            with self.lock:
                self.diagnostics = diag


class SimulatedDataSource(StereoDataSource):
    """Simulated data source for testing without ROS2"""

    def __init__(self):
        super().__init__()
        self.running = True
        self.thread = threading.Thread(target=self._generate_data, daemon=True)
        self.thread.start()

    def _generate_data(self):
        """Generate simulated depth images"""
        height, width = 240, 320
        max_depth = 3.0

        while self.running:
            # Generate simulated depth map with moving obstacle
            t = time.time()
            y, x = np.ogrid[:height, :width]

            # Base depth (walls)
            depth = np.ones((height, width), dtype=np.float32) * max_depth

            # Moving obstacle
            cx = width // 2 + int(np.sin(t) * width // 3)
            cy = height // 2 + int(np.cos(t * 0.7) * height // 4)
            obstacle_dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            obstacle_mask = obstacle_dist < 50
            depth[obstacle_mask] = 0.5 + 0.3 * np.sin(t * 2)

            # Colorize depth
            depth_normalized = np.clip(depth / max_depth, 0, 1)
            depth_color = cv2.applyColorMap(
                (depth_normalized * 255).astype(np.uint8),
                cv2.COLORMAP_JET
            )

            # Generate simulated left image (grayscale with gradient)
            left = np.zeros((height, width), dtype=np.uint8)
            left[:] = (255 * (1 - depth_normalized)).astype(np.uint8)

            with self.lock:
                self.depth_image = depth
                self.depth_color = depth_color
                self.left_image = left
                self.right_image = left.copy()
                self.last_update = time.time()
                self.frame_count += 1

                # Simulated diagnostics
                self.diagnostics = {
                    'stereo_depth': {
                        'level': 0,
                        'message': 'OK',
                        'values': {
                            'fps': f"{2.0 + np.sin(t) * 0.5:.2f}",
                            'compute_time_ms': f"{450 + np.random.randn() * 50:.1f}",
                            'dropped_frames': '0'
                        }
                    }
                }

                # Simulated obstacles
                self.obstacles = {
                    'center': {'distance': float(depth[height // 2, width // 2]), 'status': 'clear'},
                    'left': {'distance': float(depth[height // 2, width // 4]), 'status': 'clear'},
                    'right': {'distance': float(depth[height // 2, 3 * width // 4]), 'status': 'clear'}
                }

            time.sleep(0.5)  # ~2 Hz

    def stop(self):
        self.running = False


# Create FastAPI app
app = FastAPI(title="Stereo Camera Dashboard")
manager = ConnectionManager()
data_source: Optional[StereoDataSource] = None

# Get script directory for templates
SCRIPT_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(SCRIPT_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the dashboard HTML"""
    template_path = SCRIPT_DIR / "templates" / "dashboard.html"
    if template_path.exists():
        return FileResponse(str(template_path))
    else:
        # Return inline HTML if template doesn't exist
        return HTMLResponse(content=get_inline_dashboard())


@app.get("/api/status")
async def get_status():
    """Get current status"""
    if data_source:
        return data_source.get_status()
    return {"error": "Data source not initialized"}


@app.get("/api/depth.jpg")
async def get_depth_image():
    """Get depth image as JPEG"""
    if data_source:
        jpeg = data_source.get_depth_jpeg()
        if jpeg:
            return Response(content=jpeg, media_type="image/jpeg")
    return {"error": "No depth image available"}


@app.get("/api/left.jpg")
async def get_left_image():
    """Get left camera image as JPEG"""
    if data_source:
        jpeg = data_source.get_left_jpeg()
        if jpeg:
            return Response(content=jpeg, media_type="image/jpeg")
    return {"error": "No left image available"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)

    try:
        while True:
            # Wait for new data
            await asyncio.sleep(0.3)  # ~3 Hz updates

            if data_source:
                # Get depth image as base64
                depth_jpeg = data_source.get_depth_jpeg(quality=50)
                depth_b64 = base64.b64encode(depth_jpeg).decode() if depth_jpeg else None

                left_jpeg = data_source.get_left_jpeg(quality=50)
                left_b64 = base64.b64encode(left_jpeg).decode() if left_jpeg else None

                status = data_source.get_status()

                message = {
                    'type': 'update',
                    'timestamp': time.time(),
                    'depth_image': depth_b64,
                    'left_image': left_b64,
                    'frame_count': status.get('frame_count', 0),
                    'diagnostics': status.get('diagnostics', {}),
                    'obstacles': status.get('obstacles', {})
                }

                await websocket.send_json(message)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


def get_inline_dashboard():
    """Return inline HTML dashboard"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stereo Camera Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        .header {
            background: #16213e;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #0f3460;
        }
        .header h1 { font-size: 1.5em; color: #e94560; }
        .status-badge {
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .status-connected { background: #2ecc71; color: #000; }
        .status-disconnected { background: #e74c3c; color: #fff; }
        .container {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            padding: 20px;
            max-width: 1400px;
            margin: 0 auto;
        }
        .panel {
            background: #16213e;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        .panel-title {
            font-size: 1.1em;
            color: #e94560;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #0f3460;
        }
        .image-container {
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            position: relative;
        }
        .image-container img {
            width: 100%;
            height: auto;
            display: block;
        }
        .image-label {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0, 0, 0, 0.7);
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 0.9em;
        }
        .images-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        .metric {
            background: #0f3460;
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }
        .metric-value {
            font-size: 1.8em;
            font-weight: bold;
            color: #e94560;
        }
        .metric-label {
            font-size: 0.85em;
            color: #888;
            margin-top: 5px;
        }
        .obstacles {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 15px;
        }
        .obstacle-zone {
            background: #0f3460;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .obstacle-zone.clear { border-left: 4px solid #2ecc71; }
        .obstacle-zone.warning { border-left: 4px solid #f39c12; }
        .obstacle-zone.danger { border-left: 4px solid #e74c3c; }
        .obstacle-distance {
            font-size: 1.4em;
            font-weight: bold;
        }
        .obstacle-label {
            font-size: 0.8em;
            color: #888;
            margin-top: 5px;
        }
        .log-container {
            background: #0a0a1a;
            border-radius: 8px;
            padding: 10px;
            height: 150px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 0.85em;
        }
        .log-entry { padding: 3px 0; border-bottom: 1px solid #1a1a2e; }
        .log-time { color: #888; }
        .log-message { color: #eee; }
        @media (max-width: 900px) {
            .container { grid-template-columns: 1fr; }
            .images-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎥 Stereo Camera Dashboard</h1>
        <span id="status" class="status-badge status-disconnected">Disconnected</span>
    </div>

    <div class="container">
        <div class="main-content">
            <div class="panel">
                <h2 class="panel-title">Depth View</h2>
                <div class="image-container">
                    <img id="depth-image" src="" alt="Depth">
                    <span class="image-label">Depth Map</span>
                </div>
            </div>

            <div class="panel" style="margin-top: 20px;">
                <h2 class="panel-title">Camera Views</h2>
                <div class="images-grid">
                    <div class="image-container">
                        <img id="left-image" src="" alt="Left Camera">
                        <span class="image-label">Left</span>
                    </div>
                    <div class="image-container">
                        <img id="right-image" src="" alt="Right Camera">
                        <span class="image-label">Right</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="sidebar">
            <div class="panel">
                <h2 class="panel-title">Performance</h2>
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-value" id="fps">--</div>
                        <div class="metric-label">FPS</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="latency">--</div>
                        <div class="metric-label">Latency (ms)</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="frames">--</div>
                        <div class="metric-label">Frames</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="dropped">--</div>
                        <div class="metric-label">Dropped</div>
                    </div>
                </div>
            </div>

            <div class="panel" style="margin-top: 20px;">
                <h2 class="panel-title">Obstacle Detection</h2>
                <div class="obstacles">
                    <div class="obstacle-zone" id="zone-left">
                        <div class="obstacle-distance" id="dist-left">--</div>
                        <div class="obstacle-label">Left</div>
                    </div>
                    <div class="obstacle-zone" id="zone-center">
                        <div class="obstacle-distance" id="dist-center">--</div>
                        <div class="obstacle-label">Center</div>
                    </div>
                    <div class="obstacle-zone" id="zone-right">
                        <div class="obstacle-distance" id="dist-right">--</div>
                        <div class="obstacle-label">Right</div>
                    </div>
                </div>
            </div>

            <div class="panel" style="margin-top: 20px;">
                <h2 class="panel-title">Activity Log</h2>
                <div class="log-container" id="log"></div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 10;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = function() {
                console.log('Connected');
                document.getElementById('status').textContent = 'Connected';
                document.getElementById('status').className = 'status-badge status-connected';
                reconnectAttempts = 0;
                addLog('Connected to server');
            };

            ws.onclose = function() {
                console.log('Disconnected');
                document.getElementById('status').textContent = 'Disconnected';
                document.getElementById('status').className = 'status-badge status-disconnected';
                addLog('Disconnected from server');

                // Reconnect
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    setTimeout(connect, 2000);
                }
            };

            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
                addLog('Connection error');
            };

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleUpdate(data);
            };
        }

        function handleUpdate(data) {
            // Update depth image
            if (data.depth_image) {
                document.getElementById('depth-image').src = 'data:image/jpeg;base64,' + data.depth_image;
            }

            // Update left image
            if (data.left_image) {
                document.getElementById('left-image').src = 'data:image/jpeg;base64,' + data.left_image;
                document.getElementById('right-image').src = 'data:image/jpeg;base64,' + data.left_image;
            }

            // Update frame count
            document.getElementById('frames').textContent = data.frame_count || '--';

            // Update diagnostics
            if (data.diagnostics && data.diagnostics.stereo_depth) {
                const diag = data.diagnostics.stereo_depth.values;
                document.getElementById('fps').textContent = diag.fps || '--';
                document.getElementById('latency').textContent = diag.compute_time_ms || '--';
                document.getElementById('dropped').textContent = diag.dropped_frames || '0';
            }

            // Update obstacles
            if (data.obstacles) {
                updateObstacleZone('left', data.obstacles.left);
                updateObstacleZone('center', data.obstacles.center);
                updateObstacleZone('right', data.obstacles.right);
            }
        }

        function updateObstacleZone(zone, data) {
            if (!data) return;

            const zoneEl = document.getElementById('zone-' + zone);
            const distEl = document.getElementById('dist-' + zone);

            const distance = data.distance;
            distEl.textContent = distance ? distance.toFixed(2) + 'm' : '--';

            // Update class based on distance
            zoneEl.classList.remove('clear', 'warning', 'danger');
            if (distance < 0.3) {
                zoneEl.classList.add('danger');
            } else if (distance < 0.7) {
                zoneEl.classList.add('warning');
            } else {
                zoneEl.classList.add('clear');
            }
        }

        function addLog(message) {
            const log = document.getElementById('log');
            const time = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-message">${message}</span>`;
            log.insertBefore(entry, log.firstChild);

            // Keep only last 50 entries
            while (log.children.length > 50) {
                log.removeChild(log.lastChild);
            }
        }

        // Start connection
        connect();
    </script>
</body>
</html>
"""


# Only define ROS2 spinner if ROS2 is available
if HAS_ROS2:
    def run_ros2_spinner(node):
        """Run ROS2 spinner in background thread"""
        rclpy.spin(node)


async def main_async(args):
    """Main async entry point"""
    global data_source

    # Initialize data source
    if args.ros2 and HAS_ROS2:
        if not rclpy.ok():
            rclpy.init()
        data_source = ROS2DataSource()
        spinner = threading.Thread(target=run_ros2_spinner, args=(data_source,), daemon=True)
        spinner.start()
        print("Using ROS2 data source")
    else:
        data_source = SimulatedDataSource()
        print("Using simulated data source (use --ros2 for real data)")

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
    parser = argparse.ArgumentParser(description='Stereo Camera Dashboard')
    parser.add_argument('--port', '-p', type=int, default=8080,
                        help='Server port (default: 8080)')
    parser.add_argument('--host', '-H', default='0.0.0.0',
                        help='Server host (default: 0.0.0.0)')
    parser.add_argument('--ros2', action='store_true',
                        help='Connect to ROS2 topics')

    args = parser.parse_args()

    if not HAS_FASTAPI:
        print("Error: FastAPI required. Install with: pip install fastapi uvicorn jinja2")
        return 1

    if not HAS_CV2:
        print("Error: OpenCV required")
        return 1

    print(f"Starting Stereo Camera Dashboard on http://{args.host}:{args.port}")

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nShutdown requested")
        if data_source and hasattr(data_source, 'stop'):
            data_source.stop()

    return 0


# Need Response import for image endpoints
from fastapi import Response

if __name__ == '__main__':
    sys.exit(main())
