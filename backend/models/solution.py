"""Solution output model with discrete 30-degree rotation support."""

from __future__ import annotations
import math
from dataclasses import dataclass, field


def _fmt_num(value: float) -> str:
    """Serialize numbers compactly for CSV/JSON-friendly logs."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


@dataclass(frozen=True, slots=True)
class PlacedBay:
    """A bay placed in the warehouse.

    Local coordinate frame of the bay:
      - (0, 0)     = back-left corner (x=0 is the BACK)
      - (width, 0) = front-left corner (x=width is the FRONT)
      - The gap extends outward from the front face (x=width edge)

    Rotation is counter-clockwise in degrees around ``(0, 0)``, then
    translated to world position ``(x, y)``. The live system snaps rotations
    to the challenge lattice ``{0, 30, ..., 330}``.
    """
    bay_type_id: int
    x: float
    y: float
    rotation: float

    def _transform(self, lx: float, ly: float, cos_t: float, sin_t: float) -> tuple[float, float]:
        return (self.x + lx * cos_t - ly * sin_t,
                self.y + lx * sin_t + ly * cos_t)

    def corners(self, width: int, depth: int) -> list[tuple[float, float]]:
        """4 corners of the bay body in world coords (CCW order)."""
        theta = math.radians(self.rotation)
        c, s = math.cos(theta), math.sin(theta)
        return [
            self._transform(0, 0, c, s),          # back-left
            self._transform(width, 0, c, s),       # front-left
            self._transform(width, depth, c, s),    # front-right
            self._transform(0, depth, c, s),        # back-right
        ]

    def gap_zone(self, width: int, depth: int, gap: int) -> list[tuple[float, float]]:
        """4 corners of the gap zone extending from the depth edge (top face)."""
        if gap <= 0:
            return []
        theta = math.radians(self.rotation)
        c, s = math.cos(theta), math.sin(theta)
        return [
            self._transform(0, depth, c, s),
            self._transform(width, depth, c, s),
            self._transform(width, depth + gap, c, s),
            self._transform(0, depth + gap, c, s),
        ]

    def aabb(self, width: int, depth: int) -> tuple[float, float, float, float]:
        """Axis-aligned bounding box of the rotated bay."""
        cs = self.corners(width, depth)
        xs = [p[0] for p in cs]
        ys = [p[1] for p in cs]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class Solution:
    """Complete placement solution."""
    placements: list[PlacedBay] = field(default_factory=list)

    def to_csv(self, path: str) -> None:
        with open(path, "w") as f:
            for p in self.placements:
                f.write(
                    f"{p.bay_type_id}, {_fmt_num(p.x)}, {_fmt_num(p.y)}, {_fmt_num(p.rotation)}\n"
                )

    @staticmethod
    def from_csv(path: str) -> "Solution":
        placements: list[PlacedBay] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = [x.strip() for x in line.split(",")]
                placements.append(PlacedBay(
                    bay_type_id=int(parts[0]), x=float(parts[1]),
                    y=float(parts[2]), rotation=float(parts[3]),
                ))
        return Solution(placements=placements)
