"""
Pydantic models for the Mecalux Warehouse Optimizer API.
Aligned with the CSV input format from the challenge.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime, timezone
import uuid


# ─── Input models (parsed from CSVs) ──────────────────────────────────────────

class BayType(BaseModel):
    """A type of bay available for placement. From types_of_bays.csv."""
    id: int
    width: float
    depth: float
    height: float
    gap: float
    nLoads: int
    price: float


class Obstacle(BaseModel):
    """An obstacle inside the warehouse. From obstacles.csv."""
    x: float
    y: float
    width: float
    depth: float


class CeilingPoint(BaseModel):
    """A point in the ceiling height profile. From ceiling.csv."""
    x: float
    height: float


class WallPoint(BaseModel):
    """A vertex of the warehouse polygon. From warehouse.csv."""
    x: float
    y: float


class OptimizationInput(BaseModel):
    """Complete input for the optimizer, parsed from 4 CSVs."""
    warehouse: List[WallPoint]
    obstacles: List[Obstacle]
    ceiling: List[CeilingPoint]
    bay_types: List[BayType]


# ─── Output models ────────────────────────────────────────────────────────────

class PlacedBay(BaseModel):
    """A bay placed in the warehouse by the optimizer."""
    id: int
    x: float
    y: float
    rotation: float  # degrees (0, 90, 180, 270 typically)


class SolveResult(BaseModel):
    """Result from the optimizer."""
    placed_bays: List[PlacedBay]
    Q: float
    B: float
    E: float
    coverage: float
    solved_in_ms: int


# ─── Job models ───────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class Job(BaseModel):
    """A job representing an optimization run."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_data: Optional[OptimizationInput] = None
    result: Optional[SolveResult] = None
    error: Optional[str] = None


# ─── API response models ─────────────────────────────────────────────────────

class JobCreatedResponse(BaseModel):
    job_id: str
    status: JobStatus


class HealthResponse(BaseModel):
    status: str
    version: str
