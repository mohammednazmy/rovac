# ROVAC Enhanced System Components

This document describes the enhanced components added to the ROVAC robot system for improved functionality, reliability, and autonomy.

## New Components

### 1. System Health Monitor (`system_health_monitor.py`)
- Monitors CPU, memory, network connectivity, and ROS node status
- Automatically attempts recovery for failed components
- Publishes diagnostic information to `/diagnostics` topic
- Tracks overall system health status

### 2. Sensor Fusion Node (`sensor_fusion_node.py`)
- Combines LIDAR and ultrasonic sensor data for enhanced obstacle detection
- Integrates IMU data with odometry for improved positioning
- Applies temporal filtering to sensor readings
- Publishes fused data to `/sensors/fused_scan` and `/odom/fused`

### 3. Obstacle Avoidance Node (`obstacle_avoidance_node.py`)
- Implements reactive obstacle avoidance using fused sensor data
- Detects obstacles in multiple sectors (front, front-left, front-right, left, right)
- Calculates safe velocity commands to avoid collisions
- Publishes avoidance commands to `/cmd_vel_avoidance`

### 4. Frontier Exploration Node (`frontier_exploration_node.py`)
- Implements autonomous exploration for SLAM map building
- Finds frontiers (unknown-free boundaries) in occupancy grids
- Selects optimal frontiers to explore based on information gain and distance
- Sends navigation goals to explore unknown areas

### 5. Diagnostics Collector (`diagnostics_collector.py`)
- Collects system logs, ROS logs, and performance metrics
- Stores diagnostic reports in JSON format
- Monitors system resources continuously
- Cleans up old log files to prevent disk space issues

### 6. Enhanced Joy Mapper (`joy_mapper_enhanced.py`)
- Improved error handling and controller disconnection detection
- Automatic stop command when controller disconnects
- Better logging and status reporting
- Controller connection status publishing

## Installation

Run the installation script:
```bash
cd ~/robots/rovac
./scripts/install_enhanced_system.sh
```

## Usage

### Running Individual Components
Each component can be run separately:
```bash
# System Health Monitor
ros2 run rovac_enhanced system_health_monitor.py

# Sensor Fusion
ros2 run rovac_enhanced sensor_fusion_node.py

# Obstacle Avoidance
ros2 run rovac_enhanced obstacle_avoidance_node.py

# Frontier Exploration
ros2 run rovac_enhanced frontier_exploration_node.py --ros-args -p enable_exploration:=true

# Diagnostics Collector
ros2 run rovac_enhanced diagnostics_collector.py
```

### Running All Components
Use the launch script:
```bash
cd ~/robots/rovac
./scripts/run_enhanced_system.sh
```

### Launch File Usage
```bash
ros2 launch rovac_enhanced rovac_enhanced_system.launch.py
```

## Configuration Parameters

### System Health Monitor
- No configurable parameters

### Sensor Fusion Node
- `min_obstacle_distance`: Minimum distance for obstacle detection (default: 0.3)
- `fusion_enabled`: Enable/disable sensor fusion (default: True)

### Obstacle Avoidance Node
- `min_distance`: Minimum safe distance to obstacles (default: 0.4)
- `max_linear_speed`: Maximum forward speed (default: 0.3)
- `max_angular_speed`: Maximum turning speed (default: 1.0)
- `enable_avoidance`: Enable/disable obstacle avoidance (default: True)

### Frontier Exploration Node
- `exploration_rate`: Time between exploration updates (default: 0.5)
- `frontier_min_size`: Minimum frontier size to consider (default: 5)
- `goal_distance_threshold`: Distance threshold to reach goals (default: 0.5)
- `enable_exploration`: Enable/disable frontier exploration (default: False)

### Diagnostics Collector
- `log_directory`: Directory to store diagnostic logs (default: /tmp/rovac_logs)
- `collection_interval`: Time between diagnostic collections (default: 30.0)
- `max_log_files`: Maximum number of log files to keep (default: 10)

## Topics

### Published
- `/diagnostics`: DiagnosticArray - System diagnostic information
- `/system/health_status`: String - JSON-formatted health status
- `/sensors/fused_scan`: LaserScan - Fused LIDAR/ultrasonic data
- `/odom/fused`: Odometry - Fused odometry with IMU integration
- `/sensors/obstacle_alert`: Twist - Emergency obstacle avoidance commands
- `/cmd_vel_avoidance`: Twist - Obstacle avoidance velocity commands
- `/system/avoidance_active`: Bool - Obstacle avoidance status
- `/system/exploration_active`: Bool - Frontier exploration status
- `/system/controller_connected`: Bool - Controller connection status

### Subscribed
- `/scan`: LaserScan - LIDAR data
- `/sensors/ultrasonic/range`: Range - Ultrasonic sensor data
- `/sensors/imu`: Imu - IMU data
- `/odom`: Odometry - Odometry data
- `/map`: OccupancyGrid - Map data for exploration
- `/tank/joy`: Joy - Joystick input data

## Services
- No new services implemented

## Actions
- No new actions implemented

## Logging
Diagnostic logs are stored in `/tmp/rovac_logs/` by default. Each log file contains:
- System information (CPU, memory, disk usage)
- Process information (ROS-related processes)
- Network information
- Recent diagnostic messages
- System metrics
- ROS topic/node/service information

## Recovery Mechanisms
The system health monitor implements automatic recovery for:
- Network connectivity issues
- Failed ROS nodes
- LIDAR service interruptions

Recovery attempts are limited to prevent infinite retry loops.