#!/usr/bin/env python3
"""
Remote Stereo Camera Monitor
Mobile-friendly dashboard for monitoring stereo cameras over network.
Supports SSH tunnel for secure access.

Usage:
    # On Pi (start server)
    python3 remote_monitor.py --ros2

    # On Mac (create SSH tunnel)
    ssh -L 8082:localhost:8082 pi@192.168.1.200

    # Then open http://localhost:8082 in browser
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
    from fastapi.responses import HTMLResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

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
    from geometry_msgs.msg import Twist
    from diagnostic_msgs.msg import DiagnosticArray
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False

sys.path.insert(0, str(Path(__file__).parent.parent))


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            self.disconnect(conn)


class RemoteDataSource:
    """Data source for remote monitoring"""

    def __init__(self):
        self.depth_color = None
        self.left_image = None
        self.obstacles = {}
        self.diagnostics = {}
        self.cmd_vel = {'linear': 0.0, 'angular': 0.0}
        self.frame_count = 0
        self.last_update = 0
        self.lock = threading.Lock()

    def get_depth_jpeg(self, quality: int = 50, max_width: int = 320) -> Optional[bytes]:
        """Get compressed depth image"""
        with self.lock:
            if self.depth_color is None:
                return None

            img = self.depth_color
            # Resize for mobile bandwidth
            if img.shape[1] > max_width:
                scale = max_width / img.shape[1]
                new_size = (max_width, int(img.shape[0] * scale))
                img = cv2.resize(img, new_size)

            _, buffer = cv2.imencode('.jpg', img,
                                      [cv2.IMWRITE_JPEG_QUALITY, quality])
            return buffer.tobytes()

    def get_status(self) -> dict:
        with self.lock:
            return {
                'frame_count': self.frame_count,
                'last_update': self.last_update,
                'obstacles': self.obstacles,
                'diagnostics': self.diagnostics,
                'cmd_vel': self.cmd_vel
            }


# Only define ROS2 class if ROS2 is available
if HAS_ROS2:
    class ROS2RemoteSource(RemoteDataSource, Node):
        """ROS2-based remote data source"""

        def __init__(self):
            RemoteDataSource.__init__(self)
            Node.__init__(self, 'remote_monitor')

            sensor_qos = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1
            )

            # Subscribe to depth color
            self.depth_sub = self.create_subscription(
                Image, '/stereo/depth/image_color',
                self.depth_callback, sensor_qos
            )

            # Subscribe to cmd_vel for movement indicator
            self.vel_sub = self.create_subscription(
                Twist, '/cmd_vel',
                self.vel_callback, sensor_qos
            )

            # Subscribe to diagnostics
            self.diag_sub = self.create_subscription(
                DiagnosticArray, '/stereo/diagnostics',
                self.diag_callback, 10
            )

            self.get_logger().info("Remote monitor initialized")

        def _image_to_numpy(self, msg: Image) -> Optional[np.ndarray]:
            if msg.encoding == 'bgr8':
                return np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, 3)
            elif msg.encoding == 'rgb8':
                img = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, 3)
                return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            return None

        def depth_callback(self, msg: Image):
            img = self._image_to_numpy(msg)
            if img is not None:
                with self.lock:
                    self.depth_color = img
                    self.frame_count += 1
                    self.last_update = time.time()

        def vel_callback(self, msg: Twist):
            with self.lock:
                self.cmd_vel = {
                    'linear': msg.linear.x,
                    'angular': msg.angular.z
                }

        def diag_callback(self, msg: DiagnosticArray):
            diag = {}
            for status in msg.status:
                values = {kv.key: kv.value for kv in status.values}
                diag[status.name] = {
                    'level': status.level,
                    'message': status.message,
                    'values': values
                }
            with self.lock:
                self.diagnostics = diag


class SimulatedRemoteSource(RemoteDataSource):
    """Simulated data source for testing"""

    def __init__(self):
        super().__init__()
        self.running = True
        self.thread = threading.Thread(target=self._generate, daemon=True)
        self.thread.start()

    def _generate(self):
        while self.running:
            t = time.time()
            h, w = 240, 320

            # Generate test pattern
            depth = np.zeros((h, w), dtype=np.float32)
            y, x = np.ogrid[:h, :w]
            cx = w // 2 + int(np.sin(t) * w // 3)
            cy = h // 2
            dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            depth = 3.0 - np.clip(dist / 100, 0, 2.5)

            depth_norm = np.clip(depth / 3.0, 0, 1)
            depth_color = cv2.applyColorMap(
                (depth_norm * 255).astype(np.uint8),
                cv2.COLORMAP_JET
            )

            with self.lock:
                self.depth_color = depth_color
                self.frame_count += 1
                self.last_update = time.time()
                self.cmd_vel = {
                    'linear': 0.2 * np.sin(t),
                    'angular': 0.5 * np.cos(t * 0.5)
                }
                self.obstacles = {
                    'center': {'distance': float(depth[h // 2, w // 2])},
                    'left': {'distance': float(depth[h // 2, w // 4])},
                    'right': {'distance': float(depth[h // 2, 3 * w // 4])}
                }

            time.sleep(0.3)

    def stop(self):
        self.running = False


app = FastAPI(title="Remote Stereo Monitor")
manager = ConnectionManager()
data_source: Optional[RemoteDataSource] = None


@app.get("/", response_class=HTMLResponse)
async def get_mobile_dashboard():
    """Serve mobile-optimized dashboard"""
    return get_mobile_html()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await asyncio.sleep(0.2)  # 5 Hz for mobile bandwidth

            if data_source:
                depth_jpeg = data_source.get_depth_jpeg(quality=40, max_width=280)
                status = data_source.get_status()

                message = {
                    'type': 'update',
                    'depth': base64.b64encode(depth_jpeg).decode() if depth_jpeg else None,
                    'status': status
                }
                await websocket.send_json(message)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


def get_mobile_html():
    """Return mobile-optimized HTML"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="theme-color" content="#1a1a2e">
    <title>Robot Monitor</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
            background: #1a1a2e;
            color: #fff;
            min-height: 100vh;
            overflow-x: hidden;
        }

        .header {
            background: linear-gradient(135deg, #16213e, #0f3460);
            padding: 12px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .header h1 {
            font-size: 1.2em;
            font-weight: 600;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #e74c3c;
        }
        .status-dot.connected { background: #2ecc71; }

        .container {
            padding: 12px;
        }

        .depth-view {
            background: #000;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 12px;
            position: relative;
        }
        .depth-view img {
            width: 100%;
            height: auto;
            display: block;
        }
        .depth-overlay {
            position: absolute;
            bottom: 8px;
            left: 8px;
            background: rgba(0,0,0,0.7);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75em;
        }

        .metrics {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-bottom: 12px;
        }
        .metric {
            background: rgba(22, 33, 62, 0.9);
            padding: 12px 8px;
            border-radius: 10px;
            text-align: center;
        }
        .metric-value {
            font-size: 1.4em;
            font-weight: bold;
            color: #e94560;
        }
        .metric-label {
            font-size: 0.7em;
            color: #888;
            margin-top: 4px;
        }

        .obstacles {
            background: rgba(22, 33, 62, 0.9);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .obstacles-title {
            font-size: 0.9em;
            color: #e94560;
            margin-bottom: 12px;
        }
        .obstacle-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }
        .obstacle-zone {
            padding: 12px;
            border-radius: 8px;
            text-align: center;
            transition: all 0.3s;
        }
        .obstacle-zone.clear { background: rgba(46, 204, 113, 0.2); border: 1px solid #2ecc71; }
        .obstacle-zone.warning { background: rgba(243, 156, 18, 0.2); border: 1px solid #f39c12; }
        .obstacle-zone.danger { background: rgba(231, 76, 60, 0.2); border: 1px solid #e74c3c; }
        .obstacle-dist {
            font-size: 1.2em;
            font-weight: bold;
        }
        .obstacle-label {
            font-size: 0.7em;
            color: #888;
            margin-top: 4px;
        }

        .movement {
            background: rgba(22, 33, 62, 0.9);
            border-radius: 12px;
            padding: 16px;
        }
        .movement-title {
            font-size: 0.9em;
            color: #e94560;
            margin-bottom: 12px;
        }
        .movement-viz {
            display: flex;
            justify-content: center;
            gap: 20px;
        }
        .movement-indicator {
            width: 80px;
            height: 80px;
            background: rgba(0,0,0,0.3);
            border-radius: 50%;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .movement-arrow {
            width: 0;
            height: 0;
            border-left: 15px solid transparent;
            border-right: 15px solid transparent;
            border-bottom: 30px solid #3498db;
            transition: transform 0.1s;
        }
        .movement-label {
            text-align: center;
            margin-top: 8px;
            font-size: 0.75em;
            color: #888;
        }
        .movement-value {
            font-weight: bold;
            color: #fff;
        }

        .emergency {
            background: rgba(231, 76, 60, 0.9);
            padding: 16px;
            text-align: center;
            font-weight: bold;
            border-radius: 12px;
            margin-bottom: 12px;
            display: none;
            animation: blink 0.5s infinite;
        }
        .emergency.active { display: block; }
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 Robot Monitor</h1>
        <span class="status-dot" id="status"></span>
    </div>

    <div class="container">
        <div class="emergency" id="emergency">
            ⚠️ EMERGENCY STOP
        </div>

        <div class="depth-view">
            <img id="depth" src="" alt="Depth">
            <span class="depth-overlay" id="frame-info">--</span>
        </div>

        <div class="metrics">
            <div class="metric">
                <div class="metric-value" id="fps">--</div>
                <div class="metric-label">FPS</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="latency">--</div>
                <div class="metric-label">Latency</div>
            </div>
            <div class="metric">
                <div class="metric-value" id="frames">--</div>
                <div class="metric-label">Frames</div>
            </div>
        </div>

        <div class="obstacles">
            <div class="obstacles-title">Obstacle Detection</div>
            <div class="obstacle-grid">
                <div class="obstacle-zone clear" id="zone-left">
                    <div class="obstacle-dist" id="dist-left">--</div>
                    <div class="obstacle-label">Left</div>
                </div>
                <div class="obstacle-zone clear" id="zone-center">
                    <div class="obstacle-dist" id="dist-center">--</div>
                    <div class="obstacle-label">Center</div>
                </div>
                <div class="obstacle-zone clear" id="zone-right">
                    <div class="obstacle-dist" id="dist-right">--</div>
                    <div class="obstacle-label">Right</div>
                </div>
            </div>
        </div>

        <div class="movement">
            <div class="movement-title">Movement</div>
            <div class="movement-viz">
                <div>
                    <div class="movement-indicator">
                        <div class="movement-arrow" id="linear-arrow"></div>
                    </div>
                    <div class="movement-label">
                        Linear<br>
                        <span class="movement-value" id="linear-val">0.0</span> m/s
                    </div>
                </div>
                <div>
                    <div class="movement-indicator">
                        <div class="movement-arrow" id="angular-arrow" style="border-bottom-color: #e94560;"></div>
                    </div>
                    <div class="movement-label">
                        Angular<br>
                        <span class="movement-value" id="angular-val">0.0</span> rad/s
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = () => {
                document.getElementById('status').classList.add('connected');
            };

            ws.onclose = () => {
                document.getElementById('status').classList.remove('connected');
                setTimeout(connect, 2000);
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleUpdate(data);
            };
        }

        function handleUpdate(data) {
            // Update depth image
            if (data.depth) {
                document.getElementById('depth').src = 'data:image/jpeg;base64,' + data.depth;
            }

            const status = data.status;

            // Update frame count
            document.getElementById('frames').textContent = status.frame_count || '--';
            document.getElementById('frame-info').textContent = `Frame: ${status.frame_count}`;

            // Update diagnostics
            if (status.diagnostics && status.diagnostics.stereo_depth) {
                const diag = status.diagnostics.stereo_depth.values;
                document.getElementById('fps').textContent = parseFloat(diag.fps || 0).toFixed(1);
                document.getElementById('latency').textContent = parseFloat(diag.compute_time_ms || 0).toFixed(0);
            }

            // Update obstacles
            if (status.obstacles) {
                updateObstacle('left', status.obstacles.left);
                updateObstacle('center', status.obstacles.center);
                updateObstacle('right', status.obstacles.right);

                // Check emergency
                const minDist = Math.min(
                    status.obstacles.left?.distance || 999,
                    status.obstacles.center?.distance || 999,
                    status.obstacles.right?.distance || 999
                );
                document.getElementById('emergency').classList.toggle('active', minDist < 0.3);
            }

            // Update movement
            if (status.cmd_vel) {
                const linear = status.cmd_vel.linear || 0;
                const angular = status.cmd_vel.angular || 0;

                document.getElementById('linear-val').textContent = linear.toFixed(2);
                document.getElementById('angular-val').textContent = angular.toFixed(2);

                // Rotate arrows
                const linearArrow = document.getElementById('linear-arrow');
                const angularArrow = document.getElementById('angular-arrow');

                linearArrow.style.transform = linear < 0 ? 'rotate(180deg)' : 'rotate(0deg)';
                linearArrow.style.opacity = Math.min(1, Math.abs(linear) * 3 + 0.3);

                angularArrow.style.transform = `rotate(${90 - angular * 45}deg)`;
                angularArrow.style.opacity = Math.min(1, Math.abs(angular) * 2 + 0.3);
            }
        }

        function updateObstacle(zone, data) {
            if (!data) return;

            const zoneEl = document.getElementById('zone-' + zone);
            const distEl = document.getElementById('dist-' + zone);

            const dist = data.distance;
            distEl.textContent = dist ? dist.toFixed(2) + 'm' : '--';

            zoneEl.classList.remove('clear', 'warning', 'danger');
            if (dist < 0.3) zoneEl.classList.add('danger');
            else if (dist < 0.7) zoneEl.classList.add('warning');
            else zoneEl.classList.add('clear');
        }

        connect();
    </script>
</body>
</html>
"""


# Only define ROS2 spinner if ROS2 is available
if HAS_ROS2:
    def run_ros2_spinner(node):
        rclpy.spin(node)


async def main_async(args):
    global data_source

    if args.ros2 and HAS_ROS2:
        if not rclpy.ok():
            rclpy.init()
        data_source = ROS2RemoteSource()
        spinner = threading.Thread(target=run_ros2_spinner, args=(data_source,), daemon=True)
        spinner.start()
        print("Using ROS2 data source")
    else:
        data_source = SimulatedRemoteSource()
        print("Using simulated data source")

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


def main():
    parser = argparse.ArgumentParser(description='Remote Stereo Monitor')
    parser.add_argument('--port', '-p', type=int, default=8082)
    parser.add_argument('--host', '-H', default='0.0.0.0')
    parser.add_argument('--ros2', action='store_true')

    args = parser.parse_args()

    if not HAS_FASTAPI or not HAS_CV2:
        print("Error: FastAPI and OpenCV required")
        return 1

    print(f"Remote Monitor: http://{args.host}:{args.port}")
    print("For SSH tunnel: ssh -L 8082:localhost:8082 pi@192.168.1.200")

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        if data_source and hasattr(data_source, 'stop'):
            data_source.stop()

    return 0


if __name__ == '__main__':
    sys.exit(main())
