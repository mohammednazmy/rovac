# ROVAC v2 — Shopping List

Parts inventory for the v2 build. Status as of 2026-05-01.

> NOTE: v2 scope under revision — the vacuum subsystem is retired; vacuum-related parts in this list need re-scoping by the maintainer.

## Already in hand (existing ROVAC stack)

| Item | Quantity | Notes |
|---|---|---|
| Raspberry Pi 5 (8GB) | 1 | Mac brain stays on Mac; Pi handles edge ROS2 nodes |
| ESP32 motor controller (NULLLAB Maker-ESP32, CH340) | 1 | Currently running USB serial COBS firmware |
| ESP32 sensor hub (DevKitV1, CP2102) | 1 | Currently running USB serial COBS firmware |
| BNO055 9-axis IMU | 1 | On ESP32 motor controller I²C bus |
| RPLIDAR C1 | 1 | DTOF, 16 m, will mount in Neato turret bay |
| AS5600 magnetic encoders | TBD | Need to confirm count |
| TB67H450FNG H-bridge drivers | TBD | For brushroll, side brush, possibly drive motors |
| JGB37-520R60-12 motors | 2 (current ROVAC drive) | Backup option if Neato motors don't work out |
| Sense HAT panel | 1 | Optional for v2 (good debugging UI) |
| HC-SR04 ultrasonic sensors | 4 | Currently on sensor hub; may keep for redundancy |
| Sharp GP2Y0A51SK0F cliff sensors | 2 | Will be replaced by VL6180X from Neato |

## Ordered (incoming)

| Item | Quantity | Cost | ETA | Source |
|---|---|---|---|---|
| Delta BCB1012GJ-01 blower motors | 8 | ~$22 | May 6–13 | eBay (bluecloud22) |
| Neato Botvac D5 donor chassis | 1 | $39.78 | May 6–13 | eBay (thanken22) |

## Need to source before / during build

### Battery + charging (required)

| Item | Approx cost | Notes |
|---|---|---|
| Aftermarket 4S 14.4V Li-ion battery (Neato D5 form factor, 4500-5200 mAh) | $25–35 | Must fit Neato battery bay; verify dimensions on arrival before ordering |
| 4S 16.8V CC/CV charger module | $10–15 | Inputs from dock contact bars, charges battery |
| 14 AWG silicone wire (red + black, 3m each) | $8 | Main power bus |
| 20A automotive blade fuse + holder | $4 | Battery protection |
| XT60 or similar high-current connector | $5 | Battery-to-distribution disconnect |

**Subtotal: ~$50–67**

### Vacuum subsystem (Phase 1 single-motor)

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

| Item | Approx cost | Notes |
|---|---|---|
| Filament (PETG, 500g for adapters and manifold) | $20 | Phase 1 only needs motor mount adapter; Phase 3 needs full manifold |
| M3 heat-set inserts (qty 30) | $5 | For motor mounts and manifold assembly |
| M3 × 8 mm screws (qty 25) | $4 | Motor mount fasteners |
| M3 × 16 mm screws (qty 25) | $4 | Through-mount fasteners |
| Silicone foam gasket sheet (1 mm × A4) | $8 | Motor-to-manifold sealing |
| EPDM O-rings (#013, qty 8) | $4 | Round port sealing |

**Subtotal: ~$45**

### Misc electrical / mechanical

| Item | Approx cost | Notes |
|---|---|---|
| JST-PH 2.0 mm connectors + crimp pins | $10 | For sensor + motor harnesses |
| 22 AWG hookup wire assortment | $8 | For control / sensor signals |
| Sorbothane vibration pads (4 × 50 × 50 mm, 50A durometer) | $10 | Between vacuum manifold and chassis |
| Heat-shrink tubing assortment | $5 | Wire insulation |

**Subtotal: ~$33**

### Total v2 build cost estimate

| Phase | Cost |
|---|---|
| Already in hand | $0 (sunk) |
| Ordered | $62 |
| Battery + charging | $50–67 |
| Vacuum Phase 1 (single motor) | $45 |
| Misc | $33 |
| **Total estimated build cost** | **$190–207** |

Phase 3 (full Layout B1 compound) adds:
- 3 more inter-stage ducts and 1 more motor mount printable: ~$10 filament
- Larger battery (5200+ mAh) optional: +$15–25

## Inventory check tasks (before build)

These need confirmation. **TODO** before committing build:

- [ ] Count AS5600 modules in inventory — need 2 (one per drive motor)
- [ ] Count TB67H450FNG H-bridges — need 4 (2 drive motors + brushroll + side brush)
- [ ] Verify quality of existing 14 AWG silicone wire stock
- [ ] Inventory M3 hardware — heat-set inserts, screws of various lengths
- [ ] Check if existing JST-PH crimp tool is in working order
- [ ] Confirm 4S Li-ion charging adapter (if any) — would save buying one

## Specific product recommendations to research

These haven't been pinned down yet — pending separate research:

### Aftermarket Neato D5 battery
- Search "Neato Botvac D5 battery replacement 4S 14.4V Li-ion 5200mAh" on Amazon and eBay
- Target: brand-name cells (Samsung, LG, Sony — not no-name), built-in BMS, fits original Neato bay
- Don't buy generic "compatible" batteries with unknown cell quality
- Verify recent positive reviews specifically calling out cell brand

### 4S CC/CV charger module
- Search "4S 16.8V Li-ion CC/CV charger module 2A" on Amazon
- Target: 16.8 V output (4S full charge), 1–2 A charge current, with BMS protection
- Brand suggestions: TP4056-based discrete chargers, BMS+charger combo modules

Both items deserve a separate focused research pass once battery bay dimensions are measured on the Neato D5.

## Honest gaps

- **Battery bay dimensions not yet measured** — verify on Neato arrival before ordering battery
- **Motor shaft diameter not yet measured** — verify on motor arrival before printing AS5600 adapter
- **Brushroll/side brush stall current not yet measured** — may need different H-bridge (BTS7960 if >3.5 A)
- **HEPA filter availability** — unclear if Neato D5 unit ships with HEPA installed; aftermarket replacements ~$8 if not
