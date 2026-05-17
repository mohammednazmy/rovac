#!/usr/bin/env python3
# =============================================================================
# fuse_dual_case.py — Properly fuse two RPi NoIR camera cases into one printable STL.
#
# The source case STLs from the design we're using have known mesh defects
# (non-manifold edges, duplicate faces, degenerate triangles). A naive Boolean
# union compounds these problems. This script:
#
#   1. REPAIR the source STL (dedupe vertices, remove degenerates, fix normals,
#      fill holes) before any boolean op.
#   2. Transform the repaired mesh into LEFT + RIGHT camera positions.
#   3. UNION using trimesh's `manifold` engine (much more robust than Blender's
#      EXACT solver for non-pristine input meshes).
#   4. POST-validate watertightness + non-manifold edge count.
#   5. Export the result.
#
# Usage:
#   python3 fuse_dual_case.py \
#     SOURCE_STL  OUTPUT_STL  --rotation R --translation X Y Z --baseline B
#
# But mostly invoked through main() — see __main__ for the default ROVAC config.
# =============================================================================

import argparse
import sys
from pathlib import Path

import numpy as np
import trimesh
from trimesh import boolean as tb
import pymeshfix


def repair_mesh_pymeshfix(mesh: trimesh.Trimesh, label: str = "mesh") -> trimesh.Trimesh:
    """Use pymeshfix (MeshFix algorithm) to forcibly produce a manifold,
    watertight mesh from a defective input. This is much more aggressive
    than trimesh.repair — it can handle holes, self-intersections,
    non-manifold edges, isolated triangles, and tunnels.

    Returns a NEW trimesh (does not mutate input).
    """
    print(f"  pymeshfix repairing {label} "
          f"(pre: {len(mesh.vertices)}v / {len(mesh.faces)}f, "
          f"watertight={mesh.is_watertight})...",
          file=sys.stderr)

    vfix = pymeshfix.MeshFix(mesh.vertices, mesh.faces)
    vfix.repair(joincomp=True, remove_smallest_components=False)
    fixed = trimesh.Trimesh(vertices=vfix.points, faces=vfix.faces, process=True)

    print(f"    post: {len(fixed.vertices)}v / {len(fixed.faces)}f, "
          f"watertight={fixed.is_watertight}, volume={fixed.is_volume}",
          file=sys.stderr)
    return fixed


def make_transform(rotation_matrix_3x3: np.ndarray,
                   translation: np.ndarray) -> np.ndarray:
    """Build a 4×4 homogeneous transform from a 3×3 rotation + 3-vector."""
    T = np.eye(4)
    T[:3, :3] = rotation_matrix_3x3
    T[:3, 3] = translation
    return T


def fuse_two(source: Path, output: Path, baseline_mm: float,
             z_position: float, y_position: float = 0.0):
    """Load `source`, repair, position 2× at ±baseline/2, union, validate, export."""
    print(f"\n=== Fusing 2× {source.name} into {output.name} ===", file=sys.stderr)

    # Load + AGGRESSIVELY repair source via pymeshfix
    src = trimesh.load_mesh(str(source), force='mesh')
    src = repair_mesh_pymeshfix(src, source.name)
    if not src.is_volume:
        raise RuntimeError(f"Source mesh {source.name} is not a valid volume after repair")

    # Center the source mesh on origin — many STL files (especially exported
    # from SketchUp / Tinkercad) have huge absolute coordinates from their
    # original model space. We need to normalize before applying our transforms.
    center = (src.bounds[0] + src.bounds[1]) / 2.0
    src.apply_translation(-center)
    print(f"  centered source on origin (bbox now: "
          f"{tuple(round(v, 2) for v in (src.bounds[1] - src.bounds[0]))} mm)",
          file=sys.stderr)

    # Rotation matrix for fins-down, lens-forward orientation:
    #   case-local +X (fin direction) → world -Z (fins point down)
    #   case-local +Y (IR LED span)   → world -X (sideways, flipped for det=+1)
    #   case-local +Z (lens face)     → world +Y (LENS POINTS FORWARD)
    rot_mat = np.array([
        [0, -1, 0],
        [0,  0, 1],
        [-1, 0, 0],
    ])

    # Build transforms for LEFT + RIGHT
    T_left = make_transform(rot_mat, np.array([-baseline_mm/2, y_position, z_position]))
    T_right = make_transform(rot_mat, np.array([+baseline_mm/2, y_position, z_position]))

    left = src.copy(); left.apply_transform(T_left)
    right = src.copy(); right.apply_transform(T_right)

    # UNION using manifold engine (uses the manifold3d C++ library — very robust)
    print(f"  unioning with manifold engine...", file=sys.stderr)
    fused = tb.union([left, right], engine='manifold')

    if not fused.is_volume:
        print(f"  WARNING: fused result is not a valid volume, applying pymeshfix...",
              file=sys.stderr)
        fused = repair_mesh_pymeshfix(fused, "fused")

    # Final validation
    edges_unique = fused.edges_unique
    faces_unique_edges = fused.faces_unique_edges
    edge_face_counts = np.bincount(
        faces_unique_edges.ravel(), minlength=len(edges_unique)
    )
    nm_edges = int(np.sum(edge_face_counts != 2))

    print(f"\n=== FINAL: {output.name} ===", file=sys.stderr)
    print(f"  vertices:                {len(fused.vertices):,}", file=sys.stderr)
    print(f"  faces:                   {len(fused.faces):,}", file=sys.stderr)
    print(f"  volume:                  {fused.volume / 1000:.2f} cm³", file=sys.stderr)
    print(f"  watertight:              {'✓' if fused.is_watertight else '✗'}", file=sys.stderr)
    print(f"  winding consistent:      {'✓' if fused.is_winding_consistent else '✗'}", file=sys.stderr)
    print(f"  valid printable volume:  {'✓' if fused.is_volume else '✗'}", file=sys.stderr)
    print(f"  non-manifold edges:      {'✓ 0' if nm_edges == 0 else f'✗ {nm_edges}'}", file=sys.stderr)

    if nm_edges > 0:
        print(f"\n  🔴 RESULT STILL HAS DEFECTS — manual review needed.", file=sys.stderr)
        sys.exit(1)

    # Export
    fused.export(str(output))
    print(f"  ✓ Exported to {output}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="Properly fuse 2 RPi camera cases into one STL.")
    p.add_argument("source", help="Source case STL (will be loaded 2×)")
    p.add_argument("output", help="Output fused STL path")
    p.add_argument("--baseline", type=float, default=78.0,
                   help="Stereo baseline in mm (center-to-center). Default: 78")
    p.add_argument("--z", type=float, default=56.4,
                   help="World Z translation for the cases. Default: 56.4")
    p.add_argument("--y", type=float, default=0.0,
                   help="World Y translation. Default: 0")
    args = p.parse_args()

    fuse_two(Path(args.source), Path(args.output), args.baseline, args.z, args.y)


if __name__ == "__main__":
    main()
