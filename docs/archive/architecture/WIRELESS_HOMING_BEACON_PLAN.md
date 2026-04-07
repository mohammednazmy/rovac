# ROVAC Wireless Homing Beacon Architecture

## Overview

Two ESP32 nodes on the robot communicate wirelessly with a stationary Raspberry Pi 5
via micro-ROS over WiFi UDP. The Pi acts as the brain AND a physical homing beacon.

```
┌────────────────────────────────────┐
│          ROBOT (mobile)            │
│                                    │
│  Battery ──► Motor ESP32 (WiFi)    │     ))) WiFi UDP )))
│               ├── Motor L          │  ◄──────────────────►  ┌──────────────────┐
│               ├── Motor R          │                        │   RPi 5 (static) │
│               ├── Encoders (PCNT)  │                        │   192.168.1.200  │
│               └── Local PID        │                        │                  │
│                                    │                        │  micro-ROS Agent │
│  Battery ──► LIDAR ESP32 (WiFi)    │  ◄──────────────────►  │  Nav2 + SLAM     │
│               ├── XV11 LIDAR       │                        │  robot_state_pub │
│               └── Motor PWM        │                        │  cmd_vel_mux     │
└────────────────────────────────────┘                        │  PS2 controller  │
                                                              │                  │
                                                              │  Position: (0,0) │
                                                              │  = HOME           │
                                                              └──────────────────┘
```

## Why This Works Now (vs. Failed Gateway Attempt)

The Gateway experiment (2026-03-03) failed because:
- micro-ROS Agent on **Mac** used Fast-DDS internally
- ROS2 on **Mac** used CycloneDDS
- Two different DDS implementations on the same machine couldn't discover each other

Now:
- micro-ROS Agent runs on **Pi** → uses CycloneDDS (Pi's native RMW)
- ROS2 on **Pi** → uses CycloneDDS
- **Same DDS implementation** on same machine = localhost discovery works
- ESP32→Agent communication uses XRCE-DDS (custom UDP), NOT DDS → no cross-vendor issue

## Network

| Device | IP | Role |
|--------|-----|------|
| Pi 5 | 192.168.1.200 | Brain + Agent + Homing Beacon |
| Motor ESP32 | 192.168.1.221 | Motors + Encoders + PID + Odom |
| LIDAR ESP32 | 192.168.1.222 | XV11 LIDAR + Scan |
| Mac (optional) | 192.168.1.104 | Foxglove / visualization |
| micro-ROS Agent | Pi:8888 (UDP) | Bridges XRCE-DDS → CycloneDDS |
| WiFi AP | 192.168.1.254 | AT&T router ("Hurry") |

## ROS2 Topic Map

| Topic | Type | Source | Rate | Transport |
|-------|------|--------|------|-----------|
| /odom | Odometry | Motor ESP32 | 20 Hz | micro-ROS → Agent |
| /tf (odom→base_link) | TFMessage | Motor ESP32 | 20 Hz | micro-ROS → Agent |
| /scan | LaserScan | LIDAR ESP32 | 5 Hz | micro-ROS → Agent |
| /cmd_vel | Twist | Pi (Nav2/mux) | 10-20 Hz | Agent → Motor ESP32 |
| /diagnostics | DiagnosticArray | Both ESP32s | 1 Hz | micro-ROS → Agent |
| /tf (static) | TFMessage | Pi (URDF) | latched | Native CycloneDDS |

## Phase 1: Motor ESP32 Firmware (ESP-IDF + micro-ROS)

**Location**: `hardware/esp32_motor_wireless/`

### Reusable from Gateway (copy verbatim or adapt):
- wifi.c/h — WiFi STA, static IP, auto-reconnect
- nvs_config.c/h — NVS read/write
- odometry.c/h — Differential drive math (pure C, no dependencies)
- led_status.c/h — WS2812 status LED
- debug_console.c/h — USB debug shell
- motor_control.c/h — cmd_vel → wheel velocities (adapt: remove UART, add PID)
- uros.c/h — micro-ROS node (adapt: remove LIDAR, add direct encoder/motor)

### New modules to write:
- motor_driver.c/h — Direct TB67H450FNG PWM via LEDC
- encoder_reader.c/h — Direct PCNT hardware encoder reading
- pid_controller.c/h — C port of WheelPID from esp32_at8236_driver.py
- oled_display.c/h — Optional SSD1306 status (Maker-ESP32 only)

### FreeRTOS Architecture:
- Core 0: WiFi + micro-ROS (odom publish, cmd_vel subscribe, diagnostics)
- Core 1: PID loop at 50Hz (encoder read → velocity → PID → motor PWM)

### PID Parameters (calibrated):
- kp=40, ki=300, kd=10
- ff_scale=200, ff_offset_left=136, ff_offset_right=132
- max_linear_speed=0.57 m/s

## Phase 2: LIDAR ESP32 Firmware (ESP-IDF + micro-ROS)

**Location**: `hardware/esp32_lidar_wireless/`

### Reusable from Gateway:
- wifi.c/h, nvs_config.c/h, led_status.c/h, debug_console.c/h
- lidar_scan.c/h — XV11 packet accumulation (pure C)

### New modules:
- lidar_uart.c/h — Direct XV11 UART reading (port from Arduino bridge)
- lidar_motor.c/h — XV11 motor PWM + RPM PID (port from Arduino bridge)
- uros_lidar.c/h — Stripped micro-ROS node (1 publisher: /scan)

## Phase 3: Pi Setup

### 3A: micro-ROS Agent
```bash
docker pull microros/micro-ros-agent:jazzy
docker run -d --restart=always --net=host --name rovac_uros_agent \
  microros/micro-ros-agent:jazzy udp4 --port 8888 -v4
```

### 3B: Bringup script
`scripts/pi_wireless_bringup.sh` — adapted from mac_wireless_bringup.sh
Starts: Agent + robot_state_publisher + cmd_vel_mux + PS2 joy + map→odom TF

### 3C: Systemd
`rovac-wireless.target` with services for Agent, RSP, mux, PS2

## Phase 4: Integration Testing

1. Motor ESP32 standalone → verify /odom, /tf, /cmd_vel on Pi
2. LIDAR ESP32 standalone → verify /scan on Pi
3. Both ESP32s + full Pi stack → SLAM mapping + Nav2 navigation
4. Homing beacon test: NavigateToPose(0, 0, 0)

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| 4MB flash too small | MEDIUM | Gateway fits in 4MB. Each node is smaller. Cut OLED first |
| WiFi latency affects control | LOW | PID runs locally on ESP32. WiFi only carries targets |
| WiFi dropout mid-drive | MEDIUM | 500ms watchdog + agent-loss detection stop motors |
| Two nodes sharing Agent port | LOW | Standard micro-ROS. Agent multiplexes by client address |

## Homing Beacon

The Pi has a known static position (0, 0, 0) in the SLAM map. "Go home" is simply:
```
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: 'map'}, pose: {position: {x: 0, y: 0}}}}"
```

For precise docking (last 50cm), future options:
- ArUco marker on Pi + ESP32-CAM on robot
- IR beacon on Pi + IR sensor on robot
- Good odometry alone (±5cm accuracy)
