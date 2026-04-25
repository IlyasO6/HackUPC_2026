"""CSV ingestion for all 4 input files.

Handles: empty files, trailing whitespace/newlines, spaces around commas.
"""

from __future__ import annotations
import os

from models.warehouse import Point, Warehouse
from models.obstacle import Obstacle
from models.ceiling import CeilingProfile
from models.bay_type import BayType
from models.case_data import CaseData


def _read_lines(path: str) -> list[list[int]]:
    """Read a CSV file and return rows as lists of ints."""
    rows: list[list[int]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [int(x.strip()) for x in line.split(",")]
            rows.append(parts)
    return rows


# ── Individual parsers ────────────────────────────────────────────


def parse_warehouse(path: str) -> Warehouse:
    """Parse WAREHOUSE.CSV → Warehouse polygon."""
    rows = _read_lines(path)
    vertices = [Point(x=r[0], y=r[1]) for r in rows]
    return Warehouse(vertices=vertices)


def parse_obstacles(path: str) -> list[Obstacle]:
    """Parse OBSTACLES.CSV → list of Obstacle rectangles."""
    rows = _read_lines(path)
    return [
        Obstacle(x=r[0], y=r[1], width=r[2], depth=r[3])
        for r in rows
    ]


def parse_ceiling(path: str) -> CeilingProfile:
    """Parse CEILING.CSV → CeilingProfile (step-function)."""
    rows = _read_lines(path)
    breakpoints = [(r[0], r[1]) for r in rows]
    return CeilingProfile(breakpoints=breakpoints)


def parse_bay_types(path: str) -> list[BayType]:
    """Parse TYPES_OF_BAYS.CSV → list of BayType."""
    rows = _read_lines(path)
    return [
        BayType(
            id=r[0], width=r[1], depth=r[2],
            height=r[3], gap=r[4], n_loads=r[5], price=r[6],
        )
        for r in rows
    ]


# ── Convenience loader ────────────────────────────────────────────


def load_case(directory: str) -> CaseData:
    """Load all 4 CSV files from a case directory into a CaseData."""
    warehouse = parse_warehouse(os.path.join(directory, "warehouse.csv"))
    obstacles = parse_obstacles(os.path.join(directory, "obstacles.csv"))
    ceiling = parse_ceiling(os.path.join(directory, "ceiling.csv"))
    bay_types = parse_bay_types(os.path.join(directory, "types_of_bays.csv"))
    return CaseData(
        warehouse=warehouse,
        obstacles=obstacles,
        ceiling=ceiling,
        bay_types=bay_types,
    )
