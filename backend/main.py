"""Mecalux Warehouse Optimizer — CLI entry point.

Usage:
    python main.py <case_directory> [--output solution.csv]

Loads a test case, (future: runs solver), validates, scores, and outputs CSV.
"""

from __future__ import annotations
import sys
import os

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.csv_parser import load_case
from validation.validator import validate_solution
from scoring.scorer import compute_score
from models.solution import Solution


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py <case_directory> [--output solution.csv]")
        sys.exit(1)

    case_dir = sys.argv[1]
    output_path = "solution.csv"
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        output_path = sys.argv[idx + 1]

    # ── Load case ─────────────────────────────────────────────────
    case = load_case(case_dir)

    print(f"=== Case loaded: {case_dir}")
    print(f"  Warehouse vertices : {len(case.warehouse.vertices)}")
    print(f"  Warehouse area     : {case.warehouse.area:,.0f} mm2")
    print(f"  Bounding box       : {case.warehouse.bounding_box}")
    print(f"  Obstacles          : {len(case.obstacles)}")
    print(f"  Ceiling breakpoints: {len(case.ceiling.breakpoints)}")
    print(f"  Bay types          : {len(case.bay_types)}")
    for bt in case.bay_types:
        print(f"    id={bt.id}  {bt.width}x{bt.depth}x{bt.height}mm"
              f"  gap={bt.gap}  loads={bt.n_loads}  price={bt.price}")
    print("===")

    # ── Solve (placeholder — returns empty) ───────────────────────
    solution = Solution(placements=[])
    print(f"\nPlacements: {len(solution.placements)}")

    # ── Validate ──────────────────────────────────────────────────
    result = validate_solution(solution, case)
    status = "PASS" if result.is_valid else "FAIL"
    print(f"Validation: {status}")
    for v in result.violations:
        print(f"  - {v}")

    # ── Score ─────────────────────────────────────────────────────
    score = compute_score(solution, case)
    print(f"Score (Q): {score:.6f}")

    # ── Output ────────────────────────────────────────────────────
    solution.to_csv(output_path)
    print(f"Solution written to {output_path}")


if __name__ == "__main__":
    main()
