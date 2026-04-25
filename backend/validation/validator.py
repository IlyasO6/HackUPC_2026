"""Solution validator — checks all placement constraints.

Constraints:
  1. Valid bay type ID.
  2. Bay body fully inside warehouse polygon.
  3. No bay body overlaps any obstacle.
  4. No two bay bodies overlap (boundary touch OK).
  5. Bay height fits under ceiling across its X-range.
  6. Gap clearance: each bay's front gap zone has no other bay body inside it.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from models.case_data import CaseData
from models.solution import Solution
from geometry.obb import (
    convex_polygons_overlap,
    rotated_rect_inside_polygon,
)
from geometry.spatial import rects_overlap


@dataclass
class ValidationResult:
    is_valid: bool = True
    violations: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.is_valid = False
        self.violations.append(msg)


def validate_solution(solution: Solution, case: CaseData) -> ValidationResult:
    result = ValidationResult()
    bt_map = case.bay_type_map
    poly = case.warehouse.vertex_tuples

    # Pre-compute corners, gap zones, and AABBs
    bay_corners: list[list[tuple[float, float]]] = []
    bay_gaps: list[list[tuple[float, float]]] = []
    bay_aabbs: list[tuple[float, float, float, float]] = []

    for idx, p in enumerate(solution.placements):
        tag = f"Bay #{idx} (type={p.bay_type_id}, pos=({p.x},{p.y}), rot={p.rotation})"

        # 1. Valid bay type ID
        bt = bt_map.get(p.bay_type_id)
        if bt is None:
            result.fail(f"{tag}: unknown bay type ID")
            bay_corners.append([])
            bay_gaps.append([])
            bay_aabbs.append((0, 0, 0, 0))
            continue

        corners = p.corners(bt.width, bt.depth)
        gap = p.gap_zone(bt.width, bt.depth, bt.gap)
        aabb = p.aabb(bt.width, bt.depth)
        bay_corners.append(corners)
        bay_gaps.append(gap)
        bay_aabbs.append(aabb)

        # 2. Inside warehouse
        if not rotated_rect_inside_polygon(corners, poly):
            result.fail(f"{tag}: extends outside warehouse boundary")

        # 3. No obstacle overlap
        for oi, obs in enumerate(case.obstacles):
            obs_corners = [
                (float(obs.x), float(obs.y)),
                (float(obs.x + obs.width), float(obs.y)),
                (float(obs.x + obs.width), float(obs.y + obs.depth)),
                (float(obs.x), float(obs.y + obs.depth)),
            ]
            if convex_polygons_overlap(corners, obs_corners):
                result.fail(f"{tag}: overlaps obstacle #{oi}")

        # 5. Ceiling height (use AABB X-range)
        x_min_f, _, x_max_f, _ = aabb
        max_h = case.ceiling.min_height_in_range(int(x_min_f), int(x_max_f) + 1)
        if bt.height > max_h:
            result.fail(f"{tag}: height {bt.height} exceeds ceiling {max_h}")

    # 4. No pairwise body overlap
    n = len(solution.placements)
    for i in range(n):
        if not bay_corners[i]:
            continue
        for j in range(i + 1, n):
            if not bay_corners[j]:
                continue
            # Quick AABB rejection
            ai, aj = bay_aabbs[i], bay_aabbs[j]
            if ai[2] <= aj[0] or aj[2] <= ai[0] or ai[3] <= aj[1] or aj[3] <= ai[1]:
                continue
            if convex_polygons_overlap(bay_corners[i], bay_corners[j]):
                result.fail(f"Bay #{i} overlaps Bay #{j}")

    # 6. Gap clearance
    for i in range(n):
        if not bay_gaps[i]:
            continue
        for j in range(n):
            if i == j or not bay_corners[j]:
                continue
            if convex_polygons_overlap(bay_gaps[i], bay_corners[j]):
                result.fail(f"Bay #{i} gap zone violated by Bay #{j}")

    return result
