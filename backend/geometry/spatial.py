"""Spatial queries: AABB overlap, obstacle intersection."""

from __future__ import annotations


def rects_overlap(
    ax_min: int, ay_min: int, ax_max: int, ay_max: int,
    bx_min: int, by_min: int, bx_max: int, by_max: int,
) -> bool:
    """Check if two AABBs *strictly* overlap (shared boundary only → False).

    Per the rules, bays may share boundaries with each other and with walls.
    """
    if ax_max <= bx_min or bx_max <= ax_min:
        return False
    if ay_max <= by_min or by_max <= ay_min:
        return False
    return True
