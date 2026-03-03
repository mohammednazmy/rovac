# Battery Inventory — Charge Settings Reference

> Charger: Hiyiton V6 (SkyRC B6 V2)
> Last updated: 2026-02-21

---

## Battery 1: Li-Ion 18650 1200 mAh 3.7V

| Field | Value |
|-------|-------|
| Chemistry | Li-Ion |
| Form Factor | 18650 (single cell) |
| Nominal Voltage | 3.7V |
| Capacity (rated) | 1200 mAh |
| Energy | 4.44 Wh |
| Cell Count | **1S** |
| Max Charge Voltage | **4.10V** |
| Discharge Cutoff | 2.9–3.0V |

### Charger Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Battery Type | **Li-Ion** | NOT LiPo (LiPo charges to 4.2V — too high for Li-Ion) |
| Mode | **CHARGE** | Balance CHG also works for 1S, but unnecessary |
| Cell Count | **1S 4.10V** | |
| Charge Current | **0.6A** (0.5C) | Safe, gentle on cell. Max recommended: 1.0A (≈1C) |
| Balance Lead | **Not needed** | Single cell — main leads only |

### Procedure
1. Connect cell to main output leads (red +, black -)
2. BATT/PROG → Li-Ion → CHARGE
3. Set 0.6A, 1S 4.10V
4. HOLD ENTER 3 sec → charge starts
5. Wait for "FULL" (~1.5–2 hours at 0.6A)

### Notes
- Genuine 1200 mAh 18650 — reasonable capacity for this size
- Good for low-drain applications (sensors, ESP32 projects)
- Run a discharge test at 0.5A to verify actual capacity

---

## Battery 2: WZS 18650 6800 mAh 3.7V

| Field | Value |
|-------|-------|
| Chemistry | Li-Ion |
| Form Factor | 18650 (single cell) |
| Nominal Voltage | 3.7V |
| Capacity (claimed) | 6800 mAh |
| Cell Count | **1S** |
| Max Charge Voltage | **4.10V** |
| Discharge Cutoff | 2.9–3.0V |

### Charger Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Battery Type | **Li-Ion** | |
| Mode | **CHARGE** | |
| Cell Count | **1S 4.10V** | |
| Charge Current | **1.0A** | Conservative — see capacity warning below |
| Balance Lead | **Not needed** | Single cell |

### Procedure
1. Connect cell to main output leads
2. BATT/PROG → Li-Ion → CHARGE
3. Set 1.0A, 1S 4.10V
4. HOLD ENTER 3 sec → charge starts
5. Watch the charged mAh counter — this reveals actual capacity

### CAPACITY WARNING

**The "6800 mAh" rating is almost certainly inflated.** The physical limit of an 18650 cell is approximately 3500 mAh (achieved by top-tier cells like Samsung 35E or Panasonic NCR18650GA). Budget 18650 cells branded with 4800–9900 mAh ratings typically measure **800–1500 mAh** in actual testing.

**Recommended: Run a capacity test.**
1. Fully charge to 4.10V (Li-Ion CHARGE mode)
2. Switch to DISCHARGE mode: 0.5A, cutoff 3.0V
3. The discharged mAh shown at "DONE" = actual usable capacity
4. Update this document with the real measured value

| Measurement | Value |
|-------------|-------|
| Actual capacity (measured) | ___ mAh (run test and fill in) |
| Test current | 0.5A |
| Test cutoff | 3.0V |

---

## Battery 3: Cybertech Ni-MH 3500 mAh 42 Wh 12V

| Field | Value |
|-------|-------|
| Chemistry | NiMH |
| Pack Voltage (nominal) | 12.0V |
| Capacity | 3500 mAh |
| Energy | 42 Wh |
| Cell Count | **10S** (12.0V ÷ 1.2V/cell = 10 cells) |
| Full Charge Voltage (approx) | ~14.5V (10 × ~1.45V) |
| Discharge Cutoff | 10.0V (1.0V/cell × 10) |

### Charger Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Battery Type | **NiMH** | |
| Mode | **CHARGE** | Or CYCLE if reconditioning |
| Cell Count | **10 cells** | Set via INC/DEC when cell count flashes |
| Charge Current | **1.75A** (0.5C) | Safe rate. Max: 3.5A (1C) if time-constrained |
| Balance Lead | **Not applicable** | NiMH packs don't use balance charging |

### Procedure
1. Connect pack to main output leads (observe polarity carefully)
2. BATT/PROG → NiMH → CHARGE
3. Set 1.75A (or up to 3.5A for faster charge)
4. HOLD ENTER 3 sec → charge starts
5. Charger uses delta-peak detection to stop when full
6. Wait for "DONE" + beep (~2–3 hours at 1.75A)

### Notes
- 42 Wh is significant energy — this is likely a power tool or RC car pack
- NiMH packs benefit from occasional cycling (DCHG>CHG, 3 cycles) to maintain capacity
- NiMH self-discharges faster than lithium (~10–20% per month)
- If pack hasn't been used in months, do a CYCLE (3x DCHG>CHG) to recondition
- Set safety timer to at least 180 min for this pack at 0.5C charge rate

### Reconditioning (if capacity seems low)
1. BATT/PROG → NiMH → CYCLE
2. Select DCHG>CHG (discharge first)
3. Set cycles: 3
4. Discharge current: 1.0A, charge current: 1.75A
5. HOLD ENTER 3 sec → charger cycles automatically

---

## Battery 4: Puredick Li-ion Laptop Battery 10.95V 6000 mAh (M/N: A1322)

> **Status: VERIFIED WORKING** — Successfully woke from BMS lockout and charged (2026-02-22)

| Field | Value |
|-------|-------|
| Chemistry | Li-ion (label says "Li-ion"; cells charge to 4.2V/cell like LiPo) |
| Form Factor | Laptop battery pack (MacBook Pro 13" Mid-2009 to Mid-2012) |
| Model Number | A1322 |
| Pack Voltage (nominal) | 10.95V (spec) / 10.85V (label) |
| Capacity (rated) | 6000 mAh |
| Energy | ~63.5 Wh |
| Cell Count | **3S** (3 series groups) |
| Internal Configuration | **3S2P** (6 pouch cells: 3 series × 2 parallel, ~3000 mAh per cell) |
| Max Charge Voltage | **12.60V** (3 × 4.20V/cell) |
| Discharge Cutoff | 9.0V (3.0V/cell × 3) |
| Onboard BMS | bq20z451 or aftermarket equivalent — overvoltage, undervoltage, thermal, cell balancing |
| Verified Wake Voltage | 10.73V (3.58V/cell, ~50-60% SOC) after BMS recovery |

### 9-Pin Connector Pinout (VERIFIED on this specific battery)

Pins numbered 1–9 from left to right, looking at the blade contacts face-on.

**This Puredick battery has REVERSED polarity vs standard Apple pinout.**

| Pin | Function | Verified |
|-----|----------|----------|
| 1 | **GND (negative)** | Continuity with pins 2, 3 |
| 2 | **GND (negative)** | Continuity with pins 1, 3 |
| 3 | **GND (negative)** | Continuity with pins 1, 2 |
| 4 | Signal (SMBus SCL) | No continuity with other pins, 0V to all groups |
| 5 | Signal (SYS_DETECT_L) | No continuity with other pins, 0V to all groups |
| 6 | Signal (SMBus SDA) | No continuity with other pins, 0V to all groups |
| 7 | **+VBAT (positive)** | Continuity with pins 8, 9 — reads +10.73V vs GND |
| 8 | **+VBAT (positive)** | Continuity with pins 7, 9 |
| 9 | **+VBAT (positive)** | Continuity with pins 7, 8 |

**Verification method used:**
1. Continuity test confirmed 3 groups: {1,2,3}, {4} {5} {6} (no mutual continuity), {7,8,9}
2. DC voltage: Red probe on Group 3 (pin 7-9), Black on Group 1 (pin 1-3) = **+10.73V**
3. Group 2 signal pins show 0V relative to both power groups

### Charger Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Battery Type | **LiPo** | On the B6 V2, "LiPo" mode charges to 4.20V/cell (correct for this pack). "Li-Ion" mode only goes to 4.10V/cell which would undercharge. |
| Mode | **CHARGE** | Balance CHG not possible — no cell taps exposed on connector |
| Cell Count | **3S** (displays as "11.1V") | The 11.1V shown is the nominal label, NOT the charge cutoff. Charger still charges to 12.6V (4.2V/cell). |
| Charge Current | **1.0A** | ~0.17C — gentle. 2.0A (~0.33C) also safe for faster charging. |
| Balance Lead | **Not available** | Internal BMS does its own passive cell balancing |
| Confirmation Screen | **R:3S S:3S → press ENTER** | Charger asks to confirm detected (R) matches set (S) cell count |

### Charging Procedure (Normal)

1. Connect charger **red (+)** to any pin in **Group 3** (pins 7, 8, or 9)
2. Connect charger **black (-)** to any pin in **Group 1** (pins 1, 2, or 3)
3. BATT/PROG → **LiPo** → **CHARGE**
4. Set current: **1.0A**
5. Set cells: **3S** (displays 11.1V — this is correct)
6. **HOLD ENTER for 3 seconds** — charger shows R:3S S:3S confirmation
7. Press **ENTER** to confirm → charging begins
8. Display shows: `Li3 1.0A <voltage>` / `CHG <time> <mAh>`
9. **Monitor temperature** every 15–20 min — should stay cool
10. **Charge on fireproof surface** (LiPo bag, ceramic tile, metal tray)
11. Wait for **"FULL"** + beep at 12.6V
12. Expected charge time: ~2–3 hours from 50% SOC, ~4–6 hours from empty

### BMS Lockout Recovery (if battery reads ~0V)

**This procedure was successfully used on this battery (2026-02-22).**

If the battery reads near 0V (e.g., 0.05V) on the main terminals, the BMS has entered undervoltage lockout — the charge/discharge FETs are open, disconnecting the cells from the output. The cells are likely still alive but the BMS won't wake up normally.

**The body-diode rescue technique:**

The MOSFET body diodes allow a tiny current to flow in the charge direction even when the FETs are off. By pushing current through these diodes, you can raise the cell voltage above the BMS lockout threshold, causing the BMS to close the FETs and restore normal operation.

1. Connect B6 V2 **red (+)** to Group 3 (pins 7-9), **black (-)** to Group 1 (pins 1-3)
2. Set charger to **NiMH** mode, **1 cell**, **0.1A** (lowest current)
3. HOLD ENTER 3 seconds to start
4. If charger refuses to start at 0.1A, try **0.2A** or **Pb (Lead-acid) mode** at 6V/0.1A
5. A small current should flow through the body diodes
6. **Every 5 minutes**: STOP, disconnect, re-measure voltage with multimeter
7. Watch for voltage to climb — even 0.05V → 0.5V is progress
8. **When voltage jumps to ~8–11V** → the BMS has woken up and closed the FETs
9. **STOP the NiMH/Pb charge immediately**
10. Switch to proper **LiPo 3S CHARGE** mode at 1.0A (see normal procedure above)
11. **Never leave the NiMH rescue unattended** — this bypasses lithium safety checks

**On this battery, the BMS woke up and showed 10.73V after the rescue, indicating the cells were at ~50-60% SOC (3.58V/cell) — healthy condition despite the lockout.**

### Safety: What the Internal BMS Does For You
- **Overvoltage cutoff**: Opens charge FET if any cell exceeds ~4.25V
- **Undervoltage lockout**: Disconnects cells below ~2.5-2.8V/cell (this is what caused the 0V reading)
- **Thermal protection**: Stops on overtemperature via NTC thermistor + thermal cutoffs
- **Internal cell balancing**: Passive balancing across the 3 series groups via internal tap wires
- **Self-burning fuse**: Permanently kills the battery on catastrophic fault (irreversible)

### Robot Integration (TODO — after first charge completes)

| Robot Component | Voltage Range | A1322 Output | Compatible? |
|----------------|--------------|--------------|-------------|
| BST-4WD motor board | 6–12V | 10.0–12.6V | Yes, direct |
| Pi 5 (via buck converter) | 5V / 5A | Needs 12V→5V converter | Yes, with converter |
| ESP32 (via regulator) | 3.3V | Needs 12V→3.3V regulator | Yes, with regulator |

Runtime estimates (65 Wh battery):
- ROVAC idle (Pi + sensors, no motors): ~10W → **~6.5 hours**
- ROVAC active (motors + Pi): ~25-30W → **~2–2.5 hours**
- ROVAC heavy load (all motors + cameras): ~40W → **~1.5 hours**

### Notes
- A1322 is a MacBook Pro 13" battery (Mid-2009 to Mid-2012)
- Label says "Li-ion" — use **LiPo mode** on the B6 V2 because the cells charge to 4.2V/cell. The B6 V2's "Li-Ion" mode stops at 4.1V/cell which would undercharge this pack.
- The 3 paralleled wires per rail handle high current — connect 1 wire from each group for testing, or twist all 3 together for permanent use
- **Do not use the 3 signal wires (Group 2)** for charging — they are SMBus communication only
- After first full charge, run a **discharge capacity test** to verify actual mAh (DISCHARGE mode, 0.5A, cutoff 9.0V)
- First charge mAh result: ___ mAh (fill in when charge completes)

---

## Battery 5: Streamlight NiMH 2600 mAh 3.6V (Flashlight Pack)

| Field | Value |
|-------|-------|
| Chemistry | NiMH |
| Form Factor | Flashlight stick pack (sub-C cells) |
| Brand | Streamlight |
| Nominal Voltage | 3.6V |
| Capacity (rated) | 2600 mAh |
| Energy | 9.36 Wh |
| Cell Count | **3S** (3.6V ÷ 1.2V/cell = 3 cells) |
| Full Charge Voltage (approx) | ~4.35V (3 × ~1.45V) |
| Discharge Cutoff | 3.0V (1.0V/cell × 3) |

### Charger Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Battery Type | **NiMH** | |
| Mode | **CHARGE** | Or CYCLE if reconditioning an old pack |
| Cell Count | **3 cells** | Set via INC/DEC when cell count flashes |
| Charge Current | **1.3A** (0.5C) | Safe rate. Max: 2.6A (1C) if time-constrained |
| Balance Lead | **Not applicable** | NiMH packs don't use balance charging |

### Procedure
1. Connect pack to main output leads (red=+, black=-)
2. BATT/PROG → NiMH → CHARGE
3. Set 1.3A (or up to 2.6A for faster charge)
4. HOLD ENTER 3 sec → charge starts
5. Charger uses delta-peak detection to stop when full
6. Wait for "DONE" + beep (~2 hours at 1.3A)

### Notes
- Streamlight flashlight battery — likely sub-C NiMH cells in a stick configuration
- NiMH self-discharges ~10–20% per month — recharge before use if stored >1 month
- If capacity seems low after sitting unused, run a CYCLE (DCHG>CHG, 3 cycles) to recondition
- Set safety timer to at least 150 min for this pack at 0.5C charge rate

### Reconditioning (if capacity seems low)
1. BATT/PROG → NiMH → CYCLE
2. Select DCHG>CHG (discharge first)
3. Set cycles: 3
4. Discharge current: 0.5A, charge current: 1.3A
5. HOLD ENTER 3 sec → charger cycles automatically

---

## Battery 6: Reassembled NiMH AA 6S Pack (7.2V)

> **Origin:** 6 AA NiMH cells from the same original pack, separated into 2+4, then reconnected in series.

| Field | Value |
|-------|-------|
| Chemistry | NiMH |
| Form Factor | 6× AA cells in two sub-packs (2S + 4S wired in series) |
| Nominal Voltage | 7.2V (6 × 1.2V) |
| Capacity (rated) | 2300 mAh |
| Energy | 16.56 Wh |
| Cell Count | **6S** |
| Full Charge Voltage (approx) | ~8.7V (6 × ~1.45V) |
| Discharge Cutoff | 6.0V (1.0V/cell × 6) |

### Charger Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Battery Type | **NiMH** | |
| Mode | **CHARGE** | Or CYCLE if reconditioning |
| Cell Count | **6 cells** | Set via INC/DEC when cell count flashes |
| Charge Current | **1.15A** (0.5C) | Safe rate. Max: 2.3A (1C) if time-constrained |
| Balance Lead | **Not applicable** | NiMH packs don't use balance charging |

### Procedure
1. Wire Pack A (2S) in series with Pack B (4S) — Pack A negative → Pack B positive
2. Connect combined pack to main output leads (red=+, black=-)
3. BATT/PROG → NiMH → CHARGE
4. Set current to 1.15A, 6 cells
5. HOLD ENTER 3 sec → charge starts
6. Charger uses delta-peak detection to stop when full
7. Wait for "DONE" + beep (~2 hours at 1.15A)

### Notes
- All 6 cells are from the same original pack — matched cells, safe to charge as a single 6S unit
- Original pack rated 2300 mAh, 7.2V
- NiMH self-discharges ~10–20% per month — recharge before use if stored >1 month
- If capacity seems low, run a CYCLE (DCHG>CHG, 3 cycles) to recondition
- Set safety timer to at least 180 min for this pack at 0.5C charge rate

### Reconditioning (if capacity seems low)
1. BATT/PROG → NiMH → CYCLE
2. Select DCHG>CHG (discharge first)
3. Set cycles: 3
4. Discharge current: 0.5A, charge current: 1.15A
5. HOLD ENTER 3 sec → charger cycles automatically

## Battery 7: LPB Salvaged Jump Starter LiPo 3S 11.1V (EC5 Connector)

> **Status: CHARGED & READY** — First charge completed 2026-02-27
> **Origin:** Salvaged from a portable emergency car jump starter kit

| Field | Value |
|-------|-------|
| Chemistry | **LiPo** (Lithium Polymer pouch cells) |
| Form Factor | 3× flat pouch cells joined by BMS PCB |
| Cell Marking | LPB 6557□ S1 (LPB = generic Shenzhen OEM "Lithium Polymer Battery") |
| Cell Dimensions | ~6.5mm thick × 57mm wide × 7□mm long (from size code; verify with calipers) |
| Cell Configuration | **3S1P** (3 cells in series, 1 in parallel) |
| Nominal Voltage | **11.1V** (3 × 3.7V) |
| Full Charge Voltage | **12.6V** (3 × 4.2V) |
| Discharge Cutoff | **9.0V** (3 × 3.0V) — recommended 9.6V (3 × 3.2V) |
| Storage Voltage | ~11.55V (3 × 3.85V) |
| Capacity (estimated) | **~3,900–4,500 mAh** (3,872 mAh charged from deep discharge; discharge test for exact number) |
| Energy (estimated) | **~43–50 Wh** |
| Manufacture Date | 2019-11-02 |
| Age at Recovery | ~6.3 years |
| Main Connector | **EC5** (blue, 5mm bullet pins, 120A continuous / 150A+ burst) |
| Balance Connector | **6-pin JST-XH** (non-standard — see pinout below) |
| Onboard BMS | ZBX-01 PCB (3S protection: overcharge, over-discharge, short circuit, passive cell balancing) |
| BMS PCB Markings | "ZBX-01", "C525364", "94V-0" (UL flammability rating, NOT voltage) |
| BMS Pad Labels | B+, B-, 1B+, 2B+ (standard 3S balance tap naming) |

### Initial Condition at Recovery (2026-02-27)

| Measurement | Value | Notes |
|-------------|-------|-------|
| Pack voltage (EC5) | **8.70V** | 2.90V/cell average — deeply discharged |
| Cell 1 (via balance) | **2.78V** | Below 3.0V safe minimum |
| Cell 2 (via balance) | **2.88V** | Below 3.0V safe minimum |
| Cell 3 (via balance) | **3.03V** | Barely above minimum |
| Cell imbalance | **0.25V** spread | Moderate — expected after 6+ years |
| Swelling/puffing | None observed | Visual inspection OK |
| BMS lockout? | **No** — voltage readable on EC5 | BMS still passing voltage |

### 6-Pin JST-XH Balance Connector Pinout

**Non-standard pinout** — B+ and B- are each doubled for current handling. This connector does NOT plug directly into the B6 V2's standard 3S balance port (which expects 4-pin JST-XH).

Orientation: notch facing back, flat face forward:

```
         -----------
Pin 1    | | | | | |  Pin 6
(Left)   -----------  (Right)
```

| Pin | Label | Wire Color | Function |
|-----|-------|------------|----------|
| 1 | B+ | RED | Pack positive (12.6V full charge) |
| 2 | B+ | RED | Pack positive (duplicate) |
| 3 | 2B+ | YELLOW | Junction of Cell 2 and Cell 3 (~7.4V) |
| 4 | 1B+ | WHITE | Junction of Cell 1 and Cell 2 (~3.7V) |
| 5 | B- | BLACK | Pack negative / ground |
| 6 | B- | BLACK | Pack negative (duplicate) |

**Measuring individual cell voltages via balance connector:**

| Cell | Red Probe (+) | Black Probe (-) | Healthy Range |
|------|--------------|-----------------|---------------|
| Cell 1 | Pin 4 (1B+, WHITE) | Pin 5 or 6 (B-, BLACK) | 3.0–4.2V |
| Cell 2 | Pin 3 (2B+, YELLOW) | Pin 4 (1B+, WHITE) | 3.0–4.2V |
| Cell 3 | Pin 1 or 2 (B+, RED) | Pin 3 (2B+, YELLOW) | 3.0–4.2V |
| Full pack | Pin 1 or 2 (B+, RED) | Pin 5 or 6 (B-, BLACK) | 9.0–12.6V |

### Charger Settings

| Setting | Value | Notes |
|---------|-------|-------|
| Battery Type | **LiPo** | |
| Mode | **CHARGE** | Balance CHG not possible — 6-pin connector incompatible with B6 V2 balance port |
| Cell Count | **3S** (displays "11.1V") | |
| Charge Current | **1.0A** | 0.5C for ~4000 mAh. 0.5A also safe (gentler, slower). |
| Balance Lead | **Not connected** | Onboard BMS handles passive cell balancing |
| Confirmation Screen | **R:3S S:3S → press ENTER** | |

### Charging Procedure

1. Connect charger **red (+)** to EC5 red pin, **black (-)** to EC5 black pin
2. BATT/PROG → **LiPo** → **CHARGE**
3. Set current: **1.0A** (standard) or **0.5A** (gentler, for storage-recovery situations)
4. Set cells: **3S** (displays 11.1V)
5. **HOLD ENTER 3 seconds** → charger shows R:3S S:3S confirmation
6. Press **ENTER** to confirm → charging begins
7. Display shows: `Li3 0.5A <voltage>` / `CHG <time> <mAh>`
8. **Charge on fireproof surface** (LiPo bag, ceramic tile, metal tray)
9. **Monitor temperature** periodically — should stay cool
10. Wait for **"FULL"** + beep at 12.6V

### If Charger Rejects (Low Voltage Error)

If the B6 V2 refuses to start LiPo charge due to low cell voltage:

1. Switch to **NiMH, 1 cell, 0.2A**
2. Charge for **5 minutes**, then STOP and re-measure cells
3. Repeat until all cells are above **3.0V**
4. **Never leave NiMH recovery unattended** — bypasses lithium safety checks
5. Once above 3.0V, switch to proper LiPo CHARGE mode above

### First Charge Results (2026-02-27)

Charged from 8.70V (deeply discharged, ~2.9V/cell average) at 0.5A.

| Measurement | Value |
|-------------|-------|
| Total mAh charged | **3,872 mAh** |
| Final pack voltage | **12.60V** |
| Charge time | **7 hours 43 min** (463 min at 0.5A) |
| Pre-charge cell voltages | Cell 1: 2.78V, Cell 2: 2.88V, Cell 3: 3.03V |

### Optional: Capacity Discharge Test

To determine exact usable capacity, run a controlled discharge:

1. Fully charge the pack first (12.6V)
2. Let pack rest 30 minutes
3. BATT/PROG → LiPo → **DISCHARGE**
4. Set current: **0.5A**, cutoff: **9.0V** (3.0V/cell)
5. HOLD ENTER 3 sec → discharge starts
6. When "DONE" appears, record discharged mAh = true usable capacity

| Measurement | Value |
|-------------|-------|
| Actual capacity (measured) | ___ mAh (run test and fill in) |
| Test current | 0.5A |
| Test cutoff | 9.0V |

### Robot Integration

| Robot Component | Voltage Range | This Pack Output | Compatible? |
|----------------|--------------|------------------|-------------|
| BST-4WD motor board | 6–12V | 9.6–12.6V | **Yes, direct via EC5** |
| Pi 5 (via buck converter) | 5V / 5A | Needs 12V→5V converter | Yes, with converter |
| ESP32 (via regulator) | 3.3V | Needs 12V→3.3V regulator | Yes, with regulator |

### Notes
- **EC5 connector** is the same standard used on jump starter cables — readily available adapters/cables on Amazon
- The 6-pin balance connector was likely used in the original jump starter for powering USB ports or LED flashlight in addition to balance monitoring
- To use balance charging on the B6 V2, you would need to build a **6-pin to 4-pin JST-XH adapter cable** (connect one B- pin, 1B+, 2B+, one B+ pin to a standard 4-pin JST-XH)
- Same 3S LiPo voltage profile as Battery 4 (Puredick A1322) — interchangeable for ROVAC use
- **Age consideration**: ~6.3 years old, was deeply discharged. First charge accepted 3,872 mAh, suggesting ~4,000 mAh usable. Original capacity was likely 5,000–6,000 mAh when new.
- **Storage**: Use STORAGE mode on the charger (brings cells to ~3.85V each) if not using for >1 week

---

## Quick Comparison Table

| Battery | Chemistry | Cells | Charge Mode | Current | Max Voltage | Est. Time |
|---------|-----------|-------|-------------|---------|-------------|-----------|
| 18650 1200mAh | Li-Ion 1S | 1 | CHARGE | 0.6A | 4.10V | ~2 hrs |
| WZS 18650 6800mAh | Li-Ion 1S | 1 | CHARGE | 1.0A | 4.10V | ~1–1.5 hrs* |
| Cybertech NiMH 12V | NiMH 10S | 10 | CHARGE | 1.75A | delta-peak | ~2.5 hrs |
| Puredick A1322 10.95V | **LiPo 3S** | 3(×2P) | CHARGE | 1.0A | **12.60V** (3S on B6 V2 shows "11.1V") | ~2–3 hrs from 50% |
| Streamlight NiMH 3.6V | NiMH 3S | 3 | CHARGE | 1.3A | delta-peak | ~2 hrs |
| Reassembled AA 6S 7.2V 2300mAh | NiMH 6S | 6 | CHARGE | 1.15A | delta-peak | ~2 hrs |
| **LPB Jump Starter 11.1V** | **LiPo 3S** | **3** | **CHARGE** | **1.0A** | **12.60V** | ~4 hrs from empty |

*WZS charge time based on likely actual capacity of ~1000–1500 mAh, not the claimed 6800 mAh.

---

## Adding New Batteries

When you get a new battery, add it to this inventory using this template:

```markdown
## Battery N: [Brand] [Chemistry] [Capacity] [Voltage]

| Field | Value |
|-------|-------|
| Chemistry | |
| Nominal Voltage | |
| Capacity (rated) | |
| Cell Count | **(V ÷ cell nominal V)** |
| Max Charge Voltage | **(cells × max V/cell)** |
| Discharge Cutoff | |

### Charger Settings
| Setting | Value |
|---------|-------|
| Battery Type | |
| Mode | |
| Cell Count | |
| Charge Current | **(0.5C recommended)** |
```

### Cell Nominal Voltages for Quick Reference
- Li-Ion: 3.6V/cell → max 4.10V
- LiPo: 3.7V/cell → max 4.20V
- LiFe: 3.3V/cell → max 3.60V
- LiHV: 3.7V/cell → max 4.35V
- NiMH: 1.2V/cell → delta-peak
- Pb: 2.0V/cell → max 2.46V
