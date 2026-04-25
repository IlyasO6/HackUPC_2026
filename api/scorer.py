"""
Scorer for the Mecalux warehouse optimization challenge.

Implements the Q heuristic from the challenge PDF:
    Q = Σ(price / nLoads²) - Σ(bay_area) / area_warehouse

Also provides validation: checks collisions, bounds, ceiling constraints.

This module is designed to be FAST — called on every interactive edit
from the frontend for real-time scoring feedback.
"""



def polygon_area(vertices: list[dict]) -> float:
    """
    Calculate area of a polygon using the Shoelace formula.
    vertices: list of {x, y} dicts, ordered (CW or CCW).
    Returns absolute area.
    """
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        xi = vertices[i]["x"]
        yi = vertices[i]["y"]
        xj = vertices[j]["x"]
        yj = vertices[j]["y"]
        area += xi * yj - xj * yi
    return abs(area) / 2.0


def _point_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> bool:
    """Check if point (px,py) lies on segment (ax,ay)-(bx,by) within epsilon."""
    eps = 1e-6
    cross = (py - ay) * (bx - ax) - (px - ax) * (by - ay)
    if abs(cross) > eps:
        return False
    if px < min(ax, bx) - eps or px > max(ax, bx) + eps:
        return False
    if py < min(ay, by) - eps or py > max(ay, by) + eps:
        return False
    return True


def point_in_polygon(px: float, py: float, vertices: list[dict]) -> bool:
    """
    Test if a point is inside or ON THE BOUNDARY of a polygon.
    Uses ray casting + boundary check.
    Per challenge rules: 'Bays can share boundaries, same with warehouse'.
    """
    n = len(vertices)

    # First check if point is on any edge (boundary counts as inside)
    for i in range(n):
        j = (i + 1) % n
        if _point_on_segment(px, py, vertices[i]["x"], vertices[i]["y"],
                             vertices[j]["x"], vertices[j]["y"]):
            return True

    # Ray casting for interior points
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]["x"], vertices[i]["y"]
        xj, yj = vertices[j]["x"], vertices[j]["y"]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside





def rects_overlap(
    x1: float, y1: float, w1: float, d1: float,
    x2: float, y2: float, w2: float, d2: float,
) -> bool:
    """
    Check if two axis-aligned rectangles overlap (strictly — shared boundaries are OK).
    Per challenge rules: "Bays can share boundaries".
    """
    # No overlap if one is to the left/right/above/below the other
    # Using strict < (not <=) because shared boundaries are allowed
    if x1 + w1 <= x2 or x2 + w2 <= x1:
        return False
    if y1 + d1 <= y2 or y2 + d2 <= y1:
        return False
    return True


def get_bay_effective_dims(width: float, depth: float, rotation: float) -> tuple[float, float]:
    """Get effective width and depth after rotation."""
    rot = int(rotation) % 360
    if rot in (90, 270):
        return depth, width
    return width, depth


def get_ceiling_height_at(x: float, ceiling: list[dict]) -> float:
    """
    Get the ceiling height at position x using the ceiling profile.
    The ceiling is piecewise constant: each entry defines the height
    from its x to the next entry's x.
    """
    if not ceiling:
        return float("inf")

    # Sort by x
    sorted_ceil = sorted(ceiling, key=lambda c: c["x"])

    # If x is before the first point, use the first height
    if x <= sorted_ceil[0]["x"]:
        return sorted_ceil[0]["height"]

    # Find the segment
    for i in range(len(sorted_ceil) - 1):
        if sorted_ceil[i]["x"] <= x < sorted_ceil[i + 1]["x"]:
            return sorted_ceil[i]["height"]

    # After the last point, use the last height
    return sorted_ceil[-1]["height"]


def rect_inside_polygon(
    x: float, y: float, w: float, d: float, vertices: list[dict]
) -> bool:
    """
    Check if an axis-aligned rectangle is fully inside a polygon.
    We check all 4 corners and also sample points along edges for concave polygons.
    """
    # Check corners
    corners = [
        (x, y), (x + w, y), (x + w, y + d), (x, y + d)
    ]
    for cx, cy in corners:
        if not point_in_polygon(cx, cy, vertices):
            return False

    # For concave polygons, also check edge midpoints
    midpoints = [
        (x + w / 2, y),
        (x + w, y + d / 2),
        (x + w / 2, y + d),
        (x, y + d / 2),
        (x + w / 2, y + d / 2),  # center
    ]
    for mx, my in midpoints:
        if not point_in_polygon(mx, my, vertices):
            return False

    return True


def validate_placement(
    placed_bays: list[dict],
    bay_types: list[dict],
    warehouse: list[dict],
    obstacles: list[dict],
    ceiling: list[dict],
) -> list[dict]:
    """
    Validate each placed bay and return a list of validation issues.

    Returns:
        List of {bay_index, issue_type, message} for each problem found.
    """
    issues = []
    bay_type_map = {bt["id"]: bt for bt in bay_types}

    # Build effective rects for collision checking
    effective_rects = []  # (x, y, w, d, bay_index)

    for i, bay in enumerate(placed_bays):
        bt = bay_type_map.get(bay["id"])
        if not bt:
            issues.append({
                "bay_index": i,
                "issue_type": "unknown_type",
                "message": f"Bay type {bay['id']} not found",
            })
            continue

        ew, ed = get_bay_effective_dims(bt["width"], bt["depth"], bay["rotation"])
        bx, by = bay["x"], bay["y"]

        # 1. Check bay is inside warehouse polygon
        if not rect_inside_polygon(bx, by, ew, ed, warehouse):
            issues.append({
                "bay_index": i,
                "issue_type": "out_of_bounds",
                "message": f"Bay {bay['id']} at ({bx},{by}) is outside warehouse",
            })

        # 2. Check ceiling height
        # Check at both x-edges of the bay
        for check_x in [bx, bx + ew / 2, bx + ew]:
            ceil_h = get_ceiling_height_at(check_x, ceiling)
            if bt["height"] + bt["gap"] > ceil_h:
                issues.append({
                    "bay_index": i,
                    "issue_type": "ceiling_violation",
                    "message": f"Bay {bay['id']} height {bt['height']}+gap {bt['gap']}={bt['height']+bt['gap']} exceeds ceiling {ceil_h} at x={check_x}",
                })
                break

        # 3. Check collision with obstacles
        for j, obs in enumerate(obstacles):
            if rects_overlap(bx, by, ew, ed, obs["x"], obs["y"], obs["width"], obs["depth"]):
                issues.append({
                    "bay_index": i,
                    "issue_type": "obstacle_collision",
                    "message": f"Bay {bay['id']} collides with obstacle {j}",
                })

        effective_rects.append((bx, by, ew, ed, i))

    # 4. Check bay-bay collisions
    for a in range(len(effective_rects)):
        for b in range(a + 1, len(effective_rects)):
            ax, ay, aw, ad, ai = effective_rects[a]
            bx, by, bw, bd, bi = effective_rects[b]
            if rects_overlap(ax, ay, aw, ad, bx, by, bw, bd):
                issues.append({
                    "bay_index": ai,
                    "issue_type": "bay_collision",
                    "message": f"Bay at index {ai} collides with bay at index {bi}",
                })

    return issues


def calculate_score(
    placed_bays: list[dict],
    bay_types: list[dict],
    warehouse: list[dict],
    obstacles: list[dict] = None,
    ceiling: list[dict] = None,
) -> dict:
    """
    Calculate the Q score and related metrics.

    Q = Σ(price / nLoads²) - Σ(bay_area) / area_warehouse

    Lower Q is better (cheap bays with many loads, covering max area).

    Returns:
        {
            "Q": float,
            "total_cost_per_load2": float,
            "coverage": float,
            "num_bays": int,
            "total_loads": int,
            "total_bay_area": float,
            "warehouse_area": float,
            "is_valid": bool,
            "issues": [...]
        }
    """
    bay_type_map = {bt["id"]: bt for bt in bay_types}
    warehouse_area = polygon_area(warehouse)

    total_price_per_load2 = 0.0
    total_bay_area = 0.0
    total_loads = 0

    for bay in placed_bays:
        bt = bay_type_map.get(bay["id"])
        if not bt:
            continue
        total_price_per_load2 += bt["price"] / (bt["nLoads"] ** 2)
        ew, ed = get_bay_effective_dims(bt["width"], bt["depth"], bay["rotation"])
        total_bay_area += ew * ed
        total_loads += bt["nLoads"]

    coverage = total_bay_area / warehouse_area if warehouse_area > 0 else 0.0
    Q = total_price_per_load2 - coverage

    # Validate placement
    issues = []
    if obstacles is not None and ceiling is not None:
        issues = validate_placement(placed_bays, bay_types, warehouse, obstacles, ceiling)

    return {
        "Q": round(Q, 6),
        "total_cost_per_load2": round(total_price_per_load2, 6),
        "coverage": round(coverage, 6),
        "num_bays": len(placed_bays),
        "total_loads": total_loads,
        "total_bay_area": total_bay_area,
        "warehouse_area": warehouse_area,
        "is_valid": len(issues) == 0,
        "issues": issues,
    }
