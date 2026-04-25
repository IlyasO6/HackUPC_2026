"""
Bridge between API Pydantic models and Backend dataclass models.

The API uses Pydantic models (api/api_models.py) for serialization/validation.
The Backend uses plain dataclasses (backend/models/) for computation.
This module converts between the two so the API can delegate real work
to the backend's solver, scorer, and validator.
"""

import sys
import os

# Add backend to sys.path for backend internal imports
_backend_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# API Pydantic models (renamed to api_models.py to avoid collision)
from api_models import OptimizationInput, PlacedBay as APIPlacedBay, SolveResult

# Backend domain models (from backend/models/ package)
from models.warehouse import Point, Warehouse
from models.obstacle import Obstacle as BackendObstacle
from models.ceiling import CeilingProfile
from models.bay_type import BayType as BackendBayType
from models.case_data import CaseData
from models.solution import PlacedBay as BackendPlacedBay, Solution


# ─── API → Backend conversions ───────────────────────────────────────────────


def to_case_data(input_data: OptimizationInput) -> CaseData:
    """Convert API OptimizationInput (Pydantic) → backend CaseData (dataclass)."""
    warehouse = Warehouse(
        vertices=[Point(x=int(p.x), y=int(p.y)) for p in input_data.warehouse]
    )
    obstacles = [
        BackendObstacle(
            x=int(o.x), y=int(o.y),
            width=int(o.width), depth=int(o.depth),
        )
        for o in input_data.obstacles
    ]
    ceiling = CeilingProfile(
        breakpoints=[(int(c.x), int(c.height)) for c in input_data.ceiling]
    )
    bay_types = [
        BackendBayType(
            id=bt.id,
            width=int(bt.width),
            depth=int(bt.depth),
            height=int(bt.height),
            gap=int(bt.gap),
            n_loads=bt.nLoads,
            price=int(bt.price),
        )
        for bt in input_data.bay_types
    ]
    return CaseData(
        warehouse=warehouse,
        obstacles=obstacles,
        ceiling=ceiling,
        bay_types=bay_types,
    )


def dicts_to_case_data(
    warehouse: list[dict],
    obstacles: list[dict],
    ceiling: list[dict],
    bay_types: list[dict],
) -> CaseData:
    """Convert raw dict lists (from ScoreRequest) → backend CaseData."""
    wh = Warehouse(
        vertices=[Point(x=int(p["x"]), y=int(p["y"])) for p in warehouse]
    )
    obs = [
        BackendObstacle(
            x=int(o["x"]), y=int(o["y"]),
            width=int(o["width"]), depth=int(o["depth"]),
        )
        for o in obstacles
    ]
    ceil = CeilingProfile(
        breakpoints=[(int(c["x"]), int(c["height"])) for c in ceiling]
    )
    bts = [
        BackendBayType(
            id=int(bt["id"]),
            width=int(bt["width"]),
            depth=int(bt["depth"]),
            height=int(bt["height"]),
            gap=int(bt["gap"]),
            n_loads=int(bt["nLoads"]),
            price=int(bt["price"]),
        )
        for bt in bay_types
    ]
    return CaseData(warehouse=wh, obstacles=obs, ceiling=ceil, bay_types=bts)


def dicts_to_solution(placed_bays: list[dict]) -> Solution:
    """Convert placed bay dicts → backend Solution."""
    placements = [
        BackendPlacedBay(
            bay_type_id=int(b.get("bay_type_id", b.get("id"))),
            x=float(b["x"]),
            y=float(b["y"]),
            rotation=float(b["rotation"]),
        )
        for b in placed_bays
    ]
    return Solution(placements=placements)


# ─── Backend → API conversions ───────────────────────────────────────────────


def solution_to_api(
    solution: Solution,
    case: CaseData,
    elapsed_ms: int,
) -> SolveResult:
    """Convert backend Solution + CaseData → API SolveResult."""
    from scoring.scorer import compute_score

    q_score = compute_score(solution, case)
    bt_map = case.bay_type_map

    total_area = sum(
        bt_map[p.bay_type_id].width * bt_map[p.bay_type_id].depth
        for p in solution.placements if p.bay_type_id in bt_map
    )
    coverage = total_area / case.warehouse.area if case.warehouse.area else 0.0

    placed = [
        APIPlacedBay(
            id=p.bay_type_id,
            x=p.x,
            y=p.y,
            rotation=p.rotation,
        )
        for p in solution.placements
    ]

    return SolveResult(
        placed_bays=placed,
        Q=round(q_score, 6),
        coverage=round(coverage, 6),
        solved_in_ms=elapsed_ms,
    )
