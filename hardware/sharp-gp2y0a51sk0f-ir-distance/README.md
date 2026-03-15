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

**NOT YET INTEGRATED** — Sensors are available but not wired or programmed.

### Potential Uses

1. **Cliff/drop detection**: Mount pointing downward at robot's front edge. Normally reads ~3-5cm (floor distance). If reading jumps to >15cm or no-return, a cliff/stair is detected. Very fast (60 Hz) response.
2. **Close-range obstacle detection**: Detect objects in the LIDAR's blind zone (below 12.5cm scan height). Mount at front bumper level (2-5cm height) pointing forward.
3. **Docking sensor**: Precise short-range alignment for autonomous charging station docking.

### Integration Consideration

These sensors output analog voltage, so they need an ADC to read. Options:
- **ESP32 ADC**: Connect Vo to an ESP32 ADC pin (12-bit, but noisy and non-linear — use with averaging)
- **External ADC**: ADS1115 (16-bit I2C ADC) for more precise readings
- **Arduino Nano ADC**: The existing Super Sensor Arduino Nano has 10-bit ADC pins available

For cliff detection, mount 2 sensors facing downward at the front-left and front-right edges of the chassis. The 60 Hz update rate is much faster than the ultrasonics (~10 Hz) and LIDAR (5 Hz), making this ideal for fast cliff detection at driving speed.
