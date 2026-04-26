"""Discrete-angle warehouse solver with exact-search fallback.

The solver operates on row bundles because the challenge instances are dominated
by long orthogonal or near-orthogonal lanes. It still evaluates all 12
discrete 30-degree rotations required by the API contract.

The search strategy is:

1. Build a fast constructive incumbent.
2. Run an exact branch-and-bound search when the candidate frontier is small
   enough to be tractable.
3. Fall back to deterministic neighborhood refinement when the exact search
   budget is exceeded.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Iterable

from config import (
    ANGLE_STEP_DEGREES,
    DEFAULT_BEAM_WIDTH,
    DEFAULT_CANDIDATE_LIMIT,
    DEFAULT_TIME_BUDGET_SECONDS,
    DISCRETE_ANGLES,
    EXACT_NODE_LIMIT,
    EXACT_REFERENCE_POINT_LIMIT,
    EXACT_ROOT_CANDIDATE_LIMIT,
    EXACT_TIME_FRACTION,
    FLOAT_TOLERANCE,
    MAX_AXIS_BASELINE_SECONDS,
    MAX_ROW_SLOTS,
    MIN_AXIS_BASELINE_SECONDS,
    REFINEMENT_TIME_FRACTION,
)
from models.bay_type import BayType
from models.case_data import CaseData
from models.solution import Solution
from solver.base import BaseSolver
from solver.layout import (
    LayoutState,
    PlacementTemplate,
    RowCandidate,
    build_empty_state,
    score_from_totals,
)
from validation.rules import CaseContext, build_case_context, is_valid_placement


def _normalize_angle(angle: float) -> float:
    """Return a canonical rotation in ``[0, 360)``.

    Parameters
    ----------
    angle:
        Input rotation in degrees.

    Returns
    -------
    float
        Normalized rotation rounded to 6 decimals.
    """

    normalized = angle % 360.0
    if abs(normalized - 360.0) < FLOAT_TOLERANCE:
        normalized = 0.0
    if abs(normalized) < FLOAT_TOLERANCE:
        return 0.0
    return round(normalized, 6)


def _snap_to_discrete_angle(angle: float) -> float:
    """Snap a rotation to the nearest valid discrete challenge angle.

    Parameters
    ----------
    angle:
        Input rotation in degrees.

    Returns
    -------
    float
        Rotation snapped to the nearest 30-degree step.
    """

    step_index = int(round(angle / ANGLE_STEP_DEGREES))
    return _normalize_angle(step_index * ANGLE_STEP_DEGREES)


def _opposite_angle(angle: float) -> float:
    """Return the opposite discrete orientation."""

    return _normalize_angle(angle + 180.0)


@dataclass(frozen=True, slots=True)
class _CandidateConfig:
    """Row-generation configuration."""

    bay_type: BayType
    angle: float
    kind: str


@dataclass(slots=True)
class SolverRunStats:
    """Metadata describing the most recent solver run."""

    elapsed_seconds: float = 0.0
    q_initial: float = float("inf")
    q_final: float = float("inf")
    bay_count: int = 0
    nodes_explored: int = 0
    exact_search_attempted: bool = False
    exact_search_completed: bool = False
    strategy: str = "constructive"


class HybridSolver(BaseSolver):
    """Discrete-angle solver with exact-search fallback.

    Parameters
    ----------
    angle_step:
        Requested angle step when ``angle_mode="fixed-step"``. The value is
        still snapped to the required 30-degree challenge lattice.
    angle_mode:
        ``"fixed-step"`` keeps evenly spaced angles. Any other value uses the
        full discrete 30-degree challenge set.
    time_budget:
        Wall-clock budget in seconds.
    seed:
        Reserved for deterministic future extensions.
    beam_width:
        Number of states retained during constructive search.
    candidate_limit:
        Maximum candidate bundles retained per constructive iteration.
    """

    def __init__(
        self,
        angle_step: float = ANGLE_STEP_DEGREES,
        angle_mode: str = "discrete",
        time_budget: float = DEFAULT_TIME_BUDGET_SECONDS,
        seed: int = 0,
        beam_width: int = DEFAULT_BEAM_WIDTH,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        self.angle_step = max(ANGLE_STEP_DEGREES, float(angle_step))
        self.angle_mode = angle_mode
        self.time_budget = max(1.0, float(time_budget))
        self.seed = seed
        self.beam_width = max(1, int(beam_width))
        self.candidate_limit = max(1, int(candidate_limit))
        self._template_cache: dict[tuple[int, float], PlacementTemplate] = {}
        self.last_run_stats = SolverRunStats()

    def solve(self, case: CaseData) -> Solution:
        """Solve a warehouse instance.

        Parameters
        ----------
        case:
            Parsed challenge case.

        Returns
        -------
        Solution
            Best layout discovered inside the time budget.
        """

        started_at = time.perf_counter()
        self._template_cache = {}
        ctx = build_case_context(case)
        ranked_types = self._ranked_types(case)
        deadline = started_at + self.time_budget

        incumbent = self._construct_incumbent(case, ctx, ranked_types, deadline)
        best_state = incumbent

        exact_attempted = self._should_attempt_exact(case, ctx)
        exact_completed = False
        nodes_explored = 0
        strategy = "constructive"

        if exact_attempted and time.perf_counter() < deadline:
            exact_deadline = min(
                deadline,
                started_at + self.time_budget * EXACT_TIME_FRACTION,
            )
            exact_state, exact_completed, nodes_explored = (
                self._solve_exact_branch_and_bound(
                    case=case,
                    ctx=ctx,
                    ranked_types=ranked_types,
                    incumbent=best_state,
                    deadline=exact_deadline,
                )
            )
            if exact_state.score + FLOAT_TOLERANCE < best_state.score:
                best_state = exact_state
            strategy = "exact" if exact_completed else "exact+refine"

        if time.perf_counter() < deadline:
            refined = self._refine_solution(
                state=best_state,
                case=case,
                ctx=ctx,
                ranked_types=ranked_types,
                deadline=deadline,
            )
            if refined.score + FLOAT_TOLERANCE < best_state.score:
                best_state = refined
            if strategy == "constructive":
                strategy = "constructive+refine"

        if time.perf_counter() < deadline:
            filled = self._fill_gaps(
                state=best_state,
                case=case,
                ctx=ctx,
                deadline=deadline,
            )
            if filled.score + FLOAT_TOLERANCE < best_state.score:
                best_state = filled

        elapsed = time.perf_counter() - started_at
        self.last_run_stats = SolverRunStats(
            elapsed_seconds=elapsed,
            q_initial=incumbent.score,
            q_final=best_state.score,
            bay_count=len(best_state.solution.placements),
            nodes_explored=nodes_explored,
            exact_search_attempted=exact_attempted,
            exact_search_completed=exact_completed,
            strategy=strategy,
        )
        return best_state.solution

    def _should_attempt_exact(self, case: CaseData, ctx: CaseContext) -> bool:
        """Return whether the exact pass is affordable for this case."""

        if len(ctx.reference_points) > EXACT_REFERENCE_POINT_LIMIT:
            return False
        if len(case.bay_types) > 12:
            return False
        return True

    def _construct_incumbent(
        self,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
    ) -> LayoutState:
        """Build a fast deterministic incumbent used by exact search pruning."""

        axis_budget = min(
            MAX_AXIS_BASELINE_SECONDS,
            max(MIN_AXIS_BASELINE_SECONDS, self.time_budget * 0.35),
        )
        axis_deadline = min(deadline, time.perf_counter() + axis_budget)
        baseline = self._solve_axis_sweep(case, ctx, ranked_types, axis_deadline)

        beam = [baseline, build_empty_state(case.warehouse.area, ctx.cell_size)]
        best = min(
            beam,
            key=lambda state: (state.score, -state.coverage, -len(state.placements)),
        )
        configs = self._configs_for_angles(ranked_types, self._select_search_angles())

        while time.perf_counter() < deadline:
            next_states: list[LayoutState] = []
            improved = False
            for state in beam:
                candidates = self._generate_candidates(
                    state=state,
                    case=case,
                    ctx=ctx,
                    configs=configs,
                    deadline=deadline,
                    limit=self.candidate_limit,
                    per_config_limit=1,
                )
                for candidate in candidates:
                    if candidate.resulting_q + FLOAT_TOLERANCE >= state.score:
                        continue
                    improved = True
                    next_states.append(state.with_candidate(candidate))
            if not improved or not next_states:
                break
            beam = self._top_states(next_states, self.beam_width)
            if beam and beam[0].score + FLOAT_TOLERANCE < best.score:
                best = beam[0]
        return best

    def _solve_exact_branch_and_bound(
        self,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        incumbent: LayoutState,
        deadline: float,
    ) -> tuple[LayoutState, bool, int]:
        """Run an exact branch-and-bound search on the finite row frontier."""

        configs = self._configs_for_angles(ranked_types, self._select_search_angles())
        best = incumbent
        root = build_empty_state(case.warehouse.area, ctx.cell_size)
        seen: set[tuple[tuple[int, float, float, float], ...]] = set()
        nodes_explored = 0
        completed = True

        def dfs(state: LayoutState) -> None:
            nonlocal best, nodes_explored, completed

            if time.perf_counter() >= deadline or nodes_explored >= EXACT_NODE_LIMIT:
                completed = False
                return

            signature = self._state_signature(state)
            if signature in seen:
                return
            seen.add(signature)
            nodes_explored += 1

            optimistic_q = self._optimistic_score(state, case)
            if optimistic_q + FLOAT_TOLERANCE >= best.score:
                return

            candidates = self._generate_candidates(
                state=state,
                case=case,
                ctx=ctx,
                configs=configs,
                deadline=deadline,
                limit=EXACT_ROOT_CANDIDATE_LIMIT,
                per_config_limit=1,
            )
            if not candidates:
                if state.score + FLOAT_TOLERANCE < best.score:
                    best = state
                return

            for candidate in candidates:
                if candidate.resulting_q + FLOAT_TOLERANCE >= best.score:
                    continue
                dfs(state.with_candidate(candidate))

            if state.score + FLOAT_TOLERANCE < best.score:
                best = state

        dfs(root)
        return best, completed, nodes_explored

    def _optimistic_score(self, state: LayoutState, case: CaseData) -> float:
        """Return a lower bound on the best score reachable from ``state``."""

        if state.total_loads <= 0 and state.total_area <= 0:
            remaining_area = case.warehouse.area
        else:
            remaining_area = max(0.0, case.warehouse.area - state.total_area)
        if remaining_area <= FLOAT_TOLERANCE:
            return state.score

        best_price_per_load = min(
            bt.price / bt.n_loads for bt in case.bay_types if bt.n_loads > 0
        )
        best_load_density = max(
            bt.n_loads / bt.area for bt in case.bay_types if bt.area > 0
        )
        optimistic_added_loads = remaining_area * best_load_density
        optimistic_added_price = optimistic_added_loads * best_price_per_load

        return score_from_totals(
            total_area=case.warehouse.area,
            total_price=state.total_price + optimistic_added_price,
            total_loads=state.total_loads + optimistic_added_loads,
            warehouse_area=case.warehouse.area,
        )

    def _state_signature(
        self,
        state: LayoutState,
    ) -> tuple[tuple[int, float, float, float], ...]:
        """Build a deterministic signature used for exact-search deduplication."""

        return tuple(
            sorted(
                (
                    placement.bay_type_id,
                    round(placement.x, 6),
                    round(placement.y, 6),
                    round(placement.rotation, 6),
                )
                for placement in state.placements
            )
        )

    def _ranked_types(self, case: CaseData) -> list[BayType]:
        """Order bay types by cost efficiency and footprint."""

        ranked = sorted(
            case.bay_types,
            key=lambda bay_type: (
                bay_type.price / bay_type.n_loads,
                -bay_type.area,
                bay_type.height,
                bay_type.id,
            ),
        )
        seen: set[int] = set()
        result: list[BayType] = []
        for bay_type in ranked:
            if bay_type.id in seen:
                continue
            seen.add(bay_type.id)
            result.append(bay_type)
        return result

    def _solve_axis_sweep(
        self,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
    ) -> LayoutState:
        """Create a fast incumbent using only the cardinal directions."""

        cardinal_angles = [0.0, 90.0, 180.0, 270.0]
        configs = [
            (bay_type, angle)
            for bay_type in ranked_types
            for angle in cardinal_angles
        ]
        best = build_empty_state(case.warehouse.area, ctx.cell_size)

        for primary_type, primary_angle in configs[: min(12, len(configs))]:
            if time.perf_counter() >= deadline:
                break
            state = build_empty_state(case.warehouse.area, ctx.cell_size)
            self._axis_scan_and_place(
                case=case,
                ctx=ctx,
                state=state,
                template=self._template(primary_type, primary_angle),
                deadline=deadline,
            )
            for bay_type, angle in configs:
                if time.perf_counter() >= deadline:
                    break
                self._axis_scan_and_place(
                    case=case,
                    ctx=ctx,
                    state=state,
                    template=self._template(bay_type, angle),
                    deadline=deadline,
                )
            if state.score + FLOAT_TOLERANCE < best.score:
                best = state
        return best

    def _axis_scan_and_place(
        self,
        case: CaseData,
        ctx: CaseContext,
        state: LayoutState,
        template: PlacementTemplate,
        deadline: float,
    ) -> None:
        """Place greedily along warehouse-aligned scan lines."""

        bay_type = template.bay_type
        xs = self._axis_candidate_x(
            case=case,
            state=state,
            width=bay_type.width,
            depth=bay_type.depth,
            angle=template.angle,
        )
        ys = self._axis_candidate_y(
            case=case,
            state=state,
            width=bay_type.width,
            depth=bay_type.depth,
            angle=template.angle,
        )
        for y_coord in ys:
            if time.perf_counter() >= deadline:
                return
            for x_coord in xs:
                footprint = template.place(float(x_coord), float(y_coord))
                if not is_valid_placement(
                    footprint=footprint,
                    ctx=ctx,
                    existing=state.footprints,
                    state=state,
                ):
                    continue
                self._append_footprint(state, footprint)

    def _append_footprint(
        self,
        state: LayoutState,
        footprint,
    ) -> None:
        """Append a single validated footprint to ``state``."""

        footprint_index = len(state.footprints)
        state.footprints.append(footprint)
        state.body_hash.add(footprint.body_aabb, footprint_index)
        if footprint.gap_aabb is not None:
            state.gap_hash.add(footprint.gap_aabb, footprint_index)
        bay_type = footprint.template.bay_type
        state.total_area += bay_type.area
        state.total_price += bay_type.price
        state.total_loads += bay_type.n_loads

    def _axis_candidate_x(
        self,
        case: CaseData,
        state: LayoutState,
        width: int,
        depth: int,
        angle: float,
    ) -> list[int]:
        """Return scan-line X anchors for the baseline constructor."""

        min_x, _, max_x, _ = case.warehouse.bounding_box
        theta = math.radians(angle)
        extent = abs(width * math.cos(theta)) + abs(depth * math.sin(theta))
        step = max(int(round(extent)), 100)

        candidates: set[int] = {vertex.x for vertex in case.warehouse.vertices}
        for obstacle in case.obstacles:
            candidates.add(obstacle.x)
            candidates.add(obstacle.x + obstacle.width)
            candidates.add(int(round(obstacle.x - extent)))
            candidates.add(int(round(obstacle.x + obstacle.width - extent)))
        for footprint in state.footprints:
            x_min, _, x_max, _ = footprint.body_aabb
            candidates.add(int(round(x_min)))
            candidates.add(int(round(x_max)))
            candidates.add(int(round(x_min - extent)))
            candidates.add(int(round(x_max - extent)))

        cursor = min_x
        while cursor <= max_x:
            candidates.add(int(cursor))
            cursor += step
        return sorted(
            value
            for value in candidates
            if min_x - int(extent) <= value <= max_x
        )

    def _axis_candidate_y(
        self,
        case: CaseData,
        state: LayoutState,
        width: int,
        depth: int,
        angle: float,
    ) -> list[int]:
        """Return scan-line Y anchors for the baseline constructor."""

        _, min_y, _, max_y = case.warehouse.bounding_box
        theta = math.radians(angle)
        extent = abs(width * math.sin(theta)) + abs(depth * math.cos(theta))
        step = max(int(round(extent)), 100)

        candidates: set[int] = {vertex.y for vertex in case.warehouse.vertices}
        for obstacle in case.obstacles:
            candidates.add(obstacle.y)
            candidates.add(obstacle.y + obstacle.depth)
            candidates.add(int(round(obstacle.y - extent)))
            candidates.add(int(round(obstacle.y + obstacle.depth - extent)))
        for footprint in state.footprints:
            _, y_min, _, y_max = footprint.body_aabb
            candidates.add(int(round(y_min)))
            candidates.add(int(round(y_max)))
            candidates.add(int(round(y_min - extent)))
            candidates.add(int(round(y_max - extent)))

        cursor = min_y
        while cursor <= max_y:
            candidates.add(int(cursor))
            cursor += step
        return sorted(
            value
            for value in candidates
            if min_y - int(extent) <= value <= max_y
        )

    def _select_search_angles(self) -> list[float]:
        """Return the discrete angle set explored by the solver."""

        if self.angle_mode == "fixed-step":
            angles: list[float] = []
            angle = 0.0
            while angle < 360.0 - FLOAT_TOLERANCE:
                angles.append(_snap_to_discrete_angle(angle))
                angle += self.angle_step
            return sorted(set(angles))
        return list(DISCRETE_ANGLES)

    def _configs_for_angles(
        self,
        ranked_types: Iterable[BayType],
        angles: Iterable[float],
    ) -> list[_CandidateConfig]:
        """Create candidate-generation configs for bay types and angles."""

        configs: list[_CandidateConfig] = []
        for angle in angles:
            snapped_angle = _snap_to_discrete_angle(angle)
            for bay_type in ranked_types:
                configs.append(_CandidateConfig(bay_type, snapped_angle, "pair"))
                configs.append(_CandidateConfig(bay_type, snapped_angle, "single"))
        return configs

    def _template(self, bay_type: BayType, angle: float) -> PlacementTemplate:
        """Return a cached placement template."""

        normalized_angle = _snap_to_discrete_angle(angle)
        key = (bay_type.id, normalized_angle)
        template = self._template_cache.get(key)
        if template is None:
            template = PlacementTemplate(bay_type, normalized_angle)
            self._template_cache[key] = template
        return template

    def _generate_candidates(
        self,
        state: LayoutState,
        case: CaseData,
        ctx: CaseContext,
        configs: list[_CandidateConfig],
        deadline: float,
        limit: int,
        per_config_limit: int,
    ) -> list[RowCandidate]:
        """Generate candidate row bundles for the given state."""

        reference_points = self._reference_points(ctx, state)
        current_q = state.score
        best_by_config: dict[tuple[int, float, str], list[RowCandidate]] = {}
        seen: set[tuple[int, float, str, float, float]] = set()

        for config in configs:
            if time.perf_counter() >= deadline:
                break
            primary = self._template(config.bay_type, config.angle)
            partner = None
            if config.kind == "pair":
                partner = self._template(
                    config.bay_type,
                    _opposite_angle(config.angle),
                )
            feature_offsets = (
                primary.pair_feature_offsets
                if config.kind == "pair"
                else primary.single_feature_offsets
            )
            for ref_x, ref_y in reference_points:
                if time.perf_counter() >= deadline:
                    break
                for feature_x, feature_y in feature_offsets:
                    anchor = (ref_x - feature_x, ref_y - feature_y)
                    key = (
                        config.bay_type.id,
                        config.angle,
                        config.kind,
                        round(anchor[0], 6),
                        round(anchor[1], 6),
                    )
                    if key in seen:
                        continue
                    seen.add(key)

                    candidate = self._build_row_candidate(
                        state=state,
                        case=case,
                        ctx=ctx,
                        primary=primary,
                        partner=partner,
                        kind=config.kind,
                        anchor=anchor,
                    )
                    if candidate is None:
                        continue
                    if candidate.resulting_q + FLOAT_TOLERANCE >= current_q:
                        continue

                    bucket_key = (
                        config.bay_type.id,
                        config.angle,
                        config.kind,
                    )
                    bucket = best_by_config.setdefault(bucket_key, [])
                    bucket.append(candidate)
                    bucket.sort(
                        key=lambda row: (
                            row.resulting_q,
                            -row.total_area,
                            -row.slot_count,
                        )
                    )
                    del bucket[per_config_limit:]

        flattened = [
            candidate
            for bucket in best_by_config.values()
            for candidate in bucket
        ]
        flattened.sort(
            key=lambda candidate: (
                candidate.resulting_q,
                -candidate.total_area,
                -candidate.slot_count,
            )
        )
        return flattened[:limit]

    def _reference_points(
        self,
        ctx: CaseContext,
        state: LayoutState,
    ) -> list[tuple[float, float]]:
        """Build dynamic anchor points from the case and current placements."""

        points: list[tuple[float, float]] = []
        seen: set[tuple[float, float]] = set()

        for point in list(ctx.reference_points) + state.anchor_points:
            key = (round(point[0], 6), round(point[1], 6))
            if key in seen:
                continue
            seen.add(key)
            points.append(point)

        for footprint in state.footprints:
            for point in footprint.body + footprint.gap:
                key = (round(point[0], 6), round(point[1], 6))
                if key in seen:
                    continue
                seen.add(key)
                points.append(point)
        for footprint in state.footprints:
            body = footprint.body
            for i in range(len(body)):
                j = (i + 1) % len(body)
                mid = ((body[i][0] + body[j][0]) / 2, (body[i][1] + body[j][1]) / 2)
                key = (round(mid[0], 6), round(mid[1], 6))
                if key not in seen:
                    seen.add(key)
                    points.append(mid)
        return points

    def _build_row_candidate(
        self,
        state: LayoutState,
        case: CaseData,
        ctx: CaseContext,
        primary: PlacementTemplate,
        partner: PlacementTemplate | None,
        kind: str,
        anchor: tuple[float, float],
    ) -> RowCandidate | None:
        """Build a candidate row starting from ``anchor``."""

        bay_type = primary.bay_type
        step_x = primary.tangent[0] * (bay_type.depth + bay_type.gap)
        step_y = primary.tangent[1] * (bay_type.depth + bay_type.gap)
        cursor_x, cursor_y = anchor

        temporary: list = []
        slot_count = 0
        total_area = 0.0
        total_price = 0.0
        total_loads = 0

        while slot_count < MAX_ROW_SLOTS:
            slot_footprints = [primary.place(cursor_x, cursor_y)]
            if kind == "pair" and partner is not None:
                partner_anchor = (cursor_x + step_x, cursor_y + step_y)
                slot_footprints.append(partner.place(*partner_anchor))

            slot_valid = True
            slot_temp: list = []
            for footprint in slot_footprints:
                if not is_valid_placement(
                    footprint=footprint,
                    ctx=ctx,
                    existing=state.footprints,
                    state=state,
                    extra=temporary + slot_temp,
                ):
                    slot_valid = False
                    break
                slot_temp.append(footprint)
            if not slot_valid:
                break

            temporary.extend(slot_temp)
            slot_count += 1
            total_area += sum(
                footprint.template.bay_type.area
                for footprint in slot_temp
            )
            total_price += sum(
                footprint.template.bay_type.price
                for footprint in slot_temp
            )
            total_loads += sum(
                footprint.template.bay_type.n_loads
                for footprint in slot_temp
            )
            cursor_x += step_x
            cursor_y += step_y

        if slot_count == 0:
            return None

        resulting_q = score_from_totals(
            total_area=state.total_area + total_area,
            total_price=state.total_price + total_price,
            total_loads=state.total_loads + total_loads,
            warehouse_area=case.warehouse.area,
        )
        line_points = self._row_line_points(primary, kind, anchor, slot_count)
        return RowCandidate(
            kind=kind,
            bay_type_id=bay_type.id,
            angle=primary.angle,
            anchor=anchor,
            slot_count=slot_count,
            footprints=tuple(temporary),
            total_area=total_area,
            total_price=total_price,
            total_loads=total_loads,
            resulting_q=resulting_q,
            delta_q=state.score - resulting_q,
            line_points=line_points,
        )

    def _row_line_points(
        self,
        primary: PlacementTemplate,
        kind: str,
        anchor: tuple[float, float],
        slot_count: int,
    ) -> tuple[tuple[float, float], ...]:
        """Return guide points describing a row envelope."""

        bay_type = primary.bay_type
        span_x = primary.tangent[0] * (bay_type.depth + bay_type.gap) * slot_count
        span_y = primary.tangent[1] * (bay_type.depth + bay_type.gap) * slot_count
        normal = primary.front_normal
        far = bay_type.width

        back_start = anchor
        back_end = (anchor[0] + span_x, anchor[1] + span_y)
        pos_front_start = (
            anchor[0] + far * normal[0],
            anchor[1] + far * normal[1],
        )
        pos_front_end = (
            pos_front_start[0] + span_x,
            pos_front_start[1] + span_y,
        )

        if kind == "single":
            return (
                back_start,
                back_end,
                pos_front_start,
                pos_front_end,
            )

        neg_front_start = (
            anchor[0] - far * normal[0],
            anchor[1] - far * normal[1],
        )
        neg_front_end = (
            neg_front_start[0] + span_x,
            neg_front_start[1] + span_y,
        )
        return (
            back_start,
            back_end,
            pos_front_start,
            pos_front_end,
            neg_front_start,
            neg_front_end,
        )

    def _top_states(
        self,
        states: list[LayoutState],
        limit: int,
    ) -> list[LayoutState]:
        """Keep the best unique states."""

        states.sort(
            key=lambda state: (
                state.score,
                -state.coverage,
                -len(state.footprints),
                len(state.rows),
            )
        )
        unique: list[LayoutState] = []
        seen: set[tuple[tuple[int, float, float, float], ...]] = set()
        for state in states:
            signature = self._state_signature(state)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(state)
            if len(unique) >= limit:
                break
        return unique

    def _refine_solution(
        self,
        state: LayoutState,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
    ) -> LayoutState:
        """Run a deterministic row-replacement refinement."""

        current = state
        filler_types = (
            sorted(
                ranked_types,
                key=lambda bay_type: (
                    bay_type.area,
                    bay_type.price / bay_type.n_loads,
                    bay_type.id,
                ),
            )[:4]
            + ranked_types[:4]
        )
        fine_angles = self._select_search_angles()
        per_pass_deadline = max(0.5, self.time_budget * REFINEMENT_TIME_FRACTION)

        while time.perf_counter() < deadline:
            improved = False

            filler_candidates = self._generate_candidates(
                state=current,
                case=case,
                ctx=ctx,
                configs=self._configs_for_angles(filler_types, fine_angles),
                deadline=min(deadline, time.perf_counter() + per_pass_deadline),
                limit=2,
                per_config_limit=1,
            )
            if (
                filler_candidates
                and filler_candidates[0].resulting_q + FLOAT_TOLERANCE
                < current.score
            ):
                current = current.with_candidate(filler_candidates[0])
                improved = True
                continue

            for row_index, row in enumerate(list(current.rows)):
                if time.perf_counter() >= deadline:
                    break
                base_state = self._rebuild_without_row(current, row_index, case, ctx)
                neighborhood = self._row_neighborhood_candidates(
                    row=row,
                    state=base_state,
                    case=case,
                    ctx=ctx,
                    ranked_types=ranked_types,
                    deadline=min(deadline, time.perf_counter() + per_pass_deadline),
                )
                if (
                    neighborhood
                    and neighborhood[0].resulting_q + FLOAT_TOLERANCE
                    < current.score
                ):
                    current = base_state.with_candidate(neighborhood[0])
                    improved = True
                    break

            if not improved:
                break

        return current

    def _rebuild_without_row(
        self,
        state: LayoutState,
        row_index: int,
        case: CaseData,
        ctx: CaseContext,
    ) -> LayoutState:
        """Rebuild a state without a given row."""

        rebuilt = build_empty_state(case.warehouse.area, ctx.cell_size)
        for index, row in enumerate(state.rows):
            if index == row_index:
                continue
            rebuilt.rows.append(row)
            for placement in row.placements:
                bay_type = case.bay_type_map[placement.bay_type_id]
                template = self._template(bay_type, placement.rotation)
                footprint = template.place(placement.x, placement.y)
                footprint_index = len(rebuilt.footprints)
                rebuilt.footprints.append(footprint)
                rebuilt.body_hash.add(footprint.body_aabb, footprint_index)
                if footprint.gap_aabb is not None:
                    rebuilt.gap_hash.add(footprint.gap_aabb, footprint_index)
                rebuilt.total_area += bay_type.area
                rebuilt.total_price += bay_type.price
                rebuilt.total_loads += bay_type.n_loads
        return rebuilt

    def _row_neighborhood_candidates(
        self,
        row,
        state: LayoutState,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
    ) -> list[RowCandidate]:
        """Generate replacement candidates around an existing row."""

        bay_type = case.bay_type_map[row.bay_type_id]
        current_anchor = row.anchor
        base_template = self._template(bay_type, row.angle)
        shift_u = (
            base_template.front_normal[0] * bay_type.width,
            base_template.front_normal[1] * bay_type.width,
        )
        shift_v = (
            base_template.tangent[0] * (bay_type.depth + bay_type.gap),
            base_template.tangent[1] * (bay_type.depth + bay_type.gap),
        )
        anchor_points = [
            current_anchor,
            (current_anchor[0] + shift_u[0], current_anchor[1] + shift_u[1]),
            (current_anchor[0] - shift_u[0], current_anchor[1] - shift_u[1]),
            (current_anchor[0] + shift_v[0], current_anchor[1] + shift_v[1]),
            (current_anchor[0] - shift_v[0], current_anchor[1] - shift_v[1]),
            *row.line_points,
        ]
        anchor_points.extend(
            self._nearest_reference_points(ctx.reference_points, current_anchor, 8)
        )

        candidate_types = [bay_type] + [
            other
            for other in ranked_types[:4]
            if other.id != bay_type.id
        ]
        candidate_angles = sorted(
            {
                row.angle,
                _normalize_angle(row.angle - ANGLE_STEP_DEGREES),
                _normalize_angle(row.angle + ANGLE_STEP_DEGREES),
            }
        )

        best: list[RowCandidate] = []
        seen: set[tuple[int, float, str, float, float]] = set()
        for kind in (row.kind, "single" if row.kind == "pair" else "pair"):
            for angle in candidate_angles:
                if time.perf_counter() >= deadline:
                    break
                for candidate_type in candidate_types:
                    primary = self._template(candidate_type, angle)
                    partner = None
                    if kind == "pair":
                        partner = self._template(
                            candidate_type,
                            _opposite_angle(angle),
                        )
                    for anchor in anchor_points:
                        key = (
                            candidate_type.id,
                            angle,
                            kind,
                            round(anchor[0], 6),
                            round(anchor[1], 6),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        candidate = self._build_row_candidate(
                            state=state,
                            case=case,
                            ctx=ctx,
                            primary=primary,
                            partner=partner,
                            kind=kind,
                            anchor=anchor,
                        )
                        if candidate is None:
                            continue
                        best.append(candidate)
                        best.sort(
                            key=lambda row_candidate: (
                                row_candidate.resulting_q,
                                -row_candidate.total_area,
                                -row_candidate.slot_count,
                            )
                        )
                        del best[3:]
        return best

    def _nearest_reference_points(
        self,
        reference_points: tuple[tuple[float, float], ...],
        anchor: tuple[float, float],
        limit: int,
    ) -> list[tuple[float, float]]:
        """Return the closest cached reference points to ``anchor``."""

        points = sorted(
            reference_points,
            key=lambda point: (
                point[0] - anchor[0]
            ) ** 2 + (
                point[1] - anchor[1]
            ) ** 2,
        )
        return list(points[:limit])


    def _fill_gaps(
        self,
        state: LayoutState,
        case: CaseData,
        ctx: CaseContext,
        deadline: float,
    ) -> LayoutState:
        """Greedily fill remaining gaps with individual bays."""

        current = state
        small_first = sorted(
            case.bay_types,
            key=lambda bt: (bt.area, bt.price / bt.n_loads, bt.id),
        )

        while time.perf_counter() < deadline:
            improved = False
            for bt in small_first:
                for angle in self._select_search_angles():
                    if time.perf_counter() >= deadline:
                        return current
                    template = self._template(bt, angle)
                    xs = self._axis_candidate_x(
                        case=case, state=current,
                        width=bt.width, depth=bt.depth, angle=angle,
                    )
                    ys = self._axis_candidate_y(
                        case=case, state=current,
                        width=bt.width, depth=bt.depth, angle=angle,
                    )
                    for y_coord in ys:
                        if time.perf_counter() >= deadline:
                            return current
                        for x_coord in xs:
                            fp = template.place(float(x_coord), float(y_coord))
                            if not is_valid_placement(
                                footprint=fp,
                                ctx=ctx,
                                existing=current.footprints,
                                state=current,
                            ):
                                continue
                            new_q = score_from_totals(
                                current.total_area + bt.area,
                                current.total_price + bt.price,
                                current.total_loads + bt.n_loads,
                                case.warehouse.area,
                            )
                            if new_q + FLOAT_TOLERANCE < current.score:
                                self._append_footprint(current, fp)
                                improved = True
            if not improved:
                break
        return current


__all__ = ["HybridSolver", "SolverRunStats"]
