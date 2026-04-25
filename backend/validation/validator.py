"""Solution validator -- checks all placement constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from config import ANGLE_STEP_DEGREES, FULL_TURN_DEGREES
from models.case_data import CaseData
from models.solution import Solution
from solver.layout import PlacementTemplate, build_empty_state
from validation.rules import build_case_context, placement_violations


@dataclass
class ValidationResult:
    is_valid: bool = True
    violations: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.is_valid = False
        self.violations.append(msg)


def _snap_rotation(angle: float) -> float:
    """Snap a rotation to the discrete 30-degree challenge lattice."""

    snapped = round(float(angle) / ANGLE_STEP_DEGREES) * ANGLE_STEP_DEGREES
    snapped %= FULL_TURN_DEGREES
    if math.isclose(snapped, FULL_TURN_DEGREES, abs_tol=1e-9):
        snapped = 0.0
    if math.isclose(snapped, 0.0, abs_tol=1e-9):
        return 0.0
    return round(snapped, 6)


def validate_solution(solution: Solution, case: CaseData) -> ValidationResult:
    result = ValidationResult()
    bt_map = case.bay_type_map
    ctx = build_case_context(case)
    state = build_empty_state(case.warehouse.area, ctx.cell_size)
    template_cache: dict[tuple[int, float], PlacementTemplate] = {}

    for idx, placement in enumerate(solution.placements):
        tag = (
            f"Bay #{idx} (type={placement.bay_type_id}, "
            f"pos=({placement.x},{placement.y}), rot={placement.rotation})"
        )
        bt = bt_map.get(placement.bay_type_id)
        if bt is None:
            result.fail(f"{tag}: unknown bay type ID")
            continue

        snapped_rotation = _snap_rotation(placement.rotation)
        key = (bt.id, snapped_rotation)
        template = template_cache.get(key)
        if template is None:
            template = PlacementTemplate(bt, snapped_rotation)
            template_cache[key] = template

        footprint = template.place(placement.x, placement.y)
        violations = placement_violations(
            footprint,
            ctx,
            state.footprints,
            state=state,
        )
        for violation in violations:
            result.fail(f"{tag}: {violation}")

        if not violations:
            fp_idx = len(state.footprints)
            state.footprints.append(footprint)
            state.body_hash.add(footprint.body_aabb, fp_idx)
            if footprint.gap_aabb is not None:
                state.gap_hash.add(footprint.gap_aabb, fp_idx)

    return result
