# Sharp GP2Y0A51SK0F Analog IR Distance Sensor

## Overview

Short-range infrared distance sensor using triangulation. Outputs an analog voltage proportional to 1/distance. Ideal for detecting very close objects (2-15cm) that LIDAR and ultrasonics miss.

## Hardware

| Spec | Value |
|------|-------|
| Model | Sharp/Socle GP2Y0A51SK0F |
| Quantity owned | 2 |
| Interface | Analog voltage output |
| Supply voltage | 4.5V - 5.5V |
| Current | ~12 mA average (pulsed, spikes higher) |
| Detection range | 2 cm - 15 cm (0.8" - 6") |
| Output voltage | ~0.4V (far) to ~2.3V (near), 1.65V differential typical |
| Update rate | ~60 Hz (16.5 ms +/- 4 ms period) |
| Connector | 1.5mm-pitch 3-pin JST ZH (NOT standard JST PH) |
| Size | 27 x 13.2 x 14.2 mm |
| Weight | 2.7g |
| Technology | IR LED + PSD (Position Sensitive Detector) triangulation |

## Purchase Info

- **Source**: Pololu (item #2450)
- **Price**: $11.95 each
- **Datasheet**: GP2Y0A51SK0F (312k PDF from Sharp)

## Pinout (front view, left to right)

| Pin | Function | Wire Color |
|-----|----------|------------|
| 1 | VCC (4.5-5.5V) | Red |
| 2 | GND | Black |
| 3 | Vo (analog output) | White |

## Important Notes

- **Bypass capacitor required**: Place 10 uF or larger between VCC and GND close to the sensor. The sensor draws current in large, short bursts that can destabilize the power supply.
- **JST ZH connector**: Uses 1.5mm pitch JST ZH, NOT the standard 2.0mm JST PH. Requires a 3-pin JST ZH cable or direct soldering.
- **Non-linear output**: Output voltage vs distance is NOT linear. Voltage is approximately proportional to 1/distance. Use a calibration curve or lookup table.
- **Minimum range**: Objects closer than 2cm may give incorrect (decreasing) readings — the sensor has a blind spot very close.

## Linearization

The output voltage relates approximately linearly to 1/distance:

```
# Approximate conversion (calibrate for your specific sensor)
distance_cm = 1 / (a * voltage + b)
# Where a and b are determined from calibration measurements
```

## ROVAC Integration Status

**INTEGRATED** — 2 GP2Y0A51SK0F sensors are used as front/rear cliff detectors, read by the **ESP32 Sensor Hub** (ESP32-DevKitV1) via the ESP32's ADC1 oneshot peripheral. The sensor hub connects to the Pi 5 over USB serial (COBS-framed binary, 460800 baud). Firmware is at `hardware/esp32_sensor_hub/` (`main/cliff_sensor.c`) and the Pi-side C++ driver is `ros2_ws/src/rovac_sensor_driver/`.

> Note: the sensors are software-integrated but not yet mounted on the robot chassis.

### Mounting

The 2 sensors are intended to mount facing downward at the robot's front and rear edges. Normally each reads the floor distance (~3-5 cm); if a reading jumps high / no-return, a cliff/drop is detected.

| Position | URDF Frame |
|----------|------------|
| Front cliff | `cliff_front_link` |
| Rear cliff | `cliff_rear_link` |

### ROS2 Topics

Published by `rovac_sensor_driver` at 10 Hz, reliable QoS:

| Topic | Type | Description |
|-------|------|-------------|
| `/sensors/cliff/front` | Range | Front Sharp IR cliff distance |
| `/sensors/cliff/rear` | Range | Rear Sharp IR cliff distance |
| `/sensors/cliff/detected` | Bool | True when a cliff is detected on any sensor |

### Code & Services

- **Sensor hub firmware**: `hardware/esp32_sensor_hub/` (`main/cliff_sensor.c` — ADC1 oneshot reads)
- **Pi C++ driver**: `ros2_ws/src/rovac_sensor_driver/`
- **Obstacle/cliff avoidance**: `scripts/obstacle_avoidance_node.py`
- **Systemd services**: `rovac-edge-sensor-hub.service`, `rovac-edge-obstacle.service`

### ADC Notes

These sensors output analog voltage and require an ADC. ROVAC reads them on the ESP32 Sensor Hub's ADC1 (12-bit oneshot). The bypass capacitor (see Important Notes above) is required because of the pulsed current draw. The output is non-linear — see the Linearization section.
