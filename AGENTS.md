# ROVAC Project Instructions for AI Agents

> For comprehensive details, see `CLAUDE.md`. This file provides the essential context any AI coding agent needs to work on this project.

## Overview

ROVAC is a mobile robot (Yahboom G1 Tank) with a USB serial architecture:
- **ESP32 Motor Controller** (on robot): USB serial COBS binary protocol — PID motor control, BNO055 IMU, odom/tf/imu/diagnostics
- **Raspberry Pi 5 (Edge)**: C++ motor driver node + sensor services at `192.168.1.200`
- **MacBook Pro (Brain)**: Nav2, SLAM, EKF, Foxglove, teleop (DHCP IP, auto-detected)

Communication: ESP32 ←USB COBS 460800 baud→ `rovac_motor_driver` C++ node on Pi ←CycloneDDS→ Mac. RPLIDAR C1 ←USB→ Pi. Phone ←WebSocket→ rosbridge on Pi :9090. All on `ROS_DOMAIN_ID=42`.

**This is ROS2 Jazzy, NOT ROS1.** Use `ros2` commands, never `roslaunch`/`roscore`/`rostopic`.

## Monorepo

`github.com/mohammednazmy/rovac` (private). Both machines clone the same repo:
- **Mac**: `~/robots/rovac/`
- **Pi**: `/home/pi/robots/rovac/`

## Quick Reference

| Resource | Value |
|----------|-------|
| Pi SSH | `ssh pi@192.168.1.200` |
| ESP32 Motor USB | `/dev/esp32_motor` on Pi (CH340, 460800 baud) |
| RPLIDAR C1 USB | `/dev/rplidar_c1` on Pi (CP2102N) |
| Serial Protocol | COBS-framed binary (`common/serial_protocol.h`) |
| Foxglove | `ws://localhost:8765` |
| ROS_DOMAIN_ID | 42 |
| DDS | CycloneDDS (unicast, auto-synced peer IPs) |

## Quick Start

```bash
# Pi edge services start automatically via systemd on boot
# Verify:
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge.target'

# Mac: source ROS2 environment (auto-detects IP, syncs to Pi if changed)
source config/ros2_env.sh

# SLAM mapping (slam-ekf recommended for best quality)
./scripts/mac_brain_launch.sh slam-ekf

# Keyboard teleop (auto-SSHes to Pi)
python3 scripts/keyboard_teleop.py

# Foxglove visualization
./scripts/mac_brain_launch.sh foxglove
```

## Key ROS2 Topics

### Motor (from ESP32 via USB serial driver on Pi)
| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `/odom` | Odometry | reliable | Dead-reckoning from encoder ticks (20 Hz) |
| `/tf` | TFMessage | reliable | odom → base_link (20 Hz, auto-disabled when EKF runs) |
| `/imu/data` | Imu | reliable | BNO055 9-axis NDOF fusion (20 Hz) |
| `/diagnostics` | DiagnosticArray | reliable | ESP32 health, PID status, IMU cal, reconnect count (1 Hz) |
| `/cmd_vel` | Twist | reliable | Motor commands (via mux, never publish directly) |

### Velocity Mux (priority order)
| Topic | Priority | Timeout | Source |
|-------|----------|---------|--------|
| `/cmd_vel_teleop` | 1 (highest) | 0.5s | Keyboard teleop |
| `/cmd_vel_joy` | 2 | 1.0s | PS2 joystick |
| `/cmd_vel_obstacle` | 3 | 0.5s | Obstacle avoidance |
| `/cmd_vel_smoothed` | 4 (lowest) | 1.0s | Nav2 autonomous |

### Sensors
| Topic | Type | Description |
|-------|------|-------------|
| `/scan` | LaserScan | RPLIDAR C1 DTOF (~500 pts, ~10 Hz) |
| `/phone/imu` | Imu | Phone IMU (50Hz) via rosbridge :9090 |
| `/phone/gps/fix` | NavSatFix | Phone GPS (1Hz) via rosbridge :9090 |

## Hardware

| Component | Details |
|-----------|---------|
| Motor Controller | NULLLAB Maker-ESP32 (ESP32-WROOM-32E, CH340, 4x TB67H450FNG). USB serial COBS at 460800 baud. |
| Motors | 2x JGB37-520R60-12 (12V, 60:1 gear, Hall encoders, 2640 ticks/rev) |
| IMU | Adafruit BNO055 (9-axis NDOF fusion) on ESP32 I2C. Calibration persists via NVS. |
| LIDAR | RPLIDAR C1 DTOF (16m range, ~10Hz). USB on Pi. Driver: patched `rplidar_ros`. |
| Computer | Raspberry Pi 5 (8GB RAM), Ubuntu 24.04 |
| Power | 12V DC barrel jack. **Motor power switch must be ON.** Battery must be >8V. |

## Project Structure

```
~/robots/rovac/
├── common/                            # Shared COBS protocol (ESP32 + Pi C++ driver)
├── hardware/
│   ├── esp32_motor_wireless/          # ESP32 firmware (ESP-IDF v5.2)
│   ├── as5600-magnetic-encoder/       # AS5600 encoder docs + test firmware
│   ├── greartisan-zgb37rg-motor/      # Motor specs
│   ├── super_sensor/                  # HC-SR04 + obstacle avoidance nodes
│   └── android_phone_sensors/         # Phone sensor app (rosbridge WebSocket)
├── scripts/
│   ├── keyboard_teleop.py             # Keyboard teleop (auto-SSHes to Pi)
│   ├── mac_brain_launch.sh            # Mac brain (slam, slam-ekf, nav, ekf, foxglove)
│   ├── ekf_launch.py                  # EKF launch file
│   ├── install_pi_systemd.sh          # Pi systemd setup
│   └── edge/                          # Pi-side scripts
├── config/
│   ├── ros2_env.sh                    # ROS2 env + DDS IP auto-sync
│   ├── cyclonedds_mac.xml             # Mac DDS (uses interface name, not hardcoded IP)
│   ├── cyclonedds_pi.xml              # Pi DDS (Mac peer auto-synced)
│   ├── ekf_params.yaml                # EKF: wheel odom + BNO055 gyro fusion
│   ├── slam_params.yaml               # SLAM Toolbox config
│   └── systemd/                       # Pi edge service units
├── ros2_ws/src/
│   ├── rovac_motor_driver/            # C++ USB serial motor driver (ament_cmake)
│   ├── tank_description/              # URDF, cmd_vel_mux.py
│   └── rplidar_ros/                   # RPLIDAR C1 driver (on Pi only)
├── tools/                             # Motor characterization, PID tuning
├── archive/                           # All legacy code (L298N, Hiwonder, QoS relays, etc.)
└── docs/                              # Architecture docs, ROS2 reference card
```

## ESP32 Firmware Development

```bash
# Build + flash directly on Pi (ESP-IDF v5.2 installed on Pi)
ssh pi@192.168.1.200
sudo systemctl stop rovac-edge-motor-driver
source ~/esp/esp-idf-v5.2/export.sh
cd ~/robots/rovac/hardware/esp32_motor_wireless
idf.py build && idf.py -p /dev/esp32_motor flash
sudo systemctl start rovac-edge-motor-driver
```

Key firmware files: `main/serial_transport.c` (COBS protocol), `main/motor_control.c` (PID + gyro correction), `main/odometry.c` (arc integration), `main/bno055.c` (IMU driver + NVS cal).

## Motor Driver (Pi C++ Node)

`ros2_ws/src/rovac_motor_driver/` — bridges ESP32 USB serial to ROS2.

Key features:
- **Serial health monitor**: auto-reconnects within 7s if USB re-enumerates (`serial_rx_timeout` param, default 5s)
- **Thread-safe**: mutex-protected serial port, atomic state variables
- **`publish_tf` param**: `true` by default, auto-set to `false` by `mac_brain_launch.sh` when EKF runs

Build on Pi: `cd ros2_ws && colcon build --packages-select rovac_motor_driver`

## Git Workflow

```bash
# Always pull before working
cd ~/robots/rovac && git pull origin main

# After changes — use specific file paths, never git add -A
git add <files> && git commit -m "message" && git push origin main

# Sync Pi
ssh pi@192.168.1.200 'cd ~/robots/rovac && git pull origin main'
```

## Critical Rules

1. **Never publish directly to `/cmd_vel`** — always use mux input topics
2. **Never run two EKF instances** — causes 40-degree yaw oscillation
3. **Never source ESP-IDF and conda ros_jazzy in the same shell**
4. **Use `--no-daemon` for `ros2 topic list`** on macOS (daemon hangs with CycloneDDS)
5. **`ros2 topic hz` does NOT accept `--no-daemon`** on Mac — use without it
6. **CH340 DTR resets ESP32** — motor driver service handles this via `stty -hupcl`
7. **Motor power switch must be ON** and battery >8V for motors to work
8. **systemd uses `Requires=` (not `BindsTo=`)** for USB devices — allows auto-restart after USB glitches
