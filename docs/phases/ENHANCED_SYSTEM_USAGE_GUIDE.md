# ROVAC Enhanced System - Complete Usage Guide

## Overview
This guide provides detailed instructions for using all enhanced components of the ROVAC system, including specific examples and best practices.

## Prerequisites

### System Requirements
1. ROVAC base system running (Raspberry Pi 5 with Yahboom G1 Tank)
2. Mac computer with ROS2 Jazzy environment
3. Nintendo Pro Controller for manual control
4. Network connectivity between Mac (192.168.1.104) and Pi (192.168.1.200)

### Environment Setup
```bash
# 1. Activate conda environment
eval "$(conda shell.bash hook)"
conda activate ros_jazzy

# 2. Source ROS2 environment
source ~/robots/rovac/config/ros2_env.sh

# 3. Verify setup
echo "ROS Domain ID: $ROS_DOMAIN_ID"
ros2 --version
```

## Enhanced Components

### 1. System Health Monitor
Monitors system status and performs automatic recovery.

**Usage Examples**:
```bash
# Run with default settings
ros2 run rovac_enhanced system_health_monitor.py

# Run with verbose logging
ros2 run rovac_enhanced system_health_monitor.py --ros-args --log-level DEBUG
```

**Published Topics**:
- `/diagnostics` - System diagnostic information
- `/system/health_status` - JSON-formatted health status

**Subscribed Topics**:
- Monitors all ROS nodes and system resources

### 2. Sensor Fusion Node
Combines LIDAR, ultrasonic, and IMU data for enhanced perception.

**Usage Examples**:
```bash
# Run with default settings
ros2 run rovac_enhanced sensor_fusion_node.py

# Run with custom parameters
ros2 run rovac_enhanced sensor_fusion_node.py --ros-args -p min_obstacle_distance:=0.5
```

**Published Topics**:
- `/sensors/fused_scan` - Combined LIDAR/ultrasonic data
- `/odom/fused` - Fused odometry with IMU integration

**Subscribed Topics**:
- `/scan` - LIDAR data
- `/sensors/ultrasonic/range` - Ultrasonic sensor data
- `/sensors/imu` - IMU data
- `/odom` - Odometry data

### 3. Obstacle Avoidance Node
Implements reactive collision avoidance using fused sensor data.

**Usage Examples**:
```bash
# Run with default settings
ros2 run rovac_enhanced obstacle_avoidance_node.py

# Run with custom speed limits
ros2 run rovac_enhanced obstacle_avoidance_node.py --ros-args -p max_linear_speed:=0.5 -p max_angular_speed:=1.5
```

**Published Topics**:
- `/cmd_vel_avoidance` - Safe velocity commands
- `/system/avoidance_active` - Obstacle avoidance status

**Subscribed Topics**:
- `/sensors/fused_scan` - Fused sensor data
- `/cmd_vel_joy` - Manual velocity commands

### 4. Frontier Exploration Node
Autonomous mapping by finding and navigating to unexplored frontiers.

**Usage Examples**:
```bash
# Run without exploration (monitoring mode)
ros2 run rovac_enhanced frontier_exploration_node.py

# Run with exploration enabled
ros2 run rovac_enhanced frontier_exploration_node.py --ros-args -p enable_exploration:=true

# Run with custom exploration rate
ros2 run rovac_enhanced frontier_exploration_node.py --ros-args -p enable_exploration:=true -p exploration_rate:=1.0
```

**Published Topics**:
- `/system/exploration_active` - Exploration status

**Subscribed Topics**:
- `/map` - Occupancy grid map
- `/scan` - LIDAR data for frontier detection

### 5. Diagnostics Collector
Collects system logs, ROS information, and performance metrics.

**Usage Examples**:
```bash
# Run with default settings
ros2 run rovac_enhanced diagnostics_collector.py

# Run with custom log directory
ros2 run rovac_enhanced diagnostics_collector.py --ros-args -p log_directory:="/custom/log/path"
```

**Published Topics**:
- Periodic system diagnostic reports

**Subscribed Topics**:
- Monitors various system and ROS metrics

### 6. Enhanced Joy Mapper
Improved controller handling with better error detection and logging.

**Usage Examples**:
```bash
# Replace standard joy mapper
ros2 run rovac_enhanced joy_mapper_enhanced.py

# Run with verbose logging
ros2 run rovac_enhanced joy_mapper_enhanced.py --ros-args --log-level INFO
```

**Published Topics**:
- `/cmd_vel_joy` - Velocity commands
- `/sensors/servo_cmd` - Servo commands
- `/sensors/led_cmd` - LED commands
- `/sensors/buzzer_cmd` - Buzzer commands
- `/tank/speed` - Speed settings
- `/system/controller_connected` - Connection status

**Subscribed Topics**:
- `/tank/joy` - Joystick input

## Launch File Usage

### Running All Components
```bash
# Run all enhanced components
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py

# Run with frontier exploration enabled
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py enable_frontier_exploration:=true

# Run specific components only
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \
  enable_health_monitor:=true \
  enable_sensor_fusion:=true \
  enable_obstacle_avoidance:=true
```

### Custom Configuration Example
```bash
# High-performance exploration setup
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \
  enable_frontier_exploration:=true \
  enable_obstacle_avoidance:=true \
  --ros-args \
  -p exploration_rate:=0.3 \
  -p max_linear_speed:=0.6 \
  -p max_angular_speed:=2.0
```

## Testing Procedures

### 1. Component Integration Test
```bash
# Step 1: Start base ROVAC system
cd ~/robots/rovac
./scripts/standalone_control.sh start

# Step 2: Verify sensor topics
ros2 topic list | grep -E "(scan|ultrasonic|imu)"

# Step 3: Start enhanced components
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py

# Step 4: Monitor system diagnostics
ros2 topic echo /diagnostics --once
```

### 2. Manual Control Test
```bash
# Step 1: Connect Nintendo Pro Controller
# Step 2: Start enhanced joy mapper
ros2 run rovac_enhanced joy_mapper_enhanced.py

# Step 3: Monitor controller status
ros2 topic echo /system/controller_connected --once

# Step 4: Test movement commands
ros2 topic echo /cmd_vel_joy --once
```

### 3. Sensor Fusion Test
```bash
# Step 1: Start sensor fusion node
ros2 run rovac_enhanced sensor_fusion_node.py

# Step 2: Compare raw vs fused data
echo "Raw LIDAR data:"
ros2 topic echo /scan --once

echo "Fused sensor data:"
ros2 topic echo /sensors/fused_scan --once
```

### 4. Obstacle Avoidance Test
```bash
# Step 1: Start obstacle avoidance
ros2 run rovac_enhanced obstacle_avoidance_node.py

# Step 2: Simulate obstacle
# Place object in front of robot

# Step 3: Monitor avoidance commands
ros2 topic echo /cmd_vel_avoidance --once

# Step 4: Check avoidance status
ros2 topic echo /system/avoidance_active --once
```

## Pi-Side Integration

### Running Enhanced Components on Pi
```bash
# SSH to Pi
ssh pi

# Navigate to enhanced components
cd ~/rovac_enhanced

# Run system health monitor
python3 system_health_monitor.py

# Run sensor fusion (if sensors are available locally)
python3 sensor_fusion_node.py
```

### Cross-System Communication Test
```bash
# On Mac, monitor Pi topics
ros2 topic list | grep pi

# On Pi, check Mac topics
ssh pi "ros2 topic list | grep mac"

# Test message passing
ros2 topic pub /test_cross_system std_msgs/msg/String "data: 'Hello Pi'" --once
```

## Performance Optimization

### Resource Monitoring
```bash
# Monitor CPU/Memory usage
htop

# Monitor network traffic
iftop

# Monitor ROS topic frequency
ros2 topic hz /scan

# Monitor ROS topic bandwidth
ros2 topic bw /scan
```

### Parameter Tuning
```bash
# Adjust sensor fusion sensitivity
ros2 param set /sensor_fusion_node min_obstacle_distance 0.4

# Adjust obstacle avoidance response
ros2 param set /obstacle_avoidance_node max_linear_speed 0.3

# Adjust exploration aggressiveness
ros2 param set /frontier_exploration_node exploration_rate 0.7
```

## Best Practices

### 1. Startup Sequence
1. Start base ROVAC system first
2. Wait for sensor topics to appear
3. Start enhanced components
4. Verify all components are running

### 2. Shutdown Sequence
1. Stop enhanced components gracefully
2. Stop base ROVAC system
3. Power down hardware

### 3. Maintenance
1. Regularly check log files
2. Update components as needed
3. Monitor system health metrics

## Emergency Procedures

### Immediate Stop
```bash
# Stop all motion
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{}" --once

# Stop all enhanced components
pkill -f rovac_enhanced

# Emergency system restart
cd ~/robots/rovac
./scripts/standalone_control.sh restart
```

### Component Recovery
```bash
# Restart specific component
ros2 run rovac_enhanced system_health_monitor.py &

# Restart all components
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py
```

## Additional Resources

- Troubleshooting Guide: `ENHANCED_SYSTEM_TROUBLESHOOTING.md`
- Component Documentation: `robot_mcp_server/ENHANCED_SYSTEM_README.md`
- Launch File: `robot_mcp_server/rovac_enhanced_system.launch.py`

For support, consult the troubleshooting guide or contact the development team.