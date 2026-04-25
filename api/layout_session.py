"""Stateful in-memory layout cache for real-time edits."""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass, field

from api_models import LayoutBay, LayoutResponse
from api_config import (
    ANGLE_STEP_DEGREES,
    FULL_TURN_DEGREES,
    LAYOUT_EMPTY_MESSAGE,
    LAYOUT_UPDATED_MESSAGE,
)

_BACKEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.case_data import CaseData
from models.solution import PlacedBay, Solution
from solver.layout import PlacementTemplate, PlacedFootprint, score_from_totals
from solver.spatial_hash import SpatialHash
from validation.rules import CaseContext, build_case_context, placement_violations


def snap_rotation(angle: float) -> float:
    """Snap ``angle`` to the nearest allowed 30-degree rotation."""

    snapped = round(angle / ANGLE_STEP_DEGREES) * ANGLE_STEP_DEGREES
    snapped %= FULL_TURN_DEGREES
    if abs(snapped - FULL_TURN_DEGREES) < 1e-9:
        snapped = 0.0
    if abs(snapped) < 1e-9:
        return 0.0
    return round(snapped, 6)


@dataclass(slots=True)
class _HashStateView:
    """Small view object expected by the shared validation helpers."""

    body_hash: SpatialHash
    gap_hash: SpatialHash


@dataclass(slots=True)
class SessionBay:
    """Mutable bay stored inside a live layout session."""

    instance_id: str
    slot_index: int
    footprint: PlacedFootprint
    issues: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Return whether the bay currently satisfies all constraints."""

        return not self.issues

    def to_model(self) -> LayoutBay:
        """Serialize the bay for API responses."""

        placement = self.footprint.placement
        return LayoutBay(
            instance_id=self.instance_id,
            bay_type_id=placement.bay_type_id,
            x=placement.x,
            y=placement.y,
            rotation=placement.rotation,
            valid=self.valid,
            issues=list(self.issues),
        )


class StatefulLayoutSession:
    """Stateful layout cache supporting incremental move/rotate/delete."""

    def __init__(
        self,
        case: CaseData,
        session_id: str | None = None,
    ) -> None:
        self.case = case
        self.session_id = session_id or str(uuid.uuid4())
        self.ctx: CaseContext = build_case_context(case)
        self._templates: dict[tuple[int, float], PlacementTemplate] = {}
        self._slots: list[SessionBay | None] = []
        self._footprints: list[PlacedFootprint | None] = []
        self._slot_by_id: dict[str, int] = {}
        self._body_hash = SpatialHash(cell_size=self.ctx.cell_size)
        self._gap_hash = SpatialHash(cell_size=self.ctx.cell_size)
        self._state_view = _HashStateView(
            body_hash=self._body_hash,
            gap_hash=self._gap_hash,
        )
        self._lock = asyncio.Lock()
        self.total_area = 0.0
        self.total_price = 0.0
        self.total_loads = 0
        now = time.monotonic()
        self.created_at = now
        self.last_accessed_at = now

    @classmethod
    def from_solution(
        cls,
        case: CaseData,
        solution: Solution,
        session_id: str | None = None,
    ) -> StatefulLayoutSession:
        """Build a live session from a backend optimization result."""

        session = cls(case=case, session_id=session_id)
        for index, placement in enumerate(solution.placements, start=1):
            bay_id = f"bay-{index:04d}"
            session._insert_new_bay(bay_id=bay_id, placement=placement)
        session._refresh_validity(session.active_slot_indices())
        session.touch()
        return session

    def touch(self) -> None:
        """Refresh the last-access timestamp."""

        self.last_accessed_at = time.monotonic()

    def is_expired(self, expiry_seconds: float) -> bool:
        """Return whether the session has passed the inactivity timeout."""

        return (time.monotonic() - self.last_accessed_at) > expiry_seconds

    @property
    def bay_count(self) -> int:
        """Return the number of active bays."""

        return len(self._slot_by_id)

    @property
    def coverage(self) -> float:
        """Return the current bay-area coverage."""

        warehouse_area = self.case.warehouse.area
        if warehouse_area <= 0:
            return 0.0
        return self.total_area / warehouse_area

    @property
    def q_value(self) -> float | None:
        """Return the current challenge score."""

        if self.total_loads <= 0 or self.case.warehouse.area <= 0:
            return None
        return round(
            score_from_totals(
                total_area=self.total_area,
                total_price=self.total_price,
                total_loads=self.total_loads,
                warehouse_area=self.case.warehouse.area,
            ),
            6,
        )

    @property
    def valid(self) -> bool:
        """Return whether the full layout is currently valid."""

        if self.bay_count == 0:
            return False
        return all(bay.valid for bay in self.active_bays())

    def active_bays(self) -> list[SessionBay]:
        """Return all active bays in stable slot order."""

        return [bay for bay in self._slots if bay is not None]

    def active_slot_indices(self) -> set[int]:
        """Return the active slot indices."""

        return set(self._slot_by_id.values())

    def snapshot(
        self,
        message: str,
        solved_in_ms: int | None = None,
        latency_ms: float | None = None,
    ) -> LayoutResponse:
        """Return the current layout snapshot."""

        bays = [bay.to_model() for bay in self.active_bays()]
        if self.bay_count == 0:
            message = LAYOUT_EMPTY_MESSAGE
        elif not self.valid and message == LAYOUT_UPDATED_MESSAGE:
            invalid_count = sum(1 for bay in bays if not bay.valid)
            message = f"{invalid_count} bay(s) violate the constraints."

        return LayoutResponse(
            session_id=self.session_id,
            valid=self.valid,
            Q=self.q_value,
            coverage=round(self.coverage, 6),
            bay_count=self.bay_count,
            total_loads=self.total_loads,
            total_bay_area=self.total_area,
            solved_in_ms=solved_in_ms,
            latency_ms=round(latency_ms, 3) if latency_ms is not None else None,
            message=message,
            bays=bays,
        )

    async def move_bay(self, bay_id: str, x: float, y: float) -> LayoutResponse:
        """Move a bay and revalidate only the affected neighborhood."""

        started_at = time.perf_counter()
        async with self._lock:
            slot_index = self._require_slot_index(bay_id)
            bay = self._require_bay(slot_index)
            placement = bay.footprint.placement
            updated = self._build_footprint(
                bay_type_id=placement.bay_type_id,
                x=x,
                y=y,
                rotation=placement.rotation,
            )
            self._replace_footprint(slot_index, updated)
            self.touch()
            message = self._message_for_slot(slot_index)
            return self.snapshot(
                message=message,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
            )

    async def rotate_bay(
        self,
        bay_id: str,
        rotation: float,
    ) -> LayoutResponse:
        """Rotate a bay and revalidate only the affected neighborhood."""

        started_at = time.perf_counter()
        async with self._lock:
            slot_index = self._require_slot_index(bay_id)
            bay = self._require_bay(slot_index)
            placement = bay.footprint.placement
            snapped_rotation = snap_rotation(rotation)
            updated = self._build_footprint(
                bay_type_id=placement.bay_type_id,
                x=placement.x,
                y=placement.y,
                rotation=snapped_rotation,
            )
            self._replace_footprint(slot_index, updated)
            self.touch()
            if self._require_bay(slot_index).valid:
                message = f"Bay rotated to {snapped_rotation:.0f} degrees."
            else:
                message = self._message_for_slot(slot_index)
            return self.snapshot(
                message=message,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
            )

    async def delete_bay(self, bay_id: str) -> LayoutResponse:
        """Delete a bay and revalidate only the affected neighborhood."""

        started_at = time.perf_counter()
        async with self._lock:
            slot_index = self._require_slot_index(bay_id)
            bay = self._require_bay(slot_index)
            affected = self._affected_indices(bay.footprint)
            self._remove_footprint(slot_index)
            affected.discard(slot_index)
            self._refresh_validity(affected)
            self.touch()
            message = f"Deleted {bay_id}."
            return self.snapshot(
                message=message,
                latency_ms=(time.perf_counter() - started_at) * 1000.0,
            )

    def _require_slot_index(self, bay_id: str) -> int:
        """Return the slot index for ``bay_id`` or raise ``KeyError``."""

        try:
            return self._slot_by_id[bay_id]
        except KeyError as exc:
            raise KeyError(f"Unknown bay '{bay_id}'.") from exc

    def _require_bay(self, slot_index: int) -> SessionBay:
        """Return the bay stored in ``slot_index``."""

        bay = self._slots[slot_index]
        if bay is None:
            raise KeyError(f"Unknown slot '{slot_index}'.")
        return bay

    def _template(self, bay_type_id: int, rotation: float) -> PlacementTemplate:
        """Return a cached placement template."""

        snapped_rotation = snap_rotation(rotation)
        key = (bay_type_id, snapped_rotation)
        template = self._templates.get(key)
        if template is None:
            bay_type = self.case.bay_type_map[bay_type_id]
            template = PlacementTemplate(bay_type=bay_type, angle=snapped_rotation)
            self._templates[key] = template
        return template

    def _build_footprint(
        self,
        bay_type_id: int,
        x: float,
        y: float,
        rotation: float,
    ) -> PlacedFootprint:
        """Build a transformed footprint from primitive placement data."""

        template = self._template(bay_type_id, rotation)
        return template.place(float(x), float(y))

    def _insert_new_bay(self, bay_id: str, placement: PlacedBay) -> None:
        """Insert a new bay into the session without revalidating others."""

        footprint = self._build_footprint(
            bay_type_id=placement.bay_type_id,
            x=placement.x,
            y=placement.y,
            rotation=placement.rotation,
        )
        slot_index = len(self._slots)
        bay = SessionBay(
            instance_id=bay_id,
            slot_index=slot_index,
            footprint=footprint,
        )
        self._slots.append(bay)
        self._footprints.append(footprint)
        self._slot_by_id[bay_id] = slot_index
        self._body_hash.add(footprint.body_aabb, slot_index)
        if footprint.gap_aabb is not None:
            self._gap_hash.add(footprint.gap_aabb, slot_index)
        self._add_totals(footprint)

    def _replace_footprint(
        self,
        slot_index: int,
        updated: PlacedFootprint,
    ) -> None:
        """Replace a footprint in-place and refresh affected validity."""

        bay = self._require_bay(slot_index)
        current = bay.footprint
        affected = self._affected_indices(current, updated)
        self._body_hash.remove(current.body_aabb, slot_index)
        if current.gap_aabb is not None:
            self._gap_hash.remove(current.gap_aabb, slot_index)
        self._body_hash.add(updated.body_aabb, slot_index)
        if updated.gap_aabb is not None:
            self._gap_hash.add(updated.gap_aabb, slot_index)
        bay.footprint = updated
        self._footprints[slot_index] = updated
        self._refresh_validity(affected | {slot_index})

    def _remove_footprint(self, slot_index: int) -> None:
        """Remove a footprint from the session."""

        bay = self._require_bay(slot_index)
        footprint = bay.footprint
        self._body_hash.remove(footprint.body_aabb, slot_index)
        if footprint.gap_aabb is not None:
            self._gap_hash.remove(footprint.gap_aabb, slot_index)
        self._remove_totals(footprint)
        self._slot_by_id.pop(bay.instance_id, None)
        self._slots[slot_index] = None
        self._footprints[slot_index] = None

    def _affected_indices(
        self,
        *footprints: PlacedFootprint,
    ) -> set[int]:
        """Collect bays that can be influenced by the provided footprints."""

        affected: set[int] = set()
        for footprint in footprints:
            affected.update(self._body_hash.query(footprint.body_aabb))
            affected.update(self._gap_hash.query(footprint.body_aabb))
            if footprint.gap_aabb is not None:
                affected.update(self._body_hash.query(footprint.gap_aabb))
                affected.update(self._gap_hash.query(footprint.gap_aabb))
        return affected

    def _refresh_validity(self, slot_indices: set[int]) -> None:
        """Recompute validity for a bounded set of bays."""

        for slot_index in sorted(slot_indices):
            bay = self._slots[slot_index]
            footprint = self._footprints[slot_index]
            if bay is None or footprint is None:
                continue
            bay.issues = placement_violations(
                footprint=footprint,
                ctx=self.ctx,
                existing=self._footprints,
                state=self._state_view,
                skip_indices={slot_index},
            )

    def _message_for_slot(self, slot_index: int) -> str:
        """Return a user-facing status message for one slot."""

        bay = self._require_bay(slot_index)
        if bay.valid:
            return LAYOUT_UPDATED_MESSAGE
        return "; ".join(bay.issues)

    def _add_totals(self, footprint: PlacedFootprint) -> None:
        """Accumulate score totals from ``footprint``."""

        bay_type = footprint.template.bay_type
        self.total_area += bay_type.area
        self.total_price += bay_type.price
        self.total_loads += bay_type.n_loads

    def _remove_totals(self, footprint: PlacedFootprint) -> None:
        """Subtract score totals contributed by ``footprint``."""

        bay_type = footprint.template.bay_type
        self.total_area -= bay_type.area
        self.total_price -= bay_type.price
        self.total_loads -= bay_type.n_loads
