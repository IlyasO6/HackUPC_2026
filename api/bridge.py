"""Conversions between API models and backend dataclass models."""

from __future__ import annotations

import os
import sys

from api_models import OptimizationInput, PlacedBay as ApiPlacedBay, SolveResult
from api_config import ANGLE_STEP_DEGREES, FULL_TURN_DEGREES

_BACKEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.bay_type import BayType as BackendBayType
from models.case_data import CaseData
from models.ceiling import CeilingProfile
from models.obstacle import Obstacle as BackendObstacle
from models.solution import PlacedBay as BackendPlacedBay, Solution
from models.warehouse import Point, Warehouse


def snap_rotation(angle: float) -> float:
    """Snap ``angle`` to the nearest valid 30-degree rotation."""

    snapped = round(float(angle) / ANGLE_STEP_DEGREES) * ANGLE_STEP_DEGREES
    snapped %= FULL_TURN_DEGREES
    if abs(snapped - FULL_TURN_DEGREES) < 1e-9:
        snapped = 0.0
    if abs(snapped) < 1e-9:
        return 0.0
    return round(snapped, 6)


def to_case_data(input_data: OptimizationInput) -> CaseData:
    """Convert ``OptimizationInput`` into backend ``CaseData``."""

    return dicts_to_case_data(
        warehouse=[point.model_dump() for point in input_data.warehouse],
        obstacles=[obstacle.model_dump() for obstacle in input_data.obstacles],
        ceiling=[point.model_dump() for point in input_data.ceiling],
        bay_types=[bay_type.model_dump() for bay_type in input_data.bay_types],
    )


def dicts_to_case_data(
    warehouse: list[dict],
    obstacles: list[dict],
    ceiling: list[dict],
    bay_types: list[dict],
) -> CaseData:
    """Convert primitive dictionaries into backend ``CaseData``."""

    backend_warehouse = Warehouse(
        vertices=[
            Point(x=int(point["x"]), y=int(point["y"]))
            for point in warehouse
        ]
    )
    backend_obstacles = [
        BackendObstacle(
            x=int(obstacle["x"]),
            y=int(obstacle["y"]),
            width=int(obstacle["width"]),
            depth=int(obstacle["depth"]),
        )
        for obstacle in obstacles
    ]
    backend_ceiling = CeilingProfile(
        breakpoints=[
            (int(point["x"]), int(point["height"]))
            for point in ceiling
        ]
    )
    backend_bay_types = [
        BackendBayType(
            id=int(bay_type["id"]),
            width=int(bay_type["width"]),
            depth=int(bay_type["depth"]),
            height=int(bay_type["height"]),
            gap=int(bay_type["gap"]),
            n_loads=int(bay_type["nLoads"]),
            price=int(bay_type["price"]),
        )
        for bay_type in bay_types
    ]
    return CaseData(
        warehouse=backend_warehouse,
        obstacles=backend_obstacles,
        ceiling=backend_ceiling,
        bay_types=backend_bay_types,
    )


def dicts_to_solution(placed_bays: list[dict]) -> Solution:
    """Convert primitive bay dictionaries into backend ``Solution``."""

    placements = [
        BackendPlacedBay(
            bay_type_id=int(bay.get("bay_type_id", bay.get("id"))),
            x=float(bay["x"]),
            y=float(bay["y"]),
            rotation=snap_rotation(float(bay["rotation"])),
        )
        for bay in placed_bays
    ]
    return Solution(placements=placements)


def solution_to_api(
    solution: Solution,
    case: CaseData,
    elapsed_ms: int,
) -> SolveResult:
    """Convert a backend ``Solution`` into the legacy API response."""

    from scoring.scorer import compute_score

    q_score = compute_score(solution, case)
    bay_type_map = case.bay_type_map
    total_area = sum(
        bay_type_map[placement.bay_type_id].width
        * bay_type_map[placement.bay_type_id].depth
        for placement in solution.placements
        if placement.bay_type_id in bay_type_map
    )
    coverage = total_area / case.warehouse.area if case.warehouse.area else 0.0
    placed_bays = [
        ApiPlacedBay(
            id=placement.bay_type_id,
            x=placement.x,
            y=placement.y,
            rotation=snap_rotation(placement.rotation),
        )
        for placement in solution.placements
    ]
    return SolveResult(
        placed_bays=placed_bays,
        Q=round(q_score, 6),
        coverage=round(coverage, 6),
        solved_in_ms=elapsed_ms,
    )
