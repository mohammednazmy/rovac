# ROVAC Project Handoff — March 11, 2026

## What Was Just Completed

### 1. Wireless Micro-ROS Motor Control (DONE, VERIFIED)
The Maker-ESP32 motor controller now runs wirelessly over WiFi using micro-ROS:
- **Firmware**: `hardware/esp32_motor_wireless/` (ESP-IDF v5.2 + micro-ROS Jazzy)
- **WiFi IP**: 192.168.1.221 (static) → micro-ROS Agent on Pi at 192.168.1.200:8888 (UDP)
- **QoS**: All entities use best_effort (eliminates ACK round-trips)
- **MTU**: 1024 bytes (odom ~730 bytes fits in single UDP packet, no fragmentation)
- **Latency**: 119ms median cmd_vel→odom round-trip (was 295ms with reliable QoS)
- **PID**: 50Hz loop, kp=25, ki=60, kd=3, ff_scale=200, ff_offset_left=136, ff_offset_right=132
- **Disconnect detection**: 3s ping interval x 2 failures = 6s detection → auto-reboot for clean reconnect
- **Agent restart recovery**: `ExecStartPost` in systemd runs `scripts/edge/reset_esp32_motor.sh` which waits for Agent to bind port 8888, then sends `!restart` to ESP32 via USB serial. Total recovery ~25s.

### 2. Keyboard Teleop Through Velocity Mux (DONE, VERIFIED)
- `scripts/keyboard_teleop.py` publishes to `/cmd_vel_teleop` (highest mux priority)
- Auto-SSHes to Pi from Mac for lowest latency
- Speed control is coupled: +/- changes both linear [0.05-0.50 m/s] and angular [1.0-6.5 rad/s]
- `cmd_vel_mux.py` priority: teleop (0.5s) > joy (1.0s) > obstacle (0.5s) > nav (1.0s)
- Teleop and joy callbacks forward immediately (bypass timer) for lowest latency

### 3. Repository Cleanup (DONE, COMMITTED, SYNCED)
- **Archived** 9 legacy hardware dirs + 7 legacy scripts to `archive/legacy_hardware/` and `archive/legacy_scripts/`
- **Rewrote** `CLAUDE.md` and `hardware/README.md` to reflect current wireless architecture
- **Updated** `.gitignore` for ESP-IDF artifacts, gateway experiment, vendor dirs
- **Committed** all new tools (motor_characterization, pid_step_response, latency_probe)
- **Synced** to GitHub and Pi — all three locations are clean and identical

## Current System State

```
ESP32 Motor (192.168.1.221)  ←WiFi UDP→  Pi (192.168.1.200:8888)  ←CycloneDDS→  Mac (192.168.1.104)
     micro-ROS XRCE-DDS              micro-ROS Agent                    ROS2 Jazzy
     /odom (20Hz, best_effort)        bridges to CycloneDDS              Nav2, SLAM, teleop
     /tf, /diagnostics                cmd_vel mux                        Foxglove
     /cmd_vel subscriber              robot_state_publisher
```

### Active Services on Pi
- `rovac-edge-uros-agent` — micro-ROS Agent UDP:8888 (primary motor bridge)
- `rovac-edge-mux` — cmd_vel priority mux
- `rovac-edge-tf` — robot_state_publisher
- `rovac-edge-map-tf` — map→odom static TF
- `rovac-edge-ps2-joy` + `rovac-edge-ps2-mapper` — PS2 controller
- `rovac-edge-supersensor` — HC-SR04 ultrasonic
- `rovac-edge-esp32` — **DISABLED** (old USB Python driver, replaced by wireless)
- `rovac-edge-lidar` — enabled but NOT started (LIDAR not connected)

### Key Files
- `hardware/esp32_motor_wireless/` — Active motor firmware (ESP-IDF + micro-ROS)
- `hardware/esp32_at8236_driver/` — USB serial motor driver (fallback)
- `hardware/esp32_xv11_bridge/` — LIDAR ESP32 bridge firmware (ready for upgrade)
- `ros2_ws/src/xv11_lidar_python/` — XV11 LIDAR ROS2 Python driver
- `config/systemd/rovac-edge-uros-agent.service` — Agent systemd unit
- `scripts/keyboard_teleop.py` — Keyboard teleop (coupled linear+angular speed)
- `scripts/edge/reset_esp32_motor.sh` — ESP32 auto-reset after Agent restart

## Next Task: LIDAR ESP32 Micro-ROS Conversion

### Goal
Convert the XV11 LIDAR ESP32 bridge from USB serial to wireless micro-ROS, matching the architecture of the motor controller. The LIDAR module will be a standalone wireless unit: ESP32 + XV11 LIDAR + battery, communicating over WiFi to the same micro-ROS Agent on the Pi.

### Current LIDAR Setup
- **Hardware**: ESP32-WROOM-32 with CP2102 USB (NOT the same board as motor — different ESP32)
- **Current firmware**: `hardware/esp32_xv11_bridge/esp32_xv11_bridge.ino` (Arduino, USB serial)
  - Reads XV11 binary packets from UART (motor control pin GPIO5, data on Serial2)
  - Outputs raw bytes over USB serial to host
  - No LIDAR data processing — just a serial bridge
- **Current ROS2 driver**: `ros2_ws/src/xv11_lidar_python/xv11_lidar_python/xv11_lidar_publisher.py`
  - Runs on Pi, reads serial port, parses XV11 binary packets
  - Accumulates packets into 360-point revolutions
  - Publishes `/scan` (LaserScan) at ~5 Hz
  - Revolution boundary detection: `prev_idx >= 70 && curr_idx <= 10 && packets >= 10`
  - Handles invalid readings (bit 7), RPM calculation (bytes 2-3 / 64.0), stall timeout

### What Needs to Happen
1. **Create new ESP-IDF firmware**: `hardware/esp32_lidar_wireless/` (similar structure to `esp32_motor_wireless/`)
   - Port the XV11 packet parsing + revolution accumulation from Python to C
   - Publish `/scan` (LaserScan) via micro-ROS over WiFi UDP
   - Same WiFi/NVS/LED/debug console pattern as motor firmware
   - Static IP: 192.168.1.222 (next after motor's .221)
   - Same Agent: 192.168.1.200:8888

2. **LaserScan message considerations**:
   - 360 ranges (float32) + 360 intensities (float32) = 2880 bytes payload
   - With MTU=1024 and STREAM_HISTORY=8, max reliable message ~8KB — fits comfortably
   - Use best_effort QoS (same as motor)
   - `frame_id = "laser_frame"`, angle_min=0, angle_max=2*PI, 360 increments

3. **Reference files for porting**:
   - `ros2_ws/src/xv11_lidar_python/xv11_lidar_python/xv11_lidar_publisher.py` — Revolution logic, LaserScan fields
   - `hardware/esp32_xv11_bridge/esp32_xv11_bridge.ino` — XV11 UART reading, packet structure
   - `hardware/esp32_motor_wireless/` — Complete micro-ROS ESP-IDF project template (WiFi, NVS, LED, uros, debug console)

4. **Hardware wiring**: The XV11 data line connects to the ESP32's UART RX. The XV11 motor control PWM connects to an ESP32 GPIO. Check `esp32_xv11_bridge.ino` for exact pin mapping.

### Architecture After Completion
```
ESP32 Motor (.221)  ─┐
                     ├── WiFi UDP ──→ micro-ROS Agent (Pi :8888) ──→ CycloneDDS ──→ Mac
ESP32 LIDAR (.222)  ─┘
```

Three wireless components on the robot: Pi (edge compute), ESP32 Motor (motors+encoders+battery), ESP32 LIDAR (XV11+battery). No USB cables between them.

### Known Gotchas
- ESP-IDF and conda ros_jazzy MUST NOT be sourced in the same shell
- micro-ROS library rebuild: delete `libmicroros.a` then `idf.py build`. Requires `ament_package` in both ESP-IDF python and conda base python.
- Best_effort QoS for all publishers (reliable causes WiFi latency issues)
- MTU=1024 in `app-colcon.meta` — must rebuild micro-ROS library if changed
- CycloneDDS type hash quirk: micro-ROS topics may intermittently drop from `ros2 topic list` but data still flows
- LaserScan with 360 floats x 2 arrays = ~3KB — verify it fits in single XRCE-DDS fragment with MTU=1024
