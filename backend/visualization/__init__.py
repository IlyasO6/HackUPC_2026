"""ASCII terminal visualization of warehouse solutions (supports rotated bays)."""

from __future__ import annotations
import math

from models.case_data import CaseData
from models.solution import Solution

_BAY_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _point_in_convex_poly(px: float, py: float, corners: list[tuple[float, float]]) -> bool:
    """Quick check if point is inside a convex polygon using cross products."""
    n = len(corners)
    for i in range(n):
        j = (i + 1) % n
        cross = ((corners[j][0] - corners[i][0]) * (py - corners[i][1]) -
                 (corners[j][1] - corners[i][1]) * (px - corners[i][0]))
        if cross < 0:
            return False
    return True


def render_ascii(
    case: CaseData,
    solution: Solution,
    width: int = 120,
    height: int = 40,
) -> str:
    bbox = case.warehouse.bounding_box
    min_x, min_y, max_x, max_y = bbox
    wh_w = max_x - min_x
    wh_h = max_y - min_y
    if wh_w == 0 or wh_h == 0:
        return "(empty warehouse)"

    sx = wh_w / width
    sy = wh_h / height

    # Pre-compute bay corners and ensure CCW ordering
    bt_map = case.bay_type_map
    bay_data: list[tuple[list[tuple[float, float]], int]] = []
    for p in solution.placements:
        bt = bt_map.get(p.bay_type_id)
        if bt is None:
            continue
        corners = p.corners(bt.width, bt.depth)
        # Ensure CCW by checking signed area
        area = 0.0
        for i in range(4):
            j = (i + 1) % 4
            area += corners[i][0] * corners[j][1] - corners[j][0] * corners[i][1]
        if area < 0:
            corners = list(reversed(corners))
        bay_data.append((corners, p.bay_type_id))

    from geometry.polygon import point_in_polygon
    poly = case.warehouse.vertex_tuples

    lines: list[str] = []
    for row in range(height):
        wy = max_y - (row + 0.5) * sy
        chars: list[str] = []
        for col in range(width):
            wx = min_x + (col + 0.5) * sx

            ch = None
            for corners, tid in bay_data:
                if _point_in_convex_poly(wx, wy, corners):
                    ch = _BAY_CHARS[tid % len(_BAY_CHARS)]
                    break

            if ch is None:
                for obs in case.obstacles:
                    ox0, oy0, ox1, oy1 = obs.bounds
                    if ox0 <= wx < ox1 and oy0 <= wy < oy1:
                        ch = "#"
                        break

            if ch is None:
                if point_in_polygon(int(wx), int(wy), poly):
                    ch = "."
                else:
                    ch = " "

            chars.append(ch)
        lines.append("".join(chars))

    border = "+" + "-" * width + "+"
    lines = [border] + ["|" + line + "|" for line in lines] + [border]

    used_types = sorted(set(p.bay_type_id for p in solution.placements))
    legend = "Legend: . = empty  # = obstacle"
    for tid in used_types:
        bt = bt_map.get(tid)
        if bt:
            c = _BAY_CHARS[tid % len(_BAY_CHARS)]
            legend += f"  {c}=t{tid}({bt.width}x{bt.depth})"

    lines.append(legend)
    return "\n".join(lines)
