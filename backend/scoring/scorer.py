"""Score a solution using the corrected Q metric.

    Q = (sum_prices / sum_loads) ^ (2 - percentage_area_used)

Lower Q is better. Minimizing Q means:
  - Minimize price/loads ratio (cost-efficient bays)
  - Maximize area coverage (brings exponent closer to 1)
"""

from __future__ import annotations

from models.case_data import CaseData
from models.solution import Solution


def compute_score(solution: Solution, case: CaseData) -> float:
    """Compute Q metric. Returns float('inf') for empty/invalid solutions."""
    if not solution.placements:
        return float("inf")

    bt_map = case.bay_type_map
    warehouse_area = case.warehouse.area

    total_bay_area = 0.0
    total_price = 0.0
    total_loads = 0

    for p in solution.placements:
        bt = bt_map.get(p.bay_type_id)
        if bt is None:
            continue
        # Use AABB of rotated bay for area (actual footprint area = width*depth regardless of rotation)
        total_bay_area += bt.width * bt.depth
        total_price += bt.price
        total_loads += bt.n_loads

    if warehouse_area == 0 or total_loads == 0:
        return float("inf")

    pct_area = total_bay_area / warehouse_area
    price_per_load = total_price / total_loads
    exponent = 2.0 - pct_area

    return price_per_load ** exponent
