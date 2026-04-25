"""
Scorer for the Mecalux warehouse optimization challenge.

Delegates to the real backend scoring and validation modules
instead of reimplementing the formulas.

This module is designed to be FAST — called on every interactive edit
from the frontend for real-time scoring feedback.
"""

import sys
import os

# Ensure backend is on sys.path (same as bridge.py does)
_backend_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from bridge import dicts_to_case_data, dicts_to_solution

from scoring.scorer import compute_score as backend_compute_score
from validation.validator import validate_solution as backend_validate_solution


def calculate_score(
    placed_bays: list[dict],
    bay_types: list[dict],
    warehouse: list[dict],
    obstacles: list[dict] = None,
    ceiling: list[dict] = None,
) -> dict:
    """
    Calculate the Q score and related metrics using the real backend formula.

    Q = (sum_prices / sum_loads) ^ (2 - percentage_area_used)

    Lower Q is better.

    Returns:
        {
            "Q": float,
            "coverage": float,
            "num_bays": int,
            "total_loads": int,
            "total_bay_area": float,
            "warehouse_area": float,
            "is_valid": bool,
            "issues": [...]
        }
    """
    obstacles = obstacles or []
    ceiling = ceiling or []

    # Build backend domain objects
    case = dicts_to_case_data(warehouse, obstacles, ceiling, bay_types)
    solution = dicts_to_solution(placed_bays)

    # Compute Q score via backend
    q_score = backend_compute_score(solution, case)

    bt_map = case.bay_type_map
    total_bay_area = 0.0
    total_loads = 0

    for p in solution.placements:
        bt = bt_map.get(p.bay_type_id)
        if not bt:
            continue
        total_bay_area += bt.width * bt.depth
        total_loads += bt.n_loads

    warehouse_area = case.warehouse.area
    coverage = total_bay_area / warehouse_area if warehouse_area > 0 else 0.0

    # Validate placement via backend
    issues = []
    validation_result = backend_validate_solution(solution, case)
    if not validation_result.is_valid:
        for i, violation in enumerate(validation_result.violations):
            issues.append({
                "bay_index": i,
                "issue_type": "constraint_violation",
                "message": violation,
            })

    return {
        "Q": round(q_score, 6) if q_score != float("inf") else None,
        "coverage": round(coverage, 6),
        "num_bays": len(placed_bays),
        "total_loads": total_loads,
        "total_bay_area": total_bay_area,
        "warehouse_area": warehouse_area,
        "is_valid": validation_result.is_valid,
        "issues": issues,
    }


def validate_placement(
    placed_bays: list[dict],
    bay_types: list[dict],
    warehouse: list[dict],
    obstacles: list[dict] = None,
    ceiling: list[dict] = None,
) -> list[dict]:
    """
    Validate a bay placement against all constraints using the real backend validator.
    Returns a list of issues (empty list = valid placement).
    """
    obstacles = obstacles or []
    ceiling = ceiling or []

    case = dicts_to_case_data(warehouse, obstacles, ceiling, bay_types)
    solution = dicts_to_solution(placed_bays)

    validation_result = backend_validate_solution(solution, case)

    issues = []
    for violation in validation_result.violations:
        issues.append({
            "issue_type": "constraint_violation",
            "message": violation,
        })
    return issues
