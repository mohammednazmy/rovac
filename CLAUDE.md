# ROVAC Project Instructions

## Overview

ROVAC is a mobile robot (Yahboom G1 Tank) with a wireless micro-ROS architecture:
- **ESP32 Motor Controller** (on robot): Wireless micro-ROS node at `192.168.1.221` — runs PID motor control, publishes `/odom`, `/tf`, subscribes `/cmd_vel`
- **Raspberry Pi 5 (Edge)**: micro-ROS Agent bridge + sensor services at `192.168.1.200` (hostname: `rovac-pi`, user: `pi`)
- **MacBook Pro (Brain)**: Nav2, SLAM, path planning, teleop at `192.168.1.104`

Communication: ESP32 Motor ←WiFi UDP→ micro-ROS Agent on Pi ←CycloneDDS→ Mac. RPLIDAR C1 ←USB→ Pi (native ROS2 driver). Phone ←WebSocket→ rosbridge on Pi :9090 ←CycloneDDS→ Mac. All on `ROS_DOMAIN_ID=42`.

Both machines clone the same monorepo: `github.com/mohammednazmy/rovac`
- **Mac path**: `~/robots/rovac/`
- **Pi path**: `/home/pi/robots/rovac/`

## Quick Reference

| Resource | Value |
|----------|-------|
| GitHub Repo | `git@github.com:mohammednazmy/rovac.git` |
| Edge SSH | `ssh pi@192.168.1.200` |
| ESP32 Motor WiFi IP | `192.168.1.221` |
| RPLIDAR C1 USB | `/dev/rplidar_c1` on Pi |
| micro-ROS Agent | Pi UDP port 8888 |
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
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge-uros-agent rovac-edge-rplidar-c1 rovac-edge-mux'
```

## Key ROS2 Topics

### Motor (from ESP32 via micro-ROS Agent)
| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `/odom` | Odometry | best_effort | Dead-reckoning from encoder ticks (20 Hz) |
| `/tf` | TFMessage | best_effort | odom → base_link transform (20 Hz) |
| `/diagnostics` | DiagnosticArray | best_effort | ESP32 health: WiFi RSSI, heap, uptime (1 Hz) |
| `/cmd_vel` | Twist | best_effort | Motor commands (subscribed by ESP32) |

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

### QoS Relays (Pi edge)
| Relay | Input QoS | Output QoS | Description |
|-------|-----------|------------|-------------|
| `tf_relay.py` | best_effort | reliable | `/tf` for tf2_ros. **Stop when EKF is running** (EKF publishes its own reliable odom→base_link TF) |
| `odom_relay.py` | best_effort | reliable | `/odom` for robot_localization EKF |

## Hardware

| Component | Details |
|-----------|---------|
| Motor Controller | NULLLAB Maker-ESP32 (ESP32-WROOM-32E, CH340) with 4x TB67H450FNG drivers. Wireless micro-ROS firmware: `hardware/esp32_motor_wireless/`. WiFi static IP 192.168.1.221. 50Hz PID loop. |
| Motors | 2x JGB37-520R60-12 (12V, 60:1 gear, Hall encoders, 2640 ticks/rev). Max: 0.57 m/s linear, 6.5 rad/s angular. |
| LIDAR | RPLIDAR C1 DTOF (16m range, ~10Hz, 5KHz). USB via CP2102N → `/dev/rplidar_c1`. Driver: `rplidar_ros` (official Slamtec, ros2 branch, SDK patched) in `ros2_ws/src/rplidar_ros/`. |
| Computer | Raspberry Pi 5 (8GB RAM, 117GB SD), Ubuntu 24.04, hostname `rovac-pi`. Runs micro-ROS Agent (UDP 8888). |
| Ultrasonic | 4x HC-SR04 (Super Sensor module, Arduino Nano) |
| Stereo Cameras | 2x USB cameras (102.67mm baseline, StereoSGBM depth) |
| Phone Sensors | Samsung Galaxy A16 (IMU/GPS/Camera) via rosbridge WebSocket on Pi :9090. App: `hardware/android_phone_sensors/` |
| Webcam | NexiGo N930E USB `/dev/webcam` |
| Power | 12V DC barrel jack. **Motor power switch must be ON.** |

## Project Structure

```
~/robots/rovac/
├── hardware/
│   ├── esp32_motor_wireless/        # ACTIVE — micro-ROS motor firmware (ESP-IDF v5.2)
│   ├── esp32_at8236_driver/         # ACTIVE — USB serial ROS2 driver (fallback mode)
│   ├── rplidar_c1/                  # RPLIDAR C1 docs + SDK reference
│   ├── esp32_xv11_bridge/           # Legacy LIDAR bridge (Arduino, USB serial)
│   ├── maker_esp32/                 # Board docs + wiring guide
│   ├── super_sensor/                # Edge ROS2 nodes (supersensor, obstacle)
│   ├── health_monitor/              # Edge health monitor
│   ├── stereo_cameras/              # Stereo camera calibration + depth
│   ├── android_phone_sensors/        # Phone sensor Android app (rosbridge WebSocket)
│   ├── phone_sensors/               # Phone IMU/GPS integration (legacy)
│   ├── phone_cameras/               # Phone camera streaming (legacy)
│   ├── webcam/                      # USB webcam publisher
│   └── lidar_usb/                   # XV-11 LIDAR docs
├── scripts/
│   ├── keyboard_teleop.py           # Keyboard teleop (auto-SSHes to Pi)
│   ├── standalone_control.sh        # Main bringup
│   ├── install_pi_systemd.sh        # Pi systemd setup
│   ├── mac_brain_launch.sh          # Mac Nav2/SLAM launcher
│   ├── ps2_joy_mapper_node.py       # PS2 controller → /cmd_vel_joy
│   ├── deploy_core_pi.sh            # Git sync to Pi
│   └── edge/
│       ├── reset_esp32_motor.sh     # ESP32 reset after Agent restart
│       ├── tf_relay.py              # best_effort→reliable /tf relay
│       ├── odom_relay.py            # best_effort→reliable /odom relay
│       └── agent_memory_watchdog.sh # Agent RSS memory watchdog
├── config/
│   ├── ros2_env.sh                  # ROS2 environment setup
│   ├── cyclonedds_mac.xml           # Mac DDS config (peers with Pi)
│   ├── cyclonedds_pi.xml            # Pi DDS config (peers with Mac)
│   ├── slam_params.yaml             # SLAM toolbox config
│   ├── nav2_params.yaml             # Navigation2 config
│   └── systemd/                     # Pi edge unit files
│       ├── rovac-edge.target        # Main orchestration target
│       ├── rovac-edge-uros-agent.service  # micro-ROS Agent (UDP 8888)
│       ├── rovac-edge-esp32.service       # USB serial motor driver (fallback)
│       ├── rovac-edge-mux.service         # cmd_vel priority mux
│       ├── rovac-edge-tf.service          # robot_state_publisher
│       ├── rovac-edge-map-tf.service      # map→odom static TF
│       ├── rovac-edge-rplidar-c1.service  # RPLIDAR C1 driver (USB serial)
│       ├── rovac-edge-obstacle.service    # Obstacle avoidance
│       ├── rovac-edge-supersensor.service # HC-SR04 ultrasonic
│       ├── rovac-edge-ps2-joy.service     # PS2 controller input
│       ├── rovac-edge-ps2-mapper.service  # PS2 → velocity commands
│       ├── rovac-edge-rosbridge.service   # rosbridge WebSocket (port 9090)
│       ├── rovac-edge-tf-relay.service    # best_effort→reliable /tf relay
│       ├── rovac-edge-odom-relay.service  # best_effort→reliable /odom relay
│       └── ...                            # stereo, webcam, phone services
├── ros2_ws/src/
│   ├── tank_description/            # URDF, cmd_vel_mux.py
│   ├── rplidar_ros/                 # RPLIDAR C1 ROS2 driver (official Slamtec, SDK patched)
│   ├── rplidar_ros2_driver/         # RPLIDAR C1 community driver (frozenreboot, has SDK threading bug)
│   ├── xv11_lidar_python/           # XV11 LIDAR ROS2 driver (legacy, unused)
│   └── rf2o_laser_odometry/         # Laser-based odometry
├── tools/
│   ├── motor_characterization.py    # Motor PID tuning (standalone serial)
│   ├── pid_step_response.py         # PID step response analyzer
│   └── latency_probe.py             # Network latency measurement
├── robot_mcp_server/                # 35+ tool MCP server
├── super_sensor/                    # Super Sensor desktop app + firmware
├── foxglove_layouts/                # Foxglove Studio layout configs
├── archive/                         # All legacy/deprecated code
│   ├── legacy_hardware/             # L298N, Hiwonder, BST-4WD, Nano encoder, esp32_lidar_wireless (XV11), etc.
│   └── legacy_scripts/              # Lenovo setup, old launchers, phone_sensor_relay.py
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
scp build/esp32_motor_wireless.bin pi@192.168.1.200:/tmp/
ssh pi@192.168.1.200 'esptool.py --port /dev/esp32_motor --baud 921600 write_flash 0x10000 /tmp/esp32_motor_wireless.bin'

# Monitor serial (on Pi)
ssh pi@192.168.1.200 'stty -F /dev/esp32_motor 115200 -hupcl && cat /dev/esp32_motor'
```

**Key firmware files:**
- `main/uros.c` — micro-ROS node, publishers, subscriber, state machine
- `main/motor_control.c` — PID controller, cmd_vel → wheel speeds
- `main/odometry.c` — Arc integration from encoder ticks
- `main/wifi.c` — WiFi STA, static IP, reconnect
- `main/nvs_config.c` — NVS for WiFi/Agent config
- `app-colcon.meta` — micro-ROS buffer sizes (MTU=1024)

## Troubleshooting

### No topics visible
1. Check `ROS_DOMAIN_ID=42` is set
2. Verify CycloneDDS config: `echo $CYCLONEDDS_URI`
3. Wait 3-5 seconds for DDS discovery
4. micro-ROS topics may intermittently drop from `ros2 topic list` (CycloneDDS type hash issue) — data still flows

### ESP32 not publishing odom
1. Check Agent: `ssh pi@192.168.1.200 'systemctl status rovac-edge-uros-agent'`
2. Check ESP32 WiFi: `ping 192.168.1.221`
3. After Agent restart, ESP32 needs reboot (XRCE-DDS session state lost). The `reset_esp32_motor.sh` ExecStartPost handles this automatically when ESP32 is USB-connected.

### cmd_vel not reaching motors
Always publish to mux INPUT topics (`/cmd_vel_teleop`, `/cmd_vel_joy`, etc.), NOT directly to `/cmd_vel`. The mux overwrites direct publishers.

### PS2 controller not working
```bash
ssh pi@192.168.1.200 'lsusb | grep 2563:0575'
ssh pi@192.168.1.200 'systemctl is-active rovac-edge-ps2-joy rovac-edge-ps2-mapper'
```
Known issue: ShanWan ZD-V+ wireless signal dropouts cause brief motor spurts. 200ms hold filter in `ps2_joy_mapper_node.py`.

### TF relay vs EKF conflict
When running EKF (`ekf` mode), stop `rovac-edge-tf-relay` — EKF publishes its own reliable odom→base_link TF, and the relay would create duplicate/conflicting transforms. The `mac_brain_launch.sh` handles this automatically.

### Agent memory looks high
micro-ROS Agent steady-state RSS is ~43-65MB (CycloneDDS discovery cache). This is normal. The watchdog threshold is 150MB. Agent memory plateaus after DDS discovery completes — it is NOT leaking.
