# AS5600 Magnetic Encoder

## Overview

12-bit contactless magnetic rotary position sensor. Measures absolute angle (0-360 degrees) of a diametrically magnetized magnet via Hall effect. Tested and verified as a motor encoder on the Greartisan GB37RG rear shaft.

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
| Max I2C polling rate | ~4,170 Hz at 400kHz I2C (~240µs per read) |
| Size | 23 x 23 mm |
| PCB mounting holes | 20mm center-to-center, M2 |
| Magnet | Diametrically magnetized disc (included 4mm, recommended 6mm) |
| Air gap | 0.5mm - 3mm between magnet and chip |

## Purchase Info

- **Source**: Amazon (Umlife US)
- **ASIN**: UMLIFE 3pcs AS5600
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

## Wiring to ESP32 DevKitV1

| AS5600 Pin | ESP32 Pin |
|------------|-----------|
| VCC | 3V3 |
| GND | GND |
| SDA | GPIO21 |
| SCL | GPIO22 |
| DIR | (leave unconnected — board R3 pulls to GND) |
| OUT | (not used in I2C mode) |

## Configuration Notes

- **I2C mode (default)**: Works out of the box. Read raw angle register (0x0C-0x0D) at address 0x36.
- **Analog output**: Remove resistor R4 on the PCB to enable analog voltage output on the OUT pin.
- **I2C address conflict**: All AS5600 modules share the fixed address 0x36. To use multiple sensors on one I2C bus, use an I2C multiplexer (e.g., TCA9548A) or separate I2C buses.
- **Magnet type**: Must be **diametrically magnetized** (N/S across diameter). Axially magnetized magnets (N/S on flat faces) produce wrong field geometry — AGC swings wildly, readings are garbage.
- **Magnet proximity**: 0.5-3mm air gap. Too close (AGC→0, STRONG status) is as bad as too far (AGC→128, WEAK/NONE). Sweet spot is AGC 30-150, status `OK`.
- **Pin cogging**: Strong magnets can cog with metal header pins. Remove/clip pins if needed.
- **Motor noise**: Solder 100nF ceramic capacitor across brushed motor terminals to prevent I2C corruption from commutation spikes.

## Test Firmware

Location: `as5600_test/as5600_test.ino`

Arduino sketch for ESP32 DevKitV1 that:
- Scans I2C bus and confirms AS5600 at 0x36
- Polls raw angle at max I2C speed (~4,170 Hz)
- Tracks multi-turn rotation (detects 0→4095 and 4095→0 wrap-arounds)
- Calculates RPM from accumulated ticks
- Reports: angle, raw value, turns, total degrees, RPM, polls/sec, magnet status, AGC

Build and flash:
```bash
arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 as5600_test/
arduino-cli upload --fqbn esp32:esp32:esp32doit-devkit-v1 --port /dev/cu.usbserial-0001 as5600_test/
```

## Polling Rate vs Accuracy (Measured 2026-03-20)

Tested on Greartisan GB37RG rear shaft at ~5,220 RPM:

| Delay (µs) | Polls/s | RPM Error | Verdict |
|------------|---------|-----------|---------|
| 0 | 4,199 | 0.0% | GOOD |
| 100 | 2,953 | 0.0% | GOOD |
| 250 | 2,046 | 0.0% | GOOD |
| 500 | 1,354 | 0.0% | GOOD |
| 1,000 | 807 | 0.1% | GOOD |
| 2,000 | 447 | 0.1% | GOOD |
| 3,000 | 309 | 0.1% | GOOD |
| 5,000 | 191 | 0.3% | GOOD |
| 7,500 | 129 | -149% | BROKEN |
| 10,000 | 98 | -112% | BROKEN |

**Minimum reliable rate**: ~191 Hz (theoretical minimum 174 Hz based on <180° per sample at 5,220 RPM).

**Recommended rates**:
- 1 motor: 309 Hz (3ms delay) — conservative, 0.1% error
- 2 motors on shared I2C: ~800 Hz each (1ms delay), alternating reads gives ~400 Hz per sensor

## 3D Printed Mount (Rear Shaft)

Designed for Greartisan GB37RG motor rear shaft. Friction-fit collar slides over 36.2mm motor body.

**Files**:
- `../../3D-prints/gb37rg_as5600_mount.scad` — parametric OpenSCAD source
- `../../3D-prints/gb37rg_as5600_mount.stl` — print-ready STL

**Key dimensions**:
- Collar ID: 36.8mm (0.3mm radial clearance)
- Collar depth: 10mm over motor body
- PCB post height: 5mm (positions IC at 5mm from end cap)
- Air gap geometry: shaft(1mm) + magnet(2.5mm) + gap(1.5mm) = 5mm
- Wire slots: 10mm wide on opposite sides for power terminal wires
- 4x grip bumps on inner collar wall for friction fit

**Print settings**: PLA/PETG, 0.2mm layers, 30-40% infill, **plate-side DOWN** (no supports needed). Drill M2 holes with 1.8mm bit after printing.

## Tested Performance (on GB37RG, 2026-03-20)

| Metric | Value |
|--------|-------|
| Motor rear shaft speed | ~5,220 RPM (at 12V) |
| Gearbox output speed | ~300 RPM (17.4:1 ratio) |
| Effective encoder resolution (through gearbox) | 71,270 counts/output-rev |
| Magnet status | OK (AGC=128, stable) |
| Stationary jitter | ±0.09° (1 count) |
| I2C errors during motor operation | 0 (with 100nF cap) |
| Multi-turn tracking | Verified 1,500+ turns, zero lost counts |
