# ROVAC Hardware Documentation

Hardware components for the ROVAC mobile robot (Yahboom G1 Tank chassis), March 2026.

## Active Hardware

| Component | Interface | Purpose | Service / Agent |
|-----------|-----------|---------|-----------------|
| [NULLLAB Maker-ESP32](./maker_esp32/) | WiFi UDP (micro-ROS) | Motor control, encoders, odometry | micro-ROS Agent on Pi |
| [ESP32 XV-11 LIDAR Bridge](./esp32_xv11_bridge/) | USB `/dev/esp32_lidar` | 360 laser scanning (not yet connected) | `rovac-edge-lidar` |
| [Super Sensor](./super_sensor/) | USB `/dev/super_sensor` | 4x ultrasonic + RGB LED + servo | `rovac-edge-supersensor` |
| [Stereo Cameras](./stereo_cameras/) | USB `/dev/video0`, `/dev/video1` | Stereo depth + obstacle detection | `rovac-edge-stereo.target` |
| [Samsung Galaxy A16](./phone_sensors/) | USB (ADB) | GPS, IMU, cameras, magnetometer | `rovac-edge-phone-sensors` |
| [NexiGo N930E Webcam](./webcam/) | USB `/dev/webcam` | USB webcam (1080p) | `rovac-edge-webcam` |

## Architecture

```
                              12V DC Power
                                  |
            +---------------------+---------------------+
            |                     |                     |
            v                     v                     v
   +------------------+  +------------------+  +------------------+
   | NULLLAB Maker-   |  | Raspberry Pi 5   |  | Phone (USB pwr)  |
   | ESP32 (motor)    |  | (Edge Computer)  |  | Samsung A16      |
   | 192.168.1.221    |  | 192.168.1.200    |  |                  |
   +------------------+  +------------------+  +------------------+
   | ESP32-WROOM-32E  |  | Ubuntu 24.04     |  | Android 15       |
   | TB67H450FNG x4   |  | ROS2 Jazzy       |  | SensorServer app |
   | Hall encoders    |  | CycloneDDS       |  | GPS, IMU, Mag    |
   | 50Hz PID loop    |  | micro-ROS Agent  |  | 4x cameras       |
   +--------+---------+  +---+---------+----+  +--------+---------+
            |                 |         |               |
            |  WiFi UDP       |  USB    |  WiFi         |  USB (ADB)
            |  (XRCE-DDS)     |  Serial |  CycloneDDS   |
            |                 |         |               |
            v                 v         |               v
   +------------------+  +--------+    |    +------------------+
   | micro-ROS Agent  |  | Super  |    |    | ADB port fwd     |
   | on Pi :8888      |  | Sensor |    |    | scrcpy cameras   |
   | bridges to DDS   |  | Nano   |    |    | phone_sensors    |
   +------------------+  +--------+    |    +------------------+
                                       |
            +----------+               |
            | XV-11    |  (not yet      |
            | LIDAR    |   connected)   |
            | ESP32    |               |
            | bridge   |               |
            +----------+               |
                                       v
                              +------------------+
                              | MacBook Pro      |
                              | (Brain)          |
                              | 192.168.1.104    |
                              +------------------+
                              | ROS2 Jazzy       |
                              | Nav2 stack       |
                              | SLAM Toolbox     |
                              | Path planning    |
                              | Foxglove viz     |
                              +------------------+

Communication Flow:
  ESP32 Motor --WiFi UDP--> micro-ROS Agent (Pi :8888)
                               |
                          XRCE-DDS <-> CycloneDDS bridge
                               |
  Pi (ROS2 nodes) <--CycloneDDS unicast--> Mac (Nav2/SLAM)

  All nodes on ROS_DOMAIN_ID=42
```

## Motor System: NULLLAB Maker-ESP32

The primary motor controller, running wireless micro-ROS firmware over WiFi.

| Attribute | Value |
|-----------|-------|
| **Board** | NULLLAB Maker-ESP32 |
| **MCU** | ESP32-WROOM-32E Rev V3.1 |
| **USB Chip** | CH340 (vendor `1a86:7523`) |
| **Motor Drivers** | 4x onboard TB67H450FNG (3.5A each, 2-pin control: IN1+IN2) |
| **Motors** | 2x JGB37-520R60-12 (12V, 60:1 gear, Hall quadrature encoders) |
| **Encoder Resolution** | 2640 ticks/rev |
| **WiFi IP** | `192.168.1.221` (static, NVS key `wifi_ip`) |
| **Agent** | micro-ROS Agent on Pi at `192.168.1.200:8888` (UDP) |
| **PID Loop** | 50 Hz |
| **Power Input** | 12V DC barrel jack (6-16V, center positive) |
| **Motor Switch** | Physical switch must be ON for motors to spin |

### PID Tuning (calibrated March 2026)

| Parameter | Value |
|-----------|-------|
| kp | 25 |
| ki | 60 |
| kd | 3 |
| ff_scale | 200 PWM/(m/s) |
| ff_offset_left | 136 (stiction compensation) |
| ff_offset_right | 132 (stiction compensation) |
| max_linear_speed | 0.57 m/s |
| max_angular_speed | 6.5 rad/s |

Steady-state error <1%, settling time ~400ms, no oscillation at 50Hz loop rate.

### Motor Pin Mapping

Physical left = board M2, physical right = board M1:

| Function | GPIO | Notes |
|----------|------|-------|
| Left motor IN1 | GPIO4 | PWM |
| Left motor IN2 | GPIO2 | Direction only (strapping pin, LOW only) |
| Right motor IN1 | GPIO13 | PWM |
| Right motor IN2 | GPIO27 | Direction |
| Left encoder A | GPIO19 | Forward = positive |
| Left encoder B | GPIO23 | |
| Right encoder A | GPIO5 | A/B swapped in firmware |
| Right encoder B | GPIO18 | |

### Firmware Options

Two firmware modes are available for the same Maker-ESP32 board:

1. **Wireless micro-ROS (active)** -- `hardware/esp32_motor_wireless/`
   - ESP-IDF v5.2 + micro-ROS Jazzy
   - WiFi UDP to Agent on Pi
   - 50Hz PID loop, 3 publishers (/odom, /tf, /diagnostics), 1 subscriber (/cmd_vel)
   - Build: `source ~/esp/esp-idf-v5.2/export.sh && idf.py build`
   - Flash via Pi: `scp` build + `esptool.py`

2. **USB serial (fallback)** -- `hardware/esp32_at8236_driver/`
   - Python ROS2 driver on Pi reads USB serial `/dev/esp32_motor`
   - Legacy Arduino firmware at `archive/legacy_hardware/maker_esp32_firmware/`
   - Useful for debugging or when WiFi is unavailable

### micro-ROS Entities

| Type | Name | QoS | Rate | Notes |
|------|------|-----|------|-------|
| Publisher | `/odom` | best_effort | 20 Hz | ~730 bytes, MTU=1024 fits in single UDP packet |
| Publisher | `/tf` | best_effort | 20 Hz | odom -> base_link transform |
| Publisher | `/diagnostics` | best_effort | 1 Hz | WiFi RSSI, heap, uptime |
| Subscriber | `/cmd_vel` | best_effort | — | Twist velocity commands, 500ms watchdog |

See [maker_esp32/](./maker_esp32/) for board documentation and wiring guide.

## XV-11 LIDAR

360-degree laser scanner for SLAM and obstacle detection. Bridge firmware ready, not yet physically connected to Pi.

| Attribute | Value |
|-----------|-------|
| **Sensor** | Neato XV-11 |
| **Range** | 0.06 - 5.0 m |
| **Resolution** | 360 points per scan |
| **Frequency** | ~5 Hz (revolution accumulation) |
| **Bridge** | ESP32-WROOM-32 with CP2102 USB |
| **Bridge Firmware** | `hardware/esp32_xv11_bridge/` v2.1.0 |
| **ROS2 Driver** | `ros2_ws/src/xv11_lidar_python/` v3.0.0 |
| **Device** | `/dev/esp32_lidar` (when connected) |
| **Next Step** | Convert to micro-ROS wireless node |

**USB power note:** The XV-11 LIDAR draws 500-680 mA. It must be connected to a direct root hub port or a powered USB hub -- regular hub ports may not supply enough current.

See [esp32_xv11_bridge/](./esp32_xv11_bridge/) for bridge firmware and [lidar_usb/](./lidar_usb/) for LIDAR documentation.

## Super Sensor Module

Arduino Nano-based sensor module with ultrasonic array.

| Attribute | Value |
|-----------|-------|
| **MCU** | Arduino Nano (ATmega328P) |
| **Ultrasonic** | 4x HC-SR04 |
| **LED** | RGB LED |
| **Servo** | 180-degree servo |
| **Interface** | USB Serial |
| **Device** | `/dev/super_sensor` |

See [super_sensor/README.md](./super_sensor/README.md) for documentation.

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
+---------------------------------------------------------------+
|                   Samsung Galaxy A16                           |
|  +-----------------------------------------------------------+|
|  | SensorServer App (WebSocket on port 8080)                  ||
|  |   - Accelerometer (500 Hz capable)                         ||
|  |   - Gyroscope (500 Hz capable)                             ||
|  |   - Magnetometer                                           ||
|  |   - Rotation Vector (fused orientation)                    ||
|  +-----------------------------+-----------------------------+||
|  | Cameras                     |                              ||
|  |   - Back (0): 4080x3060    |                              ||
|  |   - Front (1): 4128x3096   |                              ||
|  |   - Wide (2): 2576x1932    |                              ||
|  |   - Front2 (3): 3712x2556  |                              ||
|  +-----------------------------------------------------------+|
+-------------------------------+-------------------------------+
                                | USB Cable
                                v
+---------------------------------------------------------------+
|                      Raspberry Pi 5                           |
+---------------------------------------------------------------+
|                                                               |
|  +-----------------------------------------------------------+|
|  | ADB (Android Debug Bridge)                                 ||
|  |   - Port forward: tcp:8080 -> phone:8080                  ||
|  |   - GPS polling via: adb shell dumpsys location            ||
|  |   - Camera via: scrcpy --video-source=camera              ||
|  +-----------------------------------------------------------+|
|                                                               |
|  +-----------------------------------------------------------+|
|  | phone_sensors_ros2_node.py                                 ||
|  |   - WebSocket client -> SensorServer                      ||
|  |   - Publishes: /phone/imu, /phone/magnetic_field          ||
|  |   - Publishes: /phone/gps/fix, /phone/orientation         ||
|  +-----------------------------------------------------------+|
|                                                               |
|  +-----------------------------------------------------------+|
|  | v4l2loopback + scrcpy -> multi_camera_publisher.py         ||
|  |   - /dev/video10-13 -> /phone/camera/{name}/image_raw     ||
|  |   - Compressed: /phone/camera/{name}/image_raw/compressed ||
|  +-----------------------------------------------------------+|
|                                                               |
+---------------------------------------------------------------+
```

### Phone Setup

See [phone_sensors/README.md](./phone_sensors/README.md) for sensor setup and [phone_cameras/README.md](./phone_cameras/README.md) for camera setup.

**Quick Setup:**
1. Install **SensorServer** app from F-Droid or GitHub
2. Configure app: Bind Address = `0.0.0.0`, enable sensors
3. Enable USB Debugging on phone
4. Connect phone via USB to Pi
5. Start services: `sudo systemctl start rovac-edge-phone-sensors rovac-phone-cameras`

## Stereo Cameras

Dual USB cameras for stereo depth estimation.

| Attribute | Value |
|-----------|-------|
| **Cameras** | 2x USB cameras |
| **Baseline** | 102.67 mm |
| **Algorithm** | StereoSGBM depth |
| **Devices** | `/dev/video0`, `/dev/video1` |

See [stereo_cameras/README.md](./stereo_cameras/README.md) for calibration and depth estimation.

## USB Webcam

| Attribute | Value |
|-----------|-------|
| **Model** | NexiGo N930E |
| **Resolution** | 1080p |
| **Device** | `/dev/webcam` |

See [webcam/README.md](./webcam/README.md) for setup.

## Edge Computer: Raspberry Pi 5

| Attribute | Value |
|-----------|-------|
| **Model** | Raspberry Pi 5 (8 GB RAM, 117 GB SD) |
| **OS** | Ubuntu 24.04.3 LTS (aarch64) |
| **Hostname** | `rovac-pi` |
| **User** | `pi` |
| **IP** | `192.168.1.200` (wlan0) |
| **ROS2** | Jazzy (apt), CycloneDDS, Nav2, SLAM Toolbox |
| **Python** | 3.12 |
| **micro-ROS Agent** | UDP on port 8888 |

## Sensor Summary

| Sensor | Source | Rate | Purpose |
|--------|--------|------|---------|
| **Encoder Odom** | Maker-ESP32 (micro-ROS) | 50 Hz | Position tracking, PID control |
| **LIDAR** | XV-11 (not connected) | ~5 Hz | SLAM, obstacle detection |
| **Ultrasonic (4x)** | HC-SR04 via Super Sensor | ~10 Hz | Close obstacle detection |
| **Phone GPS** | GNSS | 1 Hz | Outdoor positioning |
| **Phone IMU** | LSM6DSOTR | ~45 Hz | Orientation, motion |
| **Phone Magnetometer** | MXG4300S | ~6 Hz | Compass heading (outdoor) |
| **Phone Camera** | Back/Front/Wide | ~12 Hz | Visual sensing |
| **Stereo Cameras** | 2x USB | variable | Depth estimation |
| **USB Webcam** | NexiGo N930E | ~16 Hz | Forward vision |

## Sensor Redundancy

| Measurement | Primary Source | Secondary Source |
|-------------|----------------|------------------|
| **Position (indoor)** | Wheel odometry (`/odom`) | LIDAR SLAM (`/map`) |
| **Position (outdoor)** | Phone GPS (`/phone/gps/fix`) | Wheel odometry |
| **Heading** | Phone magnetometer (`/phone/magnetic_field`) | Gyro Z integration (drift-prone) |
| **Obstacles** | LIDAR (`/scan`) | Ultrasonic (`/super_sensor/*`) |

## Device Paths (udev)

All devices use udev rules for persistent naming on the Pi:

| Device | Symlink | Vendor:Product | Notes |
|--------|---------|----------------|-------|
| Maker-ESP32 Motor | `/dev/esp32_motor` | `1a86:7523` (CH340) | USB serial fallback only; primary is WiFi |
| ESP32 LIDAR Bridge | `/dev/esp32_lidar` | `10c4:ea60` (CP2102) | Not yet connected |
| Super Sensor | `/dev/super_sensor` | `1a86:7523` (CH340) | KERNELS-based udev rule |
| USB Webcam | `/dev/webcam` | `1bcf:2284` (NexiGo) | |
| Phone | ADB via USB | N/A | |

## Power Budget

| Component | Voltage | Current (Typical) | Current (Max) |
|-----------|---------|-------------------|---------------|
| Raspberry Pi 5 | 5V | 2.5A | 5A |
| Maker-ESP32 (logic) | 5V (USB) or 12V barrel | 0.1A | 0.3A |
| TB67H450FNG drivers (2 motors) | 12V | 0.5A each | 1.5A each |
| XV-11 LIDAR | 5V | 0.15A | 0.68A |
| Super Sensor (Nano) | 5V | 0.1A | 0.2A |
| Phone | 5V (USB) | 0.5A | 1.5A |
| Stereo Cameras (2x) | 5V (USB) | 0.2A | 0.5A |
| USB Webcam | 5V (USB) | 0.1A | 0.3A |
| **Total** | - | ~4.7A | ~11.5A |

**TB67H450FNG UVLO note:** Battery must be above 8V under load. Voltage below 6.8V causes UVLO (Under-Voltage Lock-Out) on the motor drivers.

## Legacy Hardware

All legacy hardware has been moved to `archive/legacy_hardware/`:

| Component | Original Location | Replaced By |
|-----------|-------------------|-------------|
| Hiwonder ROS Controller V1.2 | `hiwonder-ros-controller/` | Maker-ESP32 (micro-ROS) |
| L298N + ESP32 DevKitV1 | `esp32_l298n_firmware/` | Maker-ESP32 (micro-ROS) |
| Arduino Nano Encoder Bridge | `nano_encoder_bridge/` | ESP32 PCNT hardware encoders |
| ESP32 Encoder Bridge | `esp32_encoder_bridge/` | ESP32 PCNT hardware encoders |
| Yahboom BST-4WD V4.5 | `yahboom-bst-4wd-expansion-board/` | Maker-ESP32 |
| Yahboom ROS Expansion Board V3.0 | `yahboom-ros-expansion-board-v3/` | Maker-ESP32 |
| Maker-ESP32 Arduino Firmware | `maker_esp32_firmware/` | micro-ROS firmware (ESP-IDF) |
| Arduino LIDAR Bridge | `arduino_lidar_bridge/` | ESP32 LIDAR bridge |
| Nano LIDAR USB Bridge | `lidar_nano_usb/` | ESP32 LIDAR bridge |

## Active Directories in hardware/

| Directory | Purpose |
|-----------|---------|
| `esp32_motor_wireless/` | Active motor firmware (micro-ROS + ESP-IDF) |
| `esp32_at8236_driver/` | USB serial ROS2 motor driver (fallback) |
| `esp32_xv11_bridge/` | LIDAR bridge firmware |
| `maker_esp32/` | Board documentation and wiring guide |
| `super_sensor/` | Edge ROS2 nodes (ultrasonic, obstacle) |
| `health_monitor/` | Edge health monitor node |
| `stereo_cameras/` | Stereo camera calibration and depth |
| `phone_sensors/` | Phone IMU/GPS/magnetometer integration |
| `phone_cameras/` | Phone camera streaming |
| `webcam/` | USB webcam publisher |
| `lidar_usb/` | LIDAR hardware documentation |

## Documentation Index

| Document | Description |
|----------|-------------|
| [maker_esp32/](./maker_esp32/) | Motor board documentation and wiring |
| [esp32_motor_wireless/](./esp32_motor_wireless/) | Active micro-ROS motor firmware |
| [esp32_at8236_driver/](./esp32_at8236_driver/) | USB serial motor driver (fallback) |
| [esp32_xv11_bridge/](./esp32_xv11_bridge/) | LIDAR bridge firmware |
| [lidar_usb/](./lidar_usb/) | LIDAR hardware documentation |
| [super_sensor/README.md](./super_sensor/README.md) | Super Sensor module |
| [phone_sensors/README.md](./phone_sensors/README.md) | Phone IMU/GPS/magnetometer |
| [phone_cameras/README.md](./phone_cameras/README.md) | Phone camera streaming |
| [stereo_cameras/README.md](./stereo_cameras/README.md) | Stereo camera calibration |
| [webcam/README.md](./webcam/README.md) | USB webcam setup |
| [health_monitor/](./health_monitor/) | Edge health monitor |
