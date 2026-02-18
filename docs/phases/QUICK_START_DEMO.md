# ROVAC Enhanced System - Quick Start Demo

## Overview
This guide provides a quick demonstration of the newly implemented enhanced system features.

## Prerequisites Check
```bash
# Navigate to ROVAC directory
cd ~/robots/rovac

# Verify enhanced components are installed
ls -la robot_mcp_server/*enhanced* robot_mcp_server/*recognition* robot_mcp_server/*dashboard*
```

Expected output:
```
robot_mcp_server/object_recognition_node.py
robot_mcp_server/object_recognition.launch.py
robot_mcp_server/rovac_enhanced_system.launch.py
robot_mcp_server/web_dashboard.py
```

## Demo 1: Launch Enhanced System Components

```bash
# Activate ROS2 environment
eval "$(conda shell.bash hook)"
conda activate ros_jazzy
source config/ros2_env.sh

# Launch all enhanced components
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py

# Or launch with specific components enabled
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \
  enable_object_recognition:=true \
  enable_frontier_exploration:=true
```

## Demo 2: Start Web Dashboard

```bash
# In a new terminal, start the web dashboard
cd ~/robots/rovac
source robot_mcp_server/venv/bin/activate
python robot_mcp_server/web_dashboard.py

# Access the dashboard at: http://localhost:5001
```

## Demo 3: Check System Status

```bash
# Check what nodes are running
ros2 node list | grep enhanced

# Check available topics
ros2 topic list | grep objects

# Monitor system diagnostics
ros2 topic echo /diagnostics --once
```

## Expected Results

### Enhanced Nodes Running:
- `/object_recognition_node`
- `/system_health_monitor`
- `/sensor_fusion_node`
- `/obstacle_avoidance_node`

### Enhanced Topics Available:
- `/objects/detected`
- `/objects/markers`
- `/system/health_status`
- `/sensors/fused_scan`

### Web Dashboard Features:
- Real-time sensor visualization
- System status monitoring
- Object detection display
- Remote control interface

## Component Highlights

### Object Recognition System
- Processes camera feed for object detection
- Identifies people, furniture, and environmental objects
- Publishes visualization markers for Foxglove
- Works with or without DNN models (fallback detection)

### Web Dashboard
- Flask-based web application
- Real-time data visualization
- Remote control capabilities
- Responsive design for all devices

## Next Steps

### For Full Testing:
1. Connect Android phone with SensorServer app
2. Start phone integration system
3. Test object recognition with live camera feed
4. Verify web dashboard with real data

### For Further Exploration:
1. Review detailed documentation:
   - `robot_mcp_server/OBJECT_RECOGNITION_README.md`
   - `robot_mcp_server/WEB_DASHBOARD_README.md`
   - `ENHANCED_SYSTEM_DEMO_GUIDE.md`

2. Experiment with parameters:
   ```bash
   # Adjust object recognition sensitivity
   ros2 param set /object_recognition_node confidence_threshold 0.3
   
   # Control processing rate
   ros2 param set /object_recognition_node frame_skip 10
   ```

## Troubleshooting

### Common Issues:
1. **Import errors**: Ensure ROS2 environment is activated
2. **Node not found**: Check that launch files are in PATH
3. **Topics not appearing**: Verify components are running
4. **Dashboard not loading**: Check port usage and firewall

### Quick Fixes:
```bash
# Restart enhanced system
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py

# Check node status
ros2 node list | grep enhanced

# Verify topic availability
ros2 topic list | grep objects
```

## Success Criteria
✅ All enhanced components import without errors
✅ Launch files execute successfully
✅ Web dashboard starts and serves content
✅ System integration verified
✅ Documentation accessible

Congratulations! You've successfully deployed the enhanced ROVAC system with advanced perception and monitoring capabilities.