# ROVAC Project Instructions

## CRITICAL: Use ONLY the information in this file. DO NOT make up commands, file paths, or topics that are not explicitly listed here. If you're unsure, say "I don't have that information" rather than guessing.

## Overview

ROVAC is a Raspberry Pi 5-based mobile robot (Yahboom G1 Tank) with a split-brain architecture:
- **Pi 5 (Edge)**: Sensors, motors, MCP server at `192.168.1.200` (hostname: `rovac-pi`, user: `pi`)
- **MacBook Pro (Brain)**: Nav2, SLAM, path planning at `192.168.1.104`

**Monorepo**: `github.com/mohammednazmy/rovac` (private). Both Mac and Pi code live in one repo, cloned to:
- **Mac**: `~/robots/rovac/`
- **Pi**: `/home/pi/robots/rovac/`

Communication via **ROS2 Jazzy** (NOT ROS1) over CycloneDDS (unicast, `ROS_DOMAIN_ID=42`).

## IMPORTANT: This is ROS2, NOT ROS1
- Use `ros2` commands, NOT `roslaunch`, `roscore`, `rostopic`
- There is NO `roslaunch` - use scripts in `~/robots/rovac/scripts/`
- All commands run from Mac at `~/robots/rovac/`

## Git Workflow (REQUIRED for all agents)

```bash
# BEFORE starting any work — always pull latest
cd ~/robots/rovac
git pull origin main

# AFTER completing work — commit and push
git add <changed-files>
git commit -m "descriptive message"
git push origin main

# On Pi — pull to deploy changes
ssh pi 'cd /home/pi/robots/rovac && git pull origin main'
```

**Rules:**
- Always `git pull` before making changes to avoid conflicts
- Always `git push` after completing work so Pi can pull
- Use specific file paths in `git add` — never `git add .` or `git add -A`
- Pi edge code lives in `hardware/`, `config/systemd/`, `scripts/edge/`, `super_sensor/`, `robot_mcp_server/`
- Mac brain code lives in `scripts/`, `config/`, `ros2_ws/`

## Quick Reference

| Resource | Value |
|----------|-------|
| Git Repo | `github.com/mohammednazmy/rovac` (private) |
| Mac Path | `~/robots/rovac/` |
| Pi Path | `/home/pi/robots/rovac/` |
| Pi SSH | `ssh pi` (alias for `pi@192.168.1.200`) |
| Pi MCP Server | `http://192.168.1.200:8000` |
| Foxglove | `ws://localhost:8765` |
| ROS_DOMAIN_ID | 42 |
| DDS | CycloneDDS (unicast) |

## Quick Start Commands (ALL RUN FROM MAC)

```bash
# Setup (one-time)
cd ~/robots/rovac
./scripts/install_mac_autostart.sh install   # macOS launchd: joy_node + joy_mapper
./scripts/install_pi_systemd.sh install      # Pi systemd: motors + sensors + mux + lidar

# Daily bringup (from Mac ~/robots/rovac)
source config/ros2_env.sh
./scripts/standalone_control.sh start

# SLAM / Navigation / Visualization (from Mac)
./scripts/mac_brain_launch.sh slam
./scripts/mac_brain_launch.sh nav ~/maps/house.yaml
./scripts/mac_brain_launch.sh foxglove

# Check Pi edge status
ssh pi 'sudo systemctl status rovac-edge.target'
```

## Available Scripts (~/robots/rovac/scripts/)

- `standalone_control.sh` - Main bringup (Pi edge + controllers)
- `install_mac_autostart.sh` - macOS launchd controller autostart
- `rovac_controller_supervisor.sh` - (launchd) keeps joy stack alive
- `install_pi_systemd.sh` - Pi systemd edge autostart
- `mac_brain_launch.sh` - Mac Nav2/SLAM/Foxglove launcher
- `joy_mapper_node.py` - Nintendo Pro Controller -> topics

## Key ROS2 Topics

### From Pi (Sensors)
| Topic | Type | Description |
|-------|------|-------------|
| `/scan` | LaserScan | XV11 LIDAR (360 ranges, ~2.8 Hz) |
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
| Motor/IMU Board | Hiwonder ROS Robot Controller V1.2 (STM32F407VET6, USB serial `/dev/hiwonder_board`, CH9102, baud 1000000) |
| Computer | Raspberry Pi 5 (8GB), Ubuntu 24.04, hostname `rovac-pi` |
| Motors | 4x 520 DC Gear Motors with Hall Encoders (12V) |
| IMU | QMI8658 6-axis (accel + gyro only, NO magnetometer) on Hiwonder board |
| LIDAR | XV11 (Neato) via ESP32 bridge, USB `/dev/esp32_lidar` (currently disconnected) |
| Camera | Samsung Galaxy A16 via ADB + scrcpy |
| Ultrasonic | 4x HC-SR04 (Super Sensor module, Arduino Nano) |
| Webcam | NexiGo N930E USB `/dev/webcam` |
| Power Input | 6-12V DC (board supplies 5V/5A to Pi via USB-C) |

## Project Structure (Monorepo)

Both Mac and Pi share the same repo. On Pi it is cloned to `/home/pi/robots/rovac/`.

```
~/robots/rovac/                         # github.com/mohammednazmy/rovac
├── scripts/
│   ├── standalone_control.sh           # Main bringup (Pi edge + controllers)
│   ├── install_mac_autostart.sh        # macOS launchd controller autostart
│   ├── install_pi_systemd.sh           # Pi systemd edge autostart
│   ├── mac_brain_launch.sh             # Mac Nav2/SLAM/Foxglove launcher
│   ├── joy_mapper_node.py              # Nintendo Pro Controller -> topics
│   └── edge/                           # Pi-side edge launch scripts
├── config/
│   ├── ros2_env.sh                     # ROS2 environment setup
│   ├── cyclonedds_mac.xml              # Mac DDS config
│   ├── cyclonedds_pi.xml               # Pi DDS config
│   ├── systemd/                        # Pi unit files (rovac-edge.*)
│   ├── slam_params.yaml                # SLAM toolbox config
│   └── nav2_params.yaml                # Navigation2 config
├── hardware/
│   ├── hiwonder-ros-controller/        # Motor/IMU board driver (Pi)
│   ├── stereo_cameras/                 # Stereo vision (Pi)
│   ├── phone_cameras/                  # Phone camera streaming (Pi)
│   ├── phone_sensors/                  # Phone IMU/GPS (Pi)
│   └── ...                             # Other hardware modules
├── robot_mcp_server/
│   └── mcp_server.py                   # 35+ tool MCP server (Pi)
├── super_sensor/                       # Arduino Nano HC-SR04 firmware + ROS2 node
├── ros2_ws/                            # ROS2 workspace (build artifacts gitignored)
├── maps/                               # Saved maps (generated files gitignored)
├── docs/
│   └── ARCHITECTURE_VERIFIED.md
└── archive/                            # Legacy/experimental code
```

## Environment Setup

```bash
# Mac: Activate conda environment
conda activate ros_jazzy

# IMPORTANT: Use --no-daemon on macOS — the ROS2 daemon hangs with CycloneDDS
# Verify ROS2 topics (wait 3s for DDS discovery)
ros2 topic list --no-daemon

# Check node connectivity
ros2 node list --no-daemon
```

## Troubleshooting

### No topics visible
1. Check `ROS_DOMAIN_ID=42` is set
2. Verify CycloneDDS config: `echo $CYCLONEDDS_URI`
3. Verify Mac IP `192.168.1.104` on `en0`
4. Wait 3-5 seconds for DDS discovery

### Can't connect to Pi
```bash
ping 192.168.1.200
ssh pi
```

### LIDAR not working
```bash
# On Pi, check serial port
ssh pi 'ls -la /dev/esp32_lidar'
ssh pi 'sudo systemctl status rovac-edge-lidar.service'
ssh pi 'sudo systemctl restart rovac-edge-lidar.service'
```

## OpenCode Agents

### Primary Agents (Tab to switch)

| Agent | Description |
|-------|-------------|
| rovac | ROVAC robot project specialist with full ROS2 context |
| web | Web dashboard development specialist for Flask/FastAPI |

### Subagents (invoke with @agent-name)

#### Robot Development
| Subagent | Use For |
|----------|---------|
| @nav2 | Navigation2, path planning, costmaps |
| @slam | SLAM toolbox, mapping, localization |
| @tf | Transform tree, coordinate frames |
| @motors | Hiwonder ROS Controller V1.2 motor/IMU |
| @lidar | XV11 LIDAR via ESP32 bridge |
| @imu | QMI8658 6-axis IMU (accel + gyro, no magnetometer) |
| @pi-ssh | Remote SSH operations on Pi |

#### Web Development
| Subagent | Use For |
|----------|---------|
| @frontend | HTML/CSS/JS, UI components, styling |
| @backend | Flask routes, FastAPI endpoints |
| @playwright | E2E testing, browser automation |
| @ux | Usability, accessibility (a11y) |
| @api-design | REST API design, documentation |

## OpenCode Commands

### Robot Commands
| Command | Description |
|---------|-------------|
| /start | Start full robot system |
| /stop | Stop robot system |
| /slam | Start SLAM mapping |
| /nav | Start navigation with map |
| /check | Full system health check |
| /drive | Send drive commands |

### Web Development Commands
| Command | Description |
|---------|-------------|
| /dev-server | Start Flask + MCP servers |
| /test-web | Run Playwright E2E tests |
| /validate-ui | Check accessibility and usability |
| /api-docs | View API documentation |
| /web-component | Create new UI component |
