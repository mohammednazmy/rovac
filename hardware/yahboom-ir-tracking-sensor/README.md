# Yahboom 4-Channel Infrared Tracking Sensor

## Overview

4-channel line-following / surface-detection IR sensor module. Each channel has an IR LED emitter and phototransistor receiver pair that detects reflectance differences (e.g., black tape on white floor). Originally designed for line-following robots.

## Hardware

| Spec | Value |
|------|-------|
| Brand | Yahboom |
| Channels | 4 (side by side) |
| Connector | XH2.54-6Pin |
| Quantity owned | 1 |
| Interface | 4x digital outputs (HIGH/LOW per channel) |
| Supply voltage | 3.3V - 5V |
| Detection distance | ~1-3 cm from surface |
| Output | Active LOW when detecting reflective surface (white), HIGH on dark (black) |
| Indicator LEDs | Per-channel status LEDs on board |
| Adjustment | Per-channel sensitivity potentiometer |

## Pinout (XH2.54-6Pin)

| Pin | Function |
|-----|----------|
| VCC | 5V power supply (3.3V also works — see Sensor Hub wiring guide) |
| GND | Ground |
| X1 | Tracking pin 1 (leftmost sensor) |
| X2 | Tracking pin 2 (inner left) |
| X3 | Tracking pin 3 (inner right) |
| X4 | Tracking pin 4 (rightmost sensor) |

## Output Logic (confirmed from Yahboom manual)

- **LOW** = reflective surface detected (floor present, LED indicator ON)
- **HIGH** = dark/no reflection or void (no floor, LED indicator OFF)

## Onboard Components

- **LM324** quad op-amp comparator (U1) — compares IR receiver output against threshold
- **4x adjustable potentiometers** (SW1-SW4) — tune sensitivity per channel
- **4x IR emitter/receiver pairs** (P1-P4) — with 100Ω series resistors (R1,R3,R5,R7)
- **4x indicator LEDs** (L1-L4) — with 1kΩ series resistors (R9-R12)

## Calibration

1. Hold module 1-2cm above your floor surface
2. Turn each potentiometer (SW1-SW4) until the corresponding LED just turns OFF
3. Verify: LED should turn ON when you lift the module >3cm from floor
4. Repeat for each channel

## Reference Materials

- Schematic: `Tracking-module/Sch.pdf`
- User manual: `Tracking-module/Tracking module use instructions.pdf`
- Manufacturer GitHub: `Tracking-module/` (cloned from YahboomTechnology)

## ROVAC Integration Status

**NOT YET INTEGRATED** — Sensor is available but not wired or programmed.

### Potential Uses

1. **Cliff/edge detection**: Mount facing downward at the robot's front edge. If the sensor transitions from detecting floor (reflective) to detecting nothing (void/drop), it means a cliff/stairway edge. This is the most practical use for a vacuum robot.
2. **Line following**: The original intended use — follow a tape line on the floor. Could be used for docking guidance (follow a tape path back to charging station).
3. **Surface type detection**: Differentiate between carpet (dark/absorptive) and hard floor (reflective) to adjust vacuum power or driving speed.

### Integration Consideration

For cliff detection, mount 2 of the 4 channels at the front-left and front-right edges of the robot, pointing downward at ~45 degrees. The remaining 2 channels could cover the sides. When any channel detects "no floor" (no reflection), publish an emergency stop to `/cmd_vel_obstacle`. This is a critical safety sensor for a vacuum robot operating near stairs.
