# ROVAC Hardware Documentation

This directory contains documentation for hardware components used in the ROVAC robot project.

## Active Hardware (In Production)

| Component | Device Path | Purpose | Service |
|-----------|-------------|---------|---------|
| [Hiwonder ROS Controller V1.2](./hiwonder-ros-controller/) | `/dev/hiwonder_board` | Motor control, IMU (QMI8658), odometry, battery | `rovac-edge-hiwonder` |
| [USB LIDAR (XV-11)](./lidar_usb/) | `/dev/esp32_lidar` | 360° laser scanning (currently disconnected) | `rovac-edge-lidar` |
| [Super Sensor](./super_sensor/) | `/dev/super_sensor` | 4x ultrasonic + RGB LED + servo | `rovac-edge-supersensor` |
| [Stereo Cameras](./stereo_cameras/) | `/dev/video0`, `/dev/video1` | Stereo depth + obstacle detection | `rovac-edge-stereo.target` |
| [Samsung Galaxy A16](./phone_sensors/) | USB (ADB) | GPS, IMU, cameras, magnetometer | `rovac-edge-phone-sensors` |
| [NexiGo N930E Webcam](./webcam/) | `/dev/webcam` | USB webcam (1080p) | `rovac-edge-webcam` |

## Phone Hardware (Samsung Galaxy A16)

The robot uses an Android phone as a sensor platform, providing GPS for outdoor navigation, high-quality IMU, magnetometer, and multiple cameras.

### Phone Specifications

| Attribute | Value |
|-----------|-------|
| **Model** | Samsung Galaxy A16 (SM-A166M) |
| **OS** | Android 15 |
| **Connection** | USB to Raspberry Pi (ADB) |
| **Sensor App** | SensorServer v6.4.0 |

### Phone Sensors

| Sensor | Type | Rate | ROS2 Topic |
|--------|------|------|------------|
| **GPS** | GNSS (SPOTNAV) | 1 Hz | `/phone/gps/fix` |
| **Accelerometer** | LSM6DSOTR | ~45 Hz | `/phone/imu` |
| **Gyroscope** | LSM6DSOTR | ~45 Hz | `/phone/imu` |
| **Magnetometer** | MXG4300S | ~6 Hz | `/phone/magnetic_field` |
| **Orientation** | Fused | ~45 Hz | `/phone/orientation` |

### Phone Cameras

| Camera | ID | Position | Max Resolution | Topic |
|--------|----|---------:|----------------|-------|
| Back Main | 0 | Rear | 4080x3060 | `/phone/camera/back/image_raw` |
| Front | 1 | Front | 4128x3096 | `/phone/camera/front/image_raw` |
| Back Wide | 2 | Rear | 2576x1932 | `/phone/camera/wide/image_raw` |
| Front Secondary | 3 | Front | 3712x2556 | `/phone/camera/front2/image_raw` |

**Note:** Only one camera can stream at a time (Android limitation). Use `switch_camera.sh` to change cameras.

### Phone Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Samsung Galaxy A16                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ SensorServer App (WebSocket on port 8080)                 │  │
│  │   • Accelerometer (500 Hz capable)                        │  │
│  │   • Gyroscope (500 Hz capable)                            │  │
│  │   • Magnetometer                                          │  │
│  │   • Rotation Vector (fused orientation)                   │  │
│  └─────────────────────────────────┬─────────────────────────┘  │
│  ┌─────────────────────────────────┼─────────────────────────┐  │
│  │ Cameras                         │                         │  │
│  │   • Back (0): 4080x3060         │                         │  │
│  │   • Front (1): 4128x3096        │                         │  │
│  │   • Wide (2): 2576x1932         │                         │  │
│  │   • Front2 (3): 3712x2556       │                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ USB Cable
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Raspberry Pi 5                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ADB (Android Debug Bridge)                                  │ │
│  │   • Port forward: tcp:8080 → phone:8080                     │ │
│  │   • GPS polling via: adb shell dumpsys location             │ │
│  │   • Camera via: scrcpy --video-source=camera                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ phone_sensors_ros2_node.py                                  │ │
│  │   • WebSocket client → SensorServer                         │ │
│  │   • Publishes: /phone/imu, /phone/magnetic_field            │ │
│  │   • Publishes: /phone/gps/fix, /phone/orientation           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ v4l2loopback + scrcpy → multi_camera_publisher.py           │ │
│  │   • /dev/video10-13 → /phone/camera/{name}/image_raw        │ │
│  │   • Compressed: /phone/camera/{name}/image_raw/compressed   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Phone Setup

See [phone_sensors/README.md](./phone_sensors/README.md) for sensor setup and [phone_cameras/README.md](./phone_cameras/README.md) for camera setup.

**Quick Setup:**
1. Install **SensorServer** app from F-Droid or GitHub
2. Configure app: Bind Address = `0.0.0.0`, enable sensors
3. Enable USB Debugging on phone
4. Connect phone via USB to Pi
5. Start services: `sudo systemctl start rovac-edge-phone-sensors rovac-phone-cameras`

## Robot Board Hardware

### Hiwonder ROS Robot Controller V1.2 (Active)

The main control board for motors and onboard IMU. Replaced the Yahboom ROS Expansion Board V3.0.

| Attribute | Value |
|-----------|-------|
| **MCU** | STM32F407VET6 (Cortex-M4, 168 MHz) |
| **IMU** | QMI8658 (6-axis: accel + gyro only, **NO magnetometer**) |
| **USB Chip** | CH9102 (`1a86:55d4`) |
| **Device** | `/dev/hiwonder_board` (udev symlink → `/dev/hiwonder_board`, matched by serial `5B32013768`) |
| **Baud Rate** | 1,000,000 (1 Mbaud) |
| **Motors** | 4x DC motor channels (2 active: M1 left, M2 right for tank) |
| **Encoders** | Internal PID only (100 Hz TIM7 loop) — NOT sent to host |
| **Motor Config** | TANKBLACK: left motor inverted, M1(left)/M2(right) |
| **Firmware** | RRCLite (vendor docs removed from Pi during cleanup) |
| **Power Input** | 6-12V DC |
| **Motor Switch** | Physical switch must be ON for motors to spin |

See [hiwonder-ros-controller/README.md](./hiwonder-ros-controller/README.md) for full documentation.

### Yahboom ROS Expansion Board V3.0 (Replaced)

Previous motor/IMU board. Disabled and replaced by Hiwonder V1.2. Documentation retained for reference.

See [yahboom-ros-expansion-board-v3/README.md](./yahboom-ros-expansion-board-v3/README.md) for legacy documentation.

### XV-11 LIDAR (USB)

360° laser scanner for SLAM and obstacle detection.

| Attribute | Value |
|-----------|-------|
| **Type** | Neato XV-11 |
| **Range** | 0.06 - 5m |
| **Resolution** | 360 points per scan |
| **Frequency** | ~5-10 Hz |
| **Interface** | USB (via CH340) |
| **Device** | `/dev/usb_lidar` |

See [lidar_usb/README.md](./lidar_usb/docs/README.md) for setup and calibration.

### Super Sensor Module

Arduino Nano-based sensor module with ultrasonic array.

| Attribute | Value |
|-----------|-------|
| **MCU** | Arduino Nano (ATmega328P) |
| **Ultrasonic** | 4x HC-SR04 |
| **LED** | RGB LED |
| **Servo** | 180° servo |
| **Interface** | USB Serial |
| **Device** | `/dev/super_sensor` |

See [super_sensor/README.md](./super_sensor/README.md) for documentation.

## Deprecated Hardware

| Component | Purpose | Status |
|-----------|---------|--------|
| [Yahboom ROS Expansion Board V3.0](./yahboom-ros-expansion-board-v3/) | Motor/IMU (STM32F103, MPU9250) | **Replaced** by Hiwonder V1.2 |
| [Yahboom BST-4WD Expansion Board](./yahboom-bst-4wd-expansion-board/) | Motor driver (TB6612FNG) | **Deprecated** - Replaced by ROS V3.0 |

## Hardware Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              12V LiPo Battery                                │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐    ┌───────────────────────┐    ┌─────────────────────┐
│ Yahboom USB Hub │    │ Hiwonder ROS Ctrl V1.2│    │ Phone (USB Power)   │
│ (Power only)    │    │ (6-12V input)         │    │                     │
└────────┬────────┘    ├───────────────────────┤    └──────────┬──────────┘
         │             │ • STM32F407VET6 MCU   │               │
         │             │ • QMI8658 IMU (6-axis)│               │
         │             │ • 2x Motor (tank)     │               │
         │             │ • Pi 5V/5A power out  │               │
         │             └───────────┬───────────┘               │
         │                         │                           │
         │    USB Serial           │ USB-C Power               │ USB (ADB)
         │    (/dev/hiwonder_board)       │                           │
         │                         ▼                           │
         │             ┌───────────────────────────────────────┼──────────────┐
         │             │                Raspberry Pi 5                        │
         │             ├──────────────────────────────────────────────────────┤
         │             │                                                      │
         └────────────►│  USB Ports:                                          │
                       │    • /dev/hiwonder_board        → Hiwonder ROS Controller    │
┌──────────────┐       │    • /dev/usb_lidar      → XV-11 LIDAR              │
│   XV-11      │──────►│    • /dev/super_sensor   → Super Sensor              │
│   LIDAR      │  USB  │    • Phone ADB           → Samsung Galaxy A16        │
└──────────────┘       │                                                      │
                       │  Services:                                           │
┌──────────────┐       │    • rovac-edge-hiwonder    (motors, IMU, odom)     │
│ Super Sensor │──────►│    • rovac-edge-lidar       (360° scan)             │
│ (Arduino)    │  USB  │    • rovac-edge-supersensor (ultrasonic)            │
└──────────────┘       │    • rovac-edge-phone-sensors (IMU, GPS, mag)       │
                       │    • rovac-phone-cameras    (camera stream)          │
                       │                                                      │
                       └────────────────────────────┬─────────────────────────┘
                                                    │
                                                    │ Ethernet/WiFi
                                                    │ (192.168.1.x)
                                                    ▼
                                          ┌───────────────────┐
                                          │   MacBook Pro     │
                                          │   (Brain)         │
                                          │   192.168.1.104   │
                                          ├───────────────────┤
                                          │ • Nav2 stack      │
                                          │ • SLAM toolbox    │
                                          │ • Path planning   │
                                          │ • Foxglove viz    │
                                          └───────────────────┘
```

## Sensor Summary

| Sensor | Source | Rate | Purpose |
|--------|--------|------|---------|
| **LIDAR** | XV-11 | ~5-10 Hz | SLAM, obstacle detection |
| **Board IMU** | QMI8658 | ~72 Hz | Orientation, motion (6-axis, no magnetometer) |
| **Dead-reckoning Odom** | Commanded speeds + gyro Z | 20 Hz | Position tracking |
| **Ultrasonic (4x)** | HC-SR04 | ~10 Hz | Close obstacle detection |
| **Phone GPS** | GNSS | 1 Hz | Outdoor positioning |
| **Phone IMU** | LSM6DSOTR | ~45 Hz | Backup IMU |
| **Phone Magnetometer** | MXG4300S | ~6 Hz | Compass (outdoor) |
| **Phone Camera** | Back/Front/Wide | ~12 Hz | Visual sensing |
| **USB Webcam** | NexiGo N930E | ~16 Hz | Forward vision, navigation |

## Sensor Redundancy

Multiple sensors provide overlapping coverage for reliability:

| Measurement | Primary Source | Secondary Source |
|-------------|----------------|------------------|
| **Position (indoor)** | Wheel odometry (`/odom`) | LIDAR SLAM (`/map`) |
| **Position (outdoor)** | Phone GPS (`/phone/gps/fix`) | Wheel odometry |
| **Orientation** | Board IMU (`/imu/data`) | Phone IMU (`/phone/imu`) |
| **Heading** | Phone magnetometer (`/phone/magnetic_field`) | IMU gyro Z integration (drift-prone) |
| **Obstacles** | LIDAR (`/scan`) | Ultrasonic (`/super_sensor/*`) |

## Device Paths (udev)

All devices use udev rules for persistent naming:

| Device | Symlink | Vendor:Product |
|--------|---------|----------------|
| Hiwonder Board (UART1) | `/dev/hiwonder_board` | 1a86:55d4 (CH9102, serial `5B32013768`) |
| Hiwonder Board (UART2) | `/dev/hiwonder_uart2` | 1a86:55d4 (CH9102, serial `5B32013767`) — unused by firmware |
| XV-11 LIDAR | `/dev/usb_lidar` | 10c4:ea60 (CP210x) |
| Super Sensor | `/dev/super_sensor` | 1a86:7523 (CH340) |
| USB Webcam | `/dev/webcam` | 1bcf:2284 (NexiGo) |
| Phone | ADB via USB | N/A |

## Power Budget

| Component | Voltage | Current (Typical) | Current (Max) |
|-----------|---------|-------------------|---------------|
| Raspberry Pi 5 | 5V | 2.5A | 5A |
| Hiwonder Board (logic) | 5V | 0.2A | 0.5A |
| Motors (4x) | 12V | 0.5A each | 1.5A each |
| XV-11 LIDAR | 5V | 0.15A | 0.3A |
| Super Sensor | 5V | 0.1A | 0.2A |
| Phone | 5V (USB) | 0.5A | 1.5A |
| **Total** | - | ~5A | ~12A |

## Documentation Index

| Document | Description |
|----------|-------------|
| [hiwonder-ros-controller/README.md](./hiwonder-ros-controller/README.md) | Motor/IMU board (active — Hiwonder V1.2) |
| [yahboom-ros-expansion-board-v3/README.md](./yahboom-ros-expansion-board-v3/README.md) | Old motor/IMU board (replaced) |
| [lidar_usb/docs/README.md](./lidar_usb/docs/README.md) | LIDAR module setup and calibration |
| [super_sensor/README.md](./super_sensor/README.md) | Super Sensor module documentation |
| [phone_sensors/README.md](./phone_sensors/README.md) | Phone IMU/GPS/Magnetometer integration |
| [phone_cameras/README.md](./phone_cameras/README.md) | Phone camera streaming setup |
| [webcam/README.md](./webcam/README.md) | USB webcam setup and streaming |
