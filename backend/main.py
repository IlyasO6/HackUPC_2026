"""Mecalux Warehouse Optimizer -- CLI entry point.

Usage:
    python main.py <case_directory> [OPTIONS]

Options:
    --output FILE     Solution CSV path  (default: solution.csv)
    --json   FILE     JSON summary path  (default: none)
    --no-viz          Skip ASCII visualization
    --viz-width  N    ASCII viz width    (default: 100)
    --viz-height N    ASCII viz height   (default: 35)
"""

from __future__ import annotations
import json
import sys
import os
import time

# Ensure backend package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.csv_parser import load_case
from solver.greedy import GreedySolver
from validation.validator import validate_solution
from scoring.scorer import compute_score
from visualization import render_ascii


def _parse_args(argv: list[str]) -> dict:
    args = {
        "case_dir": None,
        "output": "solution.csv",
        "json_path": None,
        "viz": True,
        "viz_width": 100,
        "viz_height": 35,
    }
    positional = []
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--output" and i + 1 < len(argv):
            args["output"] = argv[i + 1]; i += 2
        elif a == "--json" and i + 1 < len(argv):
            args["json_path"] = argv[i + 1]; i += 2
        elif a == "--no-viz":
            args["viz"] = False; i += 1
        elif a == "--viz-width" and i + 1 < len(argv):
            args["viz_width"] = int(argv[i + 1]); i += 2
        elif a == "--viz-height" and i + 1 < len(argv):
            args["viz_height"] = int(argv[i + 1]); i += 2
        else:
            positional.append(a); i += 1
    if positional:
        args["case_dir"] = positional[0]
    return args


def main() -> None:
    args = _parse_args(sys.argv)

    if not args["case_dir"]:
        print(__doc__)
        sys.exit(1)

    case_dir = args["case_dir"]

    # ── 1. Load ───────────────────────────────────────────────────
    print(f"[1/4] Loading case from {case_dir} ...")
    case = load_case(case_dir)
    print(f"      Warehouse: {len(case.warehouse.vertices)} vertices, "
          f"area = {case.warehouse.area:,.0f} mm2")
    print(f"      Obstacles: {len(case.obstacles)}")
    print(f"      Ceiling  : {len(case.ceiling.breakpoints)} breakpoints")
    print(f"      Bay types: {len(case.bay_types)}")
    for bt in case.bay_types:
        print(f"        id={bt.id:>2}  {bt.width:>4}x{bt.depth:>4}x{bt.height:>4}  "
              f"gap={bt.gap:>3}  loads={bt.n_loads:>2}  price={bt.price:>5}  "
              f"P/L={bt.price/bt.n_loads:>7.1f}")

    # ── 2. Solve ──────────────────────────────────────────────────
    print("\n[2/4] Solving (greedy row-packing) ...")
    t0 = time.perf_counter()
    solver = GreedySolver()
    solution = solver.solve(case)
    elapsed = time.perf_counter() - t0
    print(f"      Placed {len(solution.placements)} bays in {elapsed:.3f}s")

    # ── 3. Validate ───────────────────────────────────────────────
    print("\n[3/4] Validating ...")
    result = validate_solution(solution, case)
    if result.is_valid:
        print("      PASS -- all constraints satisfied")
    else:
        print(f"      FAIL -- {len(result.violations)} violation(s):")
        for v in result.violations[:20]:
            print(f"        - {v}")
        if len(result.violations) > 20:
            print(f"        ... and {len(result.violations) - 20} more")

    # ── 4. Score ──────────────────────────────────────────────────
    score = compute_score(solution, case)
    bt_map = case.bay_type_map
    total_area = sum(
        bt_map[p.bay_type_id].width * bt_map[p.bay_type_id].depth
        for p in solution.placements if p.bay_type_id in bt_map
    )
    total_price = sum(bt_map[p.bay_type_id].price for p in solution.placements if p.bay_type_id in bt_map)
    total_loads = sum(bt_map[p.bay_type_id].n_loads for p in solution.placements if p.bay_type_id in bt_map)
    coverage = total_area / case.warehouse.area if case.warehouse.area else 0

    print(f"\n[4/4] Results (lower Q = better):")
    print(f"      Q Score     : {score:.4f}")
    print(f"      Coverage    : {coverage:.2%}")
    print(f"      Total area  : {total_area:,.0f} mm2 / {case.warehouse.area:,.0f} mm2")
    print(f"      Total price : {total_price:,}")
    print(f"      Total loads : {total_loads:,}")
    if total_loads:
        print(f"      Avg P/L     : {total_price/total_loads:.1f}")
    print(f"      Bays placed : {len(solution.placements)}")

    # Bay type breakdown
    from collections import Counter
    type_counts = Counter(p.bay_type_id for p in solution.placements)
    if type_counts:
        print(f"      Breakdown   :")
        for tid, cnt in sorted(type_counts.items()):
            bt = bt_map.get(tid)
            label = f"{bt.width}x{bt.depth}" if bt else "?"
            print(f"        type {tid:>2} ({label:>9}): {cnt:>4} bays")

    # ── Output CSV ────────────────────────────────────────────────
    solution.to_csv(args["output"])
    print(f"\n      Solution CSV: {args['output']}")

    # ── Optional JSON summary ─────────────────────────────────────
    if args["json_path"]:
        summary = {
            "case": case_dir,
            "score": score,
            "valid": result.is_valid,
            "violations": result.violations,
            "elapsed_seconds": round(elapsed, 4),
            "num_bays": len(solution.placements),
            "coverage": round(coverage, 6),
            "total_area": total_area,
            "warehouse_area": case.warehouse.area,
            "total_price": total_price,
            "total_loads": total_loads,
            "type_counts": dict(type_counts),
            "placements": [
                {"id": p.bay_type_id, "x": p.x, "y": p.y, "rotation": p.rotation}
                for p in solution.placements
            ],
        }
        with open(args["json_path"], "w") as f:
            json.dump(summary, f, indent=2)
        print(f"      JSON summary: {args['json_path']}")

    # ── ASCII visualization ───────────────────────────────────────
    if args["viz"]:
        print("\n" + render_ascii(
            case, solution,
            width=args["viz_width"],
            height=args["viz_height"],
        ))


if __name__ == "__main__":
    main()
