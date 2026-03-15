# MPU-6050 IMU (GY-521 Breakout)

## Overview

6-axis Inertial Measurement Unit: 3-axis accelerometer + 3-axis gyroscope. Provides orientation, tilt, and motion data for odometry fusion and collision detection.

## Hardware

| Spec | Value |
|------|-------|
| Chip | InvenSense MPU-6050 |
| Breakout board | HiLetgo GY-521 |
| Quantity owned | 3 |
| Interface | I2C (address 0x68, or 0x69 with AD0 HIGH) |
| Supply voltage | 3.3V-5V (onboard LDO, but see caveats below) |
| Gyro range | +/- 250, 500, 1000, 2000 deg/s (configurable) |
| Accel range | +/- 2, 4, 8, 16g (configurable) |
| ADC | 16-bit |
| Sample rate | Up to 1 kHz (gyro), 1 kHz (accel) |
| DMP | Onboard Digital Motion Processor for sensor fusion |
| Size | ~21 x 16 mm |
| Current | ~3.9 mA (typical) |

## Purchase Info

- **Source**: Amazon (HiLetgo Store)
- **ASIN**: B00LP25V1A
- **Price**: $10.99 for 3-pack
- **Purchased**: January 24, 2026

## Pinout (GY-521 board)

| Pin | Function |
|-----|----------|
| VCC | 3.3V or 5V power |
| GND | Ground |
| SCL | I2C clock |
| SDA | I2C data |
| XDA | Auxiliary I2C data (for external magnetometer) |
| XCL | Auxiliary I2C clock |
| AD0 | I2C address select (LOW=0x68, HIGH=0x69) |
| INT | Interrupt output |

## Known Caveats (from user reviews)

- **LDO issue at 3.3V**: The onboard LDO may cut out under load when fed 3.3V. For 3.3V operation, bypass the LDO and power VCC directly at 3.3V.
- **No level shifters**: The board has no I2C level shifting. Running I2C signals at 5V may damage the chip over time. Use 3.3V logic or add external level shifters.
- **Address pulldown weak**: If the sensor doesn't respond, tie AD0 to GND with a 4.7k resistor.
- **Calibration required**: On first power-up, keep the sensor flat and still for calibration offset calculation.

## ROVAC Integration Status

**NOT YET INTEGRATED** — Sensor is available but not wired or programmed.

### Planned Use

- Fuse with motor encoder odometry (complementary or Kalman filter) to compensate for tank tread slip
- Publish `/imu/data` (sensor_msgs/Imu) via micro-ROS on a new ESP32
- Feed AMCL and Nav2 for better localization
- Detect collisions, stuck conditions, and tilt/tipover

### Wiring Plan

Connect to ESP32 via I2C:
- SDA → ESP32 GPIO21 (or any I2C-capable pin)
- SCL → ESP32 GPIO22 (or any I2C-capable pin)
- VCC → 3.3V
- GND → GND
- AD0 → GND (address 0x68)
