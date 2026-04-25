"""Pydantic models for the Mecalux Warehouse Optimizer API."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid

from pydantic import BaseModel, Field


class BayType(BaseModel):
    """A type of bay available for placement."""

    id: int
    width: float
    depth: float
    height: float
    gap: float
    nLoads: int
    price: float


class Obstacle(BaseModel):
    """An obstacle inside the warehouse."""

    x: float
    y: float
    width: float
    depth: float


class CeilingPoint(BaseModel):
    """A ceiling breakpoint."""

    x: float
    height: float


class WallPoint(BaseModel):
    """A warehouse polygon vertex."""

    x: float
    y: float


class OptimizationInput(BaseModel):
    """Complete optimization input."""

    warehouse: list[WallPoint]
    obstacles: list[Obstacle]
    ceiling: list[CeilingPoint]
    bay_types: list[BayType]


class PlacedBay(BaseModel):
    """Legacy solve-result bay."""

    id: int
    x: float
    y: float
    rotation: float


class SolveResult(BaseModel):
    """Legacy asynchronous solve result."""

    placed_bays: list[PlacedBay]
    Q: float
    coverage: float
    solved_in_ms: int


class LayoutBay(BaseModel):
    """Interactive bay state tracked inside a live session."""

    instance_id: str
    bay_type_id: int
    x: float
    y: float
    rotation: float
    valid: bool
    issues: list[str] = Field(default_factory=list)


class LayoutResponse(BaseModel):
    """Live layout snapshot returned to the interactive frontend."""

    session_id: str
    valid: bool
    Q: Optional[float]
    coverage: float
    bay_count: int
    total_loads: int
    total_bay_area: float
    solved_in_ms: Optional[int] = None
    latency_ms: Optional[float] = None
    message: str
    bays: list[LayoutBay]


class MoveBayRequest(BaseModel):
    """Move a single bay inside an existing session."""

    session_id: str
    bay_id: str
    x: float
    y: float


class RotateBayRequest(BaseModel):
    """Rotate a single bay inside an existing session."""

    session_id: str
    bay_id: str
    rotation: float


class DeleteBayRequest(BaseModel):
    """Delete a single bay inside an existing session."""

    session_id: str
    bay_id: str


class ScoreRequest(BaseModel):
    """Request body for the legacy score and validate endpoints."""

    placed_bays: list[dict]
    bay_types: list[dict]
    warehouse: list[dict]
    obstacles: list[dict] = Field(default_factory=list)
    ceiling: list[dict] = Field(default_factory=list)


class JobStatus(str, Enum):
    """Lifecycle for a background optimization job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class Job(BaseModel):
    """A background optimization job."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    message: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    input_data: Optional[OptimizationInput] = None
    result: Optional[SolveResult] = None
    error: Optional[str] = None


class JobCreatedResponse(BaseModel):
    """Response returned when a background job is created."""

    job_id: str
    status: JobStatus


class HealthResponse(BaseModel):
    """API health response."""

    status: str
    version: str
