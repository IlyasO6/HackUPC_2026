"""Solution output model."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PlacedBay:
    """A single bay placed in the warehouse.

    Attributes:
        bay_type_id: references a BayType.id.
        x, y:        placement coordinate (bottom-left corner, mm).
        rotation:    0, 90, 180, or 270 degrees.
                     0/180 → original orientation (width along X).
                     90/270 → swapped (depth along X, width along Y).
    """
    bay_type_id: int
    x: int
    y: int
    rotation: int  # 0, 90, 180, 270

    def effective_dims(self, bay_width: int, bay_depth: int) -> tuple[int, int]:
        """Return (effective_width, effective_depth) after rotation."""
        if self.rotation in (0, 180):
            return bay_width, bay_depth
        else:  # 90, 270
            return bay_depth, bay_width

    def bounds(self, bay_width: int, bay_depth: int) -> tuple[int, int, int, int]:
        """Return (min_x, min_y, max_x, max_y) of the placed bay."""
        ew, ed = self.effective_dims(bay_width, bay_depth)
        return self.x, self.y, self.x + ew, self.y + ed


@dataclass
class Solution:
    """Complete placement solution — a list of placed bays."""
    placements: list[PlacedBay] = field(default_factory=list)

    def to_csv(self, path: str) -> None:
        """Write solution to CSV in the expected output format: Id, X, Y, Rotation."""
        with open(path, "w") as f:
            for p in self.placements:
                f.write(f"{p.bay_type_id}, {p.x}, {p.y}, {p.rotation}\n")

    @staticmethod
    def from_csv(path: str) -> "Solution":
        """Load a solution from CSV."""
        placements: list[PlacedBay] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = [int(x.strip()) for x in line.split(",")]
                placements.append(PlacedBay(
                    bay_type_id=parts[0], x=parts[1], y=parts[2], rotation=parts[3],
                ))
        return Solution(placements=placements)
