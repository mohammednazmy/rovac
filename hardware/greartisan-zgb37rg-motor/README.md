# Greartisan ZGB37RG17.4i Gear-Box Motor

## Overview

12V DC geared motor used for prototyping. **Not installed on ROVAC** — used for bench testing motor drivers and AS5600 magnetic encoder integration.

Quantity: 2

## Identification

| Field | Value |
|-------|-------|
| Brand | Greartisan (Zhejiang Zhengke Electromotor Co., Ltd.) |
| Model | ZGB37RG17.4i / ZYTD520 |
| MPN | A6587 (family-level, shared across ZGB37RG series) |
| Amazon ASIN | B072N84V8S |

## Electrical Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| Rated Voltage | 12V DC | |
| Voltage Range | 6-24V DC | Base motor ZYTD520 range |
| No-Load Speed (output) | 300 RPM | At 12V (verified with AS5600 encoder) |
| Motor Shaft Speed | ~5,220 RPM | At 12V (measured via AS5600 on rear shaft) |
| Rated Current | 0.1A | Likely no-load; true load current ~0.3-0.5A |
| Stall Current | ~3-4A | Estimated from JGB37-520 family data |
| Rated Torque | 1.6 kg.cm | |
| Stall Torque | ~3.2-3.7 kg.cm | Estimated |
| Gear Ratio | 1:17.4 | |
| Encoder | **None built-in** | AS5600 magnetic encoder added externally |

## Mechanical Specifications

| Parameter | Value |
|-----------|-------|
| Gearbox Diameter | 37mm |
| Gearbox Length | 23mm |
| Motor Body Diameter | 36.2mm |
| Motor Body Length | 33.3mm |
| Total Length | ~89mm (gearbox + motor + shaft) |
| Output Shaft (front) | D-shaped, 6mm diameter x 14mm length |
| Rear Shaft | 2mm diameter, ~1mm protrusion past end cap |
| Gearbox Mounting Holes | 6x M3 on 31mm PCD (60° spacing), 7mm deep |
| Gear Material | All metal |
| Weight | ~209g |
| Rotation | Reversible (swap polarity) |

## Wiring

2-wire motor (no encoder):

| Wire | Function |
|------|----------|
| Red (+) | Motor power positive |
| Black (-) | Motor power negative |

Swap red/black to reverse direction. **Solder 100nF ceramic capacitor across terminals** to suppress commutation noise (critical when using I2C encoder).

## Rear End Cap Features

The rear of the motor has:
- Bearing hub (~10mm diameter) with 2mm shaft stub extending ~1mm
- Two brass power terminal tabs (opposite sides, ~6mm wide)
- 4 rivets holding the end cap
- No threaded mounting holes — must use friction-fit or adhesive mounting

## AS5600 Encoder Integration (Tested 2026-03-20)

Added external AS5600 magnetic encoder on the rear shaft:

| Parameter | Value |
|-----------|-------|
| Mounting location | Rear of motor (pre-gearbox shaft) |
| Mount type | 3D printed friction-fit collar on motor body |
| Magnet | 4mm diametrically magnetized disc, super-glued to 2mm rear shaft |
| Air gap | ~1.5mm (shaft 1mm + magnet 2.5mm + gap 1.5mm = 5mm from end cap) |
| I2C address | 0x36 |
| Magnet status | OK (AGC=128) |
| Measured rear shaft speed | ~5,220 RPM at 12V |
| Measured output speed | ~300 RPM (confirms rated spec) |
| Effective resolution | 4,096 counts/motor-rev, 71,270 counts/output-rev |
| Minimum polling rate | 191 Hz (at 5,220 RPM) |
| Recommended polling rate | 309-807 Hz (with safety margin) |

### 3D Printed Mount

- **OpenSCAD source**: `../../3D-prints/gb37rg_as5600_mount.scad`
- **STL file**: `../../3D-prints/gb37rg_as5600_mount.stl`
- Friction-fit collar (ID 36.8mm) slides over motor body
- 4 posts hold AS5600 PCB at correct height
- Wire slots for power terminal access
- Print plate-side DOWN, no supports, PLA or PETG

### Dimension Diagram

See `../../3D-prints/71QaGQzmmvL._SL1500_.jpg` for the GB37RG dimension drawing.

## AT8236 Dead Zone (Bench Tested 2026-02-25)

Tested with ESP32-S3 LEDC PWM at 20 kHz, 8-bit resolution, 12V supply:

| Duty Value | Duty % | Result |
|------------|--------|--------|
| 64 | 25% | No movement |
| 128 | 50% | No movement |
| 140 | 55% | No movement |
| 150 | 59% | **Spins** |
| 160 | 63% | Spins |
| 200 | 78% | Spins |
| 255 | 100% | Spins |

**Starting dead zone: ~150/255 (59%)** at 20 kHz PWM on 12V.

## Comparison with ROVAC Motors

| | Greartisan ZGB37RG17.4i | JGB37-520R60-12 (ROVAC) |
|---|---|---|
| Gear Ratio | 1:17.4 | 1:60 |
| No-Load Speed | 300 RPM | ~170 RPM |
| Rated Torque | 1.6 kg.cm | 1.9 kg.cm |
| Stall Torque | ~3.5 kg.cm | ~9.2 kg.cm |
| Encoder | AS5600 (external, 4096/rev) | Hall quadrature (2640/rev) |
| Effective counts/output-rev | 71,270 | 2,640 |
| Weight | ~209g | ~152g |
| Dead Zone (AT8236, 20kHz, 12V) | 150/255 (59%) | 84/255 (33%) |
| Use Case | Bench testing + encoder dev | Robot drive motors |
