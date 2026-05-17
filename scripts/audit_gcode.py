#!/usr/bin/env python3
# =============================================================================
# audit_gcode.py — pre-print sanity audit of a sliced g-code file.
#
# Parses the actual toolpath (not the source STL) and reports the print
# envelope, layer structure, material usage and key slicer settings, then
# flags anomalies that tend to cause failed prints:
#   - non-monotonic or unevenly-spaced layer heights
#   - near-empty layers (a symptom of floating / disconnected geometry)
#   - toolpaths outside the build volume
#   - a missing / truncated end sequence
#
# Auditing the g-code directly means the verdict holds regardless of which
# STL it was sliced from — if the toolpath is sound, the print is sound.
#
# Usage:  python3 audit_gcode.py path/to/file.gcode  [bed_x bed_y]
# =============================================================================

import re
import statistics
import sys
from pathlib import Path

MOVE_RE = re.compile(r'([XYZEF])(-?\d*\.?\d+)')
SETTINGS = ("layer_height", "first_layer_height", "nozzle_temperature",
            "hot_plate_temp", "filament_type", "sparse_infill_density",
            "sparse_infill_pattern", "wall_loops", "enable_support",
            "nozzle_diameter")
HEADER_KEYS = ("model printing time", "total estimated time",
               "total layer number", "total filament weight [g]",
               "max_z_height")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: audit_gcode.py <file.gcode> [bed_x bed_y]")
    path = Path(sys.argv[1])
    if not path.exists():
        sys.exit(f"not found: {path}")
    bed_x = float(sys.argv[2]) if len(sys.argv) > 2 else 256.0
    bed_y = float(sys.argv[3]) if len(sys.argv) > 3 else 256.0

    settings: dict[str, str] = {}
    header: dict[str, str] = {}

    x = y = z = 0.0
    rel_e = True            # Bambu/Orca default to relative extrusion (M83)
    last_e = 0.0
    n_lines = n_ext_moves = 0
    total_e = 0.0
    exmin = [1e9, 1e9, 1e9]
    exmax = [-1e9, -1e9, -1e9]
    layer_z: list[float] = []
    layer_e: list[float] = []
    cur_layer_e = 0.0
    seen_layer = False
    tail: list[str] = []

    with path.open('r', errors='ignore') as fh:
        for line in fh:
            n_lines += 1
            s = line.strip()
            tail.append(s)
            if len(tail) > 600:
                tail.pop(0)
            if not s:
                continue
            if s.startswith(';'):
                m = re.match(r';\s*([a-z_]+)\s*=\s*(.+)', s)
                if m and m.group(1) in SETTINGS and m.group(1) not in settings:
                    settings[m.group(1)] = m.group(2).strip()
                for k in HEADER_KEYS:
                    if k in s and k not in header and ':' in s:
                        header[k] = s.split(':', 1)[1].strip().rstrip(';')
                if 'CHANGE_LAYER' in s:
                    if seen_layer:
                        layer_e.append(cur_layer_e)
                    cur_layer_e = 0.0
                    seen_layer = True
                elif s.startswith('; Z_HEIGHT:'):
                    try:
                        layer_z.append(float(s.split(':', 1)[1]))
                    except ValueError:
                        pass
                continue
            code = s.split()[0].upper()
            if code == 'M83':
                rel_e = True
            elif code == 'M82':
                rel_e = False
            elif code == 'G92':
                for axis, val in MOVE_RE.findall(s):
                    if axis == 'E':
                        last_e = float(val)
            elif code in ('G0', 'G1', 'G2', 'G3'):
                nx, ny, nz, e = x, y, z, None
                for axis, val in MOVE_RE.findall(s.split(';')[0]):
                    v = float(val)
                    if axis == 'X': nx = v
                    elif axis == 'Y': ny = v
                    elif axis == 'Z': nz = v
                    elif axis == 'E': e = v
                extruding = False
                if e is not None:
                    de = e if rel_e else e - last_e
                    if de > 1e-6:
                        extruding = True
                        total_e += de
                        cur_layer_e += de
                    if not rel_e:
                        last_e = e
                if extruding:
                    n_ext_moves += 1
                    for i, (a, b) in enumerate(((nx, x), (ny, y), (nz, z))):
                        exmin[i] = min(exmin[i], a, b)
                        exmax[i] = max(exmax[i], a, b)
                x, y, z = nx, ny, nz
    if seen_layer:
        layer_e.append(cur_layer_e)

    flags: list[str] = []

    print(f"\n=== G-CODE AUDIT: {path.name} ===")
    size_mb = path.stat().st_size / 1e6
    print(f"  file: {size_mb:.1f} MB, {n_lines:,} lines")
    for k in HEADER_KEYS:
        if k in header:
            print(f"  {k:28s} {header[k]}")

    print("\n  --- slicer settings ---")
    for k in SETTINGS:
        if k in settings:
            print(f"  {k:28s} {settings[k]}")

    print("\n  --- toolpath ---")
    print(f"  extruding moves:             {n_ext_moves:,}")
    print(f"  filament extruded (G-code E):{total_e/1000:.2f} m")
    if n_ext_moves:
        print(f"  extrusion envelope X:        [{exmin[0]:.1f}, {exmax[0]:.1f}] mm")
        print(f"  extrusion envelope Y:        [{exmin[1]:.1f}, {exmax[1]:.1f}] mm")
        print(f"  extrusion envelope Z:        [{exmin[2]:.2f}, {exmax[2]:.2f}] mm")
        if exmin[0] < -1 or exmax[0] > bed_x + 1 or exmin[1] < -1 or exmax[1] > bed_y + 1:
            flags.append(f"toolpath leaves the {bed_x:.0f}x{bed_y:.0f}mm bed envelope")

    print("\n  --- layers ---")
    print(f"  CHANGE_LAYER markers:        {len(layer_e)}")
    print(f"  Z_HEIGHT samples:            {len(layer_z)}")
    if len(layer_z) >= 2:
        deltas = [b - a for a, b in zip(layer_z, layer_z[1:])]
        nonmono = sum(1 for d in deltas if d <= 0)
        dmin, dmax = min(deltas), max(deltas)
        med = statistics.median(deltas)
        print(f"  first layer Z:               {layer_z[0]:.3f} mm")
        print(f"  layer-height delta:          min {dmin:.3f}, median {med:.3f}, max {dmax:.3f} mm")
        if nonmono:
            flags.append(f"{nonmono} non-increasing layer step(s) — Z went flat/backwards")
        if dmax > med * 2.5:
            flags.append(f"layer-height jump of {dmax:.2f}mm (median {med:.2f}) — possible gap")
    if layer_e:
        med_e = statistics.median(layer_e) or 1e-9
        empty = [i + 1 for i, le in enumerate(layer_e) if le < med_e * 0.10]
        print(f"  per-layer extrusion:         median {med_e:.1f} mm, "
              f"min {min(layer_e):.1f}, max {max(layer_e):.1f}")
        # the last layer is legitimately light; flag only interior near-empty layers
        interior = [i for i in empty if i not in (1, len(layer_e))]
        if interior:
            flags.append(f"near-empty interior layer(s) {interior[:8]} "
                          f"— possible floating/disconnected geometry")

    end_ok = any(('M104 S0' in t or 'M140 S0' in t or 'END_GCODE' in t) for t in tail)
    print(f"\n  end sequence present:        {'yes' if end_ok else 'NO'}")
    if not end_ok:
        flags.append("no end sequence found in tail — file may be truncated")

    nd = settings.get("nozzle_diameter", "")
    if nd and nd.startswith("0.2"):
        flags.append("sliced for a 0.2mm nozzle — confirm that nozzle is installed; "
                     "for chunky structural parts a 0.4mm nozzle prints ~2x faster "
                     "and bonds layers better")

    print("\n  === VERDICT ===")
    if flags:
        for f in flags:
            print(f"  FLAG: {f}")
    else:
        print("  toolpath is sound — no anomalies detected")
    print()


if __name__ == "__main__":
    main()
