"""Hybrid warehouse solver with axis sweep, row search, and angle refinement."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time

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


def _normalized_angle(angle: float) -> float:
    if abs(angle - 180.0) < 1e-9:
        return 180.0
    angle = angle % 180.0
    if abs(angle) < 1e-9:
        return 0.0
    return round(angle, 6)


@dataclass(frozen=True, slots=True)
class _CandidateConfig:
    bay_type: BayType
    angle: float
    kind: str


class HybridSolver(BaseSolver):
    """Hybrid constructive solver with deterministic refinement."""

    def __init__(
        self,
        angle_step: float = 15.0,
        angle_mode: str = "hybrid",
        time_budget: float = 29.0,
        seed: int = 0,
        beam_width: int = 6,
        candidate_limit: int = 8,
    ):
        self.angle_step = angle_step
        self.angle_mode = angle_mode
        self.time_budget = time_budget
        self.seed = seed
        self.beam_width = beam_width
        self.candidate_limit = candidate_limit
        self._template_cache: dict[tuple[int, float], PlacementTemplate] = {}

    def solve(self, case: CaseData) -> Solution:
        ctx = build_case_context(case)
        ranked_types = self._ranked_types(case)
        deadline = time.perf_counter() + self.time_budget
        axis_budget = max(4.0, min(22.0, self.time_budget * 0.75))
        axis_deadline = min(deadline, time.perf_counter() + axis_budget)
        axis_state = self._solve_axis_sweep(case, ctx, ranked_types, axis_deadline)

        if time.perf_counter() >= deadline:
            return axis_state.solution

        row_state = self._solve_row_hybrid(
            case,
            ctx,
            ranked_types,
            deadline,
            initial_states=[axis_state, build_empty_state(case.warehouse.area, ctx.cell_size)],
        )
        best = row_state if row_state.score < axis_state.score else axis_state
        best = self._probe_non_cardinal(best, case, ctx, ranked_types, deadline)
        return best.solution

    def _solve_row_hybrid(
        self,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
        initial_states: list[LayoutState] | None = None,
    ) -> LayoutState:
        constructive_deadline = deadline - min(6.0, max(3.0, self.time_budget * 0.18))
        if constructive_deadline <= time.perf_counter():
            constructive_deadline = deadline

        search_angles = self._select_search_angles(case, ctx, ranked_types, constructive_deadline)
        if initial_states:
            beam = self._top_states(list(initial_states), self.beam_width)
        else:
            beam = [build_empty_state(case.warehouse.area, ctx.cell_size)]
        best = min(
            beam,
            key=lambda state: (state.score, -state.coverage, -len(state.placements)),
        )

        while time.perf_counter() < constructive_deadline:
            next_states: list[LayoutState] = []
            improved = False
            for state in beam:
                candidates = self._generate_candidates(
                    state=state,
                    case=case,
                    ctx=ctx,
                    configs=self._configs_for_angles(ranked_types, search_angles),
                    deadline=constructive_deadline,
                    limit=self.candidate_limit,
                )
                for candidate in candidates:
                    if candidate.resulting_q + 1e-9 >= state.score:
                        continue
                    improved = True
                    next_states.append(state.with_candidate(candidate))
            if not improved or not next_states:
                break
            beam = self._top_states(next_states, self.beam_width)
            if beam and beam[0].score < best.score:
                best = beam[0]

        best = self._refine_solution(best, case, ctx, ranked_types, deadline)
        return best

    def _probe_non_cardinal(
        self,
        state: LayoutState,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
    ) -> LayoutState:
        if time.perf_counter() >= deadline:
            return state
        non_card_angles = [
            angle for angle in self._all_angles_from_rows(state.rows)
            if angle not in (0.0, 90.0, 180.0)
        ]
        if not non_card_angles:
            non_card_angles = [15.0, 30.0, 45.0, 60.0, 75.0, 105.0, 120.0, 135.0, 150.0, 165.0]

        candidates = self._generate_candidates(
            state=state,
            case=case,
            ctx=ctx,
            configs=self._configs_for_angles(ranked_types, non_card_angles),
            deadline=min(deadline, time.perf_counter() + 2.0),
            limit=4,
        )
        if not candidates:
            return state

        improved = state.with_candidate(candidates[0])
        if time.perf_counter() >= deadline:
            return improved
        refined = self._refine_solution(improved, case, ctx, ranked_types, deadline)
        return refined if refined.score < state.score else state

    def _ranked_types(self, case: CaseData) -> list[BayType]:
        ranked = sorted(
            case.bay_types,
            key=lambda bt: (bt.price / bt.n_loads, -bt.area, bt.height, bt.id),
        )
        if not case.obstacles and len(ranked) > 10:
            return ranked[:10]
        if len(ranked) <= 14:
            return ranked

        top = ranked[:12]
        fillers = sorted(case.bay_types, key=lambda bt: (bt.area, bt.price / bt.n_loads, bt.id))[:4]
        seen: set[int] = set()
        result: list[BayType] = []
        for bt in top + fillers:
            if bt.id in seen:
                continue
            seen.add(bt.id)
            result.append(bt)
        return result

    def _solve_axis_sweep(
        self,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
    ) -> LayoutState:
        configs = [
            (bt, angle)
            for bt in ranked_types
            for angle in (0.0, 90.0, 180.0)
        ]
        primary_limit = min(10, len(configs))
        best = build_empty_state(case.warehouse.area, ctx.cell_size)

        for primary_bt, primary_angle in configs[:primary_limit]:
            if time.perf_counter() >= deadline:
                break
            state = build_empty_state(case.warehouse.area, ctx.cell_size)
            primary = self._template(primary_bt, primary_angle)
            self._axis_scan_and_place(case, ctx, state, primary, deadline)
            for bay_type, angle in configs:
                if time.perf_counter() >= deadline:
                    break
                template = self._template(bay_type, angle)
                self._axis_scan_and_place(case, ctx, state, template, deadline)
            if state.score < best.score:
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
        bt = template.bay_type
        xs = self._axis_candidate_x(case, state, bt.width, bt.depth, template.angle)
        ys = self._axis_candidate_y(case, state, bt.width, bt.depth, template.angle)
        for y in ys:
            if time.perf_counter() >= deadline:
                return
            for x in xs:
                footprint = template.place(float(x), float(y))
                if not is_valid_placement(
                    footprint,
                    ctx,
                    state.footprints,
                    state=state,
                ):
                    continue
                self._append_footprint(state, footprint)

    def _append_footprint(self, state: LayoutState, footprint) -> None:
        idx = len(state.footprints)
        state.footprints.append(footprint)
        state.body_hash.add(footprint.body_aabb, idx)
        if footprint.gap_aabb is not None:
            state.gap_hash.add(footprint.gap_aabb, idx)
        bt = footprint.template.bay_type
        state.total_area += bt.area
        state.total_price += bt.price
        state.total_loads += bt.n_loads

    def _axis_candidate_x(
        self,
        case: CaseData,
        state: LayoutState,
        width: int,
        depth: int,
        angle: float,
    ) -> list[int]:
        min_x, _, max_x, _ = case.warehouse.bounding_box
        theta = math.radians(angle)
        extent = abs(width * math.cos(theta)) + abs(depth * math.sin(theta))
        step = max(int(round(extent)), 100)

        xs: set[int] = set()
        for vertex in case.warehouse.vertices:
            xs.add(vertex.x)
        for obs in case.obstacles:
            xs.add(obs.x)
            xs.add(obs.x + obs.width)
            xs.add(int(round(obs.x - extent)))
            xs.add(int(round(obs.x + obs.width - extent)))
        for footprint in state.footprints:
            x_min, _, x_max, _ = footprint.body_aabb
            xs.add(int(round(x_min)))
            xs.add(int(round(x_max)))
            xs.add(int(round(x_min - extent)))
            xs.add(int(round(x_max - extent)))

        x = min_x
        while x <= max_x:
            xs.add(int(x))
            x += step
        return sorted(x for x in xs if min_x - int(extent) <= x <= max_x)

    def _axis_candidate_y(
        self,
        case: CaseData,
        state: LayoutState,
        width: int,
        depth: int,
        angle: float,
    ) -> list[int]:
        _, min_y, _, max_y = case.warehouse.bounding_box
        theta = math.radians(angle)
        extent = abs(width * math.sin(theta)) + abs(depth * math.cos(theta))
        step = max(int(round(extent)), 100)

        ys: set[int] = set()
        for vertex in case.warehouse.vertices:
            ys.add(vertex.y)
        for obs in case.obstacles:
            ys.add(obs.y)
            ys.add(obs.y + obs.depth)
            ys.add(int(round(obs.y - extent)))
            ys.add(int(round(obs.y + obs.depth - extent)))
        for footprint in state.footprints:
            _, y_min, _, y_max = footprint.body_aabb
            ys.add(int(round(y_min)))
            ys.add(int(round(y_max)))
            ys.add(int(round(y_min - extent)))
            ys.add(int(round(y_max - extent)))

        y = min_y
        while y <= max_y:
            ys.add(int(y))
            y += step
        return sorted(y for y in ys if min_y - int(extent) <= y <= max_y)

    def _configs_for_angles(
        self,
        ranked_types: list[BayType],
        angles: list[float],
    ) -> list[_CandidateConfig]:
        configs: list[_CandidateConfig] = []
        for angle in angles:
            for bt in ranked_types:
                configs.append(_CandidateConfig(bt, angle, "pair"))
                configs.append(_CandidateConfig(bt, angle, "single"))
        return configs

    def _select_search_angles(
        self,
        case: CaseData,
        ctx: CaseContext,
        ranked_types: list[BayType],
        deadline: float,
    ) -> list[float]:
        if self.angle_mode == "fixed-step":
            angles: list[float] = []
            angle = 0.0
            while angle < 180.0 + 1e-9:
                angles.append(_normalized_angle(angle))
                angle += self.angle_step
            if 180.0 not in angles:
                angles.append(180.0)
            return sorted(set(angles))

        coarse = [0.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0]
        previews: list[tuple[float, float]] = []
        empty_state = build_empty_state(case.warehouse.area, ctx.cell_size)
        preview_deadline = min(deadline, time.perf_counter() + 3.0)
        for angle in coarse:
            configs = self._configs_for_angles(ranked_types[:4], [angle])
            candidates = self._generate_candidates(
                state=empty_state,
                case=case,
                ctx=ctx,
                configs=configs,
                deadline=preview_deadline,
                limit=1,
            )
            best_q = candidates[0].resulting_q if candidates else float("inf")
            previews.append((best_q, angle))

        previews.sort()
        selected = {angle for _, angle in previews[:3]}
        fine = set(coarse)
        for angle in selected:
            for delta in (-15.0, 15.0):
                candidate = angle + delta
                if 0.0 <= candidate <= 180.0:
                    fine.add(round(candidate, 6))
        return sorted(fine)

    def _template(self, bay_type: BayType, angle: float) -> PlacementTemplate:
        key = (bay_type.id, angle)
        template = self._template_cache.get(key)
        if template is None:
            template = PlacementTemplate(bay_type, angle)
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
    ) -> list[RowCandidate]:
        reference_points = self._reference_points(ctx, state)
        current_q = state.score
        best_by_config: dict[tuple[int, float, str], RowCandidate] = {}
        seen: set[tuple[int, float, str, float, float]] = set()

        for config in configs:
            if time.perf_counter() >= deadline:
                break
            primary = self._template(config.bay_type, config.angle)
            partner = None
            if config.kind == "pair":
                partner_angle = 0.0 if abs(config.angle - 180.0) < 1e-9 else _normalized_angle(config.angle + 180.0)
                partner = self._template(config.bay_type, partner_angle)
            feature_offsets = (
                primary.pair_feature_offsets if config.kind == "pair" else primary.single_feature_offsets
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
                    if candidate is None or candidate.resulting_q + 1e-9 >= current_q:
                        continue
                    config_key = (config.bay_type.id, config.angle, config.kind)
                    incumbent = best_by_config.get(config_key)
                    if incumbent is None or (
                        candidate.resulting_q,
                        -candidate.total_area,
                        -candidate.slot_count,
                    ) < (
                        incumbent.resulting_q,
                        -incumbent.total_area,
                        -incumbent.slot_count,
                    ):
                        best_by_config[config_key] = candidate
        best = sorted(
            best_by_config.values(),
            key=lambda cand: (cand.resulting_q, -cand.total_area, -cand.slot_count),
        )
        return best[:limit]

    def _reference_points(self, ctx: CaseContext, state: LayoutState) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        seen: set[tuple[float, float]] = set()
        for point in list(ctx.reference_points) + state.anchor_points:
            key = (round(point[0], 6), round(point[1], 6))
            if key in seen:
                continue
            seen.add(key)
            points.append(point)
        for footprint in state.footprints:
            for point in footprint.body:
                key = (round(point[0], 6), round(point[1], 6))
                if key in seen:
                    continue
                seen.add(key)
                points.append(point)
            for point in footprint.gap:
                key = (round(point[0], 6), round(point[1], 6))
                if key in seen:
                    continue
                seen.add(key)
                points.append(point)
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
        bt = primary.bay_type
        step_x = primary.tangent[0] * bt.depth
        step_y = primary.tangent[1] * bt.depth
        cursor_x, cursor_y = anchor
        temp: list = []
        slot_count = 0
        total_area = 0.0
        total_price = 0.0
        total_loads = 0

        while slot_count < 2048:
            slot_footprints = [primary.place(cursor_x, cursor_y)]
            if kind == "pair":
                partner_anchor = (cursor_x + step_x, cursor_y + step_y)
                slot_footprints.append(partner.place(*partner_anchor))

            slot_valid = True
            slot_temp: list = []
            for footprint in slot_footprints:
                if not is_valid_placement(
                    footprint,
                    ctx,
                    state.footprints,
                    state=state,
                    extra=temp + slot_temp,
                ):
                    slot_valid = False
                    break
                slot_temp.append(footprint)
            if not slot_valid:
                break

            temp.extend(slot_temp)
            slot_count += 1
            total_area += sum(fp.template.bay_type.area for fp in slot_temp)
            total_price += sum(fp.template.bay_type.price for fp in slot_temp)
            total_loads += sum(fp.template.bay_type.n_loads for fp in slot_temp)
            cursor_x += step_x
            cursor_y += step_y

        if slot_count == 0:
            return None

        resulting_q = score_from_totals(
            state.total_area + total_area,
            state.total_price + total_price,
            state.total_loads + total_loads,
            case.warehouse.area,
        )
        line_points = self._row_line_points(primary, kind, anchor, slot_count)
        return RowCandidate(
            kind=kind,
            bay_type_id=bt.id,
            angle=primary.angle,
            anchor=anchor,
            slot_count=slot_count,
            footprints=tuple(temp),
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
        bt = primary.bay_type
        span_x = primary.tangent[0] * bt.depth * slot_count
        span_y = primary.tangent[1] * bt.depth * slot_count
        u = primary.front_normal
        far = bt.width + bt.gap

        back_start = anchor
        back_end = (anchor[0] + span_x, anchor[1] + span_y)
        pos_front_start = (anchor[0] + far * u[0], anchor[1] + far * u[1])
        pos_front_end = (pos_front_start[0] + span_x, pos_front_start[1] + span_y)

        if kind == "single":
            return (
                back_start,
                back_end,
                pos_front_start,
                pos_front_end,
            )

        neg_front_start = (anchor[0] - far * u[0], anchor[1] - far * u[1])
        neg_front_end = (neg_front_start[0] + span_x, neg_front_start[1] + span_y)
        return (
            back_start,
            back_end,
            pos_front_start,
            pos_front_end,
            neg_front_start,
            neg_front_end,
        )

    def _top_states(self, states: list[LayoutState], limit: int) -> list[LayoutState]:
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
            signature = tuple(
                sorted(
                    (
                        p.bay_type_id,
                        round(p.x, 6),
                        round(p.y, 6),
                        round(p.rotation, 6),
                    )
                    for p in state.placements
                )
            )
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
        current = state
        filler_types = sorted(ranked_types, key=lambda bt: (bt.area, bt.price / bt.n_loads, bt.id))[:4] + ranked_types[:4]
        fine_angles = self._all_angles_from_rows(current.rows)
        if not fine_angles:
            fine_angles = [0.0, 15.0, 30.0, 45.0, 60.0, 90.0, 120.0, 135.0, 150.0, 165.0, 180.0]

        while time.perf_counter() < deadline:
            improved = False

            filler_candidates = self._generate_candidates(
                state=current,
                case=case,
                ctx=ctx,
                configs=self._configs_for_angles(filler_types, fine_angles),
                deadline=min(deadline, time.perf_counter() + 1.0),
                limit=2,
            )
            if filler_candidates and filler_candidates[0].resulting_q + 1e-9 < current.score:
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
                    deadline=min(deadline, time.perf_counter() + 1.0),
                )
                if neighborhood and neighborhood[0].resulting_q + 1e-9 < current.score:
                    current = base_state.with_candidate(neighborhood[0])
                    improved = True
                    break

            if not improved:
                break

        return current

    def _all_angles_from_rows(self, rows) -> list[float]:
        angles = {0.0, 90.0, 180.0}
        for row in rows:
            angles.add(_normalized_angle(row.angle))
            for delta in (-15.0, 15.0, -7.5, 7.5):
                candidate = row.angle + delta
                if 0.0 <= candidate <= 180.0:
                    angles.add(round(candidate, 6))
        return sorted(angles)

    def _rebuild_without_row(
        self,
        state: LayoutState,
        row_index: int,
        case: CaseData,
        ctx: CaseContext,
    ) -> LayoutState:
        rebuilt = build_empty_state(case.warehouse.area, ctx.cell_size)
        for idx, row in enumerate(state.rows):
            if idx == row_index:
                continue
            rebuilt.rows.append(row)
            for placement in row.placements:
                bt = case.bay_type_map[placement.bay_type_id]
                template = self._template(bt, placement.rotation)
                footprint = template.place(placement.x, placement.y)
                fp_idx = len(rebuilt.footprints)
                rebuilt.footprints.append(footprint)
                rebuilt.body_hash.add(footprint.body_aabb, fp_idx)
                if footprint.gap_aabb is not None:
                    rebuilt.gap_hash.add(footprint.gap_aabb, fp_idx)
                rebuilt.total_area += bt.area
                rebuilt.total_price += bt.price
                rebuilt.total_loads += bt.n_loads
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
        bt = case.bay_type_map[row.bay_type_id]
        current_anchor = row.anchor
        base_template = self._template(bt, row.angle)
        shift_u = (
            base_template.front_normal[0] * (bt.width + bt.gap),
            base_template.front_normal[1] * (bt.width + bt.gap),
        )
        shift_v = (
            base_template.tangent[0] * bt.depth,
            base_template.tangent[1] * bt.depth,
        )
        anchor_points = [
            current_anchor,
            (current_anchor[0] + shift_u[0], current_anchor[1] + shift_u[1]),
            (current_anchor[0] - shift_u[0], current_anchor[1] - shift_u[1]),
            (current_anchor[0] + shift_v[0], current_anchor[1] + shift_v[1]),
            (current_anchor[0] - shift_v[0], current_anchor[1] - shift_v[1]),
            *row.line_points,
        ]
        anchor_points.extend(self._nearest_reference_points(ctx.reference_points, current_anchor, 8))

        candidate_types = [bt] + [other for other in ranked_types[:4] if other.id != bt.id]
        candidate_angles = sorted(
            {
                row.angle,
                *[
                    round(candidate, 6)
                    for candidate in (row.angle - 15.0, row.angle + 15.0, row.angle - 7.5, row.angle + 7.5)
                    if 0.0 <= candidate <= 180.0
                ],
            }
        )

        best: list[RowCandidate] = []
        seen: set[tuple[int, float, str, float, float]] = set()
        for kind in (row.kind, "single" if row.kind == "pair" else "pair"):
            for angle in candidate_angles:
                if time.perf_counter() >= deadline:
                    break
                for bay_type in candidate_types:
                    primary = self._template(bay_type, angle)
                    partner = None
                    if kind == "pair":
                        partner_angle = 0.0 if abs(angle - 180.0) < 1e-9 else _normalized_angle(angle + 180.0)
                        partner = self._template(bay_type, partner_angle)
                    for anchor in anchor_points:
                        key = (
                            bay_type.id,
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
                        best.sort(key=lambda cand: (cand.resulting_q, -cand.total_area, -cand.slot_count))
                        if len(best) > 3:
                            best.pop()
        return best

    def _nearest_reference_points(
        self,
        reference_points: tuple[tuple[float, float], ...],
        anchor: tuple[float, float],
        limit: int,
    ) -> list[tuple[float, float]]:
        points = sorted(
            reference_points,
            key=lambda point: (point[0] - anchor[0]) ** 2 + (point[1] - anchor[1]) ** 2,
        )
        return list(points[:limit])
