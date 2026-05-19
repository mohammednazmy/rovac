# HC-SR04 Ultrasonic Distance Sensor

## Overview

Ultrasonic ranging module that measures distance using sonar (sound echo timing). Widely used for obstacle detection in robotics.

## Hardware

| Spec | Value |
|------|-------|
| Model | HC-SR04 |
| Quantity owned | 4 |
| Interface | Digital (TRIG input, ECHO output) |
| Supply voltage | 5V |
| Range | 2 cm - 400 cm |
| Accuracy | ~3 mm |
| Beam angle | ~30 degrees (cone) |
| Frequency | 40 kHz ultrasonic |
| Trigger pulse | 10 us HIGH on TRIG pin |
| Echo pulse | HIGH duration proportional to distance |
| Update rate | ~10-20 Hz (limited by sound travel time) |
| Size | 45 x 20 x 15 mm |
| Current | ~15 mA |

## Pinout

| Pin | Function |
|-----|----------|
| VCC | 5V power |
| TRIG | Trigger input (10us HIGH pulse to start measurement) |
| ECHO | Echo output (HIGH duration = round-trip time) |
| GND | Ground |

## Distance Calculation

```
distance_cm = (echo_pulse_duration_us / 2) / 29.1
```

## ROVAC Integration Status

**INTEGRATED** — 4 HC-SR04 sensors are driven by the **ESP32 Sensor Hub** (ESP32-DevKitV1, WROOM-32, CP2102) which connects to the Pi 5 over USB serial (COBS-framed binary, 460800 baud). The sensor hub firmware is at `hardware/esp32_sensor_hub/` and the Pi-side C++ driver is `ros2_ws/src/rovac_sensor_driver/`. This replaced the retired Arduino-Nano "Super Sensor" module (now in `archive/legacy_hardware/super_sensor/`).

> Note: the sensors are physically wired and software-integrated, but not yet mounted on the robot chassis.

### Mounting (front/rear/left/right)

| Position | Direction | URDF Frame |
|----------|-----------|------------|
| Front | Forward | `us_front_link` |
| Rear | Backward | `us_rear_link` |
| Left | 90 degrees left | `us_left_link` |
| Right | 90 degrees right | `us_right_link` |

### ROS2 Topics

Published by `rovac_sensor_driver` at 10 Hz, reliable QoS:

| Topic | Type | Description |
|-------|------|-------------|
| `/sensors/ultrasonic/front` | Range | Front HC-SR04 obstacle distance |
| `/sensors/ultrasonic/rear` | Range | Rear HC-SR04 obstacle distance |
| `/sensors/ultrasonic/left` | Range | Left HC-SR04 obstacle distance |
| `/sensors/ultrasonic/right` | Range | Right HC-SR04 obstacle distance |
| `/obstacle/points` | PointCloud2 | Ultrasonic readings as 3D points for the Nav2 costmap |

### Code & Services

- **Sensor hub firmware**: `hardware/esp32_sensor_hub/` (ESP-IDF v5.2; `main/ultrasonic.c` handles HC-SR04 sequential trigger/echo)
- **Pi C++ driver**: `ros2_ws/src/rovac_sensor_driver/`
- **Obstacle avoidance**: `scripts/obstacle_avoidance_node.py`
- **Systemd services**: `rovac-edge-sensor-hub.service`, `rovac-edge-obstacle.service`

The ESP32 Sensor Hub enumerates on the Pi as `/dev/esp32_sensor` (udev rule for CP2102, vendor `10c4:ea60`).
