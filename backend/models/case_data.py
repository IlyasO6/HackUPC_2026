"""Aggregate container for a complete test case."""

from __future__ import annotations
from dataclasses import dataclass

from .warehouse import Warehouse
from .obstacle import Obstacle
from .ceiling import CeilingProfile
from .bay_type import BayType


@dataclass
class CaseData:
    """All input data for a single warehouse optimization case."""
    warehouse: Warehouse
    obstacles: list[Obstacle]
    ceiling: CeilingProfile
    bay_types: list[BayType]

    @property
    def bay_type_map(self) -> dict[int, BayType]:
        """Lookup bay type by ID."""
        return {bt.id: bt for bt in self.bay_types}
