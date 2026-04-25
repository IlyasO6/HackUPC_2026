"""
In-memory job store for the optimizer API.

For a hackathon, a dict in memory is perfectly sufficient.
All jobs live in the same process as FastAPI (via BackgroundTasks).
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
from models import Job


# ─── In-memory storage ────────────────────────────────────────────────────────

_jobs: dict[str, Job] = {}

# SSE progress queues: job_id → asyncio.Queue
# The SSE endpoint consumes from these queues
_progress_queues: dict[str, asyncio.Queue] = {}


# ─── Job CRUD ─────────────────────────────────────────────────────────────────

def create_job(job: Job) -> Job:
    """Store a new job."""
    _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    """Retrieve a job by ID."""
    return _jobs.get(job_id)


def update_job(job_id: str, **kwargs) -> Optional[Job]:
    """Update specific fields of a job."""
    job = _jobs.get(job_id)
    if not job:
        return None
    for key, value in kwargs.items():
        if hasattr(job, key):
            setattr(job, key, value)
    job.updated_at = datetime.now(timezone.utc)
    return job


def list_jobs() -> list[Job]:
    """Return all jobs, most recent first."""
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


# ─── Progress queues (for SSE streaming) ──────────────────────────────────────

def get_progress_queue(job_id: str) -> asyncio.Queue:
    """Get or create a progress queue for a job."""
    if job_id not in _progress_queues:
        _progress_queues[job_id] = asyncio.Queue()
    return _progress_queues[job_id]


def cleanup_queue(job_id: str):
    """Remove a progress queue after the job finishes."""
    _progress_queues.pop(job_id, None)
