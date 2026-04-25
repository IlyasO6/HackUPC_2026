"""Obstacle rectangle model."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Obstacle:
    """Axis-aligned rectangular obstacle inside the warehouse.

    Attributes:
        x, y:  bottom-left corner (mm).
        width: extent along the X axis (mm).
        depth: extent along the Y axis (mm).
    """
    x: int
    y: int
    width: int
    depth: int

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """Returns (min_x, min_y, max_x, max_y)."""
        return self.x, self.y, self.x + self.width, self.y + self.depth
