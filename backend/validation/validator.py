"""Solution validator — checks all placement constraints.

Constraints checked:
  1. Every bay type ID references a valid entry.
  2. Every bay rectangle is fully inside the warehouse polygon.
  3. No bay overlaps any obstacle.
  4. No two bays overlap each other (touching boundaries OK).
  5. Every bay's height fits under the ceiling in its X-range.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from models.case_data import CaseData
from models.solution import Solution
from geometry.polygon import rect_inside_polygon
from geometry.spatial import rects_overlap


@dataclass
class ValidationResult:
    """Outcome of validating a solution."""
    is_valid: bool = True
    violations: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.is_valid = False
        self.violations.append(msg)


def validate_solution(solution: Solution, case: CaseData) -> ValidationResult:
    """Validate every constraint and return a result with all violations."""
    result = ValidationResult()
    bt_map = case.bay_type_map
    poly = case.warehouse.vertex_tuples

    # Pre-compute bounds for pairwise overlap check
    bay_bounds: list[tuple[int, int, int, int]] = []

    for idx, p in enumerate(solution.placements):
        tag = f"Bay #{idx} (type={p.bay_type_id}, pos=({p.x},{p.y}), rot={p.rotation})"

        # ── 1. Valid bay type ID ──────────────────────────────────
        bt = bt_map.get(p.bay_type_id)
        if bt is None:
            result.fail(f"{tag}: unknown bay type ID {p.bay_type_id}")
            continue

        # ── Compute footprint ────────────────────────────────────
        ew, ed = p.effective_dims(bt.width, bt.depth)
        bx_min, by_min = p.x, p.y
        bx_max, by_max = p.x + ew, p.y + ed

        # ── 2. Inside warehouse ──────────────────────────────────
        if not rect_inside_polygon(bx_min, by_min, bx_max, by_max, poly):
            result.fail(f"{tag}: extends outside warehouse boundary")

        # ── 3. No obstacle overlap ───────────────────────────────
        for oi, obs in enumerate(case.obstacles):
            ox_min, oy_min, ox_max, oy_max = obs.bounds
            if rects_overlap(bx_min, by_min, bx_max, by_max,
                             ox_min, oy_min, ox_max, oy_max):
                result.fail(f"{tag}: overlaps obstacle #{oi}")

        # ── 5. Ceiling height ────────────────────────────────────
        max_h = case.ceiling.min_height_in_range(bx_min, bx_max)
        if bt.height > max_h:
            result.fail(
                f"{tag}: height {bt.height} exceeds ceiling {max_h} "
                f"in X-range [{bx_min}, {bx_max})"
            )

        bay_bounds.append((bx_min, by_min, bx_max, by_max))

    # ── 4. No pairwise bay overlap ───────────────────────────────
    n = len(bay_bounds)
    for i in range(n):
        for j in range(i + 1, n):
            if rects_overlap(*bay_bounds[i], *bay_bounds[j]):
                result.fail(
                    f"Bay #{i} overlaps Bay #{j}"
                )

    return result
