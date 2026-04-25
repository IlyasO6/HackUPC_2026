"""Polygon operations: area, point-in-polygon, rectangle containment.

All functions operate on lists of (x, y) integer tuples.
"""

from __future__ import annotations


def polygon_area(vertices: list[tuple[int, int]]) -> float:
    """Shoelace formula for polygon area."""
    n = len(vertices)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1]
        area -= vertices[j][0] * vertices[i][1]
    return abs(area) / 2.0


# ── Point-in-polygon ──────────────────────────────────────────────


def _point_on_segment(
    px: int, py: int,
    x1: int, y1: int,
    x2: int, y2: int,
) -> bool:
    """Check if (px, py) lies on segment (x1,y1)→(x2,y2)."""
    # Cross product for collinearity (exact for integers)
    cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
    if cross != 0:
        return False
    # Bounding-box check
    return (min(x1, x2) <= px <= max(x1, x2) and
            min(y1, y2) <= py <= max(y1, y2))


def point_in_polygon(px: int, py: int, vertices: list[tuple[int, int]]) -> bool:
    """Ray-casting test — returns True if (px,py) is inside OR on boundary.

    Boundary inclusion is important because bays can share boundaries
    with the warehouse walls.
    """
    n = len(vertices)

    # Boundary check first
    for i in range(n):
        j = (i + 1) % n
        if _point_on_segment(px, py, vertices[i][0], vertices[i][1],
                             vertices[j][0], vertices[j][1]):
            return True

    # Standard ray-casting (horizontal ray to the right)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if ((yi > py) != (yj > py)):
            x_intersect = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_intersect:
                inside = not inside
        j = i
    return inside


# ── Rectangle containment ────────────────────────────────────────


def rect_inside_polygon(
    rx_min: int, ry_min: int, rx_max: int, ry_max: int,
    vertices: list[tuple[int, int]],
) -> bool:
    """Check that an AABB rectangle is fully contained in a polygon.

    Two conditions (both required):
      1. All 4 corners are inside (or on boundary of) the polygon.
      2. No polygon edge passes *through* the interior of the rectangle.
         (Handles concave shapes like U/L where corners alone can lie.)
    """
    # Condition 1: all corners inside
    corners = [
        (rx_min, ry_min), (rx_max, ry_min),
        (rx_max, ry_max), (rx_min, ry_max),
    ]
    for cx, cy in corners:
        if not point_in_polygon(cx, cy, vertices):
            return False

    # Condition 2: no polygon edge passes through the rectangle interior
    n = len(vertices)
    for i in range(n):
        j = (i + 1) % n
        x1, y1 = vertices[i]
        x2, y2 = vertices[j]

        if y1 == y2:
            # Horizontal edge — problematic if it cuts through rect in Y
            y = y1
            if ry_min < y < ry_max:  # strictly inside rect vertically
                e_min_x, e_max_x = min(x1, x2), max(x1, x2)
                if e_min_x < rx_max and e_max_x > rx_min:  # overlaps in X
                    return False
        elif x1 == x2:
            # Vertical edge — problematic if it cuts through rect in X
            x = x1
            if rx_min < x < rx_max:  # strictly inside rect horizontally
                e_min_y, e_max_y = min(y1, y2), max(y1, y2)
                if e_min_y < ry_max and e_max_y > ry_min:  # overlaps in Y
                    return False

    return True
