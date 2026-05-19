# ROVAC v2 — Low-Profile Chassis Migration

**Status:** Planning / pre-arrival
**Last updated:** 2026-05-01

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

**Goal (as originally planned):** Replace ROVAC's current Yahboom G1 tank chassis (~150 mm tall) with a low-profile chassis (~100 mm tall) by repurposing a used Neato Botvac D5 as a mechanical donor.

## Hardware committed

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

| Item | Quantity | Status | Cost |
|---|---|---|---|
| Delta BCB1012GJ-01 blower motors | 8 | Ordered (eBay, est. arrival May 6–13) | ~$22 |
| Neato Botvac D5 donor chassis | 1 | Ordered (eBay, est. arrival May 6–13) | $39.78 |
| **Total committed** | | | **~$62** |

Existing ROVAC stack to migrate: Raspberry Pi 5, ESP32 motor controller, ESP32 sensor hub, BNO055 IMU, RPLIDAR C1, AS5600 magnetic encoders, TB67H450FNG H-bridges, Sense HAT panel.

## Documents in this folder

| File | Purpose |
|---|---|
| [decisions.md](decisions.md) | All design decisions made + rationale (ADR-style) |
| [neato_d5_internals.md](neato_d5_internals.md) | Research findings on what's inside the D5 |
| [shopping_list.md](shopping_list.md) | Parts inventory + parts to source |
| [conversion_checklist.md](conversion_checklist.md) | First 30-min inspection + step-by-step assembly |

> NOTE: `vacuum_subsystem.md` (4-stage compound manifold, Layout B1 plan) was moved to `archive/experiments/` when the vacuum function was retired.

## Why this migration

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

**Current ROVAC** is a Yahboom G1 tank with:
- LIDAR mast on top of the chassis stack
- Total height ~150 mm; total footprint ~250 × 250 mm

**ROVAC v2** targeted a low-profile form factor:
- D-shape
- ~100 mm total height (under-furniture access)
- ~340 × 340 mm footprint
- Differential drive (matches existing ROVAC firmware kinematics)
- Pre-engineered cliff sensors (VL6180X ToF — upgrade over current Sharp IR)

## Approach summary

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

The Neato Botvac D5 is a $40 mechanical donor. We strip its locked QNX mainboard and reuse:
- Chassis, wheels, drive motors, suspension, bumper, cliff sensors, LIDAR turret bay
- Charging dock contacts (mechanical only)

We replace:
- Mainboard → ROVAC's existing Pi 5 + ESP32 stack
- Drive motor encoders → AS5600 magnetic encoders (12-bit absolute)
- OEM LIDAR (Piccolo LDS) → RPLIDAR C1 (existing)
- Battery → fresh aftermarket 4S 14.4V Li-ion + dedicated 4S CC/CV charger

See [decisions.md](decisions.md) for full rationale on each.

## Current status

- [x] Donor chassis ordered (Neato D5, $39.78)
- [x] Blower motors ordered (8× Delta BCB1012GJ-01)
- [x] Research complete: Neato internals, motor specs, layout options
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
3. Cliff sensors confirmed as VL6180X (D7 teardown showed this; D5 likely same)
4. Charging contact polarity
5. Battery connector pinout

## Project history context

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

This v2 effort grew out of an exploration that started with "how does a blower motor work?", progressed through commercial blower research and multi-motor compound design, and converged on the Neato donor approach when it became clear that the Delta motors already ordered are the OEM Neato motors.
