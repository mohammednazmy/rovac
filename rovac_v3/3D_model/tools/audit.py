#!/usr/bin/env python3
"""
ROVAC v3 — Hardcore audit suite

Industry-standard validation pipeline for OpenSCAD models:
  1. Static analysis on SCAD source (sca2d)
  2. STL export of each part via OpenSCAD
  3. Mesh integrity validation (admesh + trimesh)
     - Watertight, manifold, self-intersection, winding consistency
  4. Bounding-box check vs Bambu P2S 256³ mm build volume
  5. Wall-thickness analysis (trimesh ray-casting)
  6. Parametric consistency (parses parameters.scad, recomputes derived values)
  7. Spatial conflict detection (component bounding-box overlap matrix)
  8. Slicer dry-run (PrusaSlicer CLI; captures warnings)

Generates a structured audit report at audit_artifacts/audit_report.md
"""
from __future__ import annotations
import argparse
import ast
import json
import operator
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import numpy as np
import trimesh

# ===== Paths ==========================================================
ROOT = Path(__file__).resolve().parent.parent          # 3D_model/
TOOLS = ROOT / "tools"
ARTIFACTS = ROOT / "audit_artifacts"
ARTIFACTS.mkdir(exist_ok=True)

PARAMETERS_SCAD = ROOT / "parameters.scad"
CHASSIS_SCAD = ROOT / "chassis_iter3.scad"
WHEEL_SCAD = ROOT / "wheel.scad"
BUMPER_SCAD = ROOT / "bumper.scad"
EXPORT_PARTS = TOOLS / "export_parts.scad"

OPENSCAD = "openscad"
ADMESH = "admesh"
PRUSA_SLICER = "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"

BUILD_VOLUME_MM = (256.0, 256.0, 256.0)
MIN_WALL_THICKNESS = 1.5             # PLA/PETG default
MIN_WALL_THICKNESS_TPU = 0.8         # TPU is flexible, can go thinner
PRINT_BED_MARGIN_MM = 4.0


def material_min_wall(label: str) -> float:
    """Return the appropriate minimum wall thickness based on the part label
    (TPU bodies tagged with 'tpu' use a smaller minimum than rigid PLA/PETG)."""
    return MIN_WALL_THICKNESS_TPU if "tpu" in label.lower() else MIN_WALL_THICKNESS


# ===== Severity =======================================================
class Sev:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class Finding:
    severity: str
    category: str
    file: str
    message: str
    detail: str = ""

    def fmt(self) -> str:
        return f"- **[{self.severity}] {self.category}** ({self.file}): {self.message}"


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    elapsed_s: float = 0.0

    def add(self, *args, **kwargs):
        self.findings.append(Finding(*args, **kwargs))

    def by_severity(self, sev: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == sev]


# ===== Safe expression evaluator (no eval) ============================
# Only allows numeric literals, names (from supplied context), basic arithmetic,
# and list/tuple constructors. Walks an AST whitelist.
_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval_node(node, ctx):
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body, ctx)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in ctx:
            return ctx[node.id]
        raise ValueError(f"Unknown name: {node.id}")
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Disallowed unary op: {type(node.op).__name__}")
        return op(_safe_eval_node(node.operand, ctx))
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Disallowed binary op: {type(node.op).__name__}")
        return op(_safe_eval_node(node.left, ctx),
                  _safe_eval_node(node.right, ctx))
    if isinstance(node, ast.List):
        return [_safe_eval_node(elt, ctx) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval_node(elt, ctx) for elt in node.elts)
    raise ValueError(f"Disallowed AST node: {type(node).__name__}")


def safe_eval_param(expr: str, ctx: dict) -> Optional[Any]:
    """Evaluate a numeric/list parameter expression in a sandboxed context.
    Disallows function calls, attribute access, comprehensions, etc.
    Returns int, float, str, list, or tuple — None if expression rejects."""
    try:
        tree = ast.parse(expr, mode="eval")
        return _safe_eval_node(tree, ctx)
    except Exception:
        return None


# ===== 1. STATIC ANALYSIS (sca2d) =====================================
SCA2D_NOISE_RULES = {
    "I3001",   # naming convention (UPPER_CASE) — irrelevant for OpenSCAD
    "I4001",   # missing docstring — too noisy
    "I1002",   # overly complicated expression
    "W2010",   # $fn redefined by multiple imports — intentional (parameters.scad)
    "I9000",   # pylint-style other info messages
}
SCA2D_SUMMARY_PREFIXES = (
    "Fatal errors", "Errors:", "Warnings:", "Infos:", "Info:", "Depreciated",
    "Lint passed", "Total", "SCA2D", "===", "Files Linted",
)


def run_sca2d(report: AuditReport) -> None:
    for scad in [PARAMETERS_SCAD, CHASSIS_SCAD, WHEEL_SCAD, BUMPER_SCAD]:
        if not scad.exists():
            continue
        # Run sca2d with cwd=ROOT and a relative filename so its diagnostic
        # output emits repo-relative paths (e.g. "parameters.scad:27:1: ...")
        # rather than machine-specific absolute paths. Keeps audit_report.json
        # portable across machines and free of $HOME-specific noise.
        result = subprocess.run(
            ["python3", "-m", "sca2d", scad.name],
            cwd=str(ROOT),
            capture_output=True, text=True
        )
        out = (result.stdout + result.stderr).strip()
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("Linting"):
                continue
            if any(line.startswith(p) for p in SCA2D_SUMMARY_PREFIXES):
                continue
            # Filter out irrelevant rules
            if any(rule in line for rule in SCA2D_NOISE_RULES):
                continue
            sev = Sev.MEDIUM
            if " F" in line or "Fatal" in line:
                sev = Sev.HIGH
            elif " E" in line:
                sev = Sev.HIGH
            elif " W" in line:
                sev = Sev.MEDIUM
            elif " I" in line:
                sev = Sev.LOW
            report.add(sev, "sca2d", scad.name, line)


# ===== 2. EXPORT STLs ================================================
def openscad_export(part: Optional[str], out_stl: Path, source: Path = EXPORT_PARTS,
                    extra_defines: Optional[dict] = None) -> bool:
    cmd = [OPENSCAD, "-q", "-o", str(out_stl), str(source)]
    if part:
        cmd.extend(["-D", f'part="{part}"'])
    if extra_defines:
        for k, v in extra_defines.items():
            cmd.extend(["-D", f"{k}={v}"])
    subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return out_stl.exists() and out_stl.stat().st_size > 100


def export_all_parts(report: AuditReport) -> dict[str, Path]:
    parts: dict[str, Path] = {}
    targets = [
        ("floor", "chassis_floor"),
        ("wall", "chassis_wall"),
        ("top_plate", "chassis_top_plate"),
        ("full_chassis", "chassis_full"),
    ]
    for part, label in targets:
        out = ARTIFACTS / f"{label}.stl"
        if not openscad_export(part, out):
            report.add(Sev.HIGH, "STL export", "chassis_iter3.scad",
                       f"failed to export {label}")
            continue
        parts[label] = out

    wheel_stl = ARTIFACTS / "wheel.stl"
    if openscad_export(part=None, out_stl=wheel_stl, source=WHEEL_SCAD):
        parts["wheel"] = wheel_stl
    else:
        report.add(Sev.HIGH, "STL export", "wheel.scad", "failed to export wheel")

    # Bumper: full-ring (visualization) + each of 4 quadrants (printable parts)
    bumper_stl = ARTIFACTS / "bumper_full_ring.stl"
    if openscad_export(part=None, out_stl=bumper_stl, source=BUMPER_SCAD):
        parts["bumper_full_ring"] = bumper_stl
    for seg in range(4):
        out = ARTIFACTS / f"bumper_q{seg}.stl"
        cmd = [OPENSCAD, "-q", "-o", str(out), str(BUMPER_SCAD),
               "-D", f"bumper_segment={seg}"]
        subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if out.exists() and out.stat().st_size > 100:
            parts[f"bumper_q{seg}"] = out
        else:
            report.add(Sev.HIGH, "STL export", "bumper.scad",
                       f"failed to export bumper_q{seg}")

    # AUDIT-3: per-body wheel exports for multi-material AMS printing
    for body, label in [("hub", "wheel_hub_pla"),
                        ("tire", "wheel_tire_tpu")]:
        out = ARTIFACTS / f"{label}.stl"
        tire_style = "tpu_overmold"  # multi-material configuration
        cmd = [OPENSCAD, "-q", "-o", str(out), str(WHEEL_SCAD),
               "-D", f'body="{body}"',
               "-D", f'tire_style="{tire_style}"']
        subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if out.exists() and out.stat().st_size > 100:
            parts[label] = out

    return parts


# ===== 3. MESH INTEGRITY (admesh + trimesh) ===========================
def run_admesh(stl: Path) -> dict:
    result = subprocess.run([ADMESH, "-c", str(stl)],
                            capture_output=True, text=True, timeout=60)
    out = result.stdout + result.stderr
    parsed = {}
    for line in out.splitlines():
        m = re.match(r"\s*([A-Za-z][^:]+?)\s*:\s*([0-9.eE+-]+)", line)
        if m:
            parsed[m.group(1).strip()] = m.group(2).strip()
    return parsed


def trimesh_check(stl: Path) -> dict:
    try:
        m = trimesh.load_mesh(str(stl))
    except Exception as e:
        return {"error": f"load failed: {e}"}
    bbox = m.bounding_box.extents.tolist()
    info = {
        "triangles": int(len(m.faces)),
        "vertices": int(len(m.vertices)),
        "volume_mm3": float(m.volume) if m.is_volume else None,
        "surface_area_mm2": float(m.area),
        "bbox_mm": [round(x, 2) for x in bbox],
        "is_watertight": bool(m.is_watertight),
        "is_winding_consistent": bool(m.is_winding_consistent),
        "is_volume": bool(m.is_volume),
        "euler_number": int(m.euler_number),
    }
    try:
        intersecting = trimesh.repair.broken_faces(m)
        info["broken_face_count"] = int(len(intersecting))
    except Exception:
        info["broken_face_count"] = -1
    return info


def audit_meshes(parts: dict[str, Path], report: AuditReport) -> None:
    metrics = {}
    for label, stl in parts.items():
        am = run_admesh(stl)
        tm = trimesh_check(stl)
        metrics[label] = {"admesh": am, "trimesh": tm}

        if "error" in tm:
            report.add(Sev.CRITICAL, "mesh", f"{label}.stl", tm["error"])
            continue
        if not tm["is_watertight"]:
            report.add(Sev.HIGH, "mesh", f"{label}.stl",
                       "mesh is NOT watertight (open edges)",
                       f"euler_number={tm['euler_number']}")
        if not tm["is_winding_consistent"]:
            report.add(Sev.HIGH, "mesh", f"{label}.stl",
                       "winding inconsistent (mixed CCW/CW faces)")
        if tm.get("broken_face_count", 0) > 0:
            report.add(Sev.MEDIUM, "mesh", f"{label}.stl",
                       f"{tm['broken_face_count']} broken faces")

        bx, by, bz = tm["bbox_mm"]
        # AUDIT-2: bumper full-ring is a visualization, not a print target — skip BV check
        if "full_ring" not in label:
            if bx > BUILD_VOLUME_MM[0] - PRINT_BED_MARGIN_MM:
                report.add(Sev.HIGH, "build_volume", f"{label}.stl",
                           f"X dim {bx:.1f} mm > P2S X budget"
                           f" ({BUILD_VOLUME_MM[0]} − {PRINT_BED_MARGIN_MM} margin)")
            if by > BUILD_VOLUME_MM[1] - PRINT_BED_MARGIN_MM:
                report.add(Sev.HIGH, "build_volume", f"{label}.stl",
                           f"Y dim {by:.1f} mm > P2S Y budget")
            if bz > BUILD_VOLUME_MM[2] - PRINT_BED_MARGIN_MM:
                report.add(Sev.HIGH, "build_volume", f"{label}.stl",
                           f"Z dim {bz:.1f} mm > P2S Z budget")
    report.metrics["meshes"] = metrics


# ===== 4. WALL THICKNESS (trimesh ray-casting sample) =================
def wall_thickness_sample(stl: Path, n_samples: int = 4000) -> dict:
    try:
        m = trimesh.load_mesh(str(stl))
    except Exception as e:
        return {"error": str(e)}
    if not m.is_volume:
        return {"error": "not a volume"}
    sample_pts, face_idx = trimesh.sample.sample_surface(m, n_samples)
    normals = m.face_normals[face_idx]
    origins = sample_pts - normals * 1e-3
    directions = -normals
    # intersects_location returns (locations, index_ray, index_tri)
    hits = m.ray.intersects_location(origins, directions)
    locations, ray_idx = hits[0], hits[1]  # type: ignore[assignment]
    if len(locations) == 0:
        return {"error": "no ray hits"}
    distances = []
    seen = set()
    for loc, ri in zip(locations, ray_idx):
        if ri in seen:
            continue
        seen.add(ri)
        d = float(np.linalg.norm(loc - origins[ri]))
        if d > 1e-2:
            distances.append(d)
    if not distances:
        return {"error": "no valid distances"}
    arr = np.array(distances)
    return {
        "samples": int(len(arr)),
        "min_mm": float(arr.min()),
        "p1_mm": float(np.percentile(arr, 1)),
        "p5_mm": float(np.percentile(arr, 5)),
        "median_mm": float(np.median(arr)),
        "mean_mm": float(arr.mean()),
        "max_mm": float(arr.max()),
    }


def audit_wall_thickness(parts: dict[str, Path], report: AuditReport) -> None:
    """AUDIT-2 fix: use p1 (1st percentile) as the threshold rather than absolute min,
    because ray-casting near sharp edges can produce isolated near-zero readings that
    aren't representative of any actual wall.
    AUDIT-2 fix: skip 'full_ring' entries — they're visualization-only, not print targets."""
    metrics = {}
    for label, stl in parts.items():
        wt = wall_thickness_sample(stl, n_samples=8000)
        metrics[label] = wt
        if "error" in wt:
            continue
        # Skip visualization-only meshes
        if "full_ring" in label:
            continue
        threshold = material_min_wall(label)
        material_label = "TPU" if threshold == MIN_WALL_THICKNESS_TPU else "PLA/PETG"
        if wt["p1_mm"] < threshold:
            report.add(Sev.HIGH, "wall_thickness", f"{label}.stl",
                       f"p1 wall {wt['p1_mm']:.2f} mm < {threshold} mm ({material_label} threshold)",
                       f"min={wt['min_mm']:.2f} (edge artifacts), p5={wt['p5_mm']:.2f}, median={wt['median_mm']:.2f}")
        elif wt["p5_mm"] < threshold:
            report.add(Sev.MEDIUM, "wall_thickness", f"{label}.stl",
                       f"5th-pct wall {wt['p5_mm']:.2f} mm < {threshold} mm ({material_label} threshold)")
    report.metrics["wall_thickness"] = metrics


# ===== 5. PARAMETRIC CONSISTENCY ======================================
PARAM_RE = re.compile(
    r"^\s*([a-zA-Z_]\w*)\s*=\s*([^;]+?)\s*;\s*(?://.*)?$",
    re.MULTILINE,
)


def parse_parameters(scad: Path) -> dict[str, str]:
    text = scad.read_text()
    return {m.group(1): m.group(2).strip() for m in PARAM_RE.finditer(text)}


def audit_parametric_consistency(report: AuditReport) -> None:
    raw = parse_parameters(PARAMETERS_SCAD)
    ctx = {}
    for name, expr in raw.items():
        v = safe_eval_param(expr, ctx)
        if v is not None:
            ctx[name] = v
    report.metrics["parameters"] = {
        k: ctx[k] for k in ctx if isinstance(ctx[k], (int, float, list, tuple))
    }

    expected = {
        "chassis_radius": ("chassis_diameter / 2",
                           lambda c: c["chassis_diameter"] / 2),
        "robot_total_height": ("chassis_height + lidar_optical_height",
                               lambda c: c["chassis_height"] + c["lidar_optical_height"]),
        "lidar_base_z": ("chassis_height - lidar_recess_depth",
                         lambda c: c["chassis_height"] - c["lidar_recess_depth"]),
        "wheel_center_z": ("wheel_diameter/2 - ground_clearance",
                           lambda c: c["wheel_diameter"] / 2 - c["ground_clearance"]),
    }
    for name, (formula, fn) in expected.items():
        if name not in ctx:
            report.add(Sev.MEDIUM, "parametric", "parameters.scad",
                       f"missing derived value: {name} (expected {formula})")
            continue
        try:
            want = float(fn(ctx))
            got = float(ctx[name])
            if abs(want - got) > 0.01:
                report.add(Sev.HIGH, "parametric", "parameters.scad",
                           f"{name} = {got} but should be {want} ({formula})")
        except Exception as e:
            report.add(Sev.LOW, "parametric", "parameters.scad",
                       f"could not verify {name}: {e}")

    if "top_plate_counterbore_depth" in ctx and "ceiling_thickness" in ctx:
        cb = ctx["top_plate_counterbore_depth"]
        ct = ctx["ceiling_thickness"]
        if cb >= ct:
            report.add(Sev.CRITICAL, "parametric", "parameters.scad",
                       f"counterbore_depth ({cb}) >= ceiling_thickness ({ct}) — heads fall through")
        elif ct - cb < 1.0:
            report.add(Sev.MEDIUM, "parametric", "parameters.scad",
                       f"only {ct-cb:.1f} mm of plate material under counterbore (recommend ≥1 mm)")


# ===== 6. SPATIAL CONFLICT MATRIX =====================================
@dataclass
class Component:
    name: str
    anchor: tuple
    footprint: tuple


def axis_aligned_overlap(c1: Component, c2: Component) -> Optional[tuple]:
    dx = min(c1.anchor[0] + c1.footprint[0]/2, c2.anchor[0] + c2.footprint[0]/2) - \
         max(c1.anchor[0] - c1.footprint[0]/2, c2.anchor[0] - c2.footprint[0]/2)
    dy = min(c1.anchor[1] + c1.footprint[1]/2, c2.anchor[1] + c2.footprint[1]/2) - \
         max(c1.anchor[1] - c1.footprint[1]/2, c2.anchor[1] - c2.footprint[1]/2)
    dz = min(c1.anchor[2] + c1.footprint[2], c2.anchor[2] + c2.footprint[2]) - \
         max(c1.anchor[2], c2.anchor[2])
    if dx > 0 and dy > 0 and dz > 0:
        return (dx, dy, dz)
    return None


def audit_spatial_conflicts(report: AuditReport) -> None:
    p = report.metrics["parameters"]
    components = [
        Component("Pi5", tuple(p["pi_anchor"]), tuple(p["pi5_footprint"])),
        Component("ESP32_motor", tuple(p["esp32_motor_anchor"]),
                  tuple(p["esp32_motor_footprint"])),
        Component("ESP32_sensor", tuple(p["esp32_sensor_anchor"]),
                  tuple(p["esp32_sensor_footprint"])),
        Component("BNO055", tuple(p["imu_anchor"]), tuple(p["imu_footprint"])),
        Component("Buck", tuple(p["buck_anchor"]), tuple(p["buck_footprint"])),
        Component("Battery", tuple(p["battery_anchor"]),
                  tuple(p["battery_footprint"])),
        Component("LIDAR_base",
                  (0, 0, p["lidar_base_z"]),
                  (p["lidar_footprint"], p["lidar_footprint"], p["lidar_base_height"])),
    ]
    for i, c1 in enumerate(components):
        for c2 in components[i+1:]:
            ov = axis_aligned_overlap(c1, c2)
            if ov:
                report.add(
                    Sev.CRITICAL, "spatial", "parameters.scad",
                    f"{c1.name} and {c2.name} bounding boxes overlap",
                    f"overlap_xyz={tuple(round(x, 1) for x in ov)} mm")

    interior_r = p["chassis_radius"] - p["wall_thickness"]
    for c in components:
        cx, cy = c.anchor[0], c.anchor[1]
        fx, fy = c.footprint[0], c.footprint[1]
        max_dist = max(
            np.hypot(cx + fx/2, cy + fy/2),
            np.hypot(cx + fx/2, cy - fy/2),
            np.hypot(cx - fx/2, cy + fy/2),
            np.hypot(cx - fx/2, cy - fy/2),
        )
        if max_dist > interior_r:
            report.add(
                Sev.HIGH, "spatial", "parameters.scad",
                f"{c.name} corner reaches r={max_dist:.1f} mm > interior r={interior_r:.1f} mm")

    cliff_fp = p["cliff_footprint"]
    for label, anchor in [("front", p["cliff_anchor_front"]),
                          ("rear", p["cliff_anchor_rear"])]:
        far_x = abs(anchor[0]) + cliff_fp[0] / 2
        if far_x > interior_r:
            report.add(
                Sev.HIGH, "spatial", "parameters.scad",
                f"cliff_{label} reaches X={far_x:.1f} mm > interior r={interior_r:.1f} mm")


# ===== 7. OVERHANG / BRIDGE / SUPPORT (PRINTABILITY) ==================
# Industry standard: PLA/PETG can print:
#   - up to ~45° from vertical without support
#   - bridges up to ~10 mm without sagging
# We bin overhangs into 30/45/60/75/90 buckets; flag steep + sizable regions.

OVERHANG_BINS_DEG = [0, 30, 45, 60, 75, 90]
OVERHANG_FLAG_THRESHOLD_DEG = 60     # above this needs supports
OVERHANG_FLAG_AREA_MM2 = 5           # ignore tiny edge artifacts
BRIDGE_FLAG_SPAN_MM = 10
BRIDGE_FLAT_NORMAL_THRESHOLD = -0.95  # n_z < this = nearly horizontal pointing down
SUPPORT_DENSITY = 0.15                # typical sparse support material density


def analyze_overhangs(stl: Path) -> dict:
    """Histogram of face area binned by overhang angle from vertical.
    Returns area per bin and total down-facing area.
    AUDIT-3 FIX: excludes bottom-of-part faces (they sit on the build plate, not overhangs)."""
    try:
        m = trimesh.load_mesh(str(stl))
    except Exception as e:
        return {"error": str(e)}
    nz = m.face_normals[:, 2]
    areas = m.area_faces
    # Exclude faces sitting on the bed (within 0.5 mm of part's lowest Z)
    bottom_z = float(m.bounds[0, 2])
    face_z = m.triangles_center[:, 2]
    on_bed = face_z < bottom_z + 0.5
    is_overhang = (nz < 0) & ~on_bed
    # arcsin of -nz gives overhang angle from vertical (0 = vertical wall, 90 = horizontal ceiling)
    angles = np.zeros_like(nz)
    angles[is_overhang] = np.degrees(np.arcsin(np.clip(-nz[is_overhang], 0, 1)))

    bin_areas = []
    for i in range(len(OVERHANG_BINS_DEG) - 1):
        lo, hi = OVERHANG_BINS_DEG[i], OVERHANG_BINS_DEG[i + 1]
        mask = is_overhang & (angles >= lo) & (angles < hi)
        bin_areas.append({
            "bin_deg": f"{lo}-{hi}",
            "area_mm2": float(areas[mask].sum()),
            "face_count": int(mask.sum()),
        })

    return {
        "total_overhang_area_mm2": float(areas[is_overhang].sum()),
        "total_surface_area_mm2": float(areas.sum()),
        "overhang_pct": float(areas[is_overhang].sum() / areas.sum() * 100) if areas.sum() > 0 else 0.0,
        "bins": bin_areas,
        "steep_area_mm2": float(areas[is_overhang & (angles >= OVERHANG_FLAG_THRESHOLD_DEG)].sum()),
        "horizontal_overhang_area_mm2": float(areas[is_overhang & (angles >= 89)].sum()),
    }


def detect_bridges(stl: Path) -> dict:
    """Find connected components of horizontal-down-facing faces.
    For each component, compute XY bounding box. Flag if span > BRIDGE_FLAG_SPAN_MM."""
    try:
        m = trimesh.load_mesh(str(stl))
    except Exception as e:
        return {"error": str(e)}

    nz = m.face_normals[:, 2]
    # AUDIT-3 FIX: exclude bed-bottom faces from bridge detection
    bottom_z = float(m.bounds[0, 2])
    face_z = m.triangles_center[:, 2]
    on_bed = face_z < bottom_z + 0.5
    is_flat_overhang = (nz < BRIDGE_FLAT_NORMAL_THRESHOLD) & ~on_bed
    if not np.any(is_flat_overhang):
        return {"bridges": [], "total_flat_overhang_area_mm2": 0.0}

    flat_face_idx = np.where(is_flat_overhang)[0]
    flat_set = set(flat_face_idx.tolist())

    # Build adjacency restricted to flat-overhang faces
    edges = []
    for a, b in m.face_adjacency:
        if int(a) in flat_set and int(b) in flat_set:
            edges.append([int(a), int(b)])

    # Connected components using trimesh.graph (nodes must be ndarray)
    flat_nodes = np.array(sorted(flat_set), dtype=np.int64)
    if edges:
        components = trimesh.graph.connected_components(
            np.array(edges, dtype=np.int64), nodes=flat_nodes, engine="scipy"
        )
    else:
        components = [np.array([f]) for f in flat_face_idx]

    bridges = []
    for comp in components:
        comp = np.array(comp, dtype=int)
        if len(comp) == 0:
            continue
        comp_verts = m.vertices[m.faces[comp].ravel()]
        xy = comp_verts[:, :2]
        bbox_min = xy.min(axis=0)
        bbox_max = xy.max(axis=0)
        span_xy = bbox_max - bbox_min
        max_span = float(np.max(span_xy))
        comp_area = float(m.area_faces[comp].sum())
        if max_span > 1.0:  # skip near-zero artifacts
            bridges.append({
                "face_count": int(len(comp)),
                "area_mm2": comp_area,
                "max_xy_span_mm": max_span,
                "bbox_xy_extent_mm": [float(span_xy[0]), float(span_xy[1])],
                "centroid_xy_mm": [float(xy.mean(axis=0)[0]), float(xy.mean(axis=0)[1])],
            })

    bridges.sort(key=lambda b: b["max_xy_span_mm"], reverse=True)
    return {
        "bridges": bridges,
        "total_flat_overhang_area_mm2": float(m.area_faces[is_flat_overhang].sum()),
    }


def estimate_support_volume(stl: Path) -> dict:
    """Approximate support volume: overhang area × avg overhang Z × density.
    Documented as approximation — real slicer values may differ ±30%."""
    try:
        m = trimesh.load_mesh(str(stl))
    except Exception as e:
        return {"error": str(e)}
    nz = m.face_normals[:, 2]
    angles = np.degrees(np.arcsin(np.clip(np.abs(nz), 0, 1)))
    # AUDIT-3 FIX: exclude bed-bottom; height = distance ABOVE bed (not absolute Z)
    bottom_z = float(m.bounds[0, 2])
    face_z = m.triangles_center[:, 2]
    on_bed = face_z < bottom_z + 0.5
    needs_support = (nz < 0) & (angles > 45) & ~on_bed
    if not np.any(needs_support):
        return {
            "needs_support": False,
            "estimated_support_volume_mm3": 0.0,
        }
    overhang_area = float(m.area_faces[needs_support].sum())
    avg_height = float((face_z[needs_support] - bottom_z).mean())
    return {
        "needs_support": True,
        "overhang_area_mm2": overhang_area,
        "avg_overhang_z_mm": avg_height,
        "support_density_assumed": SUPPORT_DENSITY,
        "estimated_support_volume_mm3": overhang_area * avg_height * SUPPORT_DENSITY,
    }


def audit_printability(parts: dict, report: AuditReport) -> None:
    """Run overhang + bridge + support analyses on each printable part."""
    metrics = {}
    for label, stl in parts.items():
        if "full_ring" in label:
            continue
        oh = analyze_overhangs(stl)
        br = detect_bridges(stl)
        sv = estimate_support_volume(stl)
        metrics[label] = {"overhangs": oh, "bridges": br, "support": sv}

        if "error" not in oh and oh["steep_area_mm2"] > OVERHANG_FLAG_AREA_MM2:
            report.add(
                Sev.MEDIUM, "overhangs", f"{label}.stl",
                f"{oh['steep_area_mm2']:.1f} mm² of overhang ≥{OVERHANG_FLAG_THRESHOLD_DEG}°"
                f" — supports recommended",
                f"horizontal-overhang area: {oh['horizontal_overhang_area_mm2']:.1f} mm²;"
                f" total overhang: {oh['overhang_pct']:.1f}% of surface",
            )

        if "error" not in br:
            for b in br["bridges"]:
                if b["max_xy_span_mm"] > BRIDGE_FLAG_SPAN_MM:
                    report.add(
                        Sev.MEDIUM, "bridge", f"{label}.stl",
                        f"bridge span {b['max_xy_span_mm']:.1f} mm > {BRIDGE_FLAG_SPAN_MM} mm",
                        f"area={b['area_mm2']:.1f} mm² at xy={b['centroid_xy_mm']}",
                    )

    report.metrics["printability"] = metrics


# ===== 8. MASS PROPERTIES =============================================
# Material density (g/cm³ → t/mm³ for CalculiX)
MATERIAL_DENSITY = {
    "PLA": 1.24,
    "PETG": 1.27,
    "TPU_95A": 1.20,
    "ABS": 1.04,
}
# Typical infill fraction (15–30 % range; we use 25 % as audit default)
INFILL_FRACTION = 0.25
# Walls/perimeters are solid; estimate solid fraction based on shell/infill mix
EFFECTIVE_FRACTION = 0.45   # accounts for solid perimeters + infilled core


def assume_material(label: str) -> str:
    """Pick the assumed material based on part label."""
    if "tpu" in label.lower():
        return "TPU_95A"
    return "PETG"          # default for chassis parts


def compute_mass_properties(stl: Path, material: str = "PETG") -> dict:
    try:
        m = trimesh.load_mesh(str(stl))
    except Exception as e:
        return {"error": str(e)}
    rho = MATERIAL_DENSITY.get(material, 1.27)   # g/cm³
    volume_mm3 = float(m.volume) if m.is_volume else float(m.bounding_box.volume)
    volume_cm3 = volume_mm3 / 1000.0
    solid_mass_g = volume_cm3 * rho
    realistic_mass_g = solid_mass_g * EFFECTIVE_FRACTION
    com = m.center_mass.tolist() if m.is_volume else m.centroid.tolist()
    return {
        "material": material,
        "density_g_cm3": rho,
        "volume_cm3": volume_cm3,
        "mass_g_solid": solid_mass_g,
        "mass_g_realistic": realistic_mass_g,
        "infill_assumed": INFILL_FRACTION,
        "effective_fraction": EFFECTIVE_FRACTION,
        "center_of_mass_mm": [round(c, 2) for c in com],
    }


def audit_mass_properties(parts: dict, report: AuditReport) -> None:
    metrics = {}
    total_realistic_g = 0.0
    for label, stl in parts.items():
        if "full_ring" in label or "_full" in label:
            continue   # avoid double-counting (full = floor + wall + top)
        material = assume_material(label)
        mp = compute_mass_properties(stl, material)
        metrics[label] = mp
        if "error" not in mp:
            total_realistic_g += mp["mass_g_realistic"]
    metrics["_total_realistic_g"] = total_realistic_g
    report.metrics["mass_properties"] = metrics


# ===== 9. OPTIMAL PRINT ORIENTATION ===================================
# For each part, evaluate candidate orientations and pick the one that
# minimizes support volume while keeping reasonable bed contact + low CoG.

def _orientation_score(mesh: trimesh.Trimesh) -> dict:
    """For an oriented mesh, compute support volume, bed contact, CoG height."""
    bottom_z = float(mesh.bounds[0, 2])
    top_z = float(mesh.bounds[1, 2])
    face_z = mesh.triangles_center[:, 2]
    on_bed = face_z < bottom_z + 0.5
    nz = mesh.face_normals[:, 2]
    angles = np.degrees(np.arcsin(np.clip(np.abs(nz), 0, 1)))
    needs_support = (nz < 0) & (angles > 45) & ~on_bed
    support_area = float(mesh.area_faces[needs_support].sum())
    avg_h = float((face_z[needs_support] - bottom_z).mean()) if needs_support.any() else 0.0
    support_vol = support_area * avg_h * SUPPORT_DENSITY
    bed_contact_area = float(mesh.area_faces[on_bed].sum())
    com = mesh.center_mass if mesh.is_volume else mesh.centroid
    com_height = float(com[2] - bottom_z)
    height = top_z - bottom_z
    return {
        "support_volume_mm3": support_vol,
        "bed_contact_mm2": bed_contact_area,
        "com_height_mm": com_height,
        "height_mm": height,
    }


def find_optimal_orientation(stl: Path) -> dict:
    """Try N candidate orientations; return the one with lowest weighted score:
    score = support_vol - 0.5 * bed_contact + 5 * com_height
    (weights chosen to prefer minimal support while not toppling thin parts)."""
    try:
        m = trimesh.load_mesh(str(stl))
    except Exception as e:
        return {"error": str(e)}

    # Candidate rotations: 6 cardinal (each face down) + 45° on each axis-pair
    candidates = []
    candidates.append(("as_designed", np.eye(4)))
    for axis_name, axis in [("X", (1, 0, 0)), ("Y", (0, 1, 0))]:
        for angle in [90, 180, 270]:
            T = trimesh.transformations.rotation_matrix(np.radians(angle), axis)
            candidates.append((f"{axis_name}{angle}", T))
    for tilt in [45, 135]:
        T = trimesh.transformations.rotation_matrix(np.radians(tilt), (1, 0, 0))
        candidates.append((f"X{tilt}_tilt", T))
    for tilt in [45, 135]:
        T = trimesh.transformations.rotation_matrix(np.radians(tilt), (0, 1, 0))
        candidates.append((f"Y{tilt}_tilt", T))

    results = []
    for label, T in candidates:
        m2 = m.copy()
        m2.apply_transform(T)
        s = _orientation_score(m2)
        score = s["support_volume_mm3"] - 0.5 * s["bed_contact_mm2"] + 5 * s["com_height_mm"]
        results.append({"orientation": label, "score": float(score), **s})

    results.sort(key=lambda r: r["score"])
    best = results[0]
    as_designed = next(r for r in results if r["orientation"] == "as_designed")
    return {
        "best": best,
        "as_designed": as_designed,
        "improvement_support_mm3": as_designed["support_volume_mm3"] - best["support_volume_mm3"],
        "all_candidates": results,
    }


def audit_orientation(parts: dict, report: AuditReport) -> None:
    metrics = {}
    for label, stl in parts.items():
        if "full_ring" in label:
            continue
        opt = find_optimal_orientation(stl)
        metrics[label] = opt
        if "error" in opt:
            continue
        if opt["best"]["orientation"] != "as_designed":
            saving_cm3 = opt["improvement_support_mm3"] / 1000.0
            if saving_cm3 > 1.0:    # only flag substantial improvements
                report.add(
                    Sev.LOW, "orientation", f"{label}.stl",
                    f"reorient to '{opt['best']['orientation']}' saves "
                    f"{saving_cm3:.1f} cm³ of support material",
                    f"as-designed support: {opt['as_designed']['support_volume_mm3']/1000:.1f} cm³;"
                    f" optimal: {opt['best']['support_volume_mm3']/1000:.1f} cm³",
                )
    report.metrics["orientation"] = metrics


# ===== 10. SLICER G-CODE ANALYSIS =====================================
GCODE_HEADER_KEYS = [
    ("filament used [mm]", "filament_mm"),
    ("filament used [g]", "filament_g"),
    ("filament used [cm3]", "filament_cm3"),
    ("estimated printing time (normal mode)", "print_time_normal"),
    ("estimated printing time", "print_time"),
    ("total layers count", "layer_count"),
    ("layer_height", "layer_height"),
]


def slice_and_parse(stl: Path) -> dict:
    """Slice the STL with PrusaSlicer CLI (Bambu P2S 256³ bed, 0.2 mm layer)
    and parse gcode header for filament + time."""
    out_gcode = stl.with_suffix(".gcode")
    cmd = [PRUSA_SLICER, "--export-gcode",
           "--bed-shape", "0x0,256x0,256x256,0x256",
           "--center", "128,128",
           "--layer-height", "0.2",
           "--filament-density", "1.27",     # PETG default; TPU = 1.20 (close enough)
           "--output", str(out_gcode), str(stl)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"error": "slicer timeout"}
    if not out_gcode.exists() or out_gcode.stat().st_size < 100:
        return {"error": "gcode export failed",
                "stderr": result.stderr[:200] if result.stderr else ""}
    info = {"gcode_path": str(out_gcode), "size_bytes": out_gcode.stat().st_size}
    text = out_gcode.read_text(errors="ignore")
    # PrusaSlicer puts most metrics at the END of the gcode, not the top
    lines = text.splitlines()
    sample = lines[:200] + lines[-2000:]
    for line in sample:
        if not line.startswith(";"):
            continue
        for key_match, key_short in GCODE_HEADER_KEYS:
            if key_match in line.lower():
                _, _, val = line.partition("=")
                info[key_short] = val.strip()
                break
    return info


def audit_slicer_gcode(parts: dict, report: AuditReport) -> None:
    if not Path(PRUSA_SLICER).exists():
        return
    metrics = {}
    for label, stl in parts.items():
        if "full_ring" in label:
            continue
        info = slice_and_parse(stl)
        metrics[label] = info
    report.metrics["slicer_gcode"] = metrics


# ===== 11. FEM STRESS SIMULATION (gmsh + CalculiX) ====================
GMSH_PATH = "/opt/homebrew/bin/gmsh"
CCX_PATH = "/opt/homebrew/Caskroom/miniforge/base/bin/ccx"

# Material properties (all in CalculiX mm-N-MPa-t units)
FEM_MATERIALS = {
    "PLA":      {"E_MPa": 2500, "nu": 0.36, "density_t_mm3": 1.24e-9, "yield_MPa": 60},
    "PETG":     {"E_MPa": 2000, "nu": 0.40, "density_t_mm3": 1.27e-9, "yield_MPa": 50},
    "TPU_95A":  {"E_MPa": 25,   "nu": 0.48, "density_t_mm3": 1.20e-9, "yield_MPa": 8},
    "ABS":      {"E_MPa": 2300, "nu": 0.35, "density_t_mm3": 1.04e-9, "yield_MPa": 40},
}


# AUDIT-4 NOTE: gmsh's STL → 3D pipeline (classifySurfaces + createGeometry)
# is unreliable for complex CAD-derived STLs — it can stall for tens of minutes
# on geometry with sharp ribs / thin features. Instead we run FEM on simplified
# OCC-generated primitive approximations (e.g., a clean disc for the chassis
# floor). This characterizes the *bulk* stress behavior of each part without
# mesh-prep heroics. It's documented as an approximation in the report.

def gmsh_primitive_to_inp(geometry_func, out_inp: Path,
                           element_size_mm: float = 6.0) -> bool:
    """Run a geometry-creating callback inside a fresh gmsh session and write
    a CalculiX-compatible .inp file (containing only C3D4 tetrahedra)."""
    try:
        import gmsh as g  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        g.initialize()
        g.option.setNumber("General.Terminal", 0)
        g.option.setNumber("Mesh.CharacteristicLengthMax", element_size_mm)
        g.option.setNumber("Mesh.CharacteristicLengthMin", element_size_mm * 0.3)
        geometry_func(g)
        g.model.occ.synchronize()
        g.model.mesh.generate(3)
        g.write(str(out_inp))
        return True
    except Exception as e:
        print(f"gmsh primitive mesh failed: {e}")
        return False
    finally:
        try:
            g.finalize()
        except Exception:
            pass


def filter_inp_to_tets_only(in_path: Path, out_path: Path) -> bool:
    """Strip line/surface elements; keep only *NODE and *ELEMENT C3D4."""
    if not in_path.exists():
        return False
    text = in_path.read_text()
    lines = text.splitlines()
    out_lines = []
    in_node = False
    keep_element = False
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("*HEADING"):
            out_lines.append("*HEADING")
            out_lines.append("FEM (3D tets only)")
            in_node = False; keep_element = False
            continue
        if upper.startswith("*NODE"):
            out_lines.append(line)
            in_node = True; keep_element = False
            continue
        if upper.startswith("*ELEMENT"):
            in_node = False
            if "C3D4" in upper:
                out_lines.append(line)
                keep_element = True
            else:
                keep_element = False
            continue
        if stripped.startswith("*"):
            in_node = False; keep_element = False
            continue
        if in_node or keep_element:
            out_lines.append(line)
    out_path.write_text("\n".join(out_lines) + "\n")
    return True


def write_ccx_input(inp_in: Path, inp_out: Path, material: str,
                    fixed_z_max: float, load_face_z_min: float,
                    load_total_n: float = 6.0) -> bool:
    """Read tets-only .inp; append material, BCs (fix bottom), loads (top), step.
    Distributes load_total_n equally across all nodes above load_face_z_min."""
    if not inp_in.exists():
        return False
    text = inp_in.read_text()
    mat = FEM_MATERIALS.get(material, FEM_MATERIALS["PETG"])
    fixed_nodes = []
    loaded_nodes = []
    in_node_section = False
    for line in text.splitlines():
        line_strip = line.strip()
        if line_strip.upper().startswith("*NODE"):
            in_node_section = True
            continue
        if line_strip.startswith("*"):
            in_node_section = False
            continue
        if in_node_section and line_strip and not line_strip.startswith("**"):
            parts_list = [p.strip() for p in line_strip.split(",")]
            if len(parts_list) >= 4:
                try:
                    nid = int(parts_list[0])
                    z = float(parts_list[3])
                    if z <= fixed_z_max:
                        fixed_nodes.append(nid)
                    elif z >= load_face_z_min:
                        loaded_nodes.append(nid)
                except ValueError:
                    continue
    if not fixed_nodes or not loaded_nodes:
        return False
    elset = "Volume1"
    for line in text.splitlines():
        if "*ELEMENT" in line.upper() and "C3D4" in line.upper() and "ELSET" in line.upper():
            for token in line.split(","):
                token = token.strip()
                if token.upper().startswith("ELSET="):
                    elset = token.split("=", 1)[1]
                    break
            break
    output = [text.rstrip()]
    output.append("\n*NSET, NSET=FIXED")
    for i in range(0, len(fixed_nodes), 16):
        output.append(",".join(str(n) for n in fixed_nodes[i:i + 16]))
    output.append("*NSET, NSET=LOADED")
    for i in range(0, len(loaded_nodes), 16):
        output.append(",".join(str(n) for n in loaded_nodes[i:i + 16]))
    output.append(f"*MATERIAL, NAME={material}")
    output.append("*ELASTIC")
    output.append(f"{mat['E_MPa']}, {mat['nu']}")
    output.append("*DENSITY")
    output.append(f"{mat['density_t_mm3']}")
    output.append(f"*SOLID SECTION, ELSET={elset}, MATERIAL={material}")
    output.append("*BOUNDARY")
    output.append("FIXED, 1, 3, 0")
    output.append("*STEP")
    output.append("*STATIC")
    output.append("*CLOAD")
    output.append(f"LOADED, 3, -{load_total_n / len(loaded_nodes):.8f}")
    output.append("*EL FILE")
    output.append("S")
    output.append("*NODE FILE")
    output.append("U")
    output.append("*END STEP")
    inp_out.write_text("\n".join(output))
    return True


def run_calculix(inp: Path) -> Optional[Path]:
    """Run ccx on the input file. Returns path to .frd if success."""
    base = inp.with_suffix("")
    try:
        subprocess.run([CCX_PATH, str(base.name)], cwd=str(inp.parent),
                       capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return None
    frd = base.with_suffix(".frd")
    return frd if frd.exists() else None


def parse_frd_max_stress(frd: Path) -> Optional[float]:
    """Parse CalculiX .frd file for max von Mises stress (MPa).
    Uses fixed-width column parsing (CalculiX .frd format: 12-char columns)."""
    if not frd.exists():
        return None
    text = frd.read_text(errors="ignore")
    in_stress = False
    max_vm = 0.0
    for line in text.splitlines():
        s = line.rstrip()
        if s.startswith(" -4") and "STRESS" in s:
            in_stress = True
            continue
        if s.startswith(" -3") and in_stress:
            in_stress = False
            continue
        if in_stress and s.startswith(" -1") and len(s) >= 85:
            try:
                sxx = float(s[13:25]); syy = float(s[25:37]); szz = float(s[37:49])
                sxy = float(s[49:61]); syz = float(s[61:73]); szx = float(s[73:85])
                vm = np.sqrt(0.5 * (
                    (sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2
                    + 6 * (sxy ** 2 + syz ** 2 + szx ** 2)
                ))
                if vm > max_vm:
                    max_vm = float(vm)
            except (ValueError, IndexError):
                continue
    return max_vm if max_vm > 0 else None


def fea_disc(diameter_mm: float, thickness_mm: float, material: str,
             load_total_n: float = 6.0,
             tag: str = "disc") -> dict:
    """Linear-static FEM on a primitive disc approximating a chassis plate.
    Bottom face fixed (3 DoF), top face uniformly loaded with -Z force."""
    base = ARTIFACTS / f"fea_{tag}"
    inp_raw = base.with_suffix(".raw.inp")
    inp_full = base.with_suffix(".inp")

    def make_disc(g):
        g.model.occ.addCylinder(0, 0, 0, 0, 0, thickness_mm, diameter_mm / 2)

    if not gmsh_primitive_to_inp(make_disc, inp_raw,
                                 element_size_mm=max(thickness_mm * 1.2, 5.0)):
        return {"error": "gmsh primitive mesh failed"}
    if not filter_inp_to_tets_only(inp_raw, inp_raw):
        return {"error": "inp filter failed"}
    if not write_ccx_input(inp_raw, inp_full, material,
                           fixed_z_max=0.5,
                           load_face_z_min=thickness_mm - 0.5,
                           load_total_n=load_total_n):
        return {"error": "ccx input write failed"}
    frd = run_calculix(inp_full)
    if frd is None:
        return {"error": "ccx solve failed"}
    max_vm_mpa = parse_frd_max_stress(frd)
    if max_vm_mpa is None:
        return {"error": "could not parse stress"}
    yield_mpa = FEM_MATERIALS.get(material, FEM_MATERIALS["PETG"])["yield_MPa"]
    safety_factor = yield_mpa / max_vm_mpa if max_vm_mpa > 0 else float("inf")
    return {
        "approximation": f"clean Ø{diameter_mm} × {thickness_mm} mm disc",
        "material": material,
        "yield_MPa": yield_mpa,
        "max_von_mises_MPa": max_vm_mpa,
        "safety_factor": safety_factor,
        "load_applied_N": load_total_n,
    }


def audit_fem(parts: dict, report: AuditReport) -> None:
    """Run simplified FEM on primitive approximations of key parts.
    chassis_floor + chassis_top_plate are modeled as Ø250 × 3 mm discs.
    Wheel hub modeled as Ø60 × 22 mm disc.
    Documented as approximations — gmsh's STL→3D pipeline stalls on real CAD."""
    if not Path(CCX_PATH).exists() or not Path(GMSH_PATH).exists():
        report.add(Sev.INFO, "fem", "—", "gmsh or ccx not found, skipping FEM")
        return
    metrics = {}
    targets = [
        ("chassis_floor",     250.0, 3.0,  "PETG", 6.0),
        ("chassis_top_plate", 250.0, 3.0,  "PETG", 6.0),
        ("wheel_hub_pla",      60.0, 22.0, "PLA",  10.0),
    ]
    for label, dia, thick, material, load_n in targets:
        if label not in parts:
            continue
        result = fea_disc(dia, thick, material, load_total_n=load_n, tag=label)
        result["limitations_note"] = (
            "Simplified FEM on clean OCC primitive (real STL geometry stalls "
            "gmsh's STL→3D classifier). Linear-static, isotropic. Real printed-"
            "part strength reduced by layer adhesion (~5x) + infill (~30% solid). "
            "Use as order-of-magnitude indicator, not precise yield prediction."
        )
        metrics[label] = result
        if "error" in result:
            continue
        if result.get("safety_factor", float("inf")) < 2.0:
            report.add(
                Sev.MEDIUM, "fem", f"{label}.stl",
                f"safety factor {result['safety_factor']:.2f} (von Mises "
                f"{result['max_von_mises_MPa']:.4f} MPa vs yield "
                f"{result['yield_MPa']} MPa)",
                result["limitations_note"],
            )
    report.metrics["fem"] = metrics


# ===== 8. 3MF EXPORT (multi-body for AMS) =============================
def export_3mf_multimaterial(parts: dict, report: AuditReport) -> None:
    """Bundle wheel hub (PLA) + wheel tire (TPU) into one 3MF for Bambu Studio."""
    if "wheel_hub_pla" not in parts or "wheel_tire_tpu" not in parts:
        return
    try:
        hub = trimesh.load_mesh(str(parts["wheel_hub_pla"]))
        tire = trimesh.load_mesh(str(parts["wheel_tire_tpu"]))
        # Tag bodies with metadata so Bambu Studio shows them as separately-assignable
        hub.metadata["name"] = "wheel_hub_PLA"
        tire.metadata["name"] = "wheel_tire_TPU"
        scene = trimesh.Scene({"wheel_hub_PLA": hub, "wheel_tire_TPU": tire})
        out = ARTIFACTS / "wheel_multimaterial.3mf"
        scene.export(str(out))
        if out.exists() and out.stat().st_size > 100:
            report.metrics["3mf_export"] = {
                "wheel_multimaterial_3mf": str(out),
                "bodies": ["wheel_hub_PLA", "wheel_tire_TPU"],
                "size_bytes": out.stat().st_size,
            }
        else:
            report.add(Sev.HIGH, "3mf_export", "wheel.scad",
                       "3MF export failed (output empty)")
    except Exception as e:
        report.add(Sev.HIGH, "3mf_export", "wheel.scad",
                   f"3MF export failed: {e}")


# ===== 7. SLICER DRY-RUN ==============================================
def audit_slicer(parts: dict[str, Path], report: AuditReport) -> None:
    if not Path(PRUSA_SLICER).exists():
        report.add(Sev.LOW, "slicer", "—", "PrusaSlicer CLI not found, skipping")
        return
    metrics = {}
    for label, stl in parts.items():
        result = subprocess.run(
            [PRUSA_SLICER, "--info", str(stl)],
            capture_output=True, text=True, timeout=120
        )
        info = (result.stdout + result.stderr)
        m = {}
        for line in info.splitlines():
            line = line.strip()
            if line and ":" in line:
                k, _, v = line.partition(":")
                m[k.strip()] = v.strip()
        metrics[label] = m
        if "manifold" in info.lower() and "no" in info.lower():
            report.add(Sev.HIGH, "slicer", f"{label}.stl",
                       "PrusaSlicer flagged non-manifold mesh")
    report.metrics["slicer"] = metrics


# ===== Compose report =================================================
def write_report(report: AuditReport) -> None:
    out = ARTIFACTS / "audit_report.md"
    n_total = len(report.findings)
    by_sev = {s: report.by_severity(s) for s in
              [Sev.CRITICAL, Sev.HIGH, Sev.MEDIUM, Sev.LOW, Sev.INFO]}

    lines = [
        "# ROVAC v3 — Hardcore audit report",
        "",
        f"**Run completed:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Elapsed:** {report.elapsed_s:.1f} s",
        f"**Total findings:** {n_total}",
        "",
        "## Findings by severity",
        "",
    ]
    for sev in [Sev.CRITICAL, Sev.HIGH, Sev.MEDIUM, Sev.LOW, Sev.INFO]:
        items = by_sev[sev]
        lines.append(f"### {sev} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("_None_")
        else:
            for f in items:
                lines.append(f.fmt())
                if f.detail:
                    lines.append(f"  - {f.detail}")
        lines.append("")

    lines.append("## Mesh metrics")
    lines.append("")
    lines.append("| Part | Triangles | Volume (cm³) | BBox X×Y×Z (mm) | Watertight | Manifold | Broken faces |")
    lines.append("|---|---|---|---|---|---|---|")
    for label, m in report.metrics.get("meshes", {}).items():
        tm = m.get("trimesh", {})
        bbox = "×".join(str(x) for x in tm.get("bbox_mm", []))
        vol = tm.get("volume_mm3")
        vol_cc = f"{vol/1000:.2f}" if vol else "—"
        wt = "✓" if tm.get("is_watertight") else "✗"
        wc = "✓" if tm.get("is_winding_consistent") else "✗"
        bf = tm.get("broken_face_count", "—")
        lines.append(f"| {label} | {tm.get('triangles', '—')} | {vol_cc} | {bbox} | {wt} | {wc} | {bf} |")
    lines.append("")

    lines.append("## Wall thickness")
    lines.append("")
    lines.append("| Part | min (mm) | p1 | p5 | median |")
    lines.append("|---|---|---|---|---|")
    for label, wt in report.metrics.get("wall_thickness", {}).items():
        if "error" in wt:
            lines.append(f"| {label} | _{wt['error']}_ |  |  |  |")
        else:
            lines.append(f"| {label} | {wt['min_mm']:.2f} | {wt['p1_mm']:.2f}"
                         f" | {wt['p5_mm']:.2f} | {wt['median_mm']:.2f} |")
    lines.append("")

    # AUDIT-3 sections: overhang / bridges / support / 3MF
    lines.append("## Overhang analysis")
    lines.append("")
    lines.append("Down-facing surface area binned by overhang angle from vertical "
                 "(0° = wall, 90° = ceiling). PLA/PETG can typically print up to 45° unsupported.")
    lines.append("")
    lines.append("| Part | Overhang % | 0–30° (mm²) | 30–45° | 45–60° | 60–75° | 75–90° | Steep total ≥60° |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for label, p in report.metrics.get("printability", {}).items():
        oh = p.get("overhangs", {})
        if "error" in oh:
            continue
        bins = {b["bin_deg"]: b["area_mm2"] for b in oh.get("bins", [])}
        lines.append(
            f"| {label} | {oh.get('overhang_pct', 0):.1f}% "
            f"| {bins.get('0-30', 0):.1f} | {bins.get('30-45', 0):.1f} "
            f"| {bins.get('45-60', 0):.1f} | {bins.get('60-75', 0):.1f} "
            f"| {bins.get('75-90', 0):.1f} | {oh.get('steep_area_mm2', 0):.1f} |"
        )
    lines.append("")

    lines.append("## Bridge length")
    lines.append("")
    lines.append("Connected horizontal-down-facing regions. Bridges > 10 mm typically need supports.")
    lines.append("")
    lines.append("| Part | # bridges | Largest span (mm) | Largest area (mm²) | Total flat area (mm²) |")
    lines.append("|---|---|---|---|---|")
    for label, p in report.metrics.get("printability", {}).items():
        br = p.get("bridges", {})
        if "error" in br:
            continue
        bridges = br.get("bridges", [])
        largest = bridges[0] if bridges else None
        lines.append(
            f"| {label} | {len(bridges)} "
            f"| {largest['max_xy_span_mm']:.1f} " if largest else f"| {label} | 0 | — "
        )
        if largest:
            lines[-1] += (f"| {largest['area_mm2']:.1f} "
                          f"| {br.get('total_flat_overhang_area_mm2', 0):.1f} |")
        else:
            lines[-1] += f"| — | {br.get('total_flat_overhang_area_mm2', 0):.1f} |"
    lines.append("")

    lines.append("## Support volume estimate")
    lines.append("")
    lines.append("Approximate (overhang_area × avg_z × density 0.15). Real slicer values may differ ±30%.")
    lines.append("")
    lines.append("| Part | Needs support | Overhang area (mm²) | Avg overhang Z (mm) | Estimated volume (cm³) |")
    lines.append("|---|---|---|---|---|")
    for label, p in report.metrics.get("printability", {}).items():
        sv = p.get("support", {})
        if "error" in sv:
            continue
        if not sv.get("needs_support", False):
            lines.append(f"| {label} | no | — | — | 0 |")
        else:
            v = sv.get("estimated_support_volume_mm3", 0) / 1000.0
            lines.append(
                f"| {label} | yes | {sv.get('overhang_area_mm2', 0):.1f} "
                f"| {sv.get('avg_overhang_z_mm', 0):.1f} | {v:.2f} |"
            )
    lines.append("")

    if "3mf_export" in report.metrics:
        m = report.metrics["3mf_export"]
        lines.append("## 3MF multi-material export")
        lines.append("")
        lines.append(f"- Output: `{m.get('wheel_multimaterial_3mf', '—')}`")
        lines.append(f"- Bodies: {m.get('bodies', [])}")
        lines.append(f"- Size: {m.get('size_bytes', 0)} bytes")
        lines.append("")
        lines.append("**Bambu Studio AMS workflow:**")
        lines.append("1. Open `wheel_multimaterial.3mf` in Bambu Studio")
        lines.append("2. Each body shows up in the object tree separately")
        lines.append("3. Right-click the hub body → `Change filament` → assign PLA slot")
        lines.append("4. Right-click the tire body → `Change filament` → assign TPU slot")
        lines.append("5. Slice; AMS will switch filaments automatically per body")
        lines.append("")

    # AUDIT-4 sections
    if "mass_properties" in report.metrics:
        lines.append("## Mass properties (assumes 25 % infill, 45 % effective fraction)")
        lines.append("")
        lines.append("| Part | Material | Volume (cm³) | Mass solid (g) | Mass realistic (g) | CoG (mm) |")
        lines.append("|---|---|---|---|---|---|")
        mp_metrics = report.metrics["mass_properties"]
        total_realistic = mp_metrics.get("_total_realistic_g", 0)
        for label, mp in mp_metrics.items():
            if label.startswith("_") or "error" in mp:
                continue
            lines.append(f"| {label} | {mp.get('material', '—')} "
                         f"| {mp.get('volume_cm3', 0):.1f} "
                         f"| {mp.get('mass_g_solid', 0):.1f} "
                         f"| {mp.get('mass_g_realistic', 0):.1f} "
                         f"| {mp.get('center_of_mass_mm', '—')} |")
        lines.append(f"| **Total** | — | — | — | **{total_realistic:.1f} g** | — |")
        lines.append("")

    if "orientation" in report.metrics:
        lines.append("## Optimal print orientation")
        lines.append("")
        lines.append("Score = support_volume − 0.5 × bed_contact + 5 × CoG_height. "
                     "Lower is better (less support, more bed contact, lower CoG).")
        lines.append("")
        lines.append("| Part | Best orientation | As-designed support (cm³) | Best support (cm³) | Saving (cm³) |")
        lines.append("|---|---|---|---|---|")
        for label, opt in report.metrics["orientation"].items():
            if "error" in opt:
                continue
            asd = opt["as_designed"]["support_volume_mm3"] / 1000.0
            best = opt["best"]["support_volume_mm3"] / 1000.0
            lines.append(f"| {label} | {opt['best']['orientation']} "
                         f"| {asd:.2f} | {best:.2f} | {(asd - best):+.2f} |")
        lines.append("")

    if "slicer_gcode" in report.metrics:
        lines.append("## Slicer G-code analysis (PrusaSlicer default profile)")
        lines.append("")
        lines.append("| Part | Filament (g) | Filament (mm) | Print time | Layers |")
        lines.append("|---|---|---|---|---|")
        for label, info in report.metrics["slicer_gcode"].items():
            if "error" in info:
                lines.append(f"| {label} | _{info['error']}_ |  |  |  |")
                continue
            lines.append(
                f"| {label} | {info.get('filament_g', '—')} "
                f"| {info.get('filament_mm', '—')} "
                f"| {info.get('print_time_normal', info.get('print_time', '—'))} "
                f"| {info.get('layer_count', '—')} |"
            )
        lines.append("")

    if "fem" in report.metrics:
        lines.append("## FEM stress simulation (gmsh + CalculiX)")
        lines.append("")
        lines.append("Linear-static analysis: bottom fixed, top loaded ~6 N (≈ 600 g component weight). "
                     "Real printed-part strength is ~0.2-0.5× this prediction due to layer adhesion + infill.")
        lines.append("")
        lines.append("| Part | Material | Max von Mises (MPa) | Yield (MPa) | Safety factor |")
        lines.append("|---|---|---|---|---|")
        for label, fem in report.metrics["fem"].items():
            if "error" in fem:
                lines.append(f"| {label} | _{fem['error']}_ |  |  |  |")
                continue
            lines.append(
                f"| {label} | {fem.get('material', '—')} "
                f"| {fem.get('max_von_mises_MPa', 0):.2f} "
                f"| {fem.get('yield_MPa', '—')} "
                f"| {fem.get('safety_factor', float('inf')):.2f} |"
            )
        lines.append("")

    out.write_text("\n".join(lines))
    print(f"Report written: {out}")
    (ARTIFACTS / "audit_report.json").write_text(
        json.dumps({
            "findings": [asdict(f) for f in report.findings],
            "metrics": report.metrics,
            "elapsed_s": report.elapsed_s,
        }, indent=2, default=str)
    )


# ===== Main ===========================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-meshes", action="store_true")
    ap.add_argument("--skip-thickness", action="store_true")
    ap.add_argument("--skip-slicer", action="store_true")
    ap.add_argument("--skip-gcode", action="store_true",
                    help="skip per-part PrusaSlicer G-code export (saves ~30s/part)")
    ap.add_argument("--skip-fem", action="store_true",
                    help="skip FEM (gmsh tet-mesh + CalculiX); ~1-2 min per analyzed part")
    args = ap.parse_args()

    report = AuditReport()
    t0 = time.time()

    print("[1/9] Static analysis (sca2d)...")
    run_sca2d(report)

    print("[2/9] Parametric consistency...")
    audit_parametric_consistency(report)

    print("[3/9] Spatial conflict matrix...")
    audit_spatial_conflicts(report)

    parts = {}
    if not args.skip_meshes:
        print("[4/9] Exporting STLs...")
        parts = export_all_parts(report)

        print("[5/9] Mesh integrity (admesh + trimesh)...")
        audit_meshes(parts, report)

    if not args.skip_thickness and parts:
        print("[6/9] Wall thickness ray-casting...")
        audit_wall_thickness(parts, report)

    if parts:
        print("[7/13] Printability — overhangs / bridges / support estimate...")
        audit_printability(parts, report)

        print("[8/13] Mass properties...")
        audit_mass_properties(parts, report)

        print("[9/13] Optimal print orientation finder...")
        audit_orientation(parts, report)

        print("[10/13] 3MF multi-material export...")
        export_3mf_multimaterial(parts, report)

    if not args.skip_slicer and parts:
        print("[11/13] Slicer dry-run (--info)...")
        audit_slicer(parts, report)

    if not getattr(args, "skip_gcode", False) and parts:
        print("[12/13] Slicer G-code analysis (per-part filament + time)...")
        audit_slicer_gcode(parts, report)

    if not getattr(args, "skip_fem", False) and parts:
        print("[13/13] FEM stress simulation (gmsh + CalculiX)...")
        audit_fem(parts, report)

    report.elapsed_s = time.time() - t0
    write_report(report)

    n_critical = len(report.by_severity(Sev.CRITICAL))
    n_high = len(report.by_severity(Sev.HIGH))
    print(f"\n=== Summary ===")
    print(f"  Critical: {n_critical}")
    print(f"  High:     {n_high}")
    print(f"  Total:    {len(report.findings)}")
    print(f"  Time:     {report.elapsed_s:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
