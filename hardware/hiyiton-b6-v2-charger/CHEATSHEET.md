# B6 V2 Charger — Quick Reference Cheatsheet

> Hiyiton V6 = SkyRC B6 V2 (iMAX B6 V2)
> **Always connect 11–18V DC power input first.**

---

## Button Layout

```
[BATT/PROG]   Select battery type / enter program menus
[DEC -]       Decrease value / scroll left
[INC +]       Increase value / scroll right
[ENTER/START] Confirm selection / HOLD 3 SEC to start charge
[STOP]        Stop any operation immediately
```

---

## Balance Charge a Lithium Battery (LiPo / Li-Ion / LiFe)

This is the mode you'll use 90% of the time for lithium batteries.

1. Connect **DC power** (11–18V)
2. Connect **battery main leads** (red=+, black=-)
3. Connect **balance lead** (if multi-cell)
4. **BATT/PROG** → select chemistry (LiPo / Li-Ion / LiFe / LiHV)
5. **INC/DEC** → select **BALANCE CHG**
6. **ENTER** → set charge current (flashing) → **INC/DEC**
7. **ENTER** → set voltage / cell count (flashing) → **INC/DEC**
8. **HOLD ENTER 3 seconds** → charging starts
9. Wait for **"FULL"** + beep

### Quick Settings by Chemistry

| Chemistry | Set Voltage/Cell | Cell Count Formula |
|-----------|-----------------|-------------------|
| LiPo | 4.20V | Pack V ÷ 3.7 |
| Li-Ion | 4.10V | Pack V ÷ 3.6 |
| LiFe | 3.60V | Pack V ÷ 3.3 |
| LiHV | 4.35V | Pack V ÷ 3.7 |

---

## Charge a Single 18650 Cell

1. Connect cell to main output (red=+, black=-)
2. **No balance lead needed** for single cell
3. BATT/PROG → **Li-Ion**
4. Mode → **CHARGE** (or BALANCE CHG — both work for 1S)
5. Current → **0.5A–1.0A** (0.5C safest)
6. Voltage → **1S 4.10V**
7. HOLD ENTER 3 sec → start

---

## Charge NiMH Battery Pack

1. Connect battery main leads (observe polarity)
2. BATT/PROG → **NiMH**
3. Mode → **CHARGE**
4. Set current → typically **0.5C–1C**
   - Example: 3500 mAh pack → 1.75A at 0.5C
5. HOLD ENTER 3 sec → start
6. Wait for **"DONE"** + beep (delta-peak detection)

---

## Storage Mode (Before Storing Lithium Batteries)

1. Connect battery + balance lead
2. BATT/PROG → select chemistry
3. INC/DEC → **STORAGE**
4. Set current → 1.0A is fine
5. Set cell count
6. HOLD ENTER 3 sec
7. Charger brings each cell to ~3.85V (LiPo) or ~3.75V (Li-Ion)

---

## Capacity Test (Discharge)

Want to know the real mAh capacity of a battery?

1. **Fully charge** the battery first
2. BATT/PROG → select chemistry → **DISCHARGE**
3. Set discharge current (0.5A–1.0A typical)
4. Set cutoff voltage:
   - Li-Ion: 3.0V/cell
   - LiPo: 3.0V/cell
   - NiMH: 1.0V/cell
5. HOLD ENTER 3 sec → discharge starts
6. When **"DONE"** appears, the **mAh shown = true capacity**

---

## Cycle NiMH (Restore Capacity)

Old NiMH batteries benefit from cycling:

1. BATT/PROG → NiMH → **CYCLE**
2. Select: **DCHG>CHG** (discharge first, then charge)
3. Set cycles: **3–5**
4. HOLD ENTER 3 sec
5. Charger runs up to 5 discharge/charge cycles automatically

---

## Use as Bench Power Supply (DC/DC Converter)

1. BATT/PROG → **TOOL KITS**
2. DEC/INC → **DC/DC CONVERTER**
3. ENTER → set output voltage (5–26V)
4. Set output current (1–6A)
5. HOLD ENTER 3 sec → output starts
6. Max 60W — check: V × A ≤ 60

---

## Rescue a Locked-Out Battery (reads 0V)

If a lithium pack with a BMS reads ~0V, the BMS FETs are locked open.

1. Connect charger leads to battery + and - terminals
2. Set charger to **NiMH, 1 cell, 0.1A**
3. Start charging — tiny current flows through MOSFET body diodes
4. Check voltage every 5 min — stop and remeasure
5. When voltage **jumps to 8V+** → BMS has woken up
6. **STOP NiMH immediately** → switch to proper LiPo/Li-Ion mode
7. **Never leave unattended** — this bypasses lithium safety checks

---

## Check Cell Voltages (Lithium)

1. Connect balance lead
2. BATT/PROG → **TOOL KITS** → **BATT METER**
3. ENTER → see each cell's voltage
4. INC → see total, highest, lowest

---

## Check Cell Resistance (Lithium)

1. Connect balance lead + main leads
2. BATT/PROG → **TOOL KITS** → **BATT RESISTANCE**
3. ENTER → see each cell's internal resistance (mΩ)
4. Good 18650: < 80 mΩ | Degraded: > 100 mΩ

---

## Save / Load a Memory Profile

### Save
1. BATT/PROG → **TOOL KITS** → **BATT MEMORY**
2. Select slot (1–10) → ENTER
3. Set all parameters → ENTER to save

### Load
1. Same menu → select slot
2. **HOLD ENTER 3 sec** → loads and starts

---

## Common Errors

| Screen Shows | What It Means | What to Do |
|-------------|---------------|------------|
| REVERSE POLARITY | Wires are backwards | Disconnect NOW, flip leads |
| CONNECTION BREAK | Battery disconnected | Check connections |
| CELL MISMATCH | Wrong cell count set | Verify S count matches battery |
| SUPPLY VOLT TOO LOW | Input < 11V | Check your power supply |
| BATT TEMP TOO HIGH | Battery overheating | STOP, remove battery, let cool |

---

## Safety Reminders

- **Never leave charging batteries unattended** (especially lithium)
- **Never charge a puffed/swollen lithium battery** — dispose safely
- **Motor power switch** on robot must be OFF when charging onboard batteries
- **Charge on a fireproof surface** (LiPo bag, ceramic tile, metal tray)
- **If a battery gets hot to the touch during charge → STOP immediately**
- **Storage mode before shelving** lithium batteries for >1 week
