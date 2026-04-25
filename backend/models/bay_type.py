"""Bay type catalog model."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BayType:
    """One type of storage bay available for placement.

    Attributes:
        id:      unique identifier.
        width:   extent along X when not rotated (mm).
        depth:   extent along Y when not rotated (mm).
        height:  vertical extent (mm) — must fit under ceiling.
        gap:     operational clearance (mm), used by solver for aisle spacing.
        n_loads: number of pallet loads this bay holds.
        price:   cost of this bay unit.
    """
    id: int
    width: int
    depth: int
    height: int
    gap: int
    n_loads: int
    price: int

    @property
    def area(self) -> int:
        """Footprint area in mm²."""
        return self.width * self.depth
