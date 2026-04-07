# ROVAC Hardware

This document describes the hardware that matches the current USB-serial ESP32 + Pi edge architecture and points away from older iteration-era hardware that remains in the repository.

## Current Hardware Stack

| Component | Interface | Runtime owner | Status | Repo path |
|-----------|-----------|---------------|--------|-----------|
| Maker-ESP32 motor controller | USB serial `/dev/esp32_motor` @ 460800 | Pi edge stack | Core | `hardware/esp32_motor_wireless/` |
| BNO055 IMU | I2C on ESP32 | ESP32 firmware | Core | `hardware/esp32_motor_wireless/main/bno055.*` |
| JGB37-520R60-12 motors + encoders | Direct to ESP32 motor board | ESP32 firmware | Core | `hardware/greartisan-zgb37rg-motor/` |
| RPLIDAR C1 | USB serial `/dev/rplidar_c1` | Pi edge stack | Core, external ROS driver expected | `hardware/rplidar_c1/` |
| Super Sensor | USB serial `/dev/super_sensor` | Pi edge stack | Optional but integrated | `super_sensor/`, `hardware/super_sensor/` |
| Samsung Galaxy A16 sensors | rosbridge WebSocket (Pi :9090) | Pi edge stack | Optional | `hardware/android_phone_sensors/` |
| Stereo cameras | USB | Pi edge stack | Optional | `hardware/stereo_cameras/` |
| USB webcam | USB `/dev/webcam` | Pi edge stack | Optional | `hardware/webcam/` |

## Communication Topology

```text
Motors + encoders + BNO055
        |
        v
Maker-ESP32 firmware
        |
        | USB serial @ 460800, COBS binary protocol
        v
Pi 5 edge stack
  - rovac_motor_driver
  - lidar
  - cmd_vel mux
  - TF
  - rosbridge
  - optional peripherals
        |
        | CycloneDDS, ROS_DOMAIN_ID=42
        v
Mac brain
  - SLAM Toolbox
  - Nav2
  - EKF
  - Foxglove
  - teleop
```

## Motor Control Stack

| Layer | Path | Responsibility |
|------|------|----------------|
| ESP32 firmware | `hardware/esp32_motor_wireless/main/` | PWM, encoder counting, odometry, BNO055, watchdog, serial transport |
| Shared protocol | `common/serial_protocol.h` | Message types, payload layout, CRC, and frame helpers |
| Pi driver | `ros2_ws/src/rovac_motor_driver/` | Publishes `/odom`, `/imu/data`, `/diagnostics`, optional `/tf`, and forwards `/cmd_vel` |

### Motor controller details

| Attribute | Value |
|-----------|-------|
| Board | NULLLAB Maker-ESP32 |
| MCU | ESP32-WROOM-32E |
| Transport | USB serial, COBS-framed binary protocol |
| Baud rate | 460800 |
| Motors | 2x JGB37-520R60-12 |
| Encoder resolution | 2640 ticks/rev |
| IMU | Adafruit BNO055 |
| Power | 12V barrel input, motor switch must be ON |

## Lidar

The current design targets the Slamtec RPLIDAR C1 on the Pi.

| Attribute | Value |
|-----------|-------|
| Device | `/dev/rplidar_c1` |
| Runtime service | `config/systemd/rovac-edge-rplidar-c1.service` |
| Expected ROS package | `ros2_ws/src/rplidar_ros` |
| Hardware notes | `hardware/rplidar_c1/` |

Note: `rplidar_ros` is cloned separately on the Pi (patched Slamtec driver) and is not tracked in the shared Git repo. The service runs on the Pi only.

## Phone Integration

The Samsung Galaxy A16 is optional. It is not required for the core drive stack.

The phone connects via rosbridge WebSocket on Pi port 9090. The app source is `hardware/android_phone_sensors/`.

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/phone/imu` | Imu | 50 Hz | Phone IMU via rosbridge |
| `/phone/gps/fix` | NavSatFix | 1 Hz | Phone GPS via rosbridge |
| `/phone/camera/image_raw/compressed` | CompressedImage | ~2 FPS | Phone rear camera (JPEG) |

## Active Vs Reference Directories

### Start here

- `hardware/esp32_motor_wireless/`
- `hardware/rplidar_c1/`
- `hardware/android_phone_sensors/`
- `hardware/stereo_cameras/`
- `hardware/webcam/`
- `hardware/super_sensor/`
- `hardware/greartisan-zgb37rg-motor/`

### Useful reference material

- `hardware/maker_esp32/`
- `hardware/as5600-magnetic-encoder/`
- `hardware/arduino-nano-atmega328p/`
- `hardware/hc-sr04-ultrasonic/`
- `hardware/yahboom-usb3-hub/`

### Historical or superseded experiments

- `hardware/esp32_xv11_bridge/`
- `hardware/esp32_gateway/`
- `hardware/esp32_at8236_driver/`
- `hardware/yahboom-at8236-motor-driver/`
- `hardware/yahboom-ir-tracking-sensor/`
- `hardware/nrf24l01-pa-lna-transceiver/`

Those directories are kept for reference, parts reuse, or earlier iterations. They are not part of the current bringup path documented in the root README and `docs/`.

## Power Budget

| Component | Typical | Peak | Notes |
|-----------|---------|------|-------|
| Raspberry Pi 5 | 3.0 A | 5.0 A | 5V via USB-C |
| ESP32 + motors (2x) | 0.5 A | 4.0 A | 12V barrel, depends on load |
| RPLIDAR C1 | 0.4 A | 0.6 A | 5V USB |
| Super Sensor (Nano) | 0.05 A | 0.1 A | 5V USB |
| Phone | 0.5 A | 1.0 A | 5V USB |
| **Total** | **~4.5 A** | **~11 A** | |

**UVLO warning**: The TB67H450FNG motor drivers lock out below ~6.8V input. If battery sags under load, motors will cut out without warning.

## PID Reference (calibrated March 2026)

These values are in the ESP32 firmware but documented here for quick reference:

| Parameter | Value |
|-----------|-------|
| kp | 25 |
| ki | 60 |
| kd | 3 |
| ff_scale | 200 PWM/(m/s) |
| ff_offset_left | 136 (stiction) |
| ff_offset_right | 132 (stiction) |
| max_linear_speed | 0.57 m/s |
| max_angular_speed | 6.5 rad/s |

Steady-state error <1%, settling time ~400ms. See `tools/motor_characterization.py` for tuning.

## Operator Rules

- The motor power switch must be ON and battery voltage should stay above 8V (6.8V UVLO threshold).
- Never publish directly to `/cmd_vel`; use mux inputs such as `/cmd_vel_teleop` or `/cmd_vel_joy`.
- Build and flash ESP32 firmware from a shell that has only ESP-IDF sourced (never in conda).
- Treat `docs/robot_dimensions.md` and `ros2_ws/src/tank_description/urdf/tank.urdf` as the geometry source of truth.
