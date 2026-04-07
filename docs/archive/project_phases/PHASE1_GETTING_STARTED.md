# ROVAC Enhanced System - Phase 1 Getting Started Guide

## 🚀 Quick Access

### Web Dashboard
The web dashboard is already running! Access it at:
👉 **http://localhost:5001/**

**Features:**
- Real-time sensor data visualization
- System status monitoring
- Object detection display
- Remote control interface

### Enhanced System Components
To start all enhanced components:
```bash
# Terminal 1: Start enhanced system
cd ~/robots/rovac
eval "$(conda shell.bash hook)"
conda activate ros_jazzy
source config/ros2_env.sh
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py
```

## 📋 Phase 1 Components Overview

### 1. Object Recognition System
**Purpose:** Identifies objects in the robot's environment using computer vision

**Features:**
- Real-time object detection from camera feed
- Classification of people, furniture, and environmental objects
- Visualization markers for Foxglove integration
- Fallback detection methods for edge computing

**Files:**
- `robot_mcp_server/object_recognition_node.py`
- `robot_mcp_server/object_recognition.launch.py`

### 2. Web Dashboard
**Purpose:** Provides a web-based interface for monitoring and controlling the robot

**Features:**
- Real-time sensor data visualization
- System component status monitoring
- Object detection display
- Remote control commands (Start/Stop/Explore/Return Home)

**Files:**
- `robot_mcp_server/web_dashboard.py`
- `robot_mcp_server/templates/dashboard.html`

### 3. System Integration
**Purpose:** Seamlessly integrates new components with existing ROVAC system

**Features:**
- Single-launch deployment of all enhanced components
- Configurable parameters for each component
- Conditional enabling/disabling of features

**Files:**
- `robot_mcp_server/rovac_enhanced_system.launch.py`

## 🔧 Usage Instructions

### Starting the Complete Enhanced System
```bash
# Terminal 1: Activate environment and launch
cd ~/robots/rovac
eval "$(conda shell.bash hook)"
conda activate ros_jazzy
source config/ros2_env.sh
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py

# Optional: Enable specific components
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \
  enable_object_recognition:=true \
  enable_frontier_exploration:=true \
  object_confidence_threshold:=0.7
```

### Starting Individual Components
```bash
# Object Recognition Node
ros2 run rovac_enhanced object_recognition_node.py

# With custom parameters
ros2 run rovac_enhanced object_recognition_node.py \
  --ros-args -p confidence_threshold:=0.8 -p frame_skip:=3
```

### Accessing the Web Dashboard
The dashboard is already running at **http://localhost:5001/**

If you need to restart it:
```bash
# Terminal 2: Start web dashboard
cd ~/robots/rovac
source robot_mcp_server/venv/bin/activate
python robot_mcp_server/web_dashboard.py
```

## 🔍 Monitoring and Testing

### Check Running Components
```bash
# List all running nodes
ros2 node list | grep enhanced

# Expected output:
# /object_recognition_node
# /system_health_monitor
# /sensor_fusion_node
# /obstacle_avoidance_node
# /frontier_exploration_node
# /diagnostics_collector
```

### Monitor Key Topics
```bash
# View object detections
ros2 topic echo /objects/detected

# View visualization markers
ros2 topic echo /objects/markers

# View system diagnostics
ros2 topic echo /diagnostics
```

### Test Web Dashboard API
```bash
# Get system status
curl http://localhost:5001/api/status | python -m json.tool

# Send control command
curl -X POST http://localhost:5001/api/control \
  -H "Content-Type: application/json" \
  -d '{"command":"start"}'
```

## 📊 Expected Output Examples

### Object Detection Topic
```
data: "person(0.85), chair(0.72)"
```

### Visualization Markers
```
markers:
  - header:
      frame_id: "phone_camera_link"
    ns: "objects"
    id: 0
    type: 1  # CUBE
    action: 0  # ADD
    pose:
      position:
        x: 1.0
        y: 0.2
        z: 0.5
    scale:
      x: 0.3
      y: 0.3
      z: 0.3
    color:
      r: 1.0  # Red for person
      g: 0.0
      b: 0.0
      a: 0.85  # Based on confidence
```

### Web Dashboard API Response
```json
{
  "timestamp": 1768468882.6987479,
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
  "last_update": 1768468882.134287
}
```

## ⚠️ Troubleshooting

### Web Dashboard Issues
1. **Cannot access dashboard:**
   ```bash
   # Check if dashboard is running
   lsof -i :5001
   
   # Restart dashboard if needed
   pkill -f web_dashboard.py
   cd ~/robots/rovac
   source robot_mcp_server/venv/bin/activate
   nohup python robot_mcp_server/web_dashboard.py > ~/web_dashboard.log 2>&1 &
   ```

2. **Blank page or errors:**
   - Refresh browser cache (Ctrl+F5)
   - Check browser console for errors (F12)
   - Verify network connectivity to localhost

### Object Recognition Issues
1. **Import errors:**
   ```bash
   # Ensure ROS2 environment is activated
   eval "$(conda shell.bash hook)"
   conda activate ros_jazzy
   source config/ros2_env.sh
   ```

2. **No detections:**
   - Verify camera feed is available
   - Check lighting conditions
   - Adjust confidence threshold parameter

### System Integration Issues
1. **Launch file errors:**
   ```bash
   # Check launch file syntax
   python -m py_compile robot_mcp_server/rovac_enhanced_system.launch.py
   ```

2. **Nodes not starting:**
   - Check ROS2 domain ID: `echo $ROS_DOMAIN_ID` (should be 42)
   - Verify network connectivity to Pi
   - Check system resources

## 📚 Documentation References

### Detailed Guides
- `robot_mcp_server/OBJECT_RECOGNITION_README.md`
- `robot_mcp_server/WEB_DASHBOARD_README.md`
- `ENHANCED_SYSTEM_DEMO_GUIDE.md`

### Testing and Verification
- `ENHANCED_SYSTEM_TEST_SUMMARY.md`
- `ENHANCED_SYSTEM_PHASE1_SUMMARY.md`

## 🎉 Success Confirmation

You should now have:
✅ **Web Dashboard** running at http://localhost:5001/
✅ **Enhanced System Components** ready to launch
✅ **Object Recognition** integrated and functional
✅ **Complete Documentation** for all features

Enjoy exploring the enhanced capabilities of your ROVAC robot!