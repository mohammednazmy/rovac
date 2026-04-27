# ROVAC Project Instructions

## Overview

ROVAC is a mobile robot (Yahboom G1 Tank) with a USB serial architecture:
- **ESP32 Motor Controller** (on robot): USB serial COBS binary protocol — runs PID motor control, BNO055 IMU, publishes odom/tf/imu/diagnostics
- **ESP32 Sensor Hub** (on robot): USB serial COBS binary protocol — 4x HC-SR04 ultrasonic + 2x Sharp IR cliff sensors, publishes range/cliff/diagnostics
- **Raspberry Pi 5 (Edge)**: C++ motor driver node + C++ sensor driver node + sensor services at `192.168.1.200` (hostname: `rovac-pi`, user: `pi`)
- **MacBook Pro (Brain)**: Nav2, SLAM, path planning, teleop (DHCP IP, auto-detected from en0)

Communication: ESP32 Motor ←USB COBS 460800→ `rovac_motor_driver` on Pi. ESP32 Sensor Hub ←USB COBS 460800→ `rovac_sensor_driver` on Pi. RPLIDAR C1 ←USB→ Pi. All Pi nodes ←CycloneDDS→ Mac. All on `ROS_DOMAIN_ID=42`.

Both machines clone the same monorepo: `github.com/mohammednazmy/rovac`
- **Mac path**: `~/robots/rovac/`
- **Pi path**: `/home/pi/robots/rovac/`

## Quick Reference

| Resource | Value |
|----------|-------|
| GitHub Repo | `git@github.com:mohammednazmy/rovac.git` |
| Edge SSH | `ssh pi@192.168.1.200` |
| ESP32 Motor USB | `/dev/esp32_motor` on Pi (CH340, 460800 baud) |
| ESP32 Sensor Hub USB | `/dev/esp32_sensor` on Pi (CP2102, 460800 baud) |
| RPLIDAR C1 USB | `/dev/rplidar_c1` on Pi (CP2102N) |
| Serial Protocol | COBS-framed binary (`common/serial_protocol.h`) |
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

# SLAM mapping (Mac) — slam-ekf recommended for best map quality
./scripts/mac_brain_launch.sh slam-ekf
./scripts/mac_brain_launch.sh slam
./scripts/mac_brain_launch.sh nav ~/maps/house.yaml
./scripts/mac_brain_launch.sh foxglove

# Edge status
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge-motor-driver rovac-edge-sensor-hub rovac-edge-rplidar-c1 rovac-edge-mux rovac-edge-sense-hat-panel'

# Sense HAT panel — verify on-robot status display + joystick is alive
ssh pi@192.168.1.200 'sudo systemctl is-active rovac-edge-sense-hat-panel'
ros2 topic echo /rovac/sense_hat/feature_set --once   # current feature set (STATUS/TELEOP/RAINBOW)

# Trigger remote ESTOP from any machine on the bus (publishes 0 Twist at 10 Hz):
ros2 topic pub --times 1 /rovac/sense_hat/mode_request std_msgs/String '{data: ESTOP}'
# Release ESTOP:
ros2 topic pub --times 1 /rovac/sense_hat/mode_request std_msgs/String '{data: IDLE}'
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

### Sensor Hub (from ESP32 Sensor Hub via USB serial driver on Pi)
| Topic | Type | QoS | Description |
|-------|------|-----|-------------|
| `/sensors/ultrasonic/front` | Range | reliable | HC-SR04 front obstacle (10 Hz) |
| `/sensors/ultrasonic/rear` | Range | reliable | HC-SR04 rear obstacle (10 Hz) |
| `/sensors/ultrasonic/left` | Range | reliable | HC-SR04 left obstacle (10 Hz) |
| `/sensors/ultrasonic/right` | Range | reliable | HC-SR04 right obstacle (10 Hz) |
| `/sensors/cliff/front` | Range | reliable | Sharp IR front cliff distance (10 Hz) |
| `/sensors/cliff/rear` | Range | reliable | Sharp IR rear cliff distance (10 Hz) |
| `/sensors/cliff/detected` | Bool | reliable | Cliff detected on any sensor (10 Hz) |
| `/obstacle/points` | PointCloud2 | reliable | Ultrasonic readings as 3D points for Nav2 costmap (10 Hz) |

### Other Sensors
| Topic | Type | Description |
|-------|------|-------------|
| `/scan` | LaserScan | RPLIDAR C1 DTOF (~500 pts, ~10 Hz) via USB on Pi |

### Sense HAT Panel (on-robot status display + physical joystick on Pi GPIO)
| Topic | Type | Description |
|-------|------|-------------|
| `/rovac/sense_hat/feature_set` | String | Current feature set: STATUS / TELEOP / RAINBOW (1 Hz) |
| `/rovac/sense_hat/mode_request` | String | Requested robot mode: IDLE/TELEOP/NAV/SLAM/ESTOP. Subscribed by panel itself; ESTOP triggers continuous zero-Twist publishing at 10 Hz on `/cmd_vel_teleop` (highest mux priority) until cleared. Anyone on the bus can publish to ESTOP-lock the robot. |

The panel's HAT joystick has 3 feature sets, cycled by center-click:
- **STATUS** — mode glyph + corner-badge alarm overlays (motor/sensor ESP32 health, Mac connectivity, cliff detection). Up/Down cycles requested mode (publishes `mode_request`).
- **TELEOP** — joystick directions drive robot via `/cmd_vel_teleop` (15 cm/s linear, 0.6 rad/s angular).
- **RAINBOW** — plasma-vortex animation, joystick disabled except center-click.

The Sense HAT IMU (LSM9DS1) is intentionally unused — the BNO055 on the ESP32 motor controller remains the sole IMU.

## Hardware

| Component | Details |
|-----------|---------|
| Motor Controller | NULLLAB Maker-ESP32 (ESP32-WROOM-32E, CH340) with 4x TB67H450FNG drivers. USB serial firmware: `hardware/esp32_motor_wireless/`. COBS binary at 460800 baud. 50Hz PID loop. |
| Motors | 2x JGB37-520R60-12 (12V, 60:1 gear, Hall encoders, 2640 ticks/rev). Max: 0.57 m/s linear, 6.5 rad/s angular. |
| IMU | Adafruit BNO055 (9-axis NDOF fusion) on ESP32 I2C bus. Mounted face-down, front edge toward LIDAR. |
| LIDAR | RPLIDAR C1 DTOF (16m range, ~10Hz, 5KHz). USB via CP2102N → `/dev/rplidar_c1`. Driver: `rplidar_ros` (official Slamtec, ros2 branch, SDK patched) in `ros2_ws/src/rplidar_ros/`. |
| Sensor Hub | ESP32-DevKitV1 (WROOM-32, CP2102). 4x HC-SR04 ultrasonic (front/rear/left/right) + 2x Sharp GP2Y0A51SK0F IR cliff (front/rear). USB serial firmware: `hardware/esp32_sensor_hub/`. COBS binary at 460800 baud. 10Hz sensor data. |
| Computer | Raspberry Pi 5 (8GB RAM, 117GB SD), Ubuntu 24.04, hostname `rovac-pi`. Runs C++ motor + sensor driver nodes. |
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
│   ├── esp32_sensor_hub/              # ACTIVE — USB serial sensor hub firmware (ESP-IDF v5.2)
│   ├── hc-sr04-ultrasonic/            # HC-SR04 ultrasonic sensor docs
│   ├── sharp-gp2y0a51sk0f-ir-distance/ # Sharp IR cliff sensor docs + datasheet
│   ├── as5600-magnetic-encoder/       # AS5600 encoder docs, test firmware, 3D mount
│   ├── greartisan-zgb37rg-motor/      # Motor specs + AS5600 integration data
│   ├── rplidar_c1/                    # RPLIDAR C1 docs + SDK reference
│   ├── maker_esp32/                   # Board docs + wiring guide
│   ├── super_sensor/                  # LEGACY — replaced by esp32_sensor_hub
│   ├── android_phone_sensors/          # RETIRED — BNO055 replaces phone IMU, no GPS needed
├── scripts/
│   ├── keyboard_teleop.py             # Keyboard teleop (auto-SSHes to Pi)
│   ├── install_pi_systemd.sh          # Pi systemd setup (install/uninstall/status/restart)
│   ├── mac_brain_launch.sh            # Mac brain launcher (slam, slam-ekf, nav, ekf, foxglove)
│   ├── obstacle_avoidance_node.py     # Obstacle avoidance (sensor hub ultrasonic + cliff)
│   ├── ps2_joy_mapper_node.py         # PS2 controller → /cmd_vel_joy
│   ├── ekf_launch.py                  # EKF launch (used by mac_brain_launch.sh)
│   └── edge/
│       ├── edge_health_node.py        # Pi health publisher to /rovac/edge/health
│       ├── sense_hat_panel_node.py    # Sense HAT status display + joystick panel
│       └── sense_hat_glyphs.py        # Sense HAT visual designs (palette, glyphs, rainbow)
├── config/
│   ├── ros2_env.sh                    # ROS2 environment setup
│   ├── cyclonedds_mac.xml             # Mac DDS config (peers with Pi)
│   ├── cyclonedds_pi.xml             # Pi DDS config (peers with Mac)
│   ├── ekf_params.yaml               # EKF config (subscribes /odom + /imu/data directly)
│   ├── slam_params.yaml              # SLAM toolbox config
│   ├── nav2_params.yaml              # Navigation2 config
│   └── systemd/                       # Pi edge unit files
│       ├── rovac-edge.target          # Main orchestration target
│       ├── rovac-edge-motor-driver.service  # C++ USB serial motor driver
│       ├── rovac-edge-sensor-hub.service    # C++ USB serial sensor hub driver
│       ├── rovac-edge-rplidar-c1.service    # RPLIDAR C1 driver (USB serial)
│       ├── rovac-edge-mux.service           # cmd_vel priority mux
│       ├── rovac-edge-tf.service            # robot_state_publisher
│       ├── rovac-edge-map-tf.service        # map→odom static TF
│       ├── rovac-edge-health.service        # Edge health publisher
│       ├── rovac-edge-obstacle.service      # Obstacle avoidance (sensor hub)
│       ├── rovac-edge-ps2-joy.service       # PS2 controller input
│       ├── rovac-edge-ps2-mapper.service    # PS2 → velocity commands
│       ├── rovac-edge-sense-hat-panel.service # Sense HAT panel (status display + joystick)
│       ├── rovac-edge-ekf.service           # EKF (DISABLED — run from Mac)
│       └── ...                              # stereo, webcam services
├── ros2_ws/src/
│   ├── rovac_motor_driver/            # C++ USB serial motor driver (ament_cmake)
│   ├── rovac_sensor_driver/           # C++ USB serial sensor hub driver (ament_cmake)
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
│   ├── legacy_scripts/                # QoS relays, Agent watchdog, health_monitor, etc.
│   └── legacy_launch/                 # Pre-systemd launch files (vorwerk_lidar era)
└── docs/
    ├── ros2_reference_card.md         # ROS2 command cheatsheet
    ├── architecture/
    └── guides/
```

## Environment Setup

```bash
# Mac: Activate conda environment
conda activate ros_jazzy

# Source ROS2 environment (sets DDS config, domain ID, peer IPs)
# Auto-detects Mac IP from en0 and syncs to Pi's CycloneDDS config if changed
source ~/robots/rovac/config/ros2_env.sh

# IMPORTANT: Use --no-daemon on macOS — the ROS2 daemon hangs with CycloneDDS
ros2 topic list --no-daemon

# ESP-IDF (for firmware development — NEVER in same shell as conda)
source ~/esp/esp-idf-v5.2/export.sh
```

## ESP32 Motor Firmware Development

```bash
# Option A: Build + flash directly on Pi (preferred — ESP-IDF installed on Pi)
ssh pi@192.168.1.200
sudo systemctl stop rovac-edge-motor-driver
source ~/esp/esp-idf-v5.2/export.sh
cd ~/robots/rovac/hardware/esp32_motor_wireless
idf.py build
idf.py -p /dev/esp32_motor flash
sudo systemctl start rovac-edge-motor-driver

# Option B: Build on Mac, flash via Pi
source ~/esp/esp-idf-v5.2/export.sh  # NOT in conda shell
cd ~/robots/rovac/hardware/esp32_motor_wireless
idf.py build
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

**Pi C++ driver:** `ros2_ws/src/rovac_motor_driver/` — `ament_cmake` package. Build on Pi: `cd ros2_ws && colcon build --packages-select rovac_motor_driver`. Features serial health monitoring: auto-reconnects within 7s if USB re-enumerates (configurable via `serial_rx_timeout` param, default 5s).

## ESP32 Sensor Hub Firmware Development

```bash
# Build + flash on Pi (ESP-IDF v5.2 — use -b 115200 for CP2102 flash speed)
ssh pi@192.168.1.200
sudo systemctl stop rovac-edge-sensor-hub
source ~/esp/esp-idf-v5.2/export.sh
cd ~/robots/rovac/hardware/esp32_sensor_hub
idf.py build
idf.py -p /dev/esp32_sensor -b 115200 flash
sudo systemctl start rovac-edge-sensor-hub
```

**Key firmware files:**
- `main/ultrasonic.c` — HC-SR04 sequential trigger/echo measurement (GPIO)
- `main/cliff_sensor.c` — Sharp GP2Y0A51SK0F ADC reading (ADC1 oneshot)
- `main/sensor_serial.c` — UART0 COBS binary protocol, TX timers (sensor data/diag), RX task
- `main/main.c` — Boot diagnostics (before/after ADC init comparison)

**Shared protocol:** Same `common/serial_protocol.h` as motor controller. Sensor hub uses message types `MSG_SENSOR_DATA` (0x20, 10Hz) and `MSG_SENSOR_DIAG` (0x21, 1Hz).

**Pi C++ driver:** `ros2_ws/src/rovac_sensor_driver/` — `ament_cmake` package. Build on Pi: `cd ros2_ws && colcon build --packages-select rovac_sensor_driver`. Same serial health monitoring pattern as motor driver.

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
When running EKF, `mac_brain_launch.sh` automatically sets `publish_tf: false` on the motor driver (only EKF should publish odom→base_link TF). On exit, it restores `publish_tf: true`. Default is `true` (motor driver publishes TF when EKF is not running).

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
