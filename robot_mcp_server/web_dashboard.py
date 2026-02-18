#!/usr/bin/env python3
"""
Web Dashboard for ROVAC Robot System
Provides real-time monitoring and control interface with WebSocket support
"""

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
import json
import os
import asyncio
import aiohttp

# Create Flask app
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "rovac-secret-key"
socketio = SocketIO(app, cors_allowed_origins="*")


# Shared data store
class RobotData:
    def __init__(self):
        self.sensor_data = {
            "lidar_points": 0,
            "ultrasonic_distance": 0.0,
            "battery_level": 100,
            "cpu_usage": 0,
            "memory_usage": 0,
        }
        self.system_status = {
            "health_monitor": "running",
            "sensor_fusion": "running",
            "obstacle_avoidance": "running",
            "navigation": "idle",
            "communication": "active",
        }
        self.object_detections = []
        self.last_update = time.time()
        self.camera_feed = None
        self.map_data = None


# Global data instance
robot_data = RobotData()


# Routes
@app.route("/")
def index():
    """Main dashboard page"""
    return render_template("dashboard.html")


@app.route("/test-status")
def test_status():
    """Status indicator test page"""
    return render_template("test-status.html")


@app.route("/test-websocket")
def test_websocket():
    """WebSocket test page"""
    return render_template("test-websocket.html")


@app.route("/api/status")
def api_status():
    """API endpoint for system status"""
    return jsonify(
        {
            "timestamp": time.time(),
            "sensor_data": robot_data.sensor_data,
            "system_status": robot_data.system_status,
            "object_detections": robot_data.object_detections,
            "last_update": robot_data.last_update,
            "camera_feed": robot_data.camera_feed,
            "map_data": robot_data.map_data,
        }
    )


@app.route("/api/control", methods=["POST"])
def api_control():
    """API endpoint for robot control"""
    command = request.json.get("command")
    # In a real implementation, this would send commands to the robot
    # For now, we'll just emit to WebSocket clients
    socketio.emit("robot_command", {"command": command})
    return jsonify({"status": "success", "command": command})


@app.route("/api/tool", methods=["POST"])
def api_tool():
    """API endpoint for MCP tool execution"""
    tool = request.json.get("tool")
    # In a real implementation, this would call the MCP server
    # For now, we'll just emit to WebSocket clients
    socketio.emit("tool_execution", {"tool": tool})
    return jsonify({"status": "success", "tool": tool})


@app.route("/api/map")
def api_map():
    """API endpoint for map data"""
    # Placeholder for map data
    return jsonify(
        {
            "width": 100,
            "height": 100,
            "resolution": 0.05,
            "data": [],  # Would contain occupancy grid data
        }
    )


# WebSocket events
@socketio.on("connect")
def handle_connect():
    print("Client connected")
    emit("connection_status", {"status": "connected"})


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


@socketio.on("robot_command")
def handle_robot_command(data):
    """Handle robot command from WebSocket"""
    command = data.get("command")
    print(f"Received command: {command}")
    # In a real implementation, this would send commands to the robot
    emit("command_response", {"status": "success", "command": command})


@socketio.on("tool_execution")
def handle_tool_execution(data):
    """Handle tool execution from WebSocket"""
    tool = data.get("tool")
    print(f"Received tool execution: {tool}")
    # In a real implementation, this would call the MCP server
    emit("tool_response", {"status": "success", "tool": tool})


@socketio.on("joystick")
def handle_joystick(data):
    """Handle joystick movement"""
    x = data.get("x", 0)
    y = data.get("y", 0)
    print(f"Joystick movement: x={x}, y={y}")
    # In a real implementation, this would send movement commands to the robot
    emit("movement_response", {"status": "success", "x": x, "y": y})


@socketio.on("speed")
def handle_speed(data):
    """Handle speed adjustment"""
    speed = data.get("speed", 0.5)
    print(f"Speed adjustment: {speed}x")
    # In a real implementation, this would adjust the robot's speed
    emit("speed_response", {"status": "success", "speed": speed})


def update_robot_data():
    """Simulate updating robot data (would connect to ROS in real implementation)"""
    while True:
        # Simulate sensor data updates
        robot_data.sensor_data["lidar_points"] = int(time.time()) % 360
        robot_data.sensor_data["ultrasonic_distance"] = 0.5 + (time.time() % 1.0)
        robot_data.sensor_data["battery_level"] = max(
            20, 100 - (int(time.time() / 100) % 80)
        )
        robot_data.sensor_data["cpu_usage"] = 20 + (int(time.time()) % 30)
        robot_data.sensor_data["memory_usage"] = 40 + (int(time.time()) % 20)

        # Simulate object detections
        if int(time.time()) % 10 < 2:
            robot_data.object_detections = [
                {"type": "person", "distance": 1.5, "angle": 30},
                {"type": "chair", "distance": 2.0, "angle": -45},
            ]
        else:
            robot_data.object_detections = []

        robot_data.last_update = time.time()

        # Emit data to all connected WebSocket clients
        socketio.emit(
            "robot_data",
            {
                "timestamp": time.time(),
                "sensor_data": robot_data.sensor_data,
                "system_status": robot_data.system_status,
                "object_detections": robot_data.object_detections,
                "last_update": robot_data.last_update,
            },
        )

        time.sleep(1)


# Create templates directory and HTML template
def create_templates():
    """Create HTML templates for the dashboard"""
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    os.makedirs(templates_dir, exist_ok=True)
    os.makedirs(static_dir, exist_ok=True)

    # Create dashboard HTML
    dashboard_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ROVAC Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="/static/css/dashboard.css">
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div>
                <h1><i class="fas fa-robot"></i> ROVAC Robot Dashboard</h1>
                <p>Advanced real-time monitoring and control interface for the Yahboom G1 Tank robot</p>
            </div>
            <div>
                <div class="status-badge">
                    <i class="fas fa-circle"></i>
                    <span>Connected to Robot</span>
                </div>
                <div class="connection-status">
                    <div class="status-dot" id="connection-status-dot"></div>
                    <span id="connection-status-text">Disconnected</span>
                </div>
            </div>
        </div>
    </div>

    <div class="dashboard-grid">
        <!-- System Status Card -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-heartbeat"></i>
                <h2>System Status</h2>
            </div>
            <div id="system-status">
                <p><span class="status-indicator status-unknown"></span> Health Monitor: <span id="health-status">Unknown</span></p>
                <p><span class="status-indicator status-unknown"></span> Sensor Fusion: <span id="sensor-status">Unknown</span></p>
                <p><span class="status-indicator status-unknown"></span> Obstacle Avoidance: <span id="obstacle-status">Unknown</span></p>
                <p><span class="status-indicator status-unknown"></span> Navigation: <span id="navigation-status">Unknown</span></p>
                <p><span class="status-indicator status-unknown"></span> Communication: <span id="communication-status">Unknown</span></p>
            </div>
        </div>

        <!-- Sensor Data Card -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-microchip"></i>
                <h2>Sensor Data</h2>
            </div>
            <p class="sensor-label">LIDAR Points</p>
            <span id="lidar-points" class="sensor-value">0</span>
            <p class="sensor-label">Distance Ahead</p>
            <span id="distance" class="sensor-value">0.0m</span>
            <p class="sensor-label">Battery Level</p>
            <span id="battery" class="sensor-value">100%</span>
        </div>

        <!-- Resource Usage Card -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-tachometer-alt"></i>
                <h2>Resource Usage</h2>
            </div>
            <div class="progress-container">
                <div class="progress-header">
                    <span class="sensor-label">CPU Usage</span>
                    <span id="cpu-percent">0</span>%
                </div>
                <div class="progress-bar">
                    <div class="progress-fill cpu-fill" id="cpu-bar" style="width: 0%"></div>
                </div>
            </div>
            <div class="progress-container">
                <div class="progress-header">
                    <span class="sensor-label">Memory Usage</span>
                    <span id="memory-percent">0</span>%
                </div>
                <div class="progress-bar">
                    <div class="progress-fill memory-fill" id="memory-bar" style="width: 0%"></div>
                </div>
            </div>
            <div class="progress-container">
                <div class="progress-header">
                    <span class="sensor-label">Battery</span>
                    <span id="battery-percent">100</span>%
                </div>
                <div class="progress-bar">
                    <div class="progress-fill battery-fill" id="battery-bar" style="width: 100%"></div>
                </div>
            </div>
        </div>

        <!-- Object Detection Card -->
        <div class="card">
            <div class="card-header">
                <i class="fas fa-eye"></i>
                <h2>Object Detection</h2>
            </div>
            <div id="object-detections">
                <p>No objects detected</p>
            </div>
        </div>
    </div>

    <!-- Visualization Section -->
    <div class="visualization-section">
        <div class="card">
            <div class="card-header">
                <i class="fas fa-video"></i>
                <h2>Camera Feed</h2>
            </div>
            <div id="camera-feed">
                <img src="" alt="Camera feed" id="camera-image" style="display: none;">
                <p id="camera-placeholder"><i class="fas fa-camera"></i> Camera feed loading...</p>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <i class="fas fa-map-marked-alt"></i>
                <h2>Map & Navigation</h2>
            </div>
            <div id="map-container">
                <canvas id="map-canvas" style="display: none;"></canvas>
                <p id="map-placeholder"><i class="fas fa-map"></i> Map visualization loading...</p>
            </div>
        </div>
    </div>

    <!-- Joystick Control -->
    <div class="joystick-section">
        <h2><i class="fas fa-gamepad"></i> Manual Control</h2>
        <div class="speed-control">
            <label for="speed-slider">Movement Speed:</label>
            <input type="range" min="0.1" max="1.0" step="0.1" value="0.5" class="speed-slider" id="speed-slider">
            <div class="speed-value"><span id="speed-value">0.5</span>x</div>
        </div>
        <div id="joystick-container">
            <div class="joystick-base">
                <div class="joystick-handle" id="joystick-handle"></div>
            </div>
        </div>
        <div class="btn-group" style="margin-top: 25px;">
            <button class="btn btn-warning" onclick="sendCommand('look_left')">
                <i class="fas fa-arrow-left"></i> Look Left
            </button>
            <button class="btn btn-success" onclick="sendCommand('look_center')">
                <i class="fas fa-bullseye"></i> Center Camera
            </button>
            <button class="btn btn-warning" onclick="sendCommand('look_right')">
                <i class="fas fa-arrow-right"></i> Look Right
            </button>
        </div>
    </div>

    <!-- Tool Execution Panel -->
    <div class="tool-execution">
        <h2><i class="fas fa-tools"></i> Tool Execution</h2>
        <div id="tool-execution-placeholder">
            <p><i class="fas fa-cogs"></i> Execute robot tools and commands</p>
        </div>
        <div class="command-input">
            <input type="text" id="command-input" placeholder="Enter command (e.g., move_forward, turn_left, explore_and_map)">
            <button onclick="executeTool()"><i class="fas fa-play"></i> Execute</button>
        </div>
        <div class="log-console" id="log-console">
            <div class="log-entry"><span class="log-time">[00:00:00]</span> <span class="log-info">System initialized</span></div>
        </div>
    </div>

    <!-- Control Panel -->
    <div class="control-panel">
        <h2><i class="fas fa-gamepad"></i> Robot Control</h2>
        <div class="btn-group">
            <button class="btn btn-success" onclick="sendCommand('start')">
                <i class="fas fa-play"></i> Start Systems
            </button>
            <button class="btn btn-stop" onclick="showEmergencyStopModal()">
                <i class="fas fa-stop"></i> Emergency Stop
            </button>
            <button class="btn" onclick="sendCommand('explore_and_map')">
                <i class="fas fa-compass"></i> Auto Explore
            </button>
            <button class="btn btn-warning" onclick="sendCommand('return_home')">
                <i class="fas fa-home"></i> Return Home
            </button>
            <button class="btn" onclick="sendCommand('scan_surroundings')">
                <i class="fas fa-search"></i> Scan Area
            </button>
            <button class="btn" onclick="sendCommand('sweep_scan')">
                <i class="fas fa-sync-alt"></i> Full Sweep
            </button>
        </div>
        <div class="btn-group">
            <button class="btn" onclick="sendCommand('turn_around')">
                <i class="fas fa-redo"></i> 360° Turn
            </button>
            <button class="btn" onclick="sendCommand('drive_square')">
                <i class="far fa-square"></i> Square Pattern
            </button>
            <button class="btn" onclick="sendCommand('lawn_mower')">
                <i class="fas fa-border-all"></i> Lawn Mower
            </button>
            <button class="btn" onclick="sendCommand('beep')">
                <i class="fas fa-volume-up"></i> Beep
            </button>
        </div>
    </div>

    <!-- Emergency Stop Modal -->
    <div class="modal" id="emergency-stop-modal">
        <div class="modal-content">
            <div class="modal-header">
                <i class="fas fa-exclamation-triangle"></i>
                <h2>Emergency Stop Confirmation</h2>
                <p>Are you sure you want to initiate an emergency stop? This will immediately halt all robot operations.</p>
            </div>
            <div class="modal-buttons">
                <button class="modal-btn modal-btn-confirm" onclick="confirmEmergencyStop()">Confirm Stop</button>
                <button class="modal-btn modal-btn-cancel" onclick="closeEmergencyStopModal()">Cancel</button>
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script src="/static/js/dashboard.js"></script>
</body>
</html>
"""

    with open(os.path.join(templates_dir, "dashboard.html"), "w") as f:
        f.write(dashboard_html)


def main():
    """Main function to start the web dashboard"""
    # Create templates
    create_templates()

    # Start data update thread
    data_thread = threading.Thread(target=update_robot_data, daemon=True)
    data_thread.start()

    # Start Flask app with WebSocket support
    socketio.run(
        app, host="0.0.0.0", port=5001, debug=False, allow_unsafe_werkzeug=True
    )


if __name__ == "__main__":
    main()
