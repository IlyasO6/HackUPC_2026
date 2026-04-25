"""Oriented Bounding Box (OBB) geometry for rotated rectangles.

Provides:
  - SAT-based overlap test for convex polygons (works for OBBs and gap zones)
  - Rotated rectangle inside warehouse polygon test
  - Segment-segment intersection
"""

from __future__ import annotations
from geometry.polygon import point_in_polygon


# ── SAT overlap (convex polygons) ─────────────────────────────────


def convex_polygons_overlap(
    poly1: list[tuple[float, float]],
    poly2: list[tuple[float, float]],
) -> bool:
    """Separating Axis Theorem test for two convex polygons.

    Returns True if they share interior area.
    Touching at boundary only → False (consistent with boundary-sharing rules).
    """
    for polygon in (poly1, poly2):
        n = len(polygon)
        for i in range(n):
            j = (i + 1) % n
            # Edge vector → perpendicular axis
            ax = -(polygon[j][1] - polygon[i][1])
            ay = polygon[j][0] - polygon[i][0]

            # Project both polygons onto axis
            proj1 = [ax * p[0] + ay * p[1] for p in poly1]
            proj2 = [ax * p[0] + ay * p[1] for p in poly2]

            # Separated if projections don't overlap (<=  allows boundary touch)
            if max(proj1) <= min(proj2) or max(proj2) <= min(proj1):
                return False
    return True


# ── Segment intersection ─────────────────────────────────────────


def _cross2d(ox: float, oy: float, ax: float, ay: float, bx: float, by: float) -> float:
    return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)


def segments_intersect_strict(
    p1: tuple[float, float], p2: tuple[float, float],
    p3: tuple[float, float], p4: tuple[float, float],
) -> bool:
    """True if segments p1-p2 and p3-p4 cross each other (strict, not at endpoints)."""
    d1 = _cross2d(*p3, *p4, *p1)
    d2 = _cross2d(*p3, *p4, *p2)
    d3 = _cross2d(*p1, *p2, *p3)
    d4 = _cross2d(*p1, *p2, *p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


# ── Rotated rect inside polygon ──────────────────────────────────


def _point_in_polygon_f(px: float, py: float, vertices: list[tuple[int, int]]) -> bool:
    """point_in_polygon accepting float query points."""
    # Boundary check (with tolerance for floating-point)
    EPS = 0.5  # half-mm tolerance
    n = len(vertices)
    for i in range(n):
        j = (i + 1) % n
        x1, y1 = float(vertices[i][0]), float(vertices[i][1])
        x2, y2 = float(vertices[j][0]), float(vertices[j][1])
        # Check if point is on this segment (within tolerance)
        cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        if abs(cross) < EPS * max(abs(x2 - x1) + abs(y2 - y1), 1):
            if (min(x1, x2) - EPS <= px <= max(x1, x2) + EPS and
                    min(y1, y2) - EPS <= py <= max(y1, y2) + EPS):
                return True

    # Ray casting with float coords
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(vertices[i][0]), float(vertices[i][1])
        xj, yj = float(vertices[j][0]), float(vertices[j][1])
        if ((yi > py) != (yj > py)):
            x_int = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_int:
                inside = not inside
        j = i
    return inside


def rotated_rect_inside_polygon(
    rect_corners: list[tuple[float, float]],
    poly_vertices: list[tuple[int, int]],
) -> bool:
    """Check if a rotated rectangle is fully inside a polygon.

    1. All 4 corners inside (or on boundary).
    2. No polygon edge crosses any rectangle edge.
    """
    # Condition 1: all corners inside
    for cx, cy in rect_corners:
        if not _point_in_polygon_f(cx, cy, poly_vertices):
            return False

    # Condition 2: no polygon edge crosses any rect edge
    n_poly = len(poly_vertices)
    n_rect = len(rect_corners)
    for i in range(n_poly):
        j = (i + 1) % n_poly
        pe = (float(poly_vertices[i][0]), float(poly_vertices[i][1]))
        pf = (float(poly_vertices[j][0]), float(poly_vertices[j][1]))
        for k in range(n_rect):
            m = (k + 1) % n_rect
            if segments_intersect_strict(pe, pf, rect_corners[k], rect_corners[m]):
                return False

    return True
