"""Reusable placement rules shared by the solver and validator."""

from __future__ import annotations

from dataclasses import dataclass
import math

from geometry.obb import convex_polygons_overlap, rotated_rect_inside_polygon
from models.case_data import CaseData
from models.solution import PlacedBay
from solver.layout import AABB, LayoutState, PlacementTemplate, PlacedFootprint


Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class FreeRectangle:
    """Axis-aligned free region derived from warehouse/obstacle events."""

    bounds: tuple[float, float, float, float]

    @property
    def corners(self) -> tuple[Point, Point, Point, Point]:
        min_x, min_y, max_x, max_y = self.bounds
        return (
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        )


@dataclass(frozen=True, slots=True)
class CaseContext:
    """Case-wide cached geometry and search anchors."""

    case: CaseData
    polygon: list[tuple[int, int]]
    obstacle_polygons: tuple[tuple[Point, Point, Point, Point], ...]
    free_rectangles: tuple[FreeRectangle, ...]
    reference_points: tuple[Point, ...]
    cell_size: float


def build_case_context(case: CaseData) -> CaseContext:
    polygon = case.warehouse.vertex_tuples
    obstacle_polygons = tuple(
        (
            (float(obs.x), float(obs.y)),
            (float(obs.x + obs.width), float(obs.y)),
            (float(obs.x + obs.width), float(obs.y + obs.depth)),
            (float(obs.x), float(obs.y + obs.depth)),
        )
        for obs in case.obstacles
    )
    free_rectangles = tuple(_build_free_rectangles(case))
    ref_points = _build_reference_points(case, free_rectangles)
    max_depth = max((bt.depth for bt in case.bay_types), default=1)
    max_gap = max((bt.gap for bt in case.bay_types), default=0)
    return CaseContext(
        case=case,
        polygon=polygon,
        obstacle_polygons=obstacle_polygons,
        free_rectangles=free_rectangles,
        reference_points=tuple(ref_points),
        cell_size=float(max_depth + max_gap),
    )


def _build_reference_points(case: CaseData, free_rectangles: tuple[FreeRectangle, ...]) -> list[Point]:
    points: list[Point] = []
    seen: set[tuple[float, float]] = set()
    event_ys = {float(v.y) for v in case.warehouse.vertices}
    for obs in case.obstacles:
        event_ys.add(float(obs.y))
        event_ys.add(float(obs.y + obs.depth))
    for rect in free_rectangles:
        for point in rect.corners:
            key = (round(point[0], 6), round(point[1], 6))
            if key in seen:
                continue
            seen.add(key)
            points.append(point)
    for bx, _ in case.ceiling.breakpoints:
        for y in sorted(event_ys):
            point = (float(bx), y)
            key = (round(point[0], 6), round(point[1], 6))
            if key in seen:
                continue
            seen.add(key)
            points.append(point)
    return points


def _build_free_rectangles(case: CaseData) -> list[FreeRectangle]:
    poly = case.warehouse.vertex_tuples
    min_x, min_y, max_x, max_y = case.warehouse.bounding_box
    xs = {float(min_x), float(max_x)}
    ys = {float(min_y), float(max_y)}
    for v in case.warehouse.vertices:
        xs.add(float(v.x))
        ys.add(float(v.y))
    for obs in case.obstacles:
        xs.add(float(obs.x))
        xs.add(float(obs.x + obs.width))
        ys.add(float(obs.y))
        ys.add(float(obs.y + obs.depth))
    for bx, _ in case.ceiling.breakpoints:
        if min_x <= bx <= max_x:
            xs.add(float(bx))

    sorted_x = sorted(xs)
    sorted_y = sorted(ys)
    if len(sorted_x) < 2 or len(sorted_y) < 2:
        return []

    free: list[list[bool]] = []
    for ix in range(len(sorted_x) - 1):
        row: list[bool] = []
        cx = (sorted_x[ix] + sorted_x[ix + 1]) / 2.0
        for iy in range(len(sorted_y) - 1):
            cy = (sorted_y[iy] + sorted_y[iy + 1]) / 2.0
            inside = _point_in_polygon_float(cx, cy, poly)
            blocked = False
            if inside:
                for obs in case.obstacles:
                    if obs.x < cx < obs.x + obs.width and obs.y < cy < obs.y + obs.depth:
                        blocked = True
                        break
            row.append(inside and not blocked)
        free.append(row)

    used = [[False for _ in range(len(sorted_y) - 1)] for _ in range(len(sorted_x) - 1)]
    rectangles: list[FreeRectangle] = []
    for ix in range(len(sorted_x) - 1):
        for iy in range(len(sorted_y) - 1):
            if not free[ix][iy] or used[ix][iy]:
                continue
            width = 1
            while ix + width < len(sorted_x) - 1 and free[ix + width][iy] and not used[ix + width][iy]:
                width += 1
            height = 1
            done = False
            while iy + height < len(sorted_y) - 1 and not done:
                for dx in range(width):
                    if not free[ix + dx][iy + height] or used[ix + dx][iy + height]:
                        done = True
                        break
                if not done:
                    height += 1
            for dx in range(width):
                for dy in range(height):
                    used[ix + dx][iy + dy] = True
            rectangles.append(
                FreeRectangle(
                    bounds=(
                        sorted_x[ix],
                        sorted_y[iy],
                        sorted_x[ix + width],
                        sorted_y[iy + height],
                    )
                )
            )
    rectangles.sort(
        key=lambda rect: (
            (rect.bounds[2] - rect.bounds[0]) * (rect.bounds[3] - rect.bounds[1]),
            rect.bounds[0],
            rect.bounds[1],
        ),
        reverse=True,
    )
    return rectangles


def _point_in_polygon_float(px: float, py: float, vertices: list[tuple[int, int]]) -> bool:
    eps = 1e-9
    inside = False
    j = len(vertices) - 1
    for i in range(len(vertices)):
        xi, yi = float(vertices[i][0]), float(vertices[i][1])
        xj, yj = float(vertices[j][0]), float(vertices[j][1])
        cross = (xj - xi) * (py - yi) - (yj - yi) * (px - xi)
        if abs(cross) <= eps and min(xi, xj) - eps <= px <= max(xi, xj) + eps and min(yi, yj) - eps <= py <= max(yi, yj) + eps:
            return True
        if ((yi > py) != (yj > py)):
            x_int = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_int:
                inside = not inside
        j = i
    return inside


def template_cache_for_solution(solution: list[PlacedBay], case: CaseData) -> dict[tuple[int, float], PlacementTemplate]:
    cache: dict[tuple[int, float], PlacementTemplate] = {}
    bt_map = case.bay_type_map
    for placed in solution:
        bt = bt_map.get(placed.bay_type_id)
        if bt is None:
            continue
        key = (bt.id, placed.rotation)
        if key not in cache:
            cache[key] = PlacementTemplate(bt, placed.rotation)
    return cache


def overlap_aabbs(a: AABB, b: AABB) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def placement_violations(
    footprint: PlacedFootprint,
    ctx: CaseContext,
    existing: list[PlacedFootprint],
    state: LayoutState | None = None,
    extra: list[PlacedFootprint] | None = None,
) -> list[str]:
    violations: list[str] = []
    if not rotated_rect_inside_polygon(footprint.body, ctx.polygon):
        violations.append("body extends outside warehouse boundary")
    if footprint.gap and not rotated_rect_inside_polygon(footprint.gap, ctx.polygon):
        violations.append("front gap extends outside warehouse boundary")

    bt = footprint.template.bay_type
    x_min, x_max = footprint.x_span
    start_x = math.floor(min(x_min, x_max))
    end_x = math.ceil(max(x_min, x_max))
    max_h = ctx.case.ceiling.min_height_in_range(start_x, end_x + 1)
    if bt.height > max_h:
        violations.append(f"height {bt.height} exceeds ceiling {max_h}")

    for obs_poly in ctx.obstacle_polygons:
        if convex_polygons_overlap(footprint.body, list(obs_poly)):
            violations.append("body overlaps obstacle")
            break
    if footprint.gap:
        for obs_poly in ctx.obstacle_polygons:
            if convex_polygons_overlap(footprint.gap, list(obs_poly)):
                violations.append("front gap overlaps obstacle")
                break

    compare_ids: set[int] = set()
    if state is not None:
        compare_ids.update(state.body_hash.query(footprint.body_aabb))
        if footprint.gap_aabb is not None:
            compare_ids.update(state.body_hash.query(footprint.gap_aabb))
        compare_ids.update(state.gap_hash.query(footprint.body_aabb))
    for idx in sorted(compare_ids):
        other = existing[idx]
        if overlap_aabbs(footprint.body_aabb, other.body_aabb) and convex_polygons_overlap(footprint.body, other.body):
            violations.append("body overlaps another bay body")
            break
        if other.gap and overlap_aabbs(footprint.body_aabb, other.gap_aabb) and convex_polygons_overlap(footprint.body, other.gap):
            violations.append("body violates another bay's front gap")
            break
        if footprint.gap and overlap_aabbs(footprint.gap_aabb, other.body_aabb) and convex_polygons_overlap(footprint.gap, other.body):
            violations.append("front gap is occupied by another bay body")
            break

    if extra:
        for other in extra:
            if overlap_aabbs(footprint.body_aabb, other.body_aabb) and convex_polygons_overlap(footprint.body, other.body):
                violations.append("body overlaps another bay body")
                break
            if other.gap and overlap_aabbs(footprint.body_aabb, other.gap_aabb) and convex_polygons_overlap(footprint.body, other.gap):
                violations.append("body violates another bay's front gap")
                break
            if footprint.gap and overlap_aabbs(footprint.gap_aabb, other.body_aabb) and convex_polygons_overlap(footprint.gap, other.body):
                violations.append("front gap is occupied by another bay body")
                break
    return violations


def is_valid_placement(
    footprint: PlacedFootprint,
    ctx: CaseContext,
    existing: list[PlacedFootprint],
    state: LayoutState | None = None,
    extra: list[PlacedFootprint] | None = None,
) -> bool:
    return not placement_violations(footprint, ctx, existing, state=state, extra=extra)
