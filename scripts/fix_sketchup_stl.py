#!/usr/bin/env python3
# =============================================================================
# fix_sketchup_stl.py — Minimal cleanup of SketchUp-exported STLs.
#
# SketchUp Boolean exports leave two systemic defects:
#   1. Phantom mid-air components — tiny (<50 face, sub-mm) coincident-vertex
#      "ghost" triangles outside the main mesh. The slicer prints them in
#      mid-air → spaghetti.
#   2. Main mesh floats above Z=0 because in the source assembly the part
#      was nested with siblings at non-zero heights.
#
# This fixer applies the minimum surgery needed:
#   • Load with default processing (vertex dedup → real adjacency)
#   • Split into connected components
#   • Keep only LARGEST component, drop everything else
#   • Translate so bbox bottom = Z=0, XY centered at origin
#   • Export — NO topology cleanup, NO degenerate/duplicate face removal
#     (those operations damaged the topology in a prior attempt — they turn
#     a clean mesh into one with thousands of non-manifold edges by
#     deleting faces that were essential adjacency partners.)
# =============================================================================

import argparse
import sys
from pathlib import Path

import numpy as np
import trimesh


def nm_edge_count(m: trimesh.Trimesh) -> int:
    if len(m.faces) == 0:
        return 0
    edges_unique = m.edges_unique
    faces_unique_edges = m.faces_unique_edges
    counts = np.bincount(faces_unique_edges.ravel(), minlength=len(edges_unique))
    return int(np.sum(counts != 2))


def fix(src: Path, dst: Path) -> dict:
    mesh = trimesh.load(str(src), force='mesh')
    assert isinstance(mesh, trimesh.Trimesh), f"expected Trimesh, got {type(mesh)}"
    pre_nm = nm_edge_count(mesh)
    components = mesh.split(only_watertight=False)
    pre_comp = len(components)

    main = max(components, key=lambda c: len(c.faces))
    n_dropped_components = len(components) - 1
    n_dropped_faces = len(mesh.faces) - len(main.faces)

    z_min, z_offset = main.bounds[0][2], 0.0
    if z_min != 0.0:
        z_offset = -z_min
    xy_center = (main.bounds[0][:2] + main.bounds[1][:2]) / 2.0
    main.apply_translation([-xy_center[0], -xy_center[1], z_offset])

    post_nm = nm_edge_count(main)
    main.export(str(dst))

    return {
        "src": str(src),
        "dst": str(dst),
        "pre_components": pre_comp,
        "dropped_components": n_dropped_components,
        "dropped_faces": n_dropped_faces,
        "kept_faces": len(main.faces),
        "pre_nm_edges": pre_nm,
        "post_nm_edges": post_nm,
        "z_offset_applied_mm": round(z_offset, 3),
        "xy_centered_by_mm": tuple(round(-c, 3) for c in xy_center),
        "bbox_mm": tuple(round(d, 2) for d in (main.bounds[1] - main.bounds[0])),
    }


def print_report(r: dict) -> None:
    p = lambda k, v: print(f"  {k:30s}{v}")
    print(f"\n=== {Path(r['src']).name} → {Path(r['dst']).name} ===")
    p("components in source:", r['pre_components'])
    p("dropped phantoms:", r['dropped_components'])
    p("dropped phantom faces:", r['dropped_faces'])
    p("kept main mesh faces:", r['kept_faces'])
    p("non-manifold edges (orig):", r['pre_nm_edges'])
    p("non-manifold edges (out):", r['post_nm_edges'])
    p("translated Z by (mm):", r['z_offset_applied_mm'])
    p("translated XY by (mm):", r['xy_centered_by_mm'])
    p("final bbox (mm):", r['bbox_mm'])


def main():
    p = argparse.ArgumentParser(description="Strip phantom components + position to build plate.")
    p.add_argument("source", help="Input STL (single file) OR folder if --batch")
    p.add_argument("output", nargs='?', help="Output STL (omit with --batch)")
    p.add_argument("--batch", action='store_true',
                   help="Process all .stl files in `source` folder, writing *_fixed.stl alongside")
    args = p.parse_args()

    src = Path(args.source)
    if args.batch:
        if not src.is_dir():
            print(f"ERROR: --batch requires a folder, got {src}", file=sys.stderr)
            sys.exit(2)
        stls = sorted(src.glob("*.stl"))
        stls = [s for s in stls if not s.stem.endswith("_fixed")]
        for stl in stls:
            dst = stl.with_name(stl.stem + "_fixed.stl")
            r = fix(stl, dst)
            print_report(r)
    else:
        if not args.output:
            print("ERROR: provide OUTPUT or --batch", file=sys.stderr)
            sys.exit(2)
        r = fix(src, Path(args.output))
        print_report(r)


if __name__ == "__main__":
    main()
