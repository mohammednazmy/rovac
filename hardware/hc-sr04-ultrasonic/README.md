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

**PARTIALLY INTEGRATED** — 4 sensors are mounted on the Super Sensor module (Arduino Nano-based) at the front of the robot. ROS2 driver exists at `hardware/super_sensor/`. Systemd services `rovac-edge-supersensor` and `rovac-edge-obstacle` exist but hardware is currently disconnected.

### Current Mounting (Super Sensor module)

| Position | Direction | URDF Frame |
|----------|-----------|------------|
| Front Top | Forward | `super_sensor_link/front_top_link` |
| Front Bottom | Forward, angled down | `super_sensor_link/front_bottom_link` |
| Left | 90 degrees left | `super_sensor_link/left_link` |
| Right | 90 degrees right | `super_sensor_link/right_link` |

### ROS2 Topics (when connected)

| Topic | Type | Description |
|-------|------|-------------|
| `/super_sensor/ranges` | Float32MultiArray | Raw distances from all 4 sensors |
| `/super_sensor/range/front_top` | Range | Individual sensor reading |
| `/super_sensor/range/front_bottom` | Range | Individual sensor reading |
| `/super_sensor/range/left` | Range | Individual sensor reading |
| `/super_sensor/range/right` | Range | Individual sensor reading |
| `/super_sensor/obstacle_detected` | Bool | True when any sensor below threshold |
| `/super_sensor/obstacle_points` | PointCloud2 | Obstacle points for costmap |

### Existing Code

- **Sensor driver**: `hardware/super_sensor/super_sensor_node.py`
- **Obstacle avoidance**: `hardware/super_sensor/obstacle_avoidance_node.py`
- **Systemd services**: `rovac-edge-supersensor.service`, `rovac-edge-obstacle.service`

### Reconnection Notes

The Super Sensor Arduino Nano connects to the Pi via USB serial. To reconnect:
1. Plug the Arduino Nano USB into the Pi
2. Verify device appears: `ls /dev/ttyUSB*` or check udev rules
3. Restart services: `sudo systemctl restart rovac-edge-supersensor rovac-edge-obstacle`
