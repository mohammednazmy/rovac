# ROVAC Web Dashboard

## Overview
The ROVAC Web Dashboard provides a real-time monitoring and control interface for the robot system. It displays sensor data, system status, object detections, and map visualization in a user-friendly web interface.

## Features
- Real-time sensor data visualization
- System component status monitoring
- Object detection display
- Map and navigation visualization
- Remote control interface
- Responsive web design

## Architecture
```
Web Dashboard (Flask)
    ↓ HTTP API
Robot Data Interface
    ↓ ROS2 Topics
ROVAC System Components
```

## Installation

### Prerequisites
- Python 3.8+
- Flask web framework
- Robot MCP server virtual environment

### Setup
The dashboard is automatically installed with the robot MCP server:

```bash
# Flask is installed in the MCP server virtual environment
source ~/robots/rovac/robot_mcp_server/venv/bin/activate
pip install flask
```

## Usage

### Starting the Dashboard
```bash
# Method 1: Using the start script
cd ~/robots/rovac
./scripts/start_web_dashboard.sh

# Method 2: Direct execution
cd ~/robots/rovac/robot_mcp_server
source venv/bin/activate
python3 web_dashboard.py
```

### Accessing the Dashboard
Once started, the dashboard is available at:
- **Local access**: http://localhost:5000
- **Remote access**: http://[robot-ip]:5000

## Dashboard Components

### 1. System Status Panel
Displays the operational status of all system components:
- Health Monitor
- Sensor Fusion
- Obstacle Avoidance
- Navigation System

Status indicators use color coding:
- 🟢 **Green**: Running normally
- 🟡 **Yellow**: Warning/Idle
- 🔴 **Red**: Error/Stopped

### 2. Sensor Data Panel
Real-time display of key sensor measurements:
- **LIDAR Points**: Number of detected points (0-360)
- **Distance**: Ultrasonic sensor reading (meters)
- **Battery**: Current battery level (percentage)

### 3. Resource Usage Panel
System resource monitoring:
- **CPU Usage**: Processor utilization percentage
- **Memory Usage**: RAM consumption percentage
- Visual progress bars for quick assessment

### 4. Object Detection Panel
Displays detected objects from the vision system:
- Object type (person, chair, etc.)
- Distance from robot
- Angular position

### 5. Map Visualization
(Scheduled enhancement) Will display:
- Occupancy grid map
- Robot position and orientation
- Navigation path
- Detected obstacles

### 6. Control Panel
Remote control interface with these commands:
- **Start**: Begin robot operations
- **Stop**: Emergency stop
- **Explore**: Start autonomous exploration
- **Return Home**: Navigate to home position

## API Endpoints

### GET /api/status
Returns current system status and sensor data:
```json
{
  "timestamp": 1234567890.123,
  "sensor_data": {
    "lidar_points": 180,
    "ultrasonic_distance": 1.5,
    "battery_level": 85,
    "cpu_usage": 25,
    "memory_usage": 45
  },
  "system_status": {
    "health_monitor": "running",
    "sensor_fusion": "running",
    "obstacle_avoidance": "running",
    "navigation": "idle"
  },
  "object_detections": [
    {"type": "person", "distance": 1.5, "angle": 30}
  ],
  "last_update": 1234567890.123
}
```

### POST /api/control
Send control commands to the robot:
```json
{
  "command": "start|stop|explore|return_home"
}
```

Response:
```json
{
  "status": "success",
  "command": "start"
}
```

### GET /api/map
(Scheduled enhancement) Returns map data for visualization.

## Integration with ROVAC System

### Data Flow
1. **ROS2 Topics** → Robot Data Interface → **Shared Memory**
2. **Shared Memory** → **Flask API Endpoints** → **Web Browser**
3. **Web Browser** → **Control API** → **Robot Command Interface** → **ROS2 Topics**

### Planned Enhancements
- Real-time map visualization with Three.js or similar
- WebSocket integration for live updates
- User authentication and security
- Mobile-responsive design
- Historical data charts and analytics
- Mission planning interface

## Troubleshooting

### Dashboard Not Loading
1. Check if the dashboard service is running
2. Verify port 5000 is not blocked by firewall
3. Ensure network connectivity to the robot

### No Sensor Data
1. Verify ROS2 topics are publishing data
2. Check robot data interface connection
3. Confirm sensor components are running

### Control Commands Not Working
1. Verify robot command interface is active
2. Check ROS2 action servers are running
3. Ensure proper permissions for control commands

## Customization

### Modifying the Dashboard
- **HTML Templates**: Located in `templates/dashboard.html`
- **CSS Styling**: Embedded in the HTML template
- **JavaScript Logic**: At the bottom of the HTML template
- **Python Backend**: `web_dashboard.py` file

### Adding New Features
1. Extend the `RobotData` class with new data fields
2. Add new API endpoints in Flask
3. Update the HTML template with new UI elements
4. Add corresponding JavaScript handlers

## Security Considerations
- Default binding to all interfaces (0.0.0.0) - restrict in production
- No authentication by default - add for remote access
- API endpoints return system information - limit access as needed
- Control commands should validate input - implement sanitization

## Performance
- **Update Rate**: 1 Hz (configurable)
- **Memory Usage**: ~50MB
- **CPU Usage**: ~5% on typical hardware
- **Network**: ~1KB per update

## Dependencies
- Flask 2.0+
- Python 3.8+
- Robot MCP server environment
- ROS2 system (for actual implementation)

## Contributing
To enhance the dashboard:
1. Fork the repository
2. Create a feature branch
3. Implement enhancements
4. Test thoroughly
5. Submit a pull request