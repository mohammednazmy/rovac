# ROVAC Project Instructions

## Overview

ROVAC is a Raspberry Pi 5-based mobile robot (Yahboom G1 Tank) with a split-brain architecture:
- **Pi 5 (Edge)**: Sensors, motors, MCP server at `192.168.1.200` (hostname: `rovac-pi`, user: `pi`)
- **MacBook Pro (Brain)**: Nav2, SLAM, path planning at `192.168.1.104`

Communication via ROS2 Jazzy over CycloneDDS (unicast, `ROS_DOMAIN_ID=42`).

## Quick Reference

| Resource | Value |
|----------|-------|
| Pi SSH | `ssh pi` (alias for `pi@192.168.1.200`) |
| Pi MCP Server | `http://192.168.1.200:8000` |
| Foxglove | `ws://localhost:8765` |
| ROS_DOMAIN_ID | 42 |
| DDS | CycloneDDS (unicast) |

## Quick Start Commands

```bash
# One-time persistence setup (recommended)
cd ~/robots/rovac
./scripts/install_mac_autostart.sh install   # macOS launchd: joy_node + joy_mapper
./scripts/install_pi_systemd.sh install      # Pi systemd: motors + sensors + mux + lidar

# Daily bringup (Mac)
source config/ros2_env.sh
./scripts/standalone_control.sh start        # controllers + Pi edge (via systemd)

# Optional: start SLAM mapping / Nav2 / Foxglove (Mac)
./scripts/mac_brain_launch.sh slam

./scripts/mac_brain_launch.sh nav ~/maps/house.yaml

./scripts/mac_brain_launch.sh foxglove

# Pi edge status (Pi)
ssh pi 'sudo systemctl status rovac-edge.target'
```

## Key ROS2 Topics

### From Pi (Sensors)
| Topic | Type | Description |
|-------|------|-------------|
| `/scan` | LaserScan | XV11 LIDAR (360 ranges, ~2.8 Hz) — currently disconnected |
| `/sensors/ultrasonic/range` | Range | HC-SR04 distance |
| `/imu/data` | Imu | QMI8658 IMU (accel + gyro, 6-axis, ~72 Hz) — no magnetometer |
| `/odom` | Odometry | Dead-reckoning from commanded speeds + IMU gyro Z (20 Hz) |
| `/battery_voltage` | Float32 | Battery voltage (V) |
| `/diagnostics` | DiagnosticArray | Board health diagnostics (1 Hz) |
| `/phone/camera/image_raw` | Image | Phone camera (640x480 BGR8) |
| `/cmd_vel_joy` | Twist | Joystick velocity commands |

### From Mac (Navigation)
| Topic | Type | Description |
|-------|------|-------------|
| `/map` | OccupancyGrid | SLAM-generated map |
| `/cmd_vel` | Twist | Motor commands to robot |
| `/plan` | Path | Navigation path |

## MCP Server Tools (35+)

### Movement
`move_forward`, `move_backward`, `turn_left`, `turn_right`, `stop`, `turn_around`, `drive_circle`, `drive_square`, `lawn_mower`

### Sensors
`get_distance`, `check_obstacles`, `get_position`, `scan_surroundings`, `get_lidar_summary`, `get_camera_image`

### Camera/Servo
`look_left`, `look_right`, `look_center`, `look_at_angle`, `sweep_scan`

### Navigation
`go_to_position`, `go_to_named_location`, `save_current_location`, `return_home`, `explore_and_map`, `save_map`, `load_map`

## Hardware

| Component | Details |
|-----------|---------|
| Motor/IMU Board | Hiwonder ROS Robot Controller V1.2 (STM32F407VET6, USB serial `/dev/hiwonder_board`, CH9102 `1a86:55d4`, baud 1000000) |
| Computer | Raspberry Pi 5 (8GB), Ubuntu 24.04, hostname `rovac-pi` |
| Motors | 4x 520 DC Gear Motors with Hall Encoders (12V) — 2 active (M1 left, M2 right, tank config) |
| IMU | QMI8658 6-axis (accel + gyro only, NO magnetometer) on Hiwonder board |
| LIDAR | XV11 (Neato) via ESP32 bridge, USB `/dev/esp32_lidar` (currently disconnected) |
| Camera | Samsung Galaxy A16 via ADB + scrcpy |
| Ultrasonic | 4x HC-SR04 (Super Sensor module, Arduino Nano) |
| Stereo Cameras | 2x USB cameras (102.67mm baseline, StereoSGBM depth) |
| Webcam | NexiGo N930E USB `/dev/webcam` |
| Power Input | 6-12V DC (board supplies 5V/5A to Pi via USB-C). **Motor power switch must be ON for motors.** |

## Project Structure

```
~/robots/rovac/
├── scripts/
│   ├── standalone_control.sh           # Main bringup (Pi edge + controllers)
│   ├── install_mac_autostart.sh        # macOS launchd controller autostart
│   ├── rovac_controller_supervisor.sh  # (launchd) keeps joy stack alive
│   ├── install_pi_systemd.sh           # Pi systemd edge autostart
│   ├── mac_brain_launch.sh             # Mac Nav2/SLAM launcher
│   └── joy_mapper_node.py              # Nintendo Pro Controller -> topics
├── config/
│   ├── ros2_env.sh             # ROS2 environment setup
│   ├── cyclonedds_mac.xml      # Mac DDS config
│   ├── cyclonedds_pi.xml       # Pi DDS config
│   └── systemd/                # Pi unit files (rovac-edge.*)
│   ├── slam_params.yaml        # SLAM toolbox config
│   └── nav2_params.yaml        # Navigation2 config
├── hardware/
│   ├── hiwonder-ros-controller/         # Motor/IMU board (active) — Hiwonder V1.2
│   ├── yahboom-ros-expansion-board-v3/  # Old motor/IMU board (replaced by Hiwonder)
│   ├── lidar_usb/                       # XV-11 LIDAR docs
│   ├── phone_sensors/                   # Phone IMU/GPS integration
│   ├── phone_cameras/                   # Phone camera streaming
│   ├── webcam/                          # USB webcam
│   └── README.md                        # Hardware overview
├── robot_mcp_server/
│   ├── mcp_server.py           # 35+ tool MCP server
│   └── phone_integration/      # Camera integration
└── docs/
    └── ARCHITECTURE_VERIFIED.md
```

## Environment Setup

```bash
# Mac: Activate conda environment
conda activate ros_jazzy

# Source ROS2 environment (sets DDS config, domain ID, peer IPs)
source ~/robots/rovac/config/ros2_env.sh

# Verify ROS2 topics (wait 3-5s for DDS discovery)
# IMPORTANT: Use --no-daemon on macOS — the ROS2 daemon hangs with CycloneDDS
ros2 topic list --no-daemon

# Check node connectivity
ros2 node list --no-daemon
```

## Troubleshooting

### No topics visible
1. Check `ROS_DOMAIN_ID=42` is set
2. Verify CycloneDDS config: `echo $CYCLONEDDS_URI`
3. Wait 3-5 seconds for DDS discovery

### Can't connect to Pi
```bash
ping 192.168.1.200
ssh pi    # alias configured in ~/.ssh/config (pi@192.168.1.200)
```

### LIDAR not working
```bash
# On Pi, check ESP32 LIDAR bridge serial port
ssh pi 'ls -la /dev/esp32_lidar'
ssh pi 'sudo systemctl status rovac-edge-lidar.service'
ssh pi 'sudo systemctl restart rovac-edge-lidar.service'
```
