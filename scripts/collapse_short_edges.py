#!/usr/bin/env python3
# =============================================================================
# collapse_short_edges.py — Eliminate sub-resolution edges from a manifold STL.
#
# Boolean unions (Blender EXACT, OpenSCAD, etc.) often leave near-coincident
# but not perfectly-coincident vertex pairs at intersection curves due to
# floating-point precision. The micro-edges between them (often < 0.01mm) are
# below FDM print resolution — they don't render in the print but do clutter
# the mesh and can confuse slicer path generation.
#
# Strategy:
#   • Iteratively test merge tolerances from conservative (10nm) to aggressive
#     (100µm), each round rebuilding vertex adjacency by quantizing positions.
#   • Track impact on three invariants that MUST be preserved:
#       - non-manifold edge count (must stay 0 if input was 0)
#       - connected component count (must stay 1)
#       - bbox dimensions (must change by < 0.5%)
#   • Pick the most aggressive tolerance that preserves all three invariants
#     AND maximally reduces the sub-resolution edge count.
#
# This is much safer than voxel remesh (which destroys face structure) or
# aggressive pymeshfix (which deletes faces). We only touch vertex coordinates;
# every face stays intact.
# =============================================================================

import argparse
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


def stats(m: trimesh.Trimesh) -> dict:
    eL = m.edges_unique_length
    return {
        "vertices": len(m.vertices),
        "faces": len(m.faces),
        "nm_edges": nm_edge_count(m),
        "components": len(m.split(only_watertight=False)),
        "watertight": bool(m.is_watertight),
        "bbox": tuple(float(d) for d in (m.bounds[1] - m.bounds[0])),
        "volume": float(m.volume) if m.is_volume else None,
        "sub_res_edges": int(np.sum(eL < 0.1)),
        "sub_nozzle_edges": int(np.sum(eL < 0.4)),
        "edge_count": len(eL),
        "min_edge": float(eL.min()),
        "median_edge": float(np.median(eL)),
    }


def bbox_change_pct(a: tuple, b: tuple) -> float:
    return max(abs((bi - ai) / ai * 100.0) for ai, bi in zip(a, b) if ai != 0)


def select_best_tolerance(src: trimesh.Trimesh,
                          tolerances: list[int],
                          baseline_invariants: dict,
                          max_bbox_change_pct: float = 0.5) -> tuple[int | None, dict | None]:
    """Test each tolerance, return (best_digits, best_stats) where 'best' is the
    most aggressive merge that preserves invariants AND reduces sub_res_edges."""
    best_digits = None
    best_stats = None
    print(f"\n--- Testing merge tolerances ---")
    print(f"{'digits':>6s} {'tol(mm)':>8s} {'sub_res':>8s} {'NM':>4s} "
          f"{'comp':>5s} {'wt':>4s} {'bbox_Δ%':>9s} {'verdict':>10s}")

    for d in tolerances:
        tol_mm = 10 ** (-d)
        test = src.copy()
        test.merge_vertices(digits_vertex=d)
        s = stats(test)

        bbox_d = bbox_change_pct(baseline_invariants["bbox"], s["bbox"])
        invariants_ok = (
            s["nm_edges"] == baseline_invariants["nm_edges"]
            and s["components"] == baseline_invariants["components"]
            and bbox_d < max_bbox_change_pct
        )
        verdict = "✓ accept" if invariants_ok else "✗ reject"
        print(f"{d:>6d} {tol_mm:>8.4f} {s['sub_res_edges']:>8d} "
              f"{s['nm_edges']:>4d} {s['components']:>5d} "
              f"{'✓' if s['watertight'] else '✗':>4s} "
              f"{bbox_d:>8.4f}% {verdict:>10s}")

        # Accept if invariants pass AND we actually reduced sub_res edges
        # (more aggressive than current best)
        if invariants_ok and s["sub_res_edges"] < (
            best_stats["sub_res_edges"] if best_stats else baseline_invariants["sub_res_edges"]
        ):
            best_digits = d
            best_stats = s

    return best_digits, best_stats


def clean(src_path: Path, dst_path: Path,
          tolerances: list[int] = [4, 3, 2, 1]) -> dict:
    print(f"\n=== Loading {src_path.name} ===")
    mesh = trimesh.load(str(src_path), force='mesh')
    assert isinstance(mesh, trimesh.Trimesh), f"expected Trimesh, got {type(mesh)}"

    baseline = stats(mesh)
    print(f"  baseline: {baseline['vertices']:,}v / {baseline['faces']:,}f, "
          f"NM={baseline['nm_edges']}, components={baseline['components']}, "
          f"watertight={baseline['watertight']}")
    print(f"  bbox: {baseline['bbox'][0]:.3f} × {baseline['bbox'][1]:.3f} "
          f"× {baseline['bbox'][2]:.3f} mm")
    print(f"  sub-resolution edges (<0.1mm): {baseline['sub_res_edges']:,}")
    print(f"  sub-nozzle edges (<0.4mm):     {baseline['sub_nozzle_edges']:,}")
    print(f"  min edge: {baseline['min_edge']:.5f}mm, "
          f"median: {baseline['median_edge']:.3f}mm")

    if baseline["nm_edges"] > 0:
        print(f"\n⚠  Input has {baseline['nm_edges']} non-manifold edges. "
              f"This script preserves that count — it does not fix non-manifold issues. "
              f"Run fix_sketchup_stl.py first if needed.")

    best_digits, best_stats = select_best_tolerance(mesh, tolerances, baseline)

    if best_digits is None or best_stats is None:
        print(f"\n  ✗ No safe tolerance found that improves the mesh.")
        print(f"     The source has irreducible sub-resolution edges or merging "
              f"would violate invariants.")
        return {"action": "none", "src": str(src_path), "dst": None}

    # Apply the best tolerance and write
    cleaned = mesh.copy()
    cleaned.merge_vertices(digits_vertex=best_digits)
    cleaned.export(str(dst_path))

    print(f"\n=== Result: best tolerance digits_vertex={best_digits} "
          f"({10**(-best_digits)*1000:.1f} µm) ===")
    print(f"  vertices: {baseline['vertices']:,} → {best_stats['vertices']:,} "
          f"({baseline['vertices'] - best_stats['vertices']:+,})")
    print(f"  faces:    {baseline['faces']:,} → {best_stats['faces']:,}")
    print(f"  NM edges:           {baseline['nm_edges']} → {best_stats['nm_edges']}")
    print(f"  components:         {baseline['components']} → {best_stats['components']}")
    print(f"  sub-res edges:      {baseline['sub_res_edges']:,} → {best_stats['sub_res_edges']:,} "
          f"({100*(1 - best_stats['sub_res_edges']/max(1,baseline['sub_res_edges'])):.1f}% reduction)")
    print(f"  sub-nozzle edges:   {baseline['sub_nozzle_edges']:,} → {best_stats['sub_nozzle_edges']:,}")
    print(f"  min edge length:    {baseline['min_edge']:.5f}mm → {best_stats['min_edge']:.5f}mm")
    print(f"  watertight:         {baseline['watertight']} → {best_stats['watertight']}")
    print(f"  bbox Δ:             {bbox_change_pct(baseline['bbox'], best_stats['bbox']):.4f}%")
    print(f"  ✓ Exported to {dst_path}")

    return {
        "action": "merged",
        "src": str(src_path),
        "dst": str(dst_path),
        "digits_vertex": best_digits,
        "tolerance_mm": 10 ** (-best_digits),
        "baseline": baseline,
        "result": best_stats,
    }


def main():
    p = argparse.ArgumentParser(description="Collapse sub-resolution edges by merging near-coincident vertices.")
    p.add_argument("source", help="Input STL")
    p.add_argument("output", help="Output STL")
    p.add_argument("--tolerances", nargs='+', type=int, default=[4, 3, 2, 1],
                   help="digits_vertex values to test, e.g. 4 3 2 (= 0.0001 to 0.01mm). "
                        "Default: 4 3 2 1")
    p.add_argument("--max-bbox-change", type=float, default=0.5,
                   help="Reject merge if bbox changes by more than this %% (default 0.5)")
    args = p.parse_args()

    clean(Path(args.source), Path(args.output), tolerances=args.tolerances)


if __name__ == "__main__":
    main()
