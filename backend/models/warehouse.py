"""Warehouse polygon model."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Point:
    """2D integer coordinate in millimeters."""
    x: int
    y: int


@dataclass
class Warehouse:
    """Axis-aligned polygon defining the warehouse boundary.

    Vertices are ordered (CW or CCW) and define a closed polygon.
    All coordinates are in millimeters.
    """
    vertices: list[Point]

    # ── Derived properties ────────────────────────────────────────

    @property
    def bounding_box(self) -> tuple[int, int, int, int]:
        """Returns (min_x, min_y, max_x, max_y)."""
        xs = [v.x for v in self.vertices]
        ys = [v.y for v in self.vertices]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def area(self) -> float:
        """Polygon area via the Shoelace formula (mm²)."""
        n = len(self.vertices)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += self.vertices[i].x * self.vertices[j].y
            area -= self.vertices[j].x * self.vertices[i].y
        return abs(area) / 2.0

    @property
    def vertex_tuples(self) -> list[tuple[int, int]]:
        """Vertices as a list of (x, y) tuples — handy for geometry ops."""
        return [(v.x, v.y) for v in self.vertices]
