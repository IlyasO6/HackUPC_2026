"""Uniform spatial hash for broad-phase overlap queries."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


AABB = tuple[float, float, float, float]


@dataclass
class SpatialHash:
    """Spatial hash keyed by AABB-covered grid cells."""

    cell_size: float
    _cells: dict[tuple[int, int], set[int]] = field(default_factory=dict)

    def copy(self) -> "SpatialHash":
        return SpatialHash(
            cell_size=self.cell_size,
            _cells={cell: set(ids) for cell, ids in self._cells.items()},
        )

    def add(self, aabb: AABB, item_id: int) -> None:
        for cell in self._cells_for_aabb(aabb):
            self._cells.setdefault(cell, set()).add(item_id)

    def remove(self, aabb: AABB, item_id: int) -> None:
        for cell in self._cells_for_aabb(aabb):
            ids = self._cells.get(cell)
            if not ids:
                continue
            ids.discard(item_id)
            if not ids:
                self._cells.pop(cell, None)

    def query(self, aabb: AABB) -> set[int]:
        result: set[int] = set()
        for cell in self._cells_for_aabb(aabb):
            result.update(self._cells.get(cell, ()))
        return result

    def _cells_for_aabb(self, aabb: AABB) -> list[tuple[int, int]]:
        min_x, min_y, max_x, max_y = aabb
        eps = 1e-9
        start_x = math.floor(min_x / self.cell_size)
        end_x = math.floor((max_x - eps) / self.cell_size)
        start_y = math.floor(min_y / self.cell_size)
        end_y = math.floor((max_y - eps) / self.cell_size)
        cells: list[tuple[int, int]] = []
        for cx in range(start_x, end_x + 1):
            for cy in range(start_y, end_y + 1):
                cells.append((cx, cy))
        return cells
