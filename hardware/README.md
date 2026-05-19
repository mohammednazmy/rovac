# ROVAC Hardware

ROVAC is a general-purpose autonomous mobile robot built on a Yahboom G1 Tank
(tracked) chassis. This document is the hardware index for the current
USB-serial ESP32 + Pi edge architecture and points away from older
iteration-era hardware now kept under `archive/`.

## Current Hardware Stack

| Component | Interface | Runtime owner | Status | Repo path |
|-----------|-----------|---------------|--------|-----------|
| Maker-ESP32 motor controller | USB serial `/dev/esp32_motor` @ 460800 | Pi edge stack | Core | `hardware/esp32_motor_wireless/` |
| BNO055 IMU | I2C on ESP32 | ESP32 firmware | Core | `hardware/esp32_motor_wireless/main/bno055.*` |
| JGB37-520R60-12 motors + encoders | Direct to ESP32 motor board | ESP32 firmware | Core | `hardware/greartisan-zgb37rg-motor/` |
| RPLIDAR C1 | USB serial `/dev/rplidar_c1` | Pi edge stack | Core, external ROS driver expected | `hardware/rplidar_c1/` |
| ESP32 sensor hub (4x HC-SR04 + 2x Sharp IR cliff) | USB serial `/dev/esp32_sensor` @ 460800 | Pi edge stack | Core | `hardware/esp32_sensor_hub/` |
| Dual OV5647 NoIR stereo cameras | Pi 5 CSI | Pi edge stack | Core | `ros2_ws/src/rovac_stereo_camera/` |
| Raspberry Pi Sense HAT (status LED panel + joystick) | Pi I2C / GPIO | Pi edge stack | Core | `hardware/rpi_sense_hat/` |

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
  - rovac_sensor_driver
  - lidar
  - cmd_vel mux
  - TF
  - stereo cameras
  - Sense HAT status panel
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

## Sensor Hub

The ESP32 sensor hub (ESP32-DevKitV1) handles short-range proximity and cliff
detection. It connects to the Pi over USB serial using the same COBS binary
protocol as the motor controller.

| Attribute | Value |
|-----------|-------|
| Device | `/dev/esp32_sensor` |
| Baud rate | 460800 |
| Ultrasonic | 4x HC-SR04 (front / rear / left / right) |
| Cliff | 2x Sharp GP2Y0A51SK0F IR (front / rear) |
| Runtime service | `config/systemd/rovac-edge-sensor-hub.service` |
| Pi driver | `ros2_ws/src/rovac_sensor_driver/` |
| Firmware | `hardware/esp32_sensor_hub/` |

It publishes `/sensors/ultrasonic/*`, `/sensors/cliff/*`, and `/obstacle/points`.

> Phone integration is retired. Android phone sensors (IMU / GPS / camera) were
> removed on 2026-04-11 — the BNO055 replaced the phone IMU. The app source
> moved to `archive/legacy_hardware/android_phone_sensors/`.

## Active Vs Reference Directories

### Start here (active hardware)

- `hardware/esp32_motor_wireless/` — motor controller firmware
- `hardware/esp32_sensor_hub/` — sensor hub firmware
- `hardware/rplidar_c1/` — RPLIDAR C1
- `hardware/greartisan-zgb37rg-motor/` — drive motors
- `hardware/rpi_sense_hat/` — Sense HAT status panel
- `hardware/hc-sr04-ultrasonic/` — ultrasonic sensor docs
- `hardware/sharp-gp2y0a51sk0f-ir-distance/` — IR cliff sensor docs

### Useful reference material

- `hardware/maker_esp32/`
- `hardware/as5600-magnetic-encoder/`
- `hardware/arduino-nano-atmega328p/`
- `hardware/yahboom-usb3-hub/`

### Retired / archived

The following hardware was retired and moved out of `hardware/`. It is not
part of the current bringup path. Path references should point at `archive/`.

- Android phone sensors (IMU / GPS / camera) — retired 2026-04-11, replaced by
  the BNO055. → `archive/legacy_hardware/android_phone_sensors/`,
  `archive/legacy_hardware/phone_sensors/`, `archive/legacy_hardware/phone_cameras/`
- Super Sensor (Arduino-Nano proximity module) — replaced by the ESP32 sensor
  hub. → `archive/legacy_hardware/super_sensor/`,
  `archive/legacy_hardware/super_sensor_desktop_app/`
- USB webcams — replaced by the CSI stereo cameras. →
  `archive/legacy_hardware/webcam/`, `archive/legacy_hardware/stereo_cameras_usb/`
- AT8236 Python motor driver / Yahboom AT8236 driver board → `archive/legacy_hardware/esp32_at8236_driver/`
- L298N motor driver firmware → `archive/legacy_hardware/esp32_l298n_firmware/`
- Hiwonder ROS controller → `archive/legacy_hardware/hiwonder-ros-controller/`
- WiFi micro-ROS / XV11 lidar bridges → `archive/legacy_hardware/esp32_lidar_wireless/`,
  `archive/legacy_hardware/esp32_xv11_bridge/`

## Power Budget

| Component | Typical | Peak | Notes |
|-----------|---------|------|-------|
| Raspberry Pi 5 | 3.0 A | 5.0 A | 5V via USB-C |
| ESP32 + motors (2x) | 0.5 A | 4.0 A | 12V barrel, depends on load |
| RPLIDAR C1 | 0.4 A | 0.6 A | 5V USB |
| ESP32 sensor hub | 0.05 A | 0.1 A | 5V USB |
| **Total** | **~4.0 A** | **~10 A** | |

**UVLO warning**: The TB67H450FNG motor drivers lock out below ~6.8V input. If battery sags under load, motors will cut out without warning.

## PID Reference

The canonical PID / feed-forward calibration is maintained in
`docs/guides/motor_tuning.md` ("Quick reference — canonical NVS calibration"),
which is the single source of truth for tuned values. The live values are
stored in ESP32 NVS; read them with `tools/motor_params_cli.py dump`.

Drive envelope: max linear speed 0.57 m/s, max angular speed 6.5 rad/s.

## Operator Rules

- The motor power switch must be ON and battery voltage should stay above 8V (6.8V UVLO threshold).
- Never publish directly to `/cmd_vel`; use mux inputs such as `/cmd_vel_teleop` or `/cmd_vel_joy`.
- Build and flash ESP32 firmware from a shell that has only ESP-IDF sourced (never in conda).
- Treat `docs/robot_dimensions.md` and `ros2_ws/src/tank_description/urdf/tank.urdf` as the geometry source of truth.
