# ROVAC

**ROVAC** is a Raspberry Pi 5-based mobile robot platform with a split-brain architecture. The Pi handles real-time sensor/motor operations (Edge) while a MacBook Pro runs navigation and planning (Brain). An Android phone provides additional sensors including GPS for outdoor navigation.

## System Overview

| Component | Device | Role |
|-----------|--------|------|
| **Edge** | Raspberry Pi 5 | Motors, sensors, MCP server |
| **Brain** | MacBook Pro | Nav2, SLAM, path planning |
| **Phone** | Samsung Galaxy A16 | GPS, IMU, camera, magnetometer |
| **Network** | 192.168.1.x | Home network (WiFi/Ethernet, ROS_DOMAIN_ID=42) |

## Architecture

```
┌─────────────────────────────────┐                          ┌─────────────────────────────────┐
│      Samsung Galaxy A16         │         USB              │           MacBook Pro           │
│      (Phone Sensors)            │◄────────────────────────►│  (Brain - 192.168.1.104)        │
├─────────────────────────────────┤                          ├─────────────────────────────────┤
│ • GPS/GNSS (outdoor nav)        │                          │ • Nav2 stack                    │
│ • Accelerometer + Gyroscope     │                          │ • SLAM toolbox                  │
│ • Magnetometer (compass)        │                          │ • Foxglove bridge               │
│ • 4x Cameras (back/front/wide)  │                          │ • Path planning                 │
│ • SensorServer app (WebSocket)  │                          │ • Joystick controller           │
└────────────┬────────────────────┘                          └─────────────────────────────────┘
             │ USB                                                         ▲
             ▼                                                             │
┌─────────────────────────────────┐     Home Network (192.168.1.x)        │
│         Raspberry Pi 5          │◄───────────────────────────────────────┘
│  (Edge - 192.168.1.200)         │         ROS2 Jazzy / CycloneDDS
├─────────────────────────────────┤
│ • Hiwonder ROS Controller V1.2   │
│   - Motor control (2x DC tank)  │
│   - QMI8658 IMU (6-axis)        │
│   - Dead-reckoning odometry     │
│ • XV-11 LIDAR (360°)            │
│ • Super Sensor (4x ultrasonic)  │
│ • Phone sensor bridge           │
│ • MCP server (35+ tools)        │
└─────────────────────────────────┘
```

## Repository Structure

This is a **monorepo** — both the Pi edge code and the Mac brain code live in one repository. Both machines clone the same repo to `~/robots/rovac/` and stay in sync via `git push` / `git pull`.

## Quick Start

### Prerequisites
- Raspberry Pi 5 with Ubuntu 24.04 + ROS2 Jazzy
- MacBook with ROS2 Jazzy (via conda: `ros_jazzy`)
- Both Pi and Mac on same network (192.168.1.x)
- Android phone with SensorServer app (for GPS/phone sensors)

### Clone the Repo

```bash
# Mac
git clone git@github.com:mohammednazmy/rovac.git ~/robots/rovac

# Pi (SSH in first)
ssh pi
git clone git@github.com:mohammednazmy/rovac.git ~/robots/rovac
```

### One-Time Setup

```bash
# Mac - Install autostart for joystick controller
cd ~/robots/rovac
./scripts/install_mac_autostart.sh install

# Pi - Install systemd services
cd ~/robots/rovac
./scripts/install_pi_systemd.sh install
```

### Daily Bringup

```bash
# 1. Power on robot (Pi boots automatically)

# 2. Mac - Source environment and start controllers
cd ~/robots/rovac
source config/ros2_env.sh       # Both machines use the same env script
./scripts/standalone_control.sh start

# 3. Verify topics (wait 3s for DDS discovery)
ros2 topic list --no-daemon
```

### Optional: SLAM / Navigation / Visualization

```bash
# Start SLAM for mapping
./scripts/mac_brain_launch.sh slam

# Start navigation with saved map
./scripts/mac_brain_launch.sh nav ~/maps/house.yaml

# Start Foxglove for visualization
./scripts/mac_brain_launch.sh foxglove
# Then open Foxglove Studio → Connect to ws://localhost:8765
```

## Hardware

### Active Hardware (In Production)

| Component | Device | Topics | Service |
|-----------|--------|--------|---------|
| **Hiwonder ROS Controller V1.2** | `/dev/hiwonder_board` | `/imu/data`, `/odom`, `/cmd_vel`, `/battery_voltage`, `/diagnostics` | `rovac-edge-hiwonder` |
| **XV-11 LIDAR** | `/dev/esp32_lidar` | `/scan` | `rovac-edge-lidar` (currently disconnected) |
| **Super Sensor** | `/dev/super_sensor` | `/super_sensor/*` | `rovac-edge-supersensor` |
| **Stereo Cameras** | `/dev/video0`, `/dev/video1` | `/stereo/depth/image_raw`, `/obstacles` | `rovac-edge-stereo.target` |
| **Phone Sensors** | USB (ADB) | `/phone/imu`, `/phone/gps/fix` | `rovac-edge-phone-sensors` |
| **Phone Camera** | USB (scrcpy) | `/phone/camera/back/image_raw` | `rovac-phone-cameras` |

### Specifications

| Component | Details |
|-----------|---------|
| **Motor Controller** | Hiwonder ROS Robot Controller V1.2 (STM32F407VET6, 168 MHz Cortex-M4) |
| **Board IMU** | QMI8658 6-axis (accel + gyro only, NO magnetometer) |
| **USB Serial** | CH9102 (`1a86:55d4`) at `/dev/hiwonder_board`, baud 1,000,000 |
| **LIDAR** | Neato XV-11 (360°, 0.06-5m range, ~5-10 Hz) — currently disconnected |
| **Ultrasonic** | 4x HC-SR04 via Arduino Nano |
| **Stereo Cameras** | 2x USB cameras, 102.67mm baseline, StereoSGBM depth |
| **Computer** | Raspberry Pi 5 (8GB) |
| **Base** | Yahboom G1 Tank chassis |
| **Phone** | Samsung Galaxy A16 (SM-A166M, Android 15) |
| **Phone GPS** | GNSS (SPOTNAV) - 1 Hz outdoor positioning |
| **Phone IMU** | LSM6DSOTR (500 Hz accel/gyro) + MXG4300S magnetometer |
| **Phone Cameras** | 4 cameras (back, front, wide, front2) |

See [hardware/README.md](hardware/README.md) for detailed specifications.

## ROS2 Topics

### Robot Sensors (From Hiwonder Board)

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/imu/data` | Imu | ~72 Hz | QMI8658 accel + gyro (6-axis, no orientation/magnetometer) |
| `/odom` | Odometry | 20 Hz | Dead-reckoning from commanded speeds + IMU gyro Z |
| `/battery_voltage` | Float32 | 1 Hz | Battery voltage |
| `/diagnostics` | DiagnosticArray | 1 Hz | Board health diagnostics |
| `/scan` | LaserScan | ~5-10 Hz | 360° LIDAR scan (currently disconnected) |
| `/super_sensor/range/*` | Range | ~10 Hz | 4x ultrasonic distances |
| `/stereo/depth/image_raw` | Image | ~2-3 Hz | Stereo depth image |
| `/obstacles` | MarkerArray | ~2-3 Hz | Detected obstacles from stereo depth |
| `/cmd_vel_obstacle` | Twist | on event | Emergency stop from obstacle detector |

### Phone Sensors

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/phone/imu` | Imu | ~45 Hz | Phone accelerometer + gyroscope |
| `/phone/magnetic_field` | MagneticField | ~6 Hz | Phone magnetometer (compass) |
| `/phone/gps/fix` | NavSatFix | 1 Hz | GPS location (lat/lon/alt) |
| `/phone/orientation` | Vector3Stamped | ~45 Hz | Phone orientation (roll/pitch/yaw) |
| `/phone/camera/back/image_raw` | Image | ~12 Hz | Phone back camera |
| `/phone/camera/back/image_raw/compressed` | CompressedImage | ~12 Hz | Compressed camera stream |

### From Mac (Brain)

| Topic | Type | Description |
|-------|------|-------------|
| `/cmd_vel` | Twist | Velocity commands to robot |
| `/cmd_vel_joy` | Twist | Joystick velocity commands |
| `/map` | OccupancyGrid | SLAM-generated map |
| `/plan` | Path | Navigation path |

## Phone Integration

### Setup (One-Time)

1. **Install SensorServer app** on Android phone:
   - F-Droid: https://f-droid.org/packages/github.umer0586.sensorserver/
   - Or GitHub: https://github.com/umer0586/SensorServer/releases

2. **Configure SensorServer**:
   - Open app → Settings → Set "Bind Address" to `0.0.0.0` (all interfaces)
   - Enable: Accelerometer, Gyroscope, Magnetometer, Rotation Vector

3. **Enable USB Debugging** on phone:
   - Settings → Developer Options → USB Debugging: ON

4. **Connect phone to Pi via USB** and authorize when prompted

### Daily Usage

```bash
# On phone:
# 1. Open SensorServer app
# 2. Tap "Start" to begin streaming

# On Pi (services start automatically, or manually):
sudo systemctl start rovac-edge-phone-sensors.service  # IMU/GPS/Mag
sudo systemctl start rovac-phone-cameras.service       # Camera
```

### Switching Phone Cameras

Only one camera can stream at a time (Android limitation):

```bash
# SSH to Pi
ssh pi

# Switch cameras
~/robots/rovac/hardware/phone_cameras/switch_camera.sh back    # Main back camera (default)
~/robots/rovac/hardware/phone_cameras/switch_camera.sh front   # Front selfie camera
~/robots/rovac/hardware/phone_cameras/switch_camera.sh wide    # Back wide-angle
~/robots/rovac/hardware/phone_cameras/switch_camera.sh front2  # Secondary front
```

### Verify Phone Sensors

```bash
# Check all phone topics
ros2 topic list | grep phone

# View GPS data
ros2 topic echo /phone/gps/fix

# Check IMU frequency
ros2 topic hz /phone/imu

# View camera in Foxglove
# Add Image panel → Select /phone/camera/back/image_raw/compressed
```

## Project Structure

Both machines clone to `~/robots/rovac/`. The same tree is used on Mac and Pi.

```
~/robots/rovac/                         # Monorepo root (Mac + Pi)
├── README.md                           # This file
├── CLAUDE.md                           # Claude Code instructions
├── AGENTS.md                           # Agent configuration
├── scripts/                            # Launch and management scripts
│   ├── standalone_control.sh           # Main bringup script
│   ├── mac_brain_launch.sh             # SLAM/Nav2/Foxglove launcher
│   ├── install_mac_autostart.sh        # macOS launchd setup
│   ├── install_pi_systemd.sh          # Pi systemd setup
│   └── edge/                           # Pi-only edge launch helpers
│       ├── launch_tf_publisher.sh
│       ├── launch_map_odom_tf.sh
│       └── launch_odom_static.sh
├── config/                             # Configuration (shared)
│   ├── ros2_env.sh                     # ROS2 environment (both machines)
│   ├── cyclonedds_mac.xml              # Mac DDS config
│   ├── cyclonedds_pi.xml              # Pi DDS config
│   ├── slam_params.yaml                # SLAM toolbox params
│   ├── nav2_params.yaml                # Navigation2 params
│   └── systemd/                        # Pi systemd unit files
├── hardware/                           # Hardware drivers & docs
│   ├── README.md                       # Hardware overview
│   ├── hiwonder-ros-controller/        # Motor/IMU board (active — Hiwonder V1.2)
│   ├── yahboom-ros-expansion-board-v3/ # Old motor/IMU board (replaced)
│   ├── lidar_usb/                      # XV-11 LIDAR module
│   ├── phone_sensors/                  # Phone IMU/GPS/Mag integration
│   └── phone_cameras/                  # Phone camera streaming
├── super_sensor/                       # Ultrasonic sensor array (Arduino Nano)
├── ros2_ws/                            # ROS2 workspace
│   └── src/                            # ROS2 packages
│       ├── tank_description/           # URDF, launch files, cmd_vel mux
│       ├── xv11_lidar_python/          # XV-11 LIDAR driver
│       ├── rf2o_laser_odometry/        # Laser odometry
│       └── vorwerk_lidar/              # Vorwerk LIDAR driver
├── robot_mcp_server/                   # MCP server (35+ tools)
├── shared/                             # Syncthing-synced folder (Mac ↔ Pi, gitignored)
├── docs/                               # Documentation
│   ├── architecture/                   # System architecture docs
│   ├── phases/                         # Development phase docs
│   ├── troubleshooting/                # Troubleshooting guides
│   └── guides/                         # How-to guides
├── tools/                              # Utility scripts
├── archive/                            # Old/experimental code
└── maps/                               # Saved maps (gitignored, machine-specific)
```

## Systemd Services (Pi)

```bash
# Check all ROVAC services
ssh pi
sudo systemctl status rovac-edge.target

# Core services
sudo systemctl status rovac-edge-hiwonder.service      # Motor/IMU/Odom (Hiwonder board)
sudo systemctl status rovac-edge-mux.service           # cmd_vel mux
sudo systemctl status rovac-edge-tf.service            # TF publisher
sudo systemctl status rovac-edge-supersensor.service   # Ultrasonic
sudo systemctl status rovac-edge-lidar.service         # LIDAR (when connected)

# Stereo camera services
sudo systemctl status rovac-edge-stereo.target         # Stereo subsystem
sudo systemctl status rovac-edge-stereo-depth.service  # Depth computation
sudo systemctl status rovac-edge-stereo-obstacle.service # Obstacle detection

# Phone services
sudo systemctl status rovac-edge-phone-sensors.service # Phone IMU/GPS/Mag
sudo systemctl status rovac-phone-cameras.service      # Phone camera

# View logs
sudo journalctl -u rovac-edge-hiwonder -f
sudo journalctl -u rovac-edge-phone-sensors -f
```

## MCP Server

The robot exposes 35+ tools via MCP (Model Context Protocol) server at `http://192.168.1.200:8000`.

### Movement Tools
`move_forward`, `move_backward`, `turn_left`, `turn_right`, `stop`, `turn_around`, `drive_circle`, `drive_square`, `lawn_mower`

### Sensor Tools
`get_distance`, `check_obstacles`, `get_position`, `scan_surroundings`, `get_lidar_summary`, `get_camera_image`

### Camera/Servo Tools
`look_left`, `look_right`, `look_center`, `look_at_angle`, `sweep_scan`

### Navigation Tools
`go_to_position`, `go_to_named_location`, `save_current_location`, `return_home`, `explore_and_map`, `save_map`, `load_map`

## File Sharing (Syncthing)

A **Syncthing** peer-to-peer sync folder at `~/robots/rovac/shared/` enables instant file sharing between the Mac and Pi over the local network. Drop a file into `shared/` on one machine, and it appears on the other within seconds.

| Setting | Value |
|---------|-------|
| Tool | [Syncthing](https://syncthing.net/) (open source, P2P, TLS-encrypted) |
| Folder | `~/robots/rovac/shared/` (same path on both machines) |
| Folder ID | `rovac-shared` |
| Sync mode | Send & Receive (bidirectional) |
| Network | LAN-only (global discovery and relay disabled) |
| Mac service | `brew services` (launchd: `homebrew.mxcl.syncthing`) |
| Pi service | `systemctl --user` (`syncthing.service`, lingering enabled) |
| Web UI | `http://127.0.0.1:8384` (localhost only, both machines) |

### Usage

```bash
# Copy a file to the shared folder on Mac — appears on Pi in ~3 seconds
cp ~/Downloads/model.onnx ~/robots/rovac/shared/

# Check from Pi
ssh pi 'ls ~/robots/rovac/shared/'

# Check service status
brew services list | grep syncthing            # Mac
ssh pi 'systemctl --user status syncthing'     # Pi

# Access web UI on Pi (via SSH tunnel)
ssh -L 8384:127.0.0.1:8384 pi
# Then open http://127.0.0.1:8384 in browser
```

### Notes

- Files are **duplicated** on both machines (sync, not a network mount)
- The `shared/` directory is in `.gitignore` — synced files are not tracked by git
- `.stfolder` inside `shared/` is a Syncthing marker — do not delete it
- If both sides edit the same file simultaneously, Syncthing creates a `.sync-conflict-*` copy
- Deletions sync too — removing a file on one side removes it on the other

## Troubleshooting

### No topics visible on Mac
1. Verify network: `ping 192.168.1.200`
2. Check ROS_DOMAIN_ID: `echo $ROS_DOMAIN_ID` (should be 42)
3. Check DDS config: `echo $CYCLONEDDS_URI`
4. Wait 3-5 seconds for DDS discovery
5. Try: `ros2 topic list --no-daemon`

### Pi services not starting
```bash
ssh pi
sudo systemctl status rovac-edge.target
sudo journalctl -u rovac-edge-hiwonder -n 50
```

### Device not found
```bash
# Check USB devices on Pi
ls -la /dev/hiwonder_board /dev/esp32_lidar /dev/super_sensor
# Reload udev rules if needed
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Phone sensors not working
1. Ensure SensorServer app is running on phone (tap "Start")
2. Check phone is connected: `adb devices`
3. Verify ADB forwarding: `adb forward --list`
4. Restart service: `sudo systemctl restart rovac-edge-phone-sensors`

### Phone camera not working
1. Ensure phone screen is unlocked
2. Close any camera apps on phone
3. Check scrcpy: `ps aux | grep scrcpy`
4. Restart service: `sudo systemctl restart rovac-phone-cameras`

## Documentation Index

| Document | Description |
|----------|-------------|
| [hardware/README.md](hardware/README.md) | Hardware overview and specifications |
| [hardware/hiwonder-ros-controller/README.md](hardware/hiwonder-ros-controller/README.md) | Motor/IMU board (active — Hiwonder V1.2) |
| [hardware/yahboom-ros-expansion-board-v3/README.md](hardware/yahboom-ros-expansion-board-v3/README.md) | Old motor/IMU board (replaced) |
| [hardware/lidar_usb/docs/README.md](hardware/lidar_usb/docs/README.md) | LIDAR module setup and calibration |
| [hardware/super_sensor/README.md](hardware/super_sensor/README.md) | Super Sensor module documentation |
| [hardware/phone_sensors/README.md](hardware/phone_sensors/README.md) | Phone IMU/GPS/Magnetometer integration |
| [hardware/phone_cameras/README.md](hardware/phone_cameras/README.md) | Phone camera streaming setup |
| [CLAUDE.md](CLAUDE.md) | Claude Code integration instructions |

## Network Configuration

| Device | IP Address | Role |
|--------|------------|------|
| Raspberry Pi 5 | 192.168.1.200 | Edge (sensors/motors) |
| MacBook Pro | 192.168.1.104 | Brain (navigation) |
| Android Phone | USB to Pi | Sensors (GPS/IMU/Camera) |
| ROS_DOMAIN_ID | 42 | DDS domain |
| DDS | CycloneDDS | Unicast peer discovery |

## Sensor Fusion

The robot has multiple overlapping sensors for redundancy:

| Measurement | Primary Source | Secondary Source |
|-------------|----------------|------------------|
| **Position (indoor)** | Wheel odometry (`/odom`) | LIDAR SLAM (`/map`) |
| **Position (outdoor)** | Phone GPS (`/phone/gps/fix`) | Wheel odometry |
| **Orientation** | Board IMU (`/imu/data`) | Phone IMU (`/phone/imu`) |
| **Heading** | Phone magnetometer (`/phone/magnetic_field`) | IMU gyro Z integration (drift-prone) |
| **Obstacles** | LIDAR (`/scan`) | Ultrasonic (`/super_sensor/*`) |

## License

This is a personal robotics project. Hardware documentation follows vendor licenses.
