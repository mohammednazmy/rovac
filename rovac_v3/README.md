# ROVAC v3 — Custom 3D-Printed Chassis (Experimental Track)

**Status:** Iter-3 + Audit-1 (manual) + Audit-2 (hardcore tooling) — all clean (2026-05-04)
**Started:** 2026-05-02

## Why a v3?

v3 explores a fully custom, ground-up 3D-printed chassis where every mounting
feature is purpose-designed for our exact stack (Pi 5, NULLLAB Maker-ESP32 motor
controller, ESP32 sensor hub, BNO055, RPLIDAR C1, Greartisan ZGB37RG motors).
It is the next-generation platform exploration — a learning effort to design a
chassis that fits the ROVAC stack precisely, rather than adapting to an
off-the-shelf chassis.

## Folder layout

```
rovac_v3/
├── README.md                  ← this file (project framing + index)
├── 3D_model/
│   ├── design_brief.md        ← hardware spec, constraints, decisions log, audit log
│   ├── parameters.scad        ← single source of truth for every dimension
│   ├── chassis_iter0.scad     ← initial geometric skeleton (snapshot)
│   ├── chassis_iter1.scad     ← components + mounts (snapshot)
│   ├── chassis_iter2.scad     ← cable mgmt, service access, power, ribs (snapshot)
│   ├── chassis_iter3.scad     ← current — gap closure + audit fixes
│   ├── wheel.scad             ← parametric 70 mm wheel (3 tire variants)
│   ├── bumper.scad            ← bumper (split into 4 quadrants for printing; full ring viz)
│   ├── tools/
│   │   ├── audit.py           ← hardcore audit suite (sca2d + admesh + trimesh + custom)
│   │   └── export_parts.scad  ← STL export helper for tools/audit.py
│   ├── audit_artifacts/       ← per-part STLs + audit_report.md/json
│   └── renders/               ← preview PNGs (iter*_*, wheel_iter3_*, bumper_*)
└── specs/                     ← reserved for spec sheets / reference images
```

## Current state

- [x] Folder scaffolded
- [x] All decisions locked (see `3D_model/design_brief.md` § "Decisions")
- [x] Iter-0 — geometric skeleton (chassis envelope, motor strip, LIDAR recess)
- [x] Iter-1 — components + mounts (Pi 5, both ESP32s, BNO055, battery, sensors)
- [x] Iter-2 — cable mgmt, service access, power, bumper microswitch pads, ribs
- [x] Iter-3 — vent slots, counterbores, finger grips, LED + cable pass-through, full-perimeter bumper, wheel set-screw boss, serpentine flexures
- [x] **Audit-1 (manual review)** 2026-05-03 — 17 issues identified and resolved
- [x] **Audit-2 (hardcore tooling)** 2026-05-04 — automated pipeline using sca2d + admesh + trimesh + custom analyzers; 9 additional issues found and fixed
- [x] **Audit-3 (printability analytics)** 2026-05-04 — pipeline extended with overhang angle binning, bridge length detection, support volume estimation, 3MF multi-material export
- [x] **Audit-4 (FEM + orientation + G-code + mass)** 2026-05-04 — pipeline extended with: gmsh + CalculiX FEM stress simulation, optimal print orientation finder, PrusaSlicer G-code parser (filament + time per part), mass-properties analysis. Pipeline now 13 stages.
- [x] **Audit infrastructure** — re-runnable `tools/audit.py` with structured `audit_report.md`/`audit_report.json` output
- [ ] Iter-4 — print-prep (split into individual STLs + Bambu Studio project file)
- [ ] First print + fitment validation
- [ ] Wheel traction test
- [ ] Bumper spring-rate tuning
- [ ] Full assembly

## Locked design decisions

| ID | Decision | Value |
|---|---|---|
| D1 | Form/function | **Pure nav/sensor platform** — general-purpose autonomous mobile robot |
| D2 | Form factor | **Round** |
| D3 | Outer diameter | **250 mm** (single-piece print on Bambu P2S 256 mm bed) |
| D4 | Height interpretation | **95 mm chassis** + recessed LIDAR (total robot ≈ 113 mm) |
| D5 | Drive motors | **Greartisan ZGB37RG17.4i** (12 V, 1:17.4, 300 RPM) + AS5600 encoder |
| D6 | Wheel diameter | **70 mm** with 22 mm width |
| D7 | Caster | **Single rear free-spinning wheel** (Ø40 mm) — bracket-mounted under floor |
| ext | IMU | **Adafruit BNO055 (#2472)** — reused from v1 inventory |
| ext | ESP32 motor ctrl | **NULLLAB Maker-ESP32** integrated board (80 × 57 × 12 mm) — 4× TB67H450FNG drivers on-board |
| ext | Bambu P2S build vol | **256 × 256 × 256 mm** (confirmed) |

## Reference: ROVAC v1 dimensions (for comparison)

From `docs/robot_dimensions.md` and the active URDF:

| Dimension | v1 value | v3 target |
|---|---|---|
| Chassis footprint | 220 × 245 mm rectangular | Ø 250 mm round |
| Chassis height (excl. LIDAR) | 100 mm | 95 mm |
| LIDAR scan plane | 152.5 mm above ground | ~108 mm above ground |
| Total robot height | ~150 mm (with LIDAR mast) | ~113 mm (recessed LIDAR) |
| Drive | Yahboom G1 tank tracks | Differential drive, custom wheels |

## What was audited and fixed (2026-05-03)

A comprehensive review of all SCAD files surfaced 17 issues. Highlights:

**Critical (would fail at print or assembly):**
1. Top plate counterbore depth (2.5 mm) > ceiling thickness (2.4 mm) — heads would fall through
2. Top plate alignment pin azimuth (-22.5°) collided with fastener boss at 337.5°
3. Bumper inner radius (126.5 mm) too small — would compress switches at rest with no travel
4. Cliff sensors at X=±115 protruded past chassis edge (Ø250 → outer radius 125)
5. Caster mount disk had no wheel cutout — wheel passed through solid material
6. Bumper snap-fit hooks had no chassis ledges to engage
7. Wheel shaft socket positioned wrong — extended past wheel face
8. Stiffening ribs at 0°/180° intersected the vent-slot grid (blocked airflow)
9. Status LED slot and cable pass-through overlapped at X=-90
10. Centerline cable channel ran through the IMU post

**Significant (functional but suboptimal):**
- Battery strap clip geometry mathematically wrong
- TPU tire had no mechanical interlock with hub (slip-fit only)
- Dead `perimeter_ring` module never called
- Duplicate section numbers in parameters.scad
- `chassis_radius` used before defined (worked due to OpenSCAD globals, but fragile)
- Unused `motor_mount_pcd` parameter

All fixes applied and verified via re-render. See `3D_model/design_brief.md`
§ "Audit log" for the full table of fixes with line-level diffs.

## Iteration history snapshots

Each `chassis_iterN.scad` is preserved as a historical snapshot:
- `chassis_iter0.scad` — geometric skeleton (no components, no mounts)
- `chassis_iter1.scad` — adds component placeholders + mounting standoffs
- `chassis_iter2.scad` — adds cable mgmt, service access, power, ribs, microswitch pads
- `chassis_iter3.scad` — current revision (use for next iteration)
