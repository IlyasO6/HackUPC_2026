"""Ceiling height profile model (step-function)."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CeilingProfile:
    """Piecewise-constant (step-function) ceiling height profile.

    Breakpoints are (x, height) pairs sorted by x.  The ceiling height
    at any coordinate is defined by the *last* breakpoint whose x ≤ query x.

    Example:  [(0, 3000), (3000, 2000), (6000, 3000)]
      → x ∈ [0, 3000)    : height = 3000
      → x ∈ [3000, 6000) : height = 2000
      → x ∈ [6000, ∞)    : height = 3000

    Justification for step-function over linear interpolation:
    Real warehouse ceilings change height at discrete structural zones
    (mezzanines, loading docks, beam supports), not gradually.  The test
    data confirms this pattern.
    """
    breakpoints: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.breakpoints.sort(key=lambda bp: bp[0])

    # ── Queries ───────────────────────────────────────────────────

    def height_at(self, x: int) -> int:
        """Return ceiling height at a single X coordinate."""
        height = self.breakpoints[0][1]
        for bx, bh in self.breakpoints:
            if bx <= x:
                height = bh
            else:
                break
        return height

    def min_height_in_range(self, x_start: int, x_end: int) -> int:
        """Return the *minimum* ceiling height across [x_start, x_end).

        A bay occupying this X range must have height ≤ this value.
        """
        h = self.height_at(x_start)
        for bx, bh in self.breakpoints:
            if bx <= x_start:
                continue
            if bx < x_end:
                h = min(h, bh)
            else:
                break
        return h
