# ROVAC v2 — Design Decisions

ADR-lite log of decisions made during planning, with rationale and alternatives considered. Use this as the canonical reference when working on the build — if anything in code or config conflicts with these decisions, this document is authoritative until explicitly revised.

---

## D1 — Use Neato Botvac D5 as donor chassis

**Status:** ✅ Accepted (2026-05-01)

**Context:** Current ROVAC is a Yahboom G1 tank chassis with vacuum stacked on top — ~150 mm tall, not vacuum-optimized. Need a low-profile (≤110 mm) D-shape or round chassis with differential drive, dust cup mounting, and LIDAR provision.

**Decision:** Buy a used "for parts" Neato Botvac D5 ($40 shipped) and use it as a mechanical donor.

**Rationale:**
- D-shape, ~100 mm tall — fits under furniture
- Pre-engineered drive system (wheels, suspension, motors, encoders)
- Pre-engineered dust cup + cyclone + HEPA chamber
- Pre-engineered LIDAR turret bay + bumper + cliff sensors
- Neato D-series uses Delta BCB1012GJ-01 motors as OEM suction — drop-in compatible with the 8 we already own
- Cheaper than alternatives: ~$40 vs ~$300+ for ground-up CAD/print or $300 hobby platform

**Alternatives considered:**
- Yahboom Rosmaster X3 ($300+): mecanum drive (worse for vacuum kinematics), exceeds height budget
- 3D-printed custom chassis: weeks of CAD work, no proven ergonomics
- Dyson V6 motor on a custom platform: V6 form factor is stick-vacuum-shaped (220 mm tall), incompatible with low-profile target
- Roborock S5/S6 donor: chassis available but doesn't have motor compatibility advantage

---

## D2 — Discard Neato mainboard; use ROVAC's existing Pi 5 + ESP32 stack

**Status:** ✅ Accepted (2026-05-01)

**Context:** Neato D5 mainboard is a TI Sitara SoC running QNX with signed boot. Locked, not reflashable.

**Decision:** Discard the Neato mainboard entirely. Use ROVAC's existing Pi 5 + ESP32 motor controller + ESP32 sensor hub stack with the Neato chassis.

**Rationale:**
- Sitara firmware is signed and not reflashable
- OpenNeato project (https://github.com/94-psy/OpenNeato) tried real-time control via the OEM CLI and explicitly abandoned that path
- ROVAC stack is already proven, working, ROS2-integrated
- Re-using the Neato mainboard would require reverse-engineering proprietary protocols with no upside

**Implications:**
- All sensor signals re-route to our ESP32s
- Drive motors driven by either ROVAC's TB67H450FNG H-bridges or new dedicated drivers (TBD)
- Charging logic must be replaced (it's integrated into the discarded mainboard)

---

## D3 — Keep Neato drive motors; add AS5600 magnetic encoders

**Status:** ✅ Accepted (2026-05-01) — *revised from initial recommendation*

**Original recommendation:** Replace Neato motors with ROVAC's existing JGB37 motors via 3D-printed bolt-pattern adapter.

**Revised decision:** Keep the Neato drive motors. Mount AS5600 magnetic encoders on the motor shafts to replace the OEM single-channel Hall encoders.

**Rationale for revision:**
- AS5600 provides 12-bit absolute angle (4096 positions/rev) — far higher resolution than ROVAC's current 2640 ticks/wheel-rev quadrature
- I²C interface (no GPIO pulse counting)
- Eliminates the single-channel-Hall direction ambiguity entirely
- Neato motors are pre-fit to Neato wheels — no adapter needed
- Pre-engineered wheel suspension geometry preserved
- 14.4 V drive matches the chassis battery natively (no boost converter needed)

**Trade-offs:**
- Need to re-tune motor PID for new motor characteristics (~2-4 hours)
- AS5600 mount adapter must be CAD'd after measuring motor shaft diameter on arrival
- Motor stall current must be measured to size H-bridge

**Alternatives considered:**
- Use Neato motors with OEM single-Hall encoders: incompatible with current ROVAC firmware (expects quadrature)
- Mod Neato motors with second Hall offset 90°: lower resolution than AS5600, more invasive than just replacing the encoder

---

## D4 — Replace Neato OEM LIDAR with RPLIDAR C1

**Status:** ✅ Accepted (2026-05-01)

**Context:** Neato has a Piccolo LDS (laser distance sensor) — a 360° rotating laser scanner. ROVAC already has an RPLIDAR C1.

**Decision:** Discard Neato Piccolo LDS. Mount RPLIDAR C1 in the same turret bay using a 3D-printed adapter ring.

**Rationale:**
- RPLIDAR C1: 16 m DTOF, ~10 Hz, well-supported in ROS2 (`rplidar_ros` driver already in ROVAC stack)
- Neato LDS: ~6 m ToF triangulation, lower accuracy
- C1 is self-contained (own motor + electronics) — simpler integration
- Discard subsystem: spin motor, belt, optical encoder (purpose-built for OEM LDS, no use after replacement)
- **Keep:** turret bearing (mechanical mount for C1)

---

## D5 — Migrate to VL6180X cliff sensors (upgrade)

**Status:** ✅ Accepted (2026-05-01) — *meaningful upgrade independent of chassis swap*

**Context:** ROVAC current cliff sensors are Sharp GP2Y0A51SK0F analog IR — color-sensitive, requires per-unit calibration, ~5-15 mm accuracy. The Neato D5 contains VL6180X ToF cliff sensors.

**Decision:** Replace ROVAC's current cliff sensors with the VL6180X ToF sensors found in the Neato D5.

**Rationale:**
- VL6180X is a calibration-free ToF laser ranger
- ±1-2 mm accuracy (vs ±5-15 mm for Sharp IR)
- I²C interface (cleaner than analog ADC channels)
- Pre-mounted in Neato chassis (no rebuild needed)
- Upgrade is valuable even apart from the chassis swap — could be done today on current ROVAC

**Implementation note:** Two VL6180X chips share an I²C bus; address conflict (default 0x29) is resolved by XSHUT pin pull-down sequencing during init.

---

## D6 — Vacuum motor layout: B1 (2×2 dual-pair pancake)

**Status:** ✅ Accepted (2026-05-01) for initial build; future upgrade path documented

**Context:** Eight Delta BCB1012GJ-01 motors purchased. Multiple layouts considered (Layout A quad-compound, Layout B dual-pair, Layout C dual-quad).

**Decision:** Initial build uses Layout B1: 4 of the 8 motors in a 2×2 flat pancake arrangement. Front pair (S1A → S2A) and rear pair (S1B → S2B). Two intakes (front + rear), two exhausts (sides). 4 motors held as spares.

**Rationale:**
- Compact 160×160 mm footprint fits Neato D5 chassis
- 65 mm tall — preserves low CoG
- Two cleaning paths (front + rear) — wider effective cleaning width
- ~3,500 Pa per intake (compound 2-stage)
- 4 motor spares for failure replacement and future upgrade

**Future upgrade path:** Layout C2 (stacked dual-quad, 8 motors total) for ~6,500 Pa per intake. Requires extending chassis height by ~65 mm or adding a roof-rack assembly.

**See:** [vacuum_subsystem.md](vacuum_subsystem.md) for full Layout B1 design and CAD references.

---

## D7 — Battery: Fresh aftermarket 4S Li-ion + dedicated 4S CC/CV charger

**Status:** ✅ Accepted (2026-05-01)

**Context:** Neato OEM battery may be dead (seller's diagnosis: "I believe the issue is the battery"). Neato charging logic is integrated into the discarded mainboard — not isolatable as a separate module.

**Decision:** Buy a fresh aftermarket 4S 14.4 V Li-ion replacement battery sized to fit the Neato D5 battery bay (~$30). Use a dedicated 4S CC/CV charger module (~$15) wired to the Neato dock contact bars.

**Rationale:**
- New battery: predictable lifespan, known capacity (vs unknown used)
- Dock auto-charging preserved (charger gets power from dock contacts)
- BMS built into the aftermarket pack (over-voltage, under-voltage, balance, thermistor)
- Total cost ~$45, simplest electronics
- Capacity upgrade path: drop in a higher-capacity 4S pack (5200+ mAh) any time without other changes

**Alternatives considered:**
- Custom 18650 pack: requires spot welder, BMS expertise, fire-safety practice; reject for first-time build
- Use Neato's charging logic: not possible; integrated into locked mainboard
- Use existing OEM Neato battery: condition unknown, likely degraded, not recommended
- LiFePO4 chemistry: different voltage (12.8 V vs 14.4 V), longer cycle life but lower energy density; reject for now

---

## D8 — Keep Neato bumper, wheel-drop switches, dust cup, HEPA chamber

**Status:** ✅ Accepted (2026-05-01)

**Decision:** Reuse the following Neato mechanical components in the v2 build:

| Component | Interface | ROVAC integration |
|---|---|---|
| Bumper assembly + 4 SPST microswitches | 3.3 V GPIO with internal pull-up | ESP32 sensor hub digital inputs |
| Wheel-drop microswitches (×2) | SPST, normally-closed | ESP32 sensor hub digital inputs |
| Dust cup with cyclone | Mechanical only | Slides into chassis dust bay |
| HEPA filter chamber | Mechanical only | Sits between cyclone and exhaust |
| Side brush + motor | 14.4 V brushed DC, low current | TB67H450FNG H-bridge from sensor hub |
| Brushroll + motor | 14.4 V brushed DC | TB67H450FNG H-bridge from sensor hub |
| Charging contact bars | Mechanical only | Wire to charger module input |
| LIDAR turret bearing | Mechanical only | Adapter ring to RPLIDAR C1 |

**Rationale:** All of these are pre-engineered to fit the Neato chassis and are simple electrical interfaces (digital switches, brushed DC motors). Reusing them saves significant integration work.

**Discard:** Mainboard, WiFi module (D5 Connected only), on-board accelerometer, OEM Neato battery (likely degraded), LDS (replaced with RPLIDAR C1), LDS spin motor + belt + encoder, OEM suction fan (replaced with Delta BCB1012GJ-01).

---

## D9 — Initial vacuum power: single Delta motor

**Status:** ✅ Accepted (2026-05-01) — *deferred from full Layout B1*

**Context:** Layout B1 calls for 4 Delta motors arranged as two compound pairs. But a working single-motor configuration is simpler to bring up and validates the mechanical/electrical integration before adding compound complexity.

**Decision:** First working configuration uses ONE Delta BCB1012GJ-01 motor mounted in the Neato dust cup's existing fan bay. Validate end-to-end (Pi 5 → ESP32 → suction motor → dust cup → cyclone → HEPA → exhaust) before adding compound stages.

**Upgrade path:** Once single-motor configuration is proven and characterized:
1. Design 2-stage compound manifold (S1 → S2) on a test bench with manometer measurement
2. Verify 2-stage delivers ~3,500 Pa as predicted
3. Design Layout B1 dual-pair manifold for the chassis
4. Mount in chassis, test full B1 configuration
5. (Future) Layout C2 with all 8 motors if more power is needed

**Rationale:**
- De-risks the integration: many things could go wrong (motor fitment, ESP32 PWM, battery sag, thermal); isolate them
- Faster path to a working v2 prototype
- Holds 4-stage compound as a clean upgrade rather than a v1-blocker
- Lets us measure the OEM Neato dust path performance for comparison

---

## Decision change log

| Date | Decision | Change |
|---|---|---|
| 2026-05-01 | D3 (drive motors) | Initial recommendation was JGB37 swap; revised to keep Neato motors after user noted AS5600 availability |
