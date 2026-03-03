# Hiyiton B6 V2 Balance Charger — AI Agent Briefing

## Device Identity

| Field | Value |
|-------|-------|
| Brand Label | Hiyiton V6 |
| Actual Model | SkyRC B6 V2 (iMAX B6 V2) |
| Type | Professional Balance Charger / Discharger |
| Max Charge Power | 60W |
| Max Charge Current | 6.0A (4A for DJI batteries) |
| Max Discharge Current | 2.0A |
| Discharge Power | 5W |
| DC Input | 11–18V |
| DC/DC Output | 5–26V, 1–6A (60W max) |
| Balance Cells | 2–6S (lithium) |
| Balance Current | 300 mA/cell |
| Memory Profiles | 10 slots |
| Display | 2×16 LCD, blue backlight |
| Weight | 238g |
| Size | 115×84×31mm |
| Manual PDF | `Hiyiton_V6_Professional_Balance_Charger.pdf` in this folder |

## Supported Battery Chemistries

| Chemistry | Cell Voltage (nominal) | Charge Voltage (max/cell) | Discharge Cutoff (V/cell) | Cell Count | Capacity Range |
|-----------|----------------------|--------------------------|--------------------------|------------|---------------|
| **LiPo** | 3.7V | 4.20V | 3.0–3.3V | 1–6S | 100–50000 mAh |
| **LiHV** | 3.7V | 4.35V | 3.1–3.4V | 1–6S | 100–50000 mAh |
| **LiFe** | 3.3V | 3.60V | 2.6–2.9V | 1–6S | 100–50000 mAh |
| **Li-Ion** | 3.6V | 4.10V | 2.9–3.2V | 1–6S | 100–50000 mAh |
| **NiMH** | 1.2V | Delta-peak | 0.1–1.1V/cell | 1–15S | 100–50000 mAh |
| **NiCd** | 1.2V | Delta-peak | 0.1–1.1V/cell | 1–15S | 100–50000 mAh |
| **Pb (Lead-acid)** | 2.0V | 2.46V (normal), 2.45V (AGM), 2.45V (cold) | 1.8–2.0V/cell | 1–6S (2–12V) | 100–50000 mAh |

### Critical Voltage Limits (Lithium)

These are the hard numbers the charger uses. Getting these wrong = fire risk.

| Chemistry | Nominal (V/cell) | Full Charge (V/cell) | Storage (V/cell) | Deep Discharge Danger (V/cell) |
|-----------|------------------|---------------------|-------------------|-------------------------------|
| LiPo | 3.70 | 4.20 | ~3.85 | < 3.0 |
| LiHV | 3.70 | 4.35 | ~3.90 | < 3.0 |
| LiFe | 3.30 | 3.60 | ~3.30 | < 2.5 |
| Li-Ion | 3.60 | 4.10 | ~3.75 | < 2.5 |

## Cell Count Determination

**This is the most important calculation for safe charging.** To determine cell count:

```
Cell count (S) = Pack nominal voltage / Cell nominal voltage
```

Examples:
- 3.7V pack = 1S Li-Ion (1 × 3.6V)
- 7.4V pack = 2S LiPo (2 × 3.7V)
- 10.8V pack = 3S Li-Ion (3 × 3.6V)
- 11.1V pack = 3S LiPo (3 × 3.7V)
- 12.0V NiMH = 10S NiMH (10 × 1.2V)
- 14.8V pack = 4S LiPo (4 × 3.7V)

**Always round to nearest integer.** If the math doesn't produce a clean integer, re-check the chemistry type.

## IMPORTANT: Li-ion vs LiPo Naming on the B6 V2

The B6 V2 uses RC hobby naming conventions that differ from battery label conventions:

| B6 V2 Mode | Charge Voltage | Intended For |
|------------|---------------|--------------|
| **LiPo** | **4.20V/cell** | Lithium polymer pouches (RC packs, laptop batteries) |
| **Li-Ion** | **4.10V/cell** | Conservative mode for cylindrical cells (18650s) |

**The key gotcha:** Many batteries (including laptop packs) are labeled "Li-ion" by their manufacturer but contain pouch cells that charge to 4.2V/cell. On the B6 V2, these should use **LiPo mode** (4.2V), NOT "Li-Ion" mode (4.1V). Using "Li-Ion" mode on a 4.2V pack undercharges it to ~90%.

**When to use which mode:**
- **LiPo mode (4.2V/cell):** Laptop battery packs, RC LiPo packs, pouch cells, any pack designed for 4.2V/cell
- **Li-Ion mode (4.1V/cell):** Bare 18650/21700 cells when you want to trade ~10% capacity for longer cycle life
- **When in doubt:** Check the battery's original charger voltage. A 3S pack designed for 12.6V full charge → LiPo mode. A single 18650 where longevity matters → Li-Ion mode is fine.

## Charging Modes

### Lithium Batteries (LiPo / LiHV / LiFe / Li-Ion)

| Mode | Purpose | When to Use |
|------|---------|-------------|
| **CHARGE** | CC/CV to full capacity | Standard charge without balance |
| **BALANCE CHG** | CC/CV + cell balancing at 300mA | **Recommended default for multi-cell packs.** Equalizes cell voltages. |
| **FAST CHG** | Higher current charge | When time-critical. Less gentle on cells. |
| **STORAGE** | Charge/discharge to ~65% SOC | **Use before storing batteries for >1 week.** Prevents capacity degradation. |
| **DISCHARGE** | Controlled discharge to cutoff | Capacity testing, pack conditioning |

### NiMH / NiCd Batteries

| Mode | Purpose | When to Use |
|------|---------|-------------|
| **CHARGE** | Charge with delta-peak detection | Standard charge |
| **DISCHARGE** | Discharge to set cutoff voltage | Pre-conditioning, capacity measurement |
| **RE-PEAK** | Charge → auto top-off (1–3 cycles) | Verify full charge, condition pack |
| **CYCLE** | Repeated charge/discharge cycles (up to 5) | Restore NiMH capacity, break in new cells |

Cycle options: `DCHG>CHG` (discharge first, then charge) or `CHG>DCHG` (charge first, then discharge).

### Lead-Acid (Pb)

| Mode | Purpose |
|------|---------|
| **CHARGE** | Standard CC/CV charge |
| **AGM CHG** | For AGM (sealed) batteries |
| **COLD CHG** | For charging in cold environments |
| **DISCHARGE** | Controlled discharge |

## Charge Rate Guidelines

The "C-rate" is the charge current relative to battery capacity:
- **1C** = capacity in Ah (e.g., 2000 mAh battery → 1C = 2.0A)
- **0.5C** = half capacity (2000 mAh → 1.0A) — **safest for longevity**
- **2C** = double capacity (if battery supports it)

### Recommended Charge Rates by Chemistry

| Chemistry | Safe Rate | Fast Rate | Max (battery must support) |
|-----------|-----------|-----------|---------------------------|
| Li-Ion (18650) | 0.5C | 1C | Usually 1C max |
| LiPo (RC packs) | 1C | 2C | Some support 3-5C |
| NiMH | 0.5C–1C | 2C (if rated) | Check cell specs |
| Pb | 0.1C | 0.2C | Never exceed 0.3C |

### Charger Current Limits

| Battery Type | Charge Current Range | Discharge Current Range |
|-------------|---------------------|------------------------|
| LiPo/LiHV/LiFe/Li-Ion | 0.1–6.0A | 0.1–2.0A |
| NiMH/NiCd | 0.1–6.0A | 0.1–2.0A |
| Pb | 0.1–6.0A | 0.1–2.0A |
| DJI Mavic/TB4X | 0.1–4.0A | 0.1–2.0A |

## Operating Procedure (Lithium — Most Common)

### Balance Charge (Recommended for Multi-Cell)

1. Connect DC power input (11–18V source required)
2. Connect battery main leads to charger output (observe polarity!)
3. Connect balance lead to balance port (JST-XH connector, match cell count)
4. Press **BATT/PROG** to select battery type (LiPo / Li-Ion / LiFe / LiHV)
5. Press **INC/DEC** to navigate to **"BALANCE CHG"** mode
6. Press **ENTER** — charge current flashes → set with INC/DEC
7. Press **ENTER** again — voltage/cell-count flashes → set with INC/DEC
8. **Hold ENTER for 3 seconds** to start charging
9. Screen shows: chemistry, current, voltage, working mode, elapsed time, charged mAh
10. Charger reads **"FULL"** and beeps when complete

### Storage Mode

Same connection procedure, but select **"STORAGE"** mode. The charger will:
- **Discharge** if above ~3.85V/cell (LiPo) or ~3.75V/cell (Li-Ion)
- **Charge** if below storage voltage
- Automatically stop at storage level

### Single-Cell Li-Ion (No Balance Lead)

For single 18650 cells, only the main output leads are needed (no balance port).
Set cell count to **1S** and chemistry to **Li-Ion**.

## Operating Procedure (NiMH)

1. Connect battery to charger output (observe polarity)
2. Press **BATT/PROG** → select **NiMH**
3. Select mode: CHARGE, DISCHARGE, RE-PEAK, or CYCLE
4. For CHARGE: set current → hold ENTER 3 seconds to start
5. Charger uses **delta-peak detection** (default 4mV/cell sensitivity)
6. Charger reads **"DONE"** and beeps when complete
7. Screen shows elapsed time, end voltage, charged capacity in mAh

## Safety System Settings

| Setting | Default | Range | Purpose |
|---------|---------|-------|---------|
| Safety Timer | ON, 120 min | OFF / 1–720 min | Prevents overcharge if detection fails |
| Capacity Cut-off | ON, 5000 mAh | OFF / 100–50000 mAh | Stops if charged capacity exceeds limit |
| Temp Cut-off | ON, 50°C / 122°F | OFF / 20–80°C | Stops if battery temp exceeds limit (requires temp probe) |
| Rest Time | 10 min | 1–60 min | Cool-down between charge/discharge cycles |
| DC Input Low Cut-off | 11.0V | 10–12V | Error if input voltage drops below threshold |
| NiMH Sensitivity | 4 mV/cell | 3–15 mV/cell | Delta-peak detection sensitivity |
| NiCd Sensitivity | 3–15 mV/cell | 3–15 mV/cell | Delta-peak detection sensitivity |

## Battery Memory Profiles

The charger stores 10 profiles, each containing:
- Battery type (chemistry)
- Cell count / voltage
- Charge current (0.1–6.0A)
- Discharge current (0.1–2.0A)
- Discharge voltage (cutoff per cell)
- Terminal voltage (4.18–4.25V for LiPo; chemistry-dependent)

### Saving a Profile
1. Navigate to **BATT MEMORY** in TOOL KITS menu
2. Select memory slot (1–10)
3. Set: battery type → cell count → charge current → discharge current → discharge voltage → terminal voltage
4. Press **ENTER** to save

### Loading a Profile
1. Navigate to **BATT MEMORY** → select slot
2. Hold **ENTER for 3 seconds** — screen shows "ENTER CHARGER LOAD"
3. Profile loads and charger begins with saved settings

## Diagnostic Tools

### Lithium Battery Voltage Meter
- **TOOL KITS → BATT METER** → Press ENTER
- Shows each cell's individual voltage
- Shows total voltage, highest cell, lowest cell
- Requires balance lead connected

### Lithium Battery Resistance Meter
- **TOOL KITS → BATT RESISTANCE** → Press ENTER
- Shows each cell's internal resistance (mΩ)
- Shows total resistance, highest, lowest
- Higher resistance = aging cell (>80 mΩ for 18650 = degraded)

### DC/DC Converter
- **TOOL KITS → DC/DC CONVERTER** → Press ENTER
- Set output voltage (5–26V) and current (1–6A)
- Hold ENTER 3 seconds to start
- Maximum 60W output
- Use as bench power supply

## Error Messages

| Error | Meaning | Action |
|-------|---------|--------|
| REVERSE POLARITY | Battery connected backwards | Disconnect immediately, check polarity |
| CONNECTION BREAK | Battery disconnected mid-charge | Check connections, restart |
| CELL MISMATCH | Detected cell count ≠ set cell count | Verify cell count setting matches battery |
| VOLT ERROR | Battery voltage abnormal | Check battery health, verify chemistry |
| CELL VOLT ERROR | One cell voltage too high | Balance charge, check for damaged cell |
| WRONG BATT TYPE | Chemistry mismatch | Verify correct battery type selected |
| SUPPLY VOLT TOO HIGH | Input > 18V | Use 12V power supply |
| SUPPLY VOLT TOO LOW | Input < 11V | Check power supply voltage |
| INTERNAL TEMP TOO HIGH | Charger overheating | Let charger cool, reduce current |
| BATT TEMPERATURE TOO HIGH | Battery too hot | Stop immediately, check battery |
| OVER CHARGE CAPACITY LIMIT | Exceeded capacity cutoff | Normal safety stop — battery may be larger than setting |
| OVER TIME LIMIT | Exceeded safety timer | Normal safety stop — increase timer or check battery |

## Connector Reference

| Port | Type | Purpose |
|------|------|---------|
| DC Input | XT60 / barrel | 11–18V power input |
| Battery Output | Banana plugs (4mm) | Main charge/discharge leads |
| Balance Port | JST-XH (2S–6S) | Cell balancing (lithium only) |
| Temp Probe | 2-pin | External temperature sensor (optional) |

## Battery Pack Building — Key Formulas

### Series (S) vs Parallel (P) Configuration
- **Series (S)**: Voltages add, capacity stays same. 3S = 3 cells in series.
- **Parallel (P)**: Capacities add, voltage stays same. 2P = 2 cells in parallel.
- **Combined**: "3S2P" = 3 series × 2 parallel = 6 cells total, 3× voltage, 2× capacity.

### Watt-hour Calculation
```
Wh = Nominal voltage (V) × Capacity (Ah)
```

### Required Charging Voltage
```
Max charge voltage = Cells in series × Max charge voltage per cell
```

### C-rate to Amps
```
Charge current (A) = C-rate × Capacity (Ah)
Example: 1C for 2000mAh = 1 × 2.0 = 2.0A
```

### Important for Pack Building
- **All cells in a parallel group MUST be the same capacity and chemistry**
- **All cells in a parallel group should be at the same voltage before connecting** (±0.05V)
- **Match internal resistance** within parallel groups (±20%)
- **Always include a BMS** (Battery Management System) in finished packs
- The B6 V2 can balance charge up to 6S — for larger packs, use a BMS
- This charger maxes at 60W — plan charge times accordingly

## BMS Undervoltage Lockout Recovery (Verified Technique)

When a lithium battery pack with an onboard BMS reads ~0V on its terminals, the BMS has likely entered undervoltage lockout — the charge/discharge MOSFETs are open, disconnecting the cells from the output. The cells may still hold charge but the BMS won't wake up.

**This technique was successfully used to recover a Puredick A1322 MacBook battery (2026-02-22).**

### Symptoms
- Battery reads 0V or near-0V (e.g., 0.05V) across main terminals
- SYS_DETECT or other wake signals have no effect
- Cells are disconnected from output by the BMS protection FETs

### Body-Diode Rescue Technique
Even with FETs open, MOSFET body diodes allow small current in the charge direction:

1. Connect charger **+** to battery positive, **-** to battery negative
2. Set B6 V2 to **NiMH mode, 1 cell, 0.1–0.2A** (bypasses lithium voltage checks)
3. Start charging — a trickle current flows through body diodes
4. **Monitor every 5 minutes** — stop and re-measure voltage
5. When voltage **jumps suddenly to 8-11V+**, the BMS has woken up and closed the FETs
6. **STOP NiMH mode immediately**
7. Switch to proper lithium charging mode (LiPo/Li-Ion, correct cell count and voltage)

### Safety
- **Never leave unattended** — NiMH mode bypasses lithium safety checks
- **Monitor battery temperature** — stop if warm
- If voltage doesn't climb after 30 minutes, the pack may be dead (blown fuse or completely discharged cells)
- Alternative: try **Pb (Lead-acid) mode** at lowest voltage/current if NiMH mode refuses to start

## Capacity Testing Procedure

To verify actual battery capacity (useful for suspicious ratings):

1. **Full charge** the battery (Balance Charge mode for lithium)
2. Switch to **DISCHARGE** mode
3. Set discharge current to 0.5C (or lower for accuracy)
4. Set cutoff voltage per chemistry:
   - Li-Ion: 2.9–3.0V/cell
   - LiPo: 3.0–3.2V/cell
   - NiMH: 1.0V/cell
5. Start discharge — charger records total mAh discharged
6. The displayed **discharged capacity (mAh)** is the true usable capacity

## Power Supply Requirements

The B6 V2 requires an external DC power source (11–18V). Common options:

| Source | Typical Voltage | Notes |
|--------|----------------|-------|
| 12V car battery | 12.6V | Good for field use |
| 12V bench PSU | 12.0V | Most common desktop setup |
| 3S LiPo (charged) | 11.1–12.6V | Portable but drains itself |
| Laptop brick (if 12V) | 12V–19V | Check voltage — must be ≤18V |
| Server PSU (converted) | 12V | High current, good for workshop |

**The charger does NOT include a power supply.** You need to provide 11–18V DC input.

## File Inventory

```
hiyiton-b6-v2-charger/
├── CLAUDE.md                                    ← This file (AI agent briefing)
├── CHEATSHEET.md                                ← Human quick reference
├── BATTERY_INVENTORY.md                         ← Mohammed's batteries + settings
└── Hiyiton_V6_Professional_Balance_Charger.pdf  ← Original instruction manual
```
