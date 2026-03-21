# ROVAC Project Instructions

## Overview

ROVAC is a mobile robot (Yahboom G1 Tank) with a USB serial architecture:
- **ESP32 Motor Controller** (on robot): USB serial COBS binary protocol — runs PID motor control, BNO055 IMU, publishes odom/tf/imu/diagnostics
- **Raspberry Pi 5 (Edge)**: C++ motor driver node + sensor services at `192.168.1.200` (hostname: `rovac-pi`, user: `pi`)
- **MacBook Pro (Brain)**: Nav2, SLAM, path planning, teleop at `192.168.1.104`

Communication: ESP32 Motor ←USB COBS 460800 baud→ `rovac_motor_driver` C++ node on Pi ←CycloneDDS→ Mac. RPLIDAR C1 ←USB→ Pi (native ROS2 driver). Phone ←WebSocket→ rosbridge on Pi :9090 ←CycloneDDS→ Mac. All on `ROS_DOMAIN_ID=42`.

Both machines clone the same monorepo: `github.com/mohammednazmy/rovac`
- **Mac path**: `~/robots/rovac/`
- **Pi path**: `/home/pi/robots/rovac/`

## Quick Reference

| Resource | Value |
|----------|-------|
| GitHub Repo | `git@github.com:mohammednazmy/rovac.git` |
| Edge SSH | `ssh pi@192.168.1.200` |
| ESP32 Motor USB | `/dev/esp32_motor` on Pi (CH340, 460800 baud) |
| RPLIDAR C1 USB | `/dev/rplidar_c1` on Pi |
| Serial Protocol | COBS-framed binary (`common/serial_protocol.h`) |
| rosbridge WebSocket | Pi port 9090 (phone sensors) |
| Foxglove | `ws://localhost:8765` |
| ROS_DOMAIN_ID | 42 |
| DDS | CycloneDDS (unicast) |

## Quick Start Commands

```bash
# First-time setup (Pi edge)
ssh pi@192.168.1.200
cd ~/robots/rovac
./scripts/install_pi_systemd.sh install

# Daily bringup — Pi services start automatically via systemd
# Verify edge is running:
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge.target'

# Mac: source ROS2 environment
source config/ros2_env.sh

# Keyboard teleop (auto-SSHes to Pi for lowest latency)
python3 scripts/keyboard_teleop.py

# SLAM mapping / Nav2 / Foxglove (Mac)
./scripts/mac_brain_launch.sh slam
./scripts/mac_brain_launch.sh nav ~/maps/house.yaml
./scripts/mac_brain_launch.sh foxglove

# Edge status
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge-motor-driver rovac-edge-rplidar-c1 rovac-edge-mux'
```

## Key ROS2 Topics

### Motor (from ESP32 via USB serial driver on Pi)
| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `/odom` | Odometry | reliable | Dead-reckoning from encoder ticks (20 Hz) |
| `/tf` | TFMessage | reliable | odom → base_link transform (20 Hz, disabled when EKF runs) |
| `/imu/data` | Imu | reliable | BNO055 9-axis IMU (20 Hz) |
| `/diagnostics` | DiagnosticArray | reliable | ESP32 health: heap, PID status, IMU cal (1 Hz) |
| `/cmd_vel` | Twist | reliable | Motor commands (subscribed by motor driver → forwarded to ESP32) |

### Velocity Mux (priority order)
| Topic | Priority | Timeout | Description |
|-------|----------|---------|-------------|
| `/cmd_vel_teleop` | 1 (highest) | 0.5s | Keyboard teleop |
| `/cmd_vel_joy` | 2 | 1.0s | PS2 joystick |
| `/cmd_vel_obstacle` | 3 | 0.5s | Obstacle avoidance (only overrides nav) |
| `/cmd_vel_smoothed` | 4 (lowest) | 1.0s | Autonomous navigation |

ALL velocity commands go through the mux (`cmd_vel_mux.py`). Nothing publishes directly to `/cmd_vel`.

### Sensors
| Topic | Type | Description |
|-------|------|-------------|
| `/scan` | LaserScan | RPLIDAR C1 DTOF (~500 pts, ~10 Hz) via USB on Pi |
| `/sensors/ultrasonic/range` | Range | HC-SR04 distance |
| `/phone/imu` | Imu | Phone IMU (50Hz) via rosbridge WebSocket :9090 |
| `/phone/gps/fix` | NavSatFix | Phone GPS (1Hz) via rosbridge WebSocket :9090 |
| `/phone/camera/image_raw/compressed` | CompressedImage | Phone camera (~2FPS JPEG) via rosbridge WebSocket :9090 |

## Hardware

| Component | Details |
|-----------|---------|
| Motor Controller | NULLLAB Maker-ESP32 (ESP32-WROOM-32E, CH340) with 4x TB67H450FNG drivers. USB serial firmware: `hardware/esp32_motor_wireless/`. COBS binary at 460800 baud. 50Hz PID loop. |
| Motors | 2x JGB37-520R60-12 (12V, 60:1 gear, Hall encoders, 2640 ticks/rev). Max: 0.57 m/s linear, 6.5 rad/s angular. |
| IMU | Adafruit BNO055 (9-axis NDOF fusion) on ESP32 I2C bus. Mounted face-down, front edge toward LIDAR. |
| LIDAR | RPLIDAR C1 DTOF (16m range, ~10Hz, 5KHz). USB via CP2102N → `/dev/rplidar_c1`. Driver: `rplidar_ros` (official Slamtec, ros2 branch, SDK patched) in `ros2_ws/src/rplidar_ros/`. |
| Computer | Raspberry Pi 5 (8GB RAM, 117GB SD), Ubuntu 24.04, hostname `rovac-pi`. Runs C++ motor driver node. |
| Ultrasonic | 4x HC-SR04 (Super Sensor module, Arduino Nano) |
| Stereo Cameras | 2x USB cameras (102.67mm baseline, StereoSGBM depth) |
| Phone Sensors | Samsung Galaxy A16 (IMU/GPS/Camera) via rosbridge WebSocket on Pi :9090. App: `hardware/android_phone_sensors/` |
| Webcam | NexiGo N930E USB `/dev/webcam` |
| Power | 12V DC barrel jack. **Motor power switch must be ON.** |

## Project Structure

```
~/robots/rovac/
├── common/
│   ├── serial_protocol.h              # Shared COBS binary protocol (ESP32 + Pi)
│   ├── cobs.c                         # COBS encode/decode implementation
│   └── cobs.h                         # COBS header
├── hardware/
│   ├── esp32_motor_wireless/          # ACTIVE — USB serial motor firmware (ESP-IDF v5.2)
│   ├── esp32_at8236_driver/           # Legacy Python USB serial driver (replaced by C++ node)
│   ├── rplidar_c1/                    # RPLIDAR C1 docs + SDK reference
│   ├── maker_esp32/                   # Board docs + wiring guide
│   ├── super_sensor/                  # Edge ROS2 nodes (supersensor, obstacle)
│   ├── health_monitor/                # Edge health monitor
│   ├── stereo_cameras/                # Stereo camera calibration + depth
│   ├── android_phone_sensors/          # Phone sensor Android app (rosbridge WebSocket)
│   ├── webcam/                        # USB webcam publisher
│   └── lidar_usb/                     # XV-11 LIDAR docs
├── scripts/
│   ├── keyboard_teleop.py             # Keyboard teleop (auto-SSHes to Pi)
│   ├── standalone_control.sh          # Main bringup
│   ├── install_pi_systemd.sh          # Pi systemd setup
│   ├── mac_brain_launch.sh            # Mac Nav2/SLAM launcher
│   ├── ps2_joy_mapper_node.py         # PS2 controller → /cmd_vel_joy
│   ├── deploy_core_pi.sh             # Git sync to Pi
│   └── edge/
│       └── edge_health_node.py        # Pi health publisher to /rovac/edge/health
├── config/
│   ├── ros2_env.sh                    # ROS2 environment setup
│   ├── cyclonedds_mac.xml             # Mac DDS config (peers with Pi)
│   ├── cyclonedds_pi.xml             # Pi DDS config (peers with Mac)
│   ├── ekf_params.yaml               # EKF config (subscribes /odom + /imu/data directly)
│   ├── slam_params.yaml              # SLAM toolbox config
│   ├── nav2_params.yaml              # Navigation2 config
│   └── systemd/                       # Pi edge unit files
│       ├── rovac-edge.target          # Main orchestration target
│       ├── rovac-edge-motor-driver.service  # C++ USB serial motor driver (ACTIVE)
│       ├── rovac-edge-mux.service           # cmd_vel priority mux
│       ├── rovac-edge-tf.service            # robot_state_publisher
│       ├── rovac-edge-map-tf.service        # map→odom static TF
│       ├── rovac-edge-rplidar-c1.service    # RPLIDAR C1 driver (USB serial)
│       ├── rovac-edge-obstacle.service      # Obstacle avoidance
│       ├── rovac-edge-supersensor.service   # HC-SR04 ultrasonic
│       ├── rovac-edge-ps2-joy.service       # PS2 controller input
│       ├── rovac-edge-ps2-mapper.service    # PS2 → velocity commands
│       ├── rovac-edge-rosbridge.service     # rosbridge WebSocket (port 9090)
│       ├── rovac-edge-ekf.service           # EKF (DISABLED — run from Mac)
│       └── ...                              # stereo, webcam, phone services
├── ros2_ws/src/
│   ├── rovac_motor_driver/            # C++ USB serial motor driver (ament_cmake)
│   ├── tank_description/              # URDF, cmd_vel_mux.py
│   ├── rplidar_ros/                   # RPLIDAR C1 ROS2 driver (official Slamtec, SDK patched)
│   └── rf2o_laser_odometry/           # Laser-based odometry
├── tools/
│   ├── motor_characterization.py      # Motor PID tuning (standalone serial)
│   ├── pid_step_response.py           # PID step response analyzer
│   └── latency_probe.py              # Network latency measurement
├── robot_mcp_server/                  # 35+ tool MCP server
├── super_sensor/                      # Super Sensor desktop app + firmware
├── foxglove_layouts/                  # Foxglove Studio layout configs
├── archive/                           # All legacy/deprecated code
│   ├── legacy_hardware/               # L298N, Hiwonder, BST-4WD, esp32_lidar_wireless, etc.
│   └── legacy_scripts/                # QoS relays, Agent watchdog, Lenovo setup, etc.
└── docs/
    ├── architecture/
    └── guides/
```

## Environment Setup

```bash
# Mac: Activate conda environment
conda activate ros_jazzy

# Source ROS2 environment (sets DDS config, domain ID, peer IPs)
source ~/robots/rovac/config/ros2_env.sh

# IMPORTANT: Use --no-daemon on macOS — the ROS2 daemon hangs with CycloneDDS
ros2 topic list --no-daemon

# ESP-IDF (for firmware development — NEVER in same shell as conda)
source ~/esp/esp-idf-v5.2/export.sh
```

## ESP32 Motor Firmware Development

```bash
# Build (in ESP-IDF shell, NOT conda)
source ~/esp/esp-idf-v5.2/export.sh
cd ~/robots/rovac/hardware/esp32_motor_wireless
idf.py build

# Flash via Pi (ESP32 connected to Pi USB)
scp build/bootloader/bootloader.bin build/partition_table/partition-table.bin build/esp32_motor_wireless.bin pi@192.168.1.200:/tmp/
ssh pi@192.168.1.200 'esptool.py --chip esp32 --port /dev/esp32_motor --baud 460800 write_flash 0x1000 /tmp/bootloader.bin 0x8000 /tmp/partition-table.bin 0x10000 /tmp/esp32_motor_wireless.bin'
```

**Key firmware files:**
- `main/serial_transport.c` — UART0 COBS binary protocol, TX timers (odom/imu/diag), RX task (cmd_vel)
- `main/motor_control.c` — PID controller, cmd_vel → wheel speeds, gyro heading correction
- `main/odometry.c` — Arc integration from encoder ticks
- `main/bno055.c` — BNO055 IMU driver (I2C, NDOF fusion, NVS calibration persistence)
- `main/motor_driver.c` — TB67H450FNG PWM via LEDC
- `main/encoder_reader.c` — PCNT hardware quadrature decoder

**Shared protocol:** `common/serial_protocol.h` defines message types, packed structs, and CRC-16 used by both ESP32 firmware and Pi C++ driver.

**Pi C++ driver:** `ros2_ws/src/rovac_motor_driver/` — `ament_cmake` package. Build on Pi: `cd ros2_ws && colcon build --packages-select rovac_motor_driver`

## Troubleshooting

### No topics visible
1. Check `ROS_DOMAIN_ID=42` is set
2. Verify CycloneDDS config: `echo $CYCLONEDDS_URI`
3. Wait 3-5 seconds for DDS discovery

### ESP32 not publishing odom
1. Check motor driver: `ssh pi@192.168.1.200 'systemctl status rovac-edge-motor-driver'`
2. Check USB connection: `ssh pi@192.168.1.200 'ls -la /dev/esp32_motor'`
3. If USB device missing, check cable and try different USB port on Pi
4. Check ESP32 diagnostics: `ros2 topic echo /diagnostics` — look for "ROVAC Motor Serial"

### cmd_vel not reaching motors
1. Always publish to mux INPUT topics (`/cmd_vel_teleop`, `/cmd_vel_joy`, etc.), NOT directly to `/cmd_vel`
2. **Check for stale publishers:** `ssh pi@192.168.1.200 'ps aux | grep "ros2 topic pub"'` — kill any zombie processes
3. Check mux is running: `ssh pi@192.168.1.200 'systemctl is-active rovac-edge-mux'`

### Keyboard teleop not working
1. **First check for stale pub processes** on Pi: `ssh pi@192.168.1.200 'pgrep -a -f "ros2 topic pub.*cmd_vel"'` — kill any found
2. The teleop auto-kills stale pubs on startup, but check manually if issues persist
3. Verify odom is flowing: `ros2 topic hz /odom`

### TF jumping / position oscillation in Foxglove
When running EKF, ensure `motor_driver_node` has `publish_tf: false` (default). Only the EKF should publish odom→base_link TF. Two TF publishers on the same link = jumping. Fix: `ros2 param set /motor_driver_node publish_tf false`

### PS2 controller not working
```bash
ssh pi@192.168.1.200 'lsusb | grep 2563:0575'
ssh pi@192.168.1.200 'systemctl is-active rovac-edge-ps2-joy rovac-edge-ps2-mapper'
```
Known issue: ShanWan ZD-V+ wireless signal dropouts cause brief motor spurts. 200ms hold filter in `ps2_joy_mapper_node.py`.

### CH340 USB not detected on Pi
The CH340 chip can intermittently fail to enumerate (`error -71` in dmesg). Try:
1. Unplug USB, wait 5 seconds, replug
2. Try a different USB port on the Pi
3. Try a different USB cable (some are power-only with no data lines)
4. Check `sudo dmesg | tail -20` for USB errors
