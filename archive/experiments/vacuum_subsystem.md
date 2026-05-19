# ROVAC v2 — Vacuum Subsystem Plan

The vacuum motor configuration for ROVAC v2. We've **received** 8× Delta BCB1012GJ-01 brushless DC blowers (2026-05-05); this document captures the layout decision and upgrade path.

> 📄 **Canonical motor reference:** [`hardware/delta-bcb1012gj-01-blower-motor/README.md`](../../hardware/delta-bcb1012gj-01-blower-motor/README.md) — full specs, verified pinout, bench-verification recipe, application guide, and source PDFs. The summary table below is just for quick reference inside this layout doc.

## Motor specifications (summary)

| Spec | Value | Source |
|---|---|---|
| Manufacturer | Delta Electronics | ✅ Label |
| Model | BCB1012GJ-01 | ✅ Label |
| Voltage | 14.4 V DC | ✅ Label |
| Current | 3.45 A | ✅ Label |
| Power | 49.7 W | 📐 Computed |
| Estimated free-air flow | ~42 CFM (1.2 m³/min, ~20 L/s) | 🔭 Scaled from BCB1012UH @ 12 V (35.3 CFM) |
| Estimated peak pressure | ~1,450–2,000 Pa | 🔭 Scaled lower bound; Neato D7 system rating implies upper bound |
| Estimated RPM (free-air) | ~15,500–17,000 | ⚠️ Inferred from class |
| Motor type | Brushless DC, integrated ESC, single-inlet centrifugal | ✅ Label + photo |
| Wiring | 4-pin: Red=V+, Black=GND, **Yellow=PWM in, Blue=FG out** | 🔬 Field-verified by Robot Reviews D7 thread |
| Bounding box | 97 × 87 × 25 mm | 📜 elecok / pchub catalogue listing |
| Housing material | PBT + 30% glass fiber, flame retardant | ✅ Visible molding mark |

## Layout decision: B1 dual-pair pancake (initial)

**Status:** Chosen for v2 initial build.

```
   FRONT INTAKE                         FRONT EXHAUST →
        ↓                                   →
   ╔═══════════════╤═══════════════╗
   ║  ╭───╮ S1A    │   S2A ╭───╮   ║
   ║  │ ◯ │ green  →  orange │ ◯ │ ║
   ║  ╰───╯  ───── │ ─────  ╰───╯  ║
   ║    inter-stage duct (compound) ║
   ╠═══════════════╪═══════════════╣
   ║  ╭───╮ S2B    │   S1B ╭───╮   ║
   ║  │ ◯ │ orange ←  green  │ ◯ │ ║
   ║  ╰───╯  ───── │ ─────  ╰───╯  ║
   ╚═══════════════╧═══════════════╝
   ←                                   ↑
   REAR EXHAUST                       REAR INTAKE
```

**Performance target:** ~3,500 Pa per intake (compound 2-stage), 200 W total power, 160×160×65 mm footprint.

**Why B1:**
- Compact — fits standard Neato chassis footprint
- Low CoG (65 mm tall)
- Two cleaning paths (front + rear) — wider effective coverage
- Uses 4 of 8 motors; 4 spares for failure / future upgrade
- Symmetrical front/rear weight distribution

**Why not C2 (dual-quad, 8 motors) yet:**
- Requires 130 mm height (extends chassis)
- 400 W power = 2× battery capacity
- More complex thermal management (top quad heats up)
- B1 is the safer first build; upgrade once B1 is proven

## Phased build plan

Per [decisions.md D9](decisions.md#d9), we're doing this in phases to de-risk integration:

### Phase 1 — Single-motor minimum viable
- 1× Delta BCB1012GJ-01 mounted in Neato dust cup fan bay
- Drive directly from ESP32 PWM
- Validate: motor → cyclone → HEPA → exhaust path works
- Measure: actual suction at floor nozzle (manometer + tissue lift test)
- Estimated suction: ~2,000 Pa peak

### Phase 2 — Dual single-motor (one per intake)
- 1× Delta in front intake position
- 1× Delta in rear intake position
- Validate: independent control of two intake zones
- Estimated suction: ~2,000 Pa per intake (parallel, not compound)

### Phase 3 — Layout B1 compound dual-pair
- 4× Delta in 2×2 pancake (front pair compound, rear pair compound)
- 3D-printed manifold cap connecting S1A→S2A and S1B→S2B
- Validate: compound stages add ~75% pressure (compounding losses ~25%)
- Estimated suction: ~3,500 Pa per intake

### Phase 4 — Layout C2 quad-compound (future, optional)
- 8× Delta in stacked dual-quad arrangement
- Requires extending chassis height by ~65 mm (roof rack or 3D-printed extension)
- Requires 2× battery capacity (10 Ah min)
- Estimated suction: ~6,500 Pa per intake — Roborock S8 territory

## Hardware sketches

SVG diagrams exploring layouts and 3D arrangements live at:
- `~/Downloads/vacuum_layouts/layout_A_quad_compound.svg`
- `~/Downloads/vacuum_layouts/layout_B_dual_pair.svg` ← chosen
- `~/Downloads/vacuum_layouts/layout_C_dual_quad.svg`
- `~/Downloads/vacuum_layouts/layout_A_3d_options.svg`
- `~/Downloads/vacuum_layouts/layout_B_3d_options.svg` ← chosen
- `~/Downloads/vacuum_layouts/layout_C_3d_options.svg`

OpenSCAD parametric model of Layout B1:
- `~/Downloads/vacuum_layouts/rovac_layout_b1_pancake.scad`
- Renders: `render_b1_isometric.png`, `render_b1_top.png`, `render_b1_front.png`, `render_b1_right.png`

These should be migrated into the project at some point — for now they live in Downloads as exploratory sketches.

## Motor wiring

Each Delta BCB1012GJ-01 has a 4-wire harness:

| Color (typical) | Function | Connection |
|---|---|---|
| Red | +14.4 V | Common power bus from battery |
| Black | GND | Common ground bus |
| Yellow | PWM in (5 V level, 25 kHz) | Independent ESP32 GPIO (LEDC PWM) |
| Blue | FG out (tach, open-collector) | Independent ESP32 GPIO (input, internal pull-up) |

Per stage: 2 power wires + 1 control + 1 monitor = 4 wires per motor. With 4 motors in B1 layout: 8 power wires + 8 control/monitor wires = 16 total.

Power bus: 14 AWG silicone wire, 20 A automotive blade fuse within 100 mm of battery.

## Inter-stage manifold geometry

Per the original 4-stage spec (now scoped to 2-stage for B1):

- **Bottleneck**: motor exhaust port = 25 × 14 mm (3.5 cm²)
- **Duct cross-section**: maintain ~22 cm² throughout to avoid velocity spikes
- **Bend radius**: ≥15 mm (no sharp corners)
- **Settling chamber**: ~10–15 cm³ between stages (dampens blade-passing pulsation)
- **Sealing**: silicone foam gasket between motor flange and manifold; EPDM O-rings on round ports
- **Material**: PETG (PLA deforms above 60 °C; stage 2 of compound can hit 60 °C)

## Cyclone separator + dust cup

The Neato D5 has a pre-engineered cyclone + dust cup in its dust bay. Per [decisions.md D8](decisions.md#d8) we keep this assembly. Rationale: it's already engineered to mate with a Delta-class fan motor, has the right air path geometry, and works.

If we later upgrade to Layout C2 with separate front and rear intakes, we'd need either:
- A second cyclone for the rear path (adapt a Thingiverse design like Yujiro's)
- A shared cyclone with manifold splitting (more complex, single point of failure)

## Pre-stage protection

**Critical:** Never run debris through the impeller. The Delta motors will be destroyed within hours by particles hitting the spinning blades. The Neato cyclone catches debris BEFORE it reaches the motor — this is non-negotiable.

The Neato dust cup includes:
- Cyclone separator (centrifugal particle drop into cup)
- HEPA filter chamber (catches fine dust before exhaust)

Both stages must be present. Don't skip the HEPA filter even though the cyclone catches most debris.

## Open issues to resolve

1. **Exact Delta exhaust port dimensions** — measured on arrival, may differ slightly from the 25 × 14 mm estimate
2. **Exact Neato dust bay fan mount geometry** — measured on arrival, may need printed adapter to fit the Delta motor
3. **Inter-stage manifold CAD** — drafted in OpenSCAD per main spec; finalize after measuring motor ports
4. **HEPA filter end** — Neato HEPA chamber discharge port may need adapter to mate with our exhaust tubing
5. **Performance verification** — manometer + flow measurement plan to validate single-motor and compound stages
