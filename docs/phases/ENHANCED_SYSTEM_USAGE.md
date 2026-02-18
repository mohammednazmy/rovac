# ROVAC Enhanced System - Usage Guide

## Overview
The enhanced ROVAC system provides advanced capabilities including sensor fusion, obstacle avoidance, frontier exploration, and system health monitoring.

## Prerequisites
1. Ensure the base ROVAC system is running:
   ```bash
   cd ~/robots/rovac
   ./scripts/standalone_control.sh start
   ```

2. Activate ROS2 environment:
   ```bash
   eval "$(conda shell.bash hook)"
   conda activate ros_jazzy
   source ~/robots/rovac/config/ros2_env.sh
   ```

## Running Enhanced Components

### Option 1: Using Launch File (Recommended)
```bash
# Run all enhanced components
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py

# Run with frontier exploration enabled
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py enable_frontier_exploration:=true

# Run specific components only
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py enable_health_monitor:=true enable_sensor_fusion:=true
```

### Option 2: Running Individual Components
```bash
# System Health Monitor
ros2 run rovac_enhanced system_health_monitor.py

# Sensor Fusion Node
ros2 run rovac_enhanced sensor_fusion_node.py

# Obstacle Avoidance Node
ros2 run rovac_enhanced obstacle_avoidance_node.py

# Frontier Exploration Node
ros2 run rovac_enhanced frontier_exploration_node.py --ros-args -p enable_exploration:=true

# Diagnostics Collector
ros2 run rovac_enhanced diagnostics_collector.py
```

## Component Descriptions

### System Health Monitor
- Monitors CPU, memory, and network connectivity
- Tracks ROS node status and attempts recovery
- Publishes diagnostics to `/diagnostics` topic

### Sensor Fusion Node
- Combines LIDAR and ultrasonic sensor data
- Integrates IMU with odometry for better positioning
- Outputs fused data to `/sensors/fused_scan` and `/odom/fused`

### Obstacle Avoidance Node
- Implements reactive collision avoidance
- Uses fused sensor data for detection
- Outputs safe velocity commands to `/cmd_vel_avoidance`

### Frontier Exploration Node
- Autonomous mapping by finding unexplored areas
- Navigates to frontiers for SLAM improvement
- Activated with `enable_exploration:=true` parameter

### Diagnostics Collector
- Collects system and ROS logs
- Stores diagnostic information in JSON format
- Monitors resource usage and performance

## Testing Components

### Verify Nodes Are Running
```bash
ros2 node list | grep enhanced
```

### Check Topics
```bash
ros2 topic list | grep enhanced
ros2 topic echo /diagnostics
```

### Monitor Logs
```bash
ros2 run rovac_enhanced diagnostics_collector.py
# Check logs in /tmp/rovac_logs/
```

## Troubleshooting

### Common Issues
1. **Components not connecting**: Ensure base ROVAC system is running
2. **Import errors**: Verify ROS2 environment is activated
3. **Permission denied**: Make sure scripts are executable (`chmod +x`)

### Stopping Components
- If launched with `ros2 launch`: Use Ctrl+C
- If launched individually: Use Ctrl+C in each terminal
- Kill all ROS2 processes: `pkill -f ros2`

## Pi-Side Components
Enhanced components have been installed on the Pi:
```bash
# On Pi
ls ~/rovac_enhanced/
```

These can be integrated into Pi-side launch files as needed.