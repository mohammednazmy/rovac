# ROVAC v2 — Low-Profile Chassis Migration

**Status:** Planning / pre-arrival
**Last updated:** 2026-05-01
**Goal:** Replace ROVAC's current Yahboom G1 tank chassis (~150 mm tall with vacuum + LIDAR stack) with a low-profile robot vacuum chassis (~100 mm tall) by repurposing a used Neato Botvac D5 as a mechanical donor.

## Hardware committed

| Item | Quantity | Status | Cost |
|---|---|---|---|
| Delta BCB1012GJ-01 suction motors | 8 | Ordered (eBay, est. arrival May 6–13) | ~$22 |
| Neato Botvac D5 donor chassis | 1 | Ordered (eBay, est. arrival May 6–13) | $39.78 |
| **Total committed** | | | **~$62** |

Existing ROVAC stack to migrate: Raspberry Pi 5, ESP32 motor controller, ESP32 sensor hub, BNO055 IMU, RPLIDAR C1, AS5600 magnetic encoders, TB67H450FNG H-bridges, Sense HAT panel.

## Documents in this folder

| File | Purpose |
|---|---|
| [decisions.md](decisions.md) | All design decisions made + rationale (ADR-style) |
| [neato_d5_internals.md](neato_d5_internals.md) | Research findings on what's inside the D5 |
| [vacuum_subsystem.md](vacuum_subsystem.md) | 4-stage compound vacuum manifold, Layout B1 plan |
| [shopping_list.md](shopping_list.md) | Parts inventory + parts to source |
| [conversion_checklist.md](conversion_checklist.md) | First 30-min inspection + step-by-step assembly |

## Why this migration

**Current ROVAC** is a Yahboom G1 tank with:
- Vacuum stacked on top of the tank chassis
- LIDAR mast on top of the vacuum
- Total height ~150 mm; total footprint ~250 × 250 mm
- Suboptimal cleaning paths (tank tracks, not optimized for floor coverage)

**ROVAC v2** targets a proper robot-vacuum form factor:
- D-shape (corners cleanable)
- ~100 mm total height (under-furniture access)
- ~340 × 340 mm footprint
- Differential drive (matches existing ROVAC firmware kinematics)
- Pre-engineered dust path (cyclone + dust cup + HEPA)
- Pre-engineered cliff sensors (VL6180X ToF — upgrade over current Sharp IR)

## Approach summary

The Neato Botvac D5 is a $40 mechanical donor. We strip its locked QNX mainboard and reuse:
- Chassis, wheels, drive motors, suspension, bumper, cliff sensors, dust cup, LIDAR turret bay
- Charging dock contacts (mechanical only)
- Brushroll, side brush, and their motors

We replace:
- Mainboard → ROVAC's existing Pi 5 + ESP32 stack
- Drive motor encoders → AS5600 magnetic encoders (12-bit absolute)
- OEM LIDAR (Piccolo LDS) → RPLIDAR C1 (existing)
- Suction fan → one Delta BCB1012GJ-01 (initially), upgradeable to 4-stage compound later
- Battery → fresh aftermarket 4S 14.4V Li-ion + dedicated 4S CC/CV charger

See [decisions.md](decisions.md) for full rationale on each.

## Current status

- [x] Donor chassis ordered (Neato D5, $39.78)
- [x] Suction motors ordered (8× Delta BCB1012GJ-01)
- [x] Research complete: Neato internals, vacuum motor specs, layout options
- [x] Layout decision: B1 dual-pair pancake (initial), C2 dual-quad as future upgrade
- [ ] Battery + charger sourced (see [shopping_list.md](shopping_list.md))
- [ ] Pre-arrival CAD: AS5600 motor shaft adapter (pending shaft measurement)
- [ ] Hardware arrival
- [ ] First 30-min inspection ([conversion_checklist.md](conversion_checklist.md))
- [ ] Brain swap
- [ ] Software bring-up
- [ ] Navigation testing

## Open questions to resolve on arrival

1. Exact Neato D5 motor shaft diameter (for AS5600 adapter)
2. Drive motor encoder PPR at the wheel (community estimate ~360, unverified)
3. Brushroll / side-brush motor stall current (sizes H-bridge requirement)
4. Cliff sensors confirmed as VL6180X (D7 teardown showed this; D5 likely same)
5. Suction fan exact Delta P/N (D7 was BFB1012UH-BA40ZYD; D5 may differ)
6. Charging contact polarity
7. Battery connector pinout

## Project history context

This v2 effort grew out of an exploration that started with "how does a vacuum motor work?" (zip-lock bag + computer fan experiment), progressed through commercial blower research, multi-motor compound design, and converged on the Neato donor approach when it became clear that the Delta motors we'd already ordered are the OEM Neato suction motors.
