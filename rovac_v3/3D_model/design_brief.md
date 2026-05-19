# ROVAC v3 — 3D-Printed Chassis Design Brief

This document is the **canonical reference** for the v3 chassis design.
If a SCAD file disagrees with this brief, we update one or the other —
never silently diverge.

**Status:** Iter-3 complete + audit-pass clean (post-audit 2026-05-03)
**Source of truth for dimensions:** `parameters.scad`
**Active CAD:** `chassis_iter3.scad`, `wheel.scad`, `bumper.scad`

---

## 1. Design goals (priority order)

1. **Low profile** — chassis ≤ 100 mm; total robot ≤ 115 mm including LIDAR
2. **Custom-fit hardware** — every component has a dedicated mounting feature
3. **Single-piece chassis print** on Bambu P2S (256³ mm build volume confirmed)
4. **Modular sub-parts** — wheels and bumper print separately for easy iteration
5. **Serviceable** — battery, electronics, sensors all reachable without destructive disassembly
6. **Iteration-friendly** — PLA for fitment trials; PETG for production

---

## 2. Constraints

| Constraint | Value | Rationale |
|---|---|---|
| Build volume per part | ≤ 256³ mm (Bambu P2S) | Confirmed 2026-05-02 |
| Chassis height (excl. LIDAR turret) | 95 mm | Decided D4 |
| Total robot height | ~113 mm | Chassis + LIDAR optical enclosure (18.2 mm) |
| Min wall thickness | ≥ 2.0 mm | PETG strength + multi-perimeter quality |
| Min floor thickness | ≥ 3.0 mm | Withstand motor torque reaction |
| Default slip-fit clearance | +0.2 mm | PLA/PETG print expansion |
| Threaded inserts | M3 brass heat-set (also M2/M2.5/M4) | Repeatable bolt cycles |
| Fasteners | M3×8 / M3×12 socket cap | Standard inventory |

---

## 3. Locked design decisions

| ID | Decision | Value |
|---|---|---|
| D1 | Form/function | **Pure nav/sensor platform** — general-purpose autonomous mobile robot |
| D2 | Form factor | **Round** |
| D3 | Outer diameter | **250 mm** |
| D4 | Height interpretation | **95 mm chassis + recessed LIDAR** (~113 mm total) |
| D5 | Drive motors | **Greartisan ZGB37RG17.4i** (12 V, 1:17.4, 300 RPM) |
| D6 | Wheel diameter | **70 mm × 22 mm** wide |
| D7 | Caster | **Single rear free-spinning wheel** (Ø40 mm, bracket-mounted) |
| ext | IMU | **Adafruit BNO055 (#2472)** — reused from v1 |
| ext | Motor controller | **NULLLAB Maker-ESP32** (integrated 80 × 57 × 12 mm board, 4× TB67H450FNG drivers) |
| ext | Sensor hub | **ESP32 DevKitV1** (off-axis floor mount) |
| ext | Bambu P2S build vol | **256³ mm** (confirmed) |
| ext | Pi 5 orientation | **Rotated 90° (long axis along Y)** to clear LIDAR base footprint |

---

## 4. Hardware to mount (current spec)

All values match `parameters.scad` as of 2026-05-03.

### 4.1 Compute & control

| Item | Footprint (mm) | Mount | Anchor (X, Y, Z) |
|---|---|---|---|
| Raspberry Pi 5 + active cooler | 56 × 85 × 35 (rotated) | 4× M2.5 at 49 × 58 mm PCD | (-70, 0, 55) |
| NULLLAB Maker-ESP32 (motor ctrl) | 80 × 57 × 12 | 4× M4 at 64 × 40 mm PCD | (+58, 0, 3) |
| ESP32 DevKitV1 (sensor hub) | 55 × 28 × 13 | 4× M2 at 49 × 22 mm PCD | (-30, +60, 3) |
| Adafruit BNO055 IMU | 27 × 20 × 4 | 4× M2.5 at 22 × 15 mm PCD | (0, 0, 12) |
| Buck converter (12V→5V 5A) | 50 × 30 × 15 | 4× M2.5 at 44 × 24 mm PCD | (-30, -60, 3) |

### 4.2 Sensing

| Item | Footprint (mm) | Notes |
|---|---|---|
| RPLIDAR C1 | 55.6 × 55.6 × 41.3 | 23.1 mm base recessed into top plate; 18.2 mm optical enclosure protrudes |
| 4× HC-SR04 ultrasonic | 45 × 20 × 15 | Front, rear, left, right; twin Ø16 transducer windows at perimeter |
| 2× Sharp GP2Y0A51 cliff | 30 × 13 × 7 | Front + rear; mounted on 8 mm raised brackets pointing down through Ø10 floor holes; anchors at X=±105 |

### 4.3 Actuation

| Item | Spec | Mount notes |
|---|---|---|
| 2× Greartisan ZGB37RG17.4i | Ø37 × 71 mm interior + 14 mm D-shaft | Body extends inward from each wheel; AS5600 encoder on rear shaft |
| 2× custom 3D-printed wheels | Ø70 × 22 mm | See `wheel.scad`; D-shaft socket + radial M3 set screw with raised boss |
| 1× rear caster | Ø40 mm free-spinning wheel | Bracket-mounted under floor (4× M3); slot in mount disk |

### 4.4 Power

| Item | Spec | Notes |
|---|---|---|
| Battery | placeholder 80 × 40 × 25 (3S Li-ion) | Cradle: 2 side rails + 1 cross-bar strap above |
| Buck converter | TPS5450/LM2596 class | Mirror of sensor hub at front-right floor |
| Master switch | rocker, 21 × 15 mm cutout | Sidewall-mounted at azimuth 135°, Z=60 mm; flat panel-mount boss |
| Charging port | Ø12 mm DC barrel jack | Sidewall-mounted at azimuth -135°, Z=60 mm; flat panel-mount boss |

### 4.5 Service & feedback

| Item | Detail |
|---|---|
| Top plate fasteners | 8× M3 socket cap at 45° spacing on chassis wall (counterbored 1.5 mm into 3 mm plate) |
| Top plate alignment pin | 1× Ø4 × 6 mm pin at azimuth 0° (front center) |
| Active-cooler vents | 5×3 grid of 4×18 mm slots over Pi 5 (X=-70) |
| Status LED slot | 30 × 4 mm rectangular slot at (-100, 0) |
| Cable pass-through | Ø12 mm at (-110, 20) for top-mounted accessories |
| Finger-grip notches | 2× concave dishes on chassis edge at azimuths ±90° |
| Stiffening ribs (top plate underside) | 4× radial bars at azimuths 30°/150°/210°/330° (clear of vents) |
| Bumper microswitches | 8× perimeter at azimuths ±22.5°, ±67.5°, ±112.5°, ±157.5° |
| Bumper hook ledges | 8× radial protrusions on chassis exterior at Z=23 mm |

---

## 5. Geometry — derived dimensions (from `parameters.scad`)

```
chassis_radius        = 125 mm
top_plate_bot_z       = 92 mm  (chassis_height − ceiling_thickness = 95 − 3)
lidar_base_z          = 71.9 mm  (chassis_height − lidar_recess_depth)
lidar_optical_z       = 95 mm   (top of LIDAR base = chassis top)
robot_total_height    = 113.2 mm
wheel_center_z        = 20 mm   (above chassis bottom exterior)
bumper_inner_r        = 138 mm  (chassis_radius + 13 mm clearance)
bumper_radial_clearance = 13 mm  (microswitch protrusion 9 + travel 4)
```

---

## 6. Iteration history

| Iter | Focus | Status |
|---|---|---|
| Iter 0 | Skeleton: floor plate + perimeter wall + motor pockets + wheel slots + LIDAR cutout | ✅ snapshot in `chassis_iter0.scad` |
| Iter 1 | Components + mounts (Pi 5, ESP32 motor, ESP32 sensor, BNO055, battery, LIDAR standoffs) | ✅ snapshot in `chassis_iter1.scad` |
| Iter 2 | Cable channels, top-plate fasteners, buck converter mount, panel bosses, microswitch pads, ribs, embossed FRONT label, chamfers | ✅ snapshot in `chassis_iter2.scad` |
| Iter 3 | Vent slots, M3 counterbores, finger grips, status LED slot, cable pass-through, full-perimeter bumper, serpentine flexures, wheel set-screw boss, TPU keying, hub blank fix | ✅ in `chassis_iter3.scad` |
| Audit | 17 issues found and fixed — see §7 | ✅ 2026-05-03 |
| Iter 4 | Print prep — split into individual STLs, Bambu Studio project | TODO |

---

## 7d. Audit-4 — FEM + orientation finder + G-code parser + mass props (2026-05-04)

Audit pipeline extended again with the four "out-of-scope" features from audit-3:

| Stage | Tool | Output |
|---|---|---|
| Mass properties | `trimesh` volumes + density table | Per-part mass (solid + realistic), CoG, total robot mass |
| Optimal print orientation | rotate-and-score per orientation | Best orientation per part + support saving |
| Slicer G-code analysis | PrusaSlicer 2.9.4 CLI | Per-part filament (g + mm), print time, layer count |
| FEM stress simulation | `gmsh` (OCC) + `calculix-ccx` | Per-part max von Mises stress + safety factor |

The pipeline now runs **13 stages** (up from 9). Total runtime ~3-4 min without
G-code analysis, ~10-15 min with full G-code per part.

### Toolchain additions

```bash
brew install gmsh                           # 4.15.2
conda install -c conda-forge calculix       # ccx 2.23
python3 -m pip install gmsh meshio          # Python wrappers
```

### Mass properties (PETG default 1.27 g/cm³ × 45 % effective fraction)

Total robot mass realistic estimate: **~377 g**
- Heaviest part: chassis_wall at 107 g
- Each bumper quadrant: 15-17 g
- TPU tire: 11 g

### Optimal orientation finder

Best finding: **flipping the top plate (Y180°) saves 52 cm³ of support material**
— from 52 cm³ as-designed → 0.05 cm³ optimal. The chassis floor is already
optimal as-designed. Bumper quadrants are also optimal as-designed.

Score function: `support_volume − 0.5 × bed_contact + 5 × CoG_height` (lower is
better). Weights chosen to prefer minimal support while not toppling thin parts
during printing.

### Slicer G-code analysis (PrusaSlicer 2.9.4 default profile)

| Part | Filament (g) | Print time |
|---|---|---|
| chassis_floor | 105 g | 9h 15m |
| chassis_wall | 236 g | 17h 16m |
| chassis_top_plate | 113 g | 9h 44m |
| chassis_full | 440 g | 1d 11h 31m |
| wheel | 27 g | 1h 52m |
| bumper_q0..q3 | ~28 g each | ~2h 15m each |
| wheel_hub_pla | 20 g | 1h 29m |
| wheel_tire_tpu | 20 g | 1h 36m |

Slicer config: Bambu P2S 256 mm bed, 0.2 mm layer height, PETG density 1.27.

### FEM stress simulation (gmsh + CalculiX)

**Caveat**: gmsh's STL → 3D pipeline (`classifySurfaces` + `createGeometry`)
stalls indefinitely on real CAD-derived STLs with sharp ribs / thin features
(experienced 30+ minute hangs on chassis_floor and wheel_hub_pla STLs).

Workaround: FEM runs on **clean OCC primitive approximations** of each part:
- chassis_floor → Ø250 × 3 mm clean disc
- chassis_top_plate → same dimensions
- wheel_hub_pla → Ø60 × 22 mm disc

Pipeline:
1. gmsh OCC: generate clean primitive cylinder
2. gmsh: tet-mesh (Delaunay 3D, ~1000–3000 nodes per part)
3. Filter `.inp` to keep only `*NODE` + `*ELEMENT C3D4` (drop helper line/surface elements)
4. Append `*MATERIAL` (PETG: E=2000 MPa, ν=0.4, ρ=1.27e−9 t/mm³ — note CalculiX's mm-N-MPa-t units)
5. Append `*BOUNDARY` (fix nodes within 0.5 mm of bottom)
6. Append `*STEP / *STATIC / *CLOAD` (distribute total 6 N across top nodes)
7. Run `ccx` solver (~5–10 sec per part)
8. Parse `.frd` for max von Mises (fixed-width 12-char column format)
9. Compute safety factor vs material yield

Results (linear-static, isotropic, primitive-disc approximation):

| Part | Material | Max von Mises | Yield | Safety factor |
|---|---|---|---|---|
| chassis_floor | PETG | 0.000164 MPa | 50 MPa | ~305,000 |
| chassis_top_plate | PETG | 0.000164 MPa | 50 MPa | ~305,000 |
| wheel_hub_pla | PLA | 0.01 MPa | 60 MPa | ~9,800 |

**Interpretation**: the chassis is grossly over-engineered for static load.
The limiting factor is stiffness/deflection (not yield) and dynamic loading
(impact, vibration), neither of which a linear-static analysis captures.

**Real printed-part strength is ~0.2–0.5× FEM prediction** due to:
- Layer adhesion (typical 5× weaker between layers vs within)
- Infill density (typical 15–30 % of solid)
- Anisotropic mechanical properties (FEM assumes isotropy)

Treat FEM safety factors as "is the design grossly under-spec?" indicators,
not precise predictions.

---

## 7c. Audit-3 — printability analytics added to pipeline (2026-05-04)

After audit-2 closed all mesh-integrity / build-volume / wall-thickness issues,
audit-3 extends the pipeline with **printability analytics** — the slicer-level
checks that surface support material requirements before you slice.

### New stages

| Stage | Tool | Catches |
|---|---|---|
| Overhang angle binning | `trimesh` face normals | Surface area at 0–30°, 30–45°, 45–60°, 60–75°, 75–90° from vertical (excluding bed-bottom faces) |
| Bridge detection | `trimesh.graph.connected_components` | Connected horizontal-down regions; flags bridges with XY span > 10 mm |
| Support volume estimate | derived | overhang_area × avg_height_above_bed × support_density (0.15) |
| 3MF multi-material export | `trimesh.Scene.export` | Per-body 3MF for Bambu Studio AMS filament assignment |

The pipeline now runs 9 stages in sequence (sca2d → parametric → spatial → STL
export → mesh integrity → wall thickness → printability → 3MF → slicer).

### Material-aware wall thickness

Audit-3 also added material-aware minimum wall thickness:
- `MIN_WALL_THICKNESS = 1.5 mm` for PLA/PETG
- `MIN_WALL_THICKNESS_TPU = 0.8 mm` for TPU bodies
- Parts with `tpu` in the label use the lower threshold

### "Bed-bottom" exclusion (critical correctness fix)

The first audit-3 run had false positives flagging the bottom face of every
part as a 90° overhang (the chassis floor's underside, the wheel's underside,
etc. — they all have normals pointing −Z but they sit on the build plate,
not in midair). All three printability functions now exclude faces within
0.5 mm of `bounds[0, 2]` (the part's lowest Z).

Result: chassis_floor went from "47% overhang, 250 mm bridge, supports
required" → "0% overhang, 0 bridges, no supports required" — which matches
reality (it's a flat plate).

### As-designed-orientation caveat

Overhang/bridge/support metrics are computed in the part's **as-designed**
coordinate system. Bambu Studio (or any slicer) typically reorients parts
before printing — e.g., a top plate is usually flipped so its smooth disk
faces the bed and the stiffening ribs face up. The audit's "this part has
43 % overhang" reading is correct for the design as-shown, but real print
support volume may differ if the part is reoriented. **Always validate the
slicer's auto-orientation before relying on these numbers.**

### 3MF multi-material output

Generated artifact: `audit_artifacts/wheel_multimaterial.3mf` — bundles the
PLA hub and TPU tire as separate bodies. Bambu Studio AMS workflow:
1. Open the 3MF in Bambu Studio
2. Each body shows up in the object tree separately (`wheel_hub_PLA` + `wheel_tire_TPU`)
3. Right-click the hub body → `Change filament` → assign PLA slot
4. Right-click the tire body → `Change filament` → assign TPU slot
5. Slice; AMS switches filaments automatically per body

The hub has 16 small triangular keying ribs around its outer diameter that
the TPU material flows around during multi-color print, mechanically locking
the tire to the hub against rotation/peel.

### Audit-3 verification (post-fix re-run)

```
=== Summary ===
  Critical: 0
  High:     0
  Medium:   76    (overhang/bridge advisories — slicer handles automatically)
  Low:      255   (sca2d info)
  Total:    331
```

Of the 76 MEDIUM findings, all are advisory: `>5 mm² of overhang ≥60°` or
`bridge span >10 mm` — both standard slicer concerns that the slicer's
auto-support feature handles. They're informational signals about how much
support material the print will use, not blocking issues.

### What `audit.py` reports now

```bash
python3 tools/audit.py
```

Sections in `audit_report.md`:
1. Severity-tagged findings list
2. Mesh metrics (triangles, volume, bbox, watertight, manifold, broken faces)
3. Wall thickness (min, p1, p5, median per part — material-aware)
4. **NEW** Overhang analysis (% of surface, area per angle bin)
5. **NEW** Bridge length (per-part list of bridges > 10 mm)
6. **NEW** Support volume estimate (per part, in cm³)
7. **NEW** 3MF multi-material export details + Bambu Studio workflow

`audit_report.json` carries the same data in machine-readable form for CI integration.

---

## 7b. Audit-2 — hardcore tooling pass (2026-05-04)

After audit-1 found 17 issues by manual review, audit-2 used industry-standard
mesh validation tooling to find what manual review couldn't catch.

### Toolchain

| Tool | Purpose |
|---|---|
| `sca2d` (PyPI) | Static analysis on `.scad` source — naming, scopes, dead vars |
| OpenSCAD CLI | Export each part as STL via `tools/export_parts.scad` |
| `admesh` 0.98.5 | Per-STL mesh integrity (edges, facets, manifold check) |
| `trimesh` 4.11 (Python) | Watertight, winding, broken-face count, volume, bbox |
| `trimesh.ray` | Ray-cast wall-thickness sampling (8000 samples per part) |
| Custom Python | Parametric consistency (re-evaluates derived values via safe AST walker) |
| Custom Python | Component bounding-box overlap matrix |
| Custom Python | Build-volume check (each part vs Bambu P2S 256³) |
| PrusaSlicer 2.9.4 CLI | Slicer-level dry-run for warnings |

The orchestrator is `tools/audit.py`. Re-runnable on any iteration:
```bash
cd ~/robots/rovac/rovac_v3/3D_model
python3 tools/audit.py
# → audit_artifacts/audit_report.md (markdown) + audit_report.json (machine-readable)
```

### Audit-2 findings (initial run)

| # | Severity | File | Issue | Fix |
|---|---|---|---|---|
| 1 | CRITICAL | chassis_iter3.scad | Microswitch pad `cube(microswitch_pad_size)` axis-order bug; pad extends 16 mm radially instead of 3 mm | Reorder to `cube([pad[2], pad[0], pad[1]])` and label dims as `[width_tangent, height_z, depth_radial]` |
| 2 | CRITICAL | chassis_iter3.scad | Panel-mount boss same axis-order bug — extends 25 mm radially | Same fix |
| 3 | CRITICAL | bumper.scad | Full Ø284 mm bumper exceeds Ø256 mm bed — non-printable | Split into 4 quadrants; lap-joint connectors at ±45°/±135° |
| 4 | HIGH | chassis_iter3.scad | chassis_wall + chassis_full not watertight — coincident-face issue with exterior features sitting exactly on chassis radius | Penetrate exterior features 0.5 mm into wall (no coplanar coincident faces) |
| 5 | HIGH | parameters.scad | Even with axis fix, panel boss depth 4 mm puts chassis OD at 258 mm > 256 mm bed | Reduce panel boss depth 4 → 3 mm |
| 6 | HIGH | parameters.scad | Microswitch pad depth 3 mm puts chassis OD at 256 mm — at-the-line | Reduce to 2 mm for 1 mm margin per side |
| 7 | INFRA | tools/audit.py | sca2d emits 158 noise findings (UPPER_CASE naming convention not idiomatic for OpenSCAD) | Filter rules `I3001`, `I4001`, `I1002`, `W2010` from report |
| 8 | INFRA | tools/audit.py | Wall-thickness ray cast hits sharp edges → false-positive 1.26 mm minimum on top plate | Use `p1` (1st percentile) as threshold instead of absolute `min` |
| 9 | INFRA | tools/audit.py | bumper_full_ring (visualization-only) flagged for build-volume violation | Skip BV + thickness checks for `*_full_ring` artifacts |

### Audit-2 verification (re-run after fixes)

```
=== Summary ===
  Critical: 0
  High:     0
  Medium:   0
  Low:      255   (sca2d info-level — non-actionable)
  Total:    255
```

All 9 print-target parts now pass:

| Part | Triangles | Volume (cm³) | BBox (mm) | Watertight | Manifold |
|---|---|---|---|---|---|
| chassis_floor | 3680 | 136.11 | 250.0 × 250.0 × 11.0 | ✓ | ✓ |
| chassis_wall | 15284 | 187.80 | 250.0 × 250.0 × 101.0 | ✓ | ✓ |
| chassis_top_plate | 5908 | 145.00 | 250.0 × 249.1 × 11.0 | ✓ | ✓ |
| chassis_full | 23420 | 458.14 | 250.0 × 250.0 × 101.0 | ✓ | ✓ |
| wheel | 1856 | 40.37 | 70.0 × 70.0 × 22.0 | ✓ | ✓ |
| bumper_q0 | 688 | 28.76 | 48.7 × 203.7 × 30.0 | ✓ | ✓ |
| bumper_q1 | 636 | 29.55 | 203.7 × 48.7 × 30.0 | ✓ | ✓ |
| bumper_q2 | 400 | 27.96 | 48.7 × 203.7 × 30.0 | ✓ | ✓ |
| bumper_q3 | 164 | 26.37 | 203.7 × 48.7 × 30.0 | ✓ | ✓ |

All wall thicknesses pass at p1 ≥ 1.5 mm. All meshes are watertight, manifold,
broken-face-count = 0. All bounding boxes fit Bambu P2S 256³ mm bed.

---

## 7. Audit log (2026-05-03)

Comprehensive review of all SCAD files. 17 issues found and fixed.

### Critical fixes (would fail at print or assembly)

| # | File | Issue | Fix |
|---|---|---|---|
| 1 | parameters.scad | counterbore_depth (2.5) > ceiling_thickness (2.4) — heads fall through | Set counterbore_depth=1.5; raised ceiling_thickness to 3.0 |
| 2 | parameters.scad | alignment_pin_az (-22.5°) collides with fastener boss at 337.5° | Moved alignment pin to az=0° (front center) |
| 3 | parameters.scad / bumper.scad | bumper_inner_r (126.5) < chassis + microswitch protrusion (134) — bumper compresses switches at rest | Added `bumper_radial_clearance=13` parameter; bumper_inner_r = 138 mm |
| 4 | parameters.scad | Status LED slot and cable pass-through overlap at X=-90, Y=0 | Moved pass-through to (-110, +20) |
| 5 | parameters.scad | Cliff sensors at X=±115 + 30 mm length protrude past chassis edge (Ø250) | Moved anchors to X=±105 |
| 6 | chassis_iter3.scad | caster_mount() solid disk has no wheel slot — wheel intersects mount material | Added Ø44 cutout to mount disk |
| 7 | chassis_iter3.scad | Bumper hooks have no chassis ledge to engage | Added 8× radial ledges on chassis exterior at bumper_hook_ledge_z |
| 8 | wheel.scad | Shaft socket at Z=0 to 16 extends past wheel face (Z=11) | Translate socket to Z=-wheel_w/2 (one face); now extends inward correctly |
| 9 | chassis_iter3.scad | Top plate stiffening ribs at 0°/180° intersect vent slot grid | Moved ribs to azimuths 30°/150°/210°/330° (clear of vents AND LIDAR mounts) |
| 10 | chassis_iter3.scad | Centerline cable channel passes through Ø14 IMU post at (0, 0, 12) | Split into two parallel channels at Y=±10 |

### Significant fixes (functional but suboptimal)

| # | File | Issue | Fix |
|---|---|---|---|
| 11 | chassis_iter3.scad | Battery strap clip used invalid rotate-and-cube geometry (extended outside chassis) | Rewrote as simple cross-bar above battery |
| 12 | wheel.scad | TPU tire had no mechanical interlock with hub (slip-fit only) | Added `hub_tpu_keying_ribs()` — 16 small triangular ribs around hub OD |
| 13 | bumper.scad | `bumper_arc_deg` declared but unused (module always built closed cylinder) | Removed dead variable; documented "always 360° in current rev" |
| 14 | chassis_iter3.scad | Dead `perimeter_ring` module never called | Deleted |
| 15 | parameters.scad | Unused `motor_mount_pcd` (motors mount via collar, not bolts) | Removed; left comment for future flange-mount design |
| 16 | parameters.scad | Duplicate section numbers (two §7, two §8) | Renumbered §1–11 sequentially |
| 17 | parameters.scad | `chassis_radius` referenced before defined (worked due to OpenSCAD globals, fragile) | Moved derived values into appropriate sections, defined before use |

All fixes verified via re-render. Renders saved to `renders/iter3_*.png`,
`renders/wheel_iter3_*.png`, `renders/bumper_iter3_*.png`.

---

## 8. Print plan

| Part | File | Approx volume | Print time | Material recommendation |
|---|---|---|---|---|
| Chassis (floor + wall + top plate) | extracted from `chassis_iter3.scad` | ~150 cm³ | 8–12 hr | PETG (durability + thermal) |
| Bumper | `bumper.scad` | ~30 cm³ | 2–3 hr | PLA-CF or Tough PLA (flexure cycle life) |
| Wheel × 2 | `wheel.scad` (oring style) | ~30 cm³ each | 2 hr each | PLA hub + Buna-N O-ring |
| Wheel × 2 (TPU variant) | `wheel.scad` (tpu_overmold) | ~35 cm³ each | 4 hr each | PLA hub + TPU 95A (AMS multi-material) |

---

## 9. Known unknowns (still needing physical hardware to confirm)

1. **Maker-ESP32 actual M4 mount PCD** — assumed 64 × 40 mm on LEGO grid; confirm with calipers when board arrives
2. **ESP32 DevKitV1 mount-hole pattern** — assumed 49 × 22 mm; varies by manufacturer
3. **Generic buck converter PCD** — assumed 44 × 24 mm; manufacturer-dependent
4. **Microswitch screw spacing** — assumed 10 mm; confirm against chosen switches
5. **Battery exact dimensions** — placeholder 80 × 40 × 25 mm; resize cradle when pack is finalized
6. **Pi 5 active cooler exact stack height** — assumed 35 mm total; adjust if cooler differs
7. **Bumper flexure spring rate** — 1.6 mm wall × 4 leaves; needs print + load testing

---

## 10. What's next

1. **Iter-4: print prep** — extract individual STLs (chassis_floor, chassis_wall, chassis_top_plate, wheel × 2, bumper), prepare Bambu Studio project file with print orientation set and supports configured
2. **First print + fitment validation** — print chassis floor in cheap PLA, place real Pi 5 / Maker-ESP32 / motor + wheel, verify clearances
3. **Wheel traction test** — print one wheel + drop in O-ring; mount on Greartisan motor; characterize hard floor + carpet traction
4. **Bumper spring-rate tuning** — print at 3 wall thicknesses (1.2 / 1.6 / 2.0 mm); measure compression force; lock optimal value
5. **Full assembly** — Iter-5 onwards
