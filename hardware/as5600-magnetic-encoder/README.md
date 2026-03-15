# AS5600 Magnetic Encoder

## Overview

12-bit contactless magnetic rotary position sensor. Measures absolute angle (0-360 degrees) of a diametrically magnetized magnet via Hall effect. Can replace or supplement existing motor Hall encoders for higher-precision odometry.

## Hardware

| Spec | Value |
|------|-------|
| Chip | ams AS5600 |
| Breakout board | UMLIFE AS5600 module |
| Quantity owned | 3 |
| Interface | I2C (address 0x36, fixed), PWM, or analog voltage output |
| Supply voltage | 3.3V-3.6V or 4.5V-5.5V (board has dual-range capacitors) |
| Resolution | 12-bit (4096 positions per revolution) |
| Accuracy | +/- 2 degrees typical (uncalibrated) |
| Update rate | ~920 Hz (I2C), ~244 Hz (PWM) |
| Size | 23 x 23 mm |
| Magnet | 6mm diametrically magnetized (included, but may be 4mm — verify) |
| Air gap | 0.5mm - 3mm between magnet and chip |

## Purchase Info

- **Source**: Amazon (Umlife US)
- **ASIN**: (UMLIFE 3pcs AS5600)
- **Price**: $8.99 for 3-pack
- **Purchased**: January 24, 2026

## Pinout

| Pin | Function |
|-----|----------|
| VCC | 3.3V or 5V power |
| GND | Ground |
| DIR | Rotation direction (GND = CW increases, VCC = CW decreases) |
| OUT | PWM or analog voltage output (mode depends on R4 resistor) |
| SCL | I2C clock |
| SDA | I2C data |
| PGO | Program/output mode select (active LOW via R4) |

## Configuration Notes

- **I2C mode (default)**: Works out of the box. Read angle register via I2C at address 0x36.
- **Analog output**: Remove resistor R4 on the PCB to enable analog voltage output on the OUT pin. Without removing R4, OUT is always at VCC.
- **PWM output**: Also requires R4 removal. PWM duty cycle proportional to angle.
- **I2C address conflict**: All AS5600 modules share the fixed address 0x36. To use multiple sensors on one I2C bus, use an I2C multiplexer (e.g., TCA9548A) or separate I2C buses.
- **Magnet proximity**: The included magnet must be within 0.5-3mm of the chip surface. The magnet is very small and easy to lose. It must be a diametrically magnetized type (not axially magnetized).
- **Pin cogging**: Strong magnets can cause "cogging" with the metal header pins. If you experience this, remove or clip the through-hole pins on the bottom of the board.

## ROVAC Integration Status

**NOT YET INTEGRATED** — Sensors are available but not wired or programmed.

### Potential Uses

1. **Motor shaft absolute position**: Mount on each motor shaft for precise absolute angle measurement (4096 steps/rev vs current Hall encoder's 2640 ticks/rev). Would replace the existing quadrature Hall encoders with higher resolution.
2. **LIDAR motor RPM**: Could provide precise XV11 motor RPM feedback without relying on LIDAR data packets for RPM measurement.
3. **Servo/turret position feedback**: If a pan/tilt camera mount is added, AS5600 provides closed-loop position control.

### Integration Consideration

The existing Hall encoders (2640 ticks/rev) already work well for odometry. The AS5600's 4096 positions/rev is marginally better, but the real advantage is absolute position (survives power cycles) vs. incremental (resets to zero). For ROVAC's differential drive, incremental encoders are sufficient since odometry accumulates from deltas. **The AS5600 is most valuable if you add a rotating turret, steering mechanism, or need the LIDAR motor RPM measured independently.**
