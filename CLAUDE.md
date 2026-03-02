# ROVAC Project Instructions

## Overview

ROVAC is a mobile robot (Yahboom G1 Tank) with a split-brain architecture:
- **Lenovo ThinkCentre M910q (Edge)**: Sensors, motors, MCP server at `192.168.1.218` (hostname: `asimo.io`, user: `asimo`)
- **MacBook Pro (Brain)**: Nav2, SLAM, path planning at `192.168.1.104`

The edge computer was originally a Raspberry Pi 5 — it broke on 2026-03-02 and was replaced by the Lenovo (i7-7700T, 24GB RAM, NVMe SSD, Ubuntu 24.04).

Communication via ROS2 Jazzy over CycloneDDS (unicast, `ROS_DOMAIN_ID=42`).

Both machines clone the same monorepo: `github.com/mohammednazmy/rovac`
- **Mac path**: `~/robots/rovac/`
- **Lenovo path**: `/home/asimo/robots/rovac/`

## Quick Reference

| Resource | Value |
|----------|-------|
| GitHub Repo | `git@github.com:mohammednazmy/rovac.git` |
| Edge SSH | `ssh asimo@192.168.1.218` |
| Edge MCP Server | `http://192.168.1.218:8000` |
| Foxglove | `ws://localhost:8765` |
| ROS_DOMAIN_ID | 42 |
| DDS | CycloneDDS (unicast) |
| Shared Folder | `~/robots/rovac/shared/` (Syncthing, Mac ↔ Lenovo) |

## Quick Start Commands

```bash
# First-time setup (Lenovo edge)
ssh asimo@192.168.1.218
cd ~
mkdir -p robots && cd robots
git clone git@github.com:mohammednazmy/rovac.git
cd rovac
# Install systemd services (adapts unit files for Lenovo user/paths)
./scripts/install_lenovo_systemd.sh install

# First-time setup (Mac)
cd ~/robots/rovac
./scripts/install_mac_autostart.sh install   # macOS launchd: joy_node + joy_mapper (DISABLED as of 2026-03-01)

# Daily bringup (Mac)
source config/ros2_env.sh
./scripts/standalone_control.sh start        # controllers + Lenovo edge (via systemd)

# Optional: start SLAM mapping / Nav2 / Foxglove (Mac)
./scripts/mac_brain_launch.sh slam

./scripts/mac_brain_launch.sh nav ~/maps/house.yaml

./scripts/mac_brain_launch.sh foxglove

# Edge status (Lenovo)
ssh asimo@192.168.1.218 'sudo systemctl status rovac-edge.target'
```

## Key ROS2 Topics

### From Edge (Sensors)
| Topic | Type | Description |
|-------|------|-------------|
| `/scan` | LaserScan | XV11 LIDAR (360 ranges, ~5.0 Hz, ~230 valid pts at 300 RPM) |
| `/sensors/ultrasonic/range` | Range | HC-SR04 distance |
| `/odom` | Odometry | Dead-reckoning from encoder ticks + commanded speeds (20 Hz) |
| `/phone/camera/image_raw` | Image | Phone camera (640x480 BGR8) |
| `/cmd_vel_joy` | Twist | PS2 joystick velocity commands |

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
| Motor + Encoder | ESP32-S3 + Yahboom AT8236 2-Channel H-bridge. Single USB-serial at `/dev/esp32_motor` (115200 baud). Motor: `M <left> <right>` (-255 to 255). Encoder: ESP32 PCNT hardware, `E <left> <right>` at 50Hz streaming. Firmware: `hardware/ESP32-S3-WROOM/examples/10_at8236_motor_control/`. Driver: `hardware/esp32_at8236_driver/esp32_at8236_driver.py` |
| Motor Driver (legacy) | Yahboom BST-4WD V4.5 (TB6612FNG GPIO HAT) — replaced by ESP32+AT8236. Driver kept at `hardware/yahboom-bst-4wd-expansion-board/` |
| Encoder Bridge (legacy) | Arduino Nano V3.0 at `/dev/encoder_bridge` — replaced by ESP32 PCNT. Firmware kept at `hardware/nano_encoder_bridge/` |
| Computer | Lenovo ThinkCentre M910q (i7-7700T, 24GB RAM, NVMe SSD), Ubuntu 24.04, hostname `asimo.io`, user `asimo`. Replaced broken Pi 5 on 2026-03-02. |
| Motors | 2x JGB37-520R60-12 (12V DC gear motors with Hall quadrature encoders, tank config) |
| LIDAR | XV11 (Neato) via ESP32 bridge, USB `/dev/esp32_lidar` (CP2102, 115200 baud) |
| Camera | Samsung Galaxy A16 via ADB + scrcpy |
| Ultrasonic | 4x HC-SR04 (Super Sensor module, Arduino Nano) |
| Stereo Cameras | 2x USB cameras (102.67mm baseline, StereoSGBM depth) |
| Webcam | NexiGo N930E USB `/dev/webcam` |
| Power Input | 6-12V DC. **Motor power switch must be ON for motors.** |

## Project Structure

Both Mac and Lenovo clone the same repo to `~/robots/rovac/`. The tree below shows the full monorepo layout.

```
~/robots/rovac/                         # Git root (github.com/mohammednazmy/rovac)
├── scripts/
│   ├── standalone_control.sh           # Main bringup (Pi edge + controllers)
│   ├── install_mac_autostart.sh        # macOS launchd controller autostart
│   ├── rovac_controller_supervisor.sh  # (launchd) keeps joy stack alive
│   ├── install_pi_systemd.sh           # Pi systemd edge autostart (legacy)
│   ├── install_lenovo_systemd.sh       # Lenovo systemd edge autostart (active)
│   ├── mac_brain_launch.sh             # Mac Nav2/SLAM launcher
│   ├── joy_mapper_node.py              # Nintendo Pro Controller -> topics
│   ├── ps2_joy_mapper_node.py          # PS2 controller -> /cmd_vel_joy
│   ├── deploy_core_pi.sh              # Deploy core files to edge
│   ├── map_house.sh                   # House mapping automation
│   └── edge/                          # Edge-side launch helpers
│       ├── launch_tf_publisher.sh
│       ├── launch_map_odom_tf.sh
│       └── launch_odom_static.sh
├── config/
│   ├── ros2_env.sh             # ROS2 environment setup
│   ├── cyclonedds_mac.xml      # Mac DDS config
│   ├── cyclonedds_pi.xml       # Pi DDS config (legacy)
│   ├── cyclonedds_lenovo.xml   # Lenovo DDS config (active)
│   ├── slam_params.yaml        # SLAM toolbox config
│   ├── nav2_params.yaml        # Navigation2 config
│   └── systemd/                # Edge unit files (deployed via install_lenovo_systemd.sh)
│       ├── rovac-edge.target
│       ├── rovac-edge-esp32.service
│       ├── rovac-edge-bst4wd.service       # Legacy (kept for reference)
│       ├── rovac-edge-hiwonder.service     # Legacy (kept for reference)
│       ├── rovac-edge-tf.service
│       ├── rovac-edge-map-tf.service
│       ├── rovac-edge-mux.service
│       ├── rovac-edge-supersensor.service
│       ├── rovac-edge-lidar.service
│       ├── rovac-edge-obstacle.service
│       ├── rovac-edge-stereo.target
│       ├── rovac-edge-stereo-depth.service
│       ├── rovac-edge-stereo-obstacle.service
│       ├── rovac-edge-webcam.service
│       ├── rovac-edge-phone-sensors.service
│       ├── rovac-camera.service
│       └── rovac-phone-cameras.service
├── hardware/
│   ├── esp32_at8236_driver/              # Motor + encoder driver (active) — ESP32-S3 + AT8236
│   ├── yahboom-bst-4wd-expansion-board/ # Legacy motor driver — BST-4WD V4.5 TB6612FNG
│   ├── nano_encoder_bridge/             # Legacy encoder bridge — Arduino Nano
│   ├── hiwonder-ros-controller/         # Legacy motor/IMU board (replaced by BST-4WD)
│   ├── yahboom-ros-expansion-board-v3/  # Legacy motor/IMU board (replaced)
│   ├── esp32_xv11_bridge/               # ESP32 LIDAR bridge firmware + docs
│   ├── super_sensor/                    # Edge-side ROS2 nodes (supersensor, obstacle)
│   ├── health_monitor/                  # Edge health monitor node
│   ├── stereo_cameras/                  # Stereo camera calibration + depth
│   ├── lidar_usb/                       # XV-11 LIDAR docs
│   ├── phone_sensors/                   # Phone IMU/GPS integration
│   ├── phone_cameras/                   # Phone camera streaming
│   ├── webcam/                          # USB webcam
│   └── README.md                        # Hardware overview
├── ros2_ws/
│   └── src/
│       ├── tank_description/            # URDF / robot description
│       ├── xv11_lidar_python/           # XV11 LIDAR ROS2 driver
│       ├── rf2o_laser_odometry/         # Laser-based odometry
│       └── vorwerk_lidar/               # Vorwerk LIDAR driver
├── super_sensor/                        # Super Sensor desktop app + firmware
├── robot_mcp_server/
│   ├── mcp_server.py           # 35+ tool MCP server
│   └── phone_integration/      # Camera integration
├── lidar_nano_usb/             # Arduino Nano LIDAR USB bridge
├── arduino_lidar_bridge/       # Arduino LIDAR bridge sketch
├── tools/                      # Calibration, diagnostics, testing utilities
├── maps/                       # Saved SLAM maps
├── shared/                     # Syncthing-synced folder (Mac ↔ Lenovo, gitignored)
├── foxglove_layouts/           # Foxglove Studio layout configs
├── archive/                    # Legacy/deprecated code
└── docs/
    ├── architecture/
    │   └── ARCHITECTURE_VERIFIED.md
    ├── guides/
    │   └── bringup.md
    └── troubleshooting/
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

### Can't connect to edge
```bash
ping 192.168.1.218
ssh asimo@192.168.1.218
```

### LIDAR not working
```bash
# On Lenovo, check ESP32 LIDAR bridge serial port
ssh asimo@192.168.1.218 'ls -la /dev/esp32_lidar'
ssh asimo@192.168.1.218 'sudo systemctl status rovac-edge-lidar.service'
ssh asimo@192.168.1.218 'sudo systemctl restart rovac-edge-lidar.service'
```

### PS2 controller not working
```bash
# Check USB receiver is plugged in
ssh asimo@192.168.1.218 'lsusb | grep 2563:0575'
# Check input device exists and is readable
ssh asimo@192.168.1.218 'ls -la /dev/input/js0'
# Check services
ssh asimo@192.168.1.218 'systemctl is-active rovac-edge-ps2-joy rovac-edge-ps2-mapper'
# Check /joy topic is publishing
ssh asimo@192.168.1.218 'source /opt/ros/jazzy/setup.bash && source ~/robots/rovac/config/ros2_env.sh && timeout 3 ros2 topic hz /joy --no-daemon 2>&1 | tail -1'
```

### Known PS2 wireless issue — motor spurts
The ShanWan ZD-V+ USB receiver drops signal intermittently (~5% of messages), causing brief zero-axis reports mid-drive. A 200ms dropout hold filter exists in `ps2_joy_mapper_node.py` but may need further tuning. See MEMORY.md for full debug history.
