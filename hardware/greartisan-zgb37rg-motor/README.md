# Greartisan ZGB37RG17.4i Gear-Box Motor

## Overview

Bench test motor used to validate the AT8236 motor driver board with the ESP32-S3.
**Not installed on ROVAC** — these are encoder-less motors used for prototyping only.

Quantity: 2

## Identification

| Field | Value |
|-------|-------|
| Brand | Greartisan (Zhejiang Zhengke Electromotor Co., Ltd.) |
| Model | ZGB37RG17.4i / ZYTD520 |
| MPN | A6587 (family-level, shared across ZGB37RG series) |
| Amazon ASIN | B072N84V8S |
| Purchase Link | https://www.amazon.com/dp/B072N84V8S |

## Electrical Specifications

| Parameter | Value | Notes |
|-----------|-------|-------|
| Rated Voltage | 12V DC | |
| Voltage Range | 6-24V DC | Base motor ZYTD520 range |
| No-Load Speed | 300 RPM | At 12V |
| Rated Current | 0.1A | Likely no-load; true load current ~0.3-0.5A |
| Stall Current | ~3-4A | Estimated from JGB37-520 family data |
| Rated Torque | 1.6 kg.cm | |
| Stall Torque | ~3.2-3.7 kg.cm | Estimated |
| Gear Ratio | 1:17.4 | |
| Encoder | **None** | No built-in encoder |

## Mechanical Specifications

| Parameter | Value |
|-----------|-------|
| Gearbox Diameter | 37mm |
| Gearbox Length | 23mm |
| Motor Body Diameter | 36.2mm |
| Motor Body Length | 33.3mm |
| Total Length | ~89mm (gearbox + motor + shaft) |
| Output Shaft | D-shaped, 6mm diameter x 14mm length |
| Mounting Holes | M3 |
| Gear Material | All metal |
| Weight | ~209g |
| Rotation | Reversible (swap polarity) |

## Wiring

2-wire motor (no encoder):

| Wire | Function |
|------|----------|
| Red (+) | Motor power positive |
| Black (-) | Motor power negative |

Swap red/black to reverse direction.

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

Despite the lower 1:17.4 gear ratio, the Greartisan has a **higher** dead zone than
the JGB37-520R60-12 (59% vs 33%) — likely due to lower-quality bearings and gear mesh.

## Comparison with ROVAC Motors

| | Greartisan ZGB37RG17.4i | JGB37-520R60-12 (ROVAC) |
|---|---|---|
| Gear Ratio | 1:17.4 | 1:60 |
| No-Load Speed | 300 RPM | ~170 RPM |
| Rated Torque | 1.6 kg.cm | 1.9 kg.cm |
| Stall Torque | ~3.5 kg.cm | ~9.2 kg.cm |
| Encoder | None | Hall quadrature (11 PPR) |
| Weight | ~209g | ~152g |
| Dead Zone (AT8236, 20kHz, 12V) | 150/255 (59%) | 84/255 (33%) |
| Use Case | Bench testing | Robot drive motors |
