"""Score a solution using the Q metric.

    Q = (sum(bay_area) / warehouse_area) - (sum(price) / sum(loads))

Higher is better.
"""

from __future__ import annotations

from models.case_data import CaseData
from models.solution import Solution


def compute_score(solution: Solution, case: CaseData) -> float:
    """Compute the Q metric for a given solution.

    Returns 0.0 for an empty solution (avoids division-by-zero).
    """
    if not solution.placements:
        return 0.0

    bt_map = case.bay_type_map
    warehouse_area = case.warehouse.area

    total_bay_area = 0.0
    total_price = 0.0
    total_loads = 0

    for p in solution.placements:
        bt = bt_map.get(p.bay_type_id)
        if bt is None:
            continue
        ew, ed = p.effective_dims(bt.width, bt.depth)
        total_bay_area += ew * ed
        total_price += bt.price
        total_loads += bt.n_loads

    if warehouse_area == 0 or total_loads == 0:
        return 0.0

    area_ratio = total_bay_area / warehouse_area
    cost_ratio = total_price / total_loads

    return area_ratio - cost_ratio
