"""Shared placement/state primitives for the solver and validator."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from models.bay_type import BayType
from models.solution import PlacedBay, Solution
from solver.spatial_hash import SpatialHash


Point = tuple[float, float]
AABB = tuple[float, float, float, float]


def _polygon_aabb(points: list[Point]) -> AABB:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _translate(points: list[Point], x: float, y: float) -> list[Point]:
    return [(x + px, y + py) for px, py in points]


@dataclass(frozen=True, slots=True)
class PlacementTemplate:
    """Cached geometry for a bay type at a fixed rotation."""

    bay_type: BayType
    angle: float
    cos_t: float = field(init=False, repr=False)
    sin_t: float = field(init=False, repr=False)
    front_normal: Point = field(init=False)
    tangent: Point = field(init=False)
    body_local: list[Point] = field(init=False, repr=False)
    gap_local: list[Point] = field(init=False, repr=False)
    body_aabb_local: AABB = field(init=False, repr=False)
    gap_aabb_local: AABB | None = field(init=False, repr=False)
    x_span_local: tuple[float, float] = field(init=False, repr=False)
    single_feature_offsets: tuple[Point, ...] = field(init=False, repr=False)
    pair_feature_offsets: tuple[Point, ...] = field(init=False, repr=False)
    single_envelope_aabb: AABB = field(init=False, repr=False)
    pair_envelope_aabb: AABB = field(init=False, repr=False)

    def __post_init__(self) -> None:
        theta = math.radians(self.angle)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        u = (cos_t, sin_t)
        v = (-sin_t, cos_t)
        bt = self.bay_type

        body_local = [
            (0.0, 0.0),
            (bt.width * u[0], bt.width * u[1]),
            (bt.width * u[0] + bt.depth * v[0], bt.width * u[1] + bt.depth * v[1]),
            (bt.depth * v[0], bt.depth * v[1]),
        ]
        gap_local: list[Point] = []
        if bt.gap > 0:
            gap_local = [
                (bt.depth * v[0], bt.depth * v[1]),
                (bt.width * u[0] + bt.depth * v[0], bt.width * u[1] + bt.depth * v[1]),
                (
                    bt.width * u[0] + (bt.depth + bt.gap) * v[0],
                    bt.width * u[1] + (bt.depth + bt.gap) * v[1],
                ),
                ((bt.depth + bt.gap) * v[0], (bt.depth + bt.gap) * v[1]),
            ]

        single_offsets = self._build_single_feature_offsets(u, v)
        pair_offsets = self._build_pair_feature_offsets(u, v)

        object.__setattr__(self, "cos_t", cos_t)
        object.__setattr__(self, "sin_t", sin_t)
        object.__setattr__(self, "front_normal", u)
        object.__setattr__(self, "tangent", v)
        object.__setattr__(self, "body_local", body_local)
        object.__setattr__(self, "gap_local", gap_local)
        object.__setattr__(self, "body_aabb_local", _polygon_aabb(body_local))
        object.__setattr__(self, "gap_aabb_local", _polygon_aabb(gap_local) if gap_local else None)
        object.__setattr__(
            self,
            "x_span_local",
            (min(p[0] for p in body_local), max(p[0] for p in body_local)),
        )
        object.__setattr__(self, "single_feature_offsets", single_offsets)
        object.__setattr__(self, "pair_feature_offsets", pair_offsets)
        object.__setattr__(self, "single_envelope_aabb", _polygon_aabb(list(single_offsets)))
        object.__setattr__(self, "pair_envelope_aabb", _polygon_aabb(list(pair_offsets)))

    def _build_single_feature_offsets(self, u: Point, v: Point) -> tuple[Point, ...]:
        bt = self.bay_type
        depth = bt.depth + bt.gap
        return (
            (0.0, 0.0),
            (bt.width * u[0], bt.width * u[1]),
            (bt.width * u[0] + depth * v[0], bt.width * u[1] + depth * v[1]),
            (depth * v[0], depth * v[1]),
        )

    def _build_pair_feature_offsets(self, u: Point, v: Point) -> tuple[Point, ...]:
        bt = self.bay_type
        far = bt.depth + bt.gap
        return (
            (-far * v[0], -far * v[1]),
            (bt.width * u[0] - far * v[0], bt.width * u[1] - far * v[1]),
            (bt.width * u[0] + far * v[0], bt.width * u[1] + far * v[1]),
            (far * v[0], far * v[1]),
        )

    def place(self, x: float, y: float) -> "PlacedFootprint":
        body = _translate(self.body_local, x, y)
        gap = _translate(self.gap_local, x, y) if self.gap_local else []
        body_aabb_local = self.body_aabb_local
        body_aabb = (
            x + body_aabb_local[0],
            y + body_aabb_local[1],
            x + body_aabb_local[2],
            y + body_aabb_local[3],
        )
        gap_aabb = None
        if self.gap_aabb_local is not None:
            gap_aabb = (
                x + self.gap_aabb_local[0],
                y + self.gap_aabb_local[1],
                x + self.gap_aabb_local[2],
                y + self.gap_aabb_local[3],
            )
        return PlacedFootprint(
            placement=PlacedBay(self.bay_type.id, x, y, self.angle),
            template=self,
            body=body,
            gap=gap,
            body_aabb=body_aabb,
            gap_aabb=gap_aabb,
            x_span=(x + self.x_span_local[0], x + self.x_span_local[1]),
        )


@dataclass(frozen=True, slots=True)
class PlacedFootprint:
    """Placed bay with cached transformed polygons."""

    placement: PlacedBay
    template: PlacementTemplate
    body: list[Point]
    gap: list[Point]
    body_aabb: AABB
    gap_aabb: AABB | None
    x_span: tuple[float, float]

    @property
    def bay_type_id(self) -> int:
        return self.placement.bay_type_id


@dataclass(frozen=True, slots=True)
class RowBundle:
    """Applied row or back-to-back row pair."""

    kind: str
    bay_type_id: int
    angle: float
    anchor: Point
    slot_count: int
    placements: tuple[PlacedBay, ...]
    line_points: tuple[Point, ...]

    @property
    def anchor_points(self) -> tuple[Point, ...]:
        return self.line_points


@dataclass(frozen=True, slots=True)
class RowCandidate:
    """Candidate bundle to add to a layout state."""

    kind: str
    bay_type_id: int
    angle: float
    anchor: Point
    slot_count: int
    footprints: tuple[PlacedFootprint, ...]
    total_area: float
    total_price: float
    total_loads: int
    resulting_q: float
    delta_q: float
    line_points: tuple[Point, ...]

    def to_bundle(self) -> RowBundle:
        return RowBundle(
            kind=self.kind,
            bay_type_id=self.bay_type_id,
            angle=self.angle,
            anchor=self.anchor,
            slot_count=self.slot_count,
            placements=tuple(fp.placement for fp in self.footprints),
            line_points=self.line_points,
        )


def score_from_totals(
    total_area: float,
    total_price: float,
    total_loads: int,
    warehouse_area: float,
) -> float:
    if warehouse_area <= 0 or total_loads <= 0:
        return float("inf")
    pct_area = total_area / warehouse_area
    return (total_price / total_loads) ** (2.0 - pct_area)


@dataclass
class LayoutState:
    """Solver state with cached placements, totals, and spatial indices."""

    warehouse_area: float
    footprints: list[PlacedFootprint] = field(default_factory=list)
    rows: list[RowBundle] = field(default_factory=list)
    body_hash: SpatialHash | None = None
    gap_hash: SpatialHash | None = None
    total_area: float = 0.0
    total_price: float = 0.0
    total_loads: int = 0

    def __post_init__(self) -> None:
        if self.body_hash is None or self.gap_hash is None:
            raise ValueError("LayoutState requires initialized spatial hashes")

    @property
    def placements(self) -> list[PlacedBay]:
        return [fp.placement for fp in self.footprints]

    @property
    def solution(self) -> Solution:
        return Solution(placements=self.placements)

    @property
    def score(self) -> float:
        return score_from_totals(
            self.total_area,
            self.total_price,
            self.total_loads,
            self.warehouse_area,
        )

    @property
    def coverage(self) -> float:
        if self.warehouse_area <= 0:
            return 0.0
        return self.total_area / self.warehouse_area

    @property
    def anchor_points(self) -> list[Point]:
        points: list[Point] = []
        seen: set[tuple[float, float]] = set()
        for row in self.rows:
            for x, y in row.anchor_points:
                key = (round(x, 6), round(y, 6))
                if key in seen:
                    continue
                seen.add(key)
                points.append((x, y))
        return points

    def clone(self) -> "LayoutState":
        return LayoutState(
            warehouse_area=self.warehouse_area,
            footprints=list(self.footprints),
            rows=list(self.rows),
            body_hash=self.body_hash.copy(),
            gap_hash=self.gap_hash.copy(),
            total_area=self.total_area,
            total_price=self.total_price,
            total_loads=self.total_loads,
        )

    def with_candidate(self, candidate: RowCandidate) -> "LayoutState":
        state = self.clone()
        bundle = candidate.to_bundle()
        for fp in candidate.footprints:
            idx = len(state.footprints)
            state.footprints.append(fp)
            state.body_hash.add(fp.body_aabb, idx)
            if fp.gap_aabb is not None:
                state.gap_hash.add(fp.gap_aabb, idx)
        state.rows.append(bundle)
        state.total_area += candidate.total_area
        state.total_price += candidate.total_price
        state.total_loads += candidate.total_loads
        return state


def build_empty_state(warehouse_area: float, cell_size: float) -> LayoutState:
    return LayoutState(
        warehouse_area=warehouse_area,
        body_hash=SpatialHash(cell_size=cell_size),
        gap_hash=SpatialHash(cell_size=cell_size),
    )
