"""In-memory benchmark runner for the backend solver."""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parsers.csv_parser import load_case
from scoring.scorer import compute_score
from solver.hybrid import HybridSolver
from validation.validator import validate_solution


def main(argv: list[str]) -> int:
    cases_root = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "testcases")
    cases_root = os.path.abspath(cases_root)
    for case_name in sorted(os.listdir(cases_root)):
        case_dir = os.path.join(cases_root, case_name)
        if not os.path.isdir(case_dir):
            continue
        case = load_case(case_dir)
        solver = HybridSolver()
        t0 = time.perf_counter()
        solution = solver.solve(case)
        elapsed = time.perf_counter() - t0
        result = validate_solution(solution, case)
        bt_map = case.bay_type_map
        total_area = sum(bt_map[p.bay_type_id].area for p in solution.placements)
        coverage = total_area / case.warehouse.area if case.warehouse.area else 0.0
        summary = {
            "case": case_name,
            "solver": "HybridSolver",
            "valid": result.is_valid,
            "violations": result.violations,
            "q_score": compute_score(solution, case),
            "coverage": coverage,
            "runtime_seconds": round(elapsed, 4),
            "placements": len(solution.placements),
            "type_counts": dict(Counter(p.bay_type_id for p in solution.placements)),
            "rotation_counts": dict(Counter(round(p.rotation, 6) for p in solution.placements)),
        }
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
