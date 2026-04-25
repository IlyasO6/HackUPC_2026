"""
API routes for the Mecalux Warehouse Optimizer.

Endpoints:
    GET  /api/v1/health              → Health check
    POST /api/v1/solve               → Submit 4 CSVs, start optimization job
    POST /api/v1/solve/json          → Submit JSON input, start optimization job
    GET  /api/v1/jobs                → List all jobs
    GET  /api/v1/jobs/{id}           → Get job status
    GET  /api/v1/jobs/{id}/result    → Get optimization result
    GET  /api/v1/jobs/{id}/stream    → SSE progress streaming
    POST /api/v1/jobs/{id}/cancel    → Cancel a running job
    POST /api/v1/score               → Real-time scoring (sync, fast) ← interactive frontend
    POST /api/v1/validate            → Validate a placement ← interactive frontend
    GET  /api/v1/testcases           → List available testcases
    GET  /api/v1/testcases/{name}    → Load a specific testcase
"""
import sys
import os
import asyncio
import json
import time
from typing import List

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api_models import (
    Job, JobStatus, SolveResult, PlacedBay,
    JobCreatedResponse, HealthResponse, OptimizationInput
)
from job_store import create_job, get_job, update_job, get_progress_queue, cleanup_queue, list_jobs
from csv_parser import parse_all
from scorer import calculate_score, validate_placement

# Bridge handles backend path setup and model conversion
from bridge import to_case_data, solution_to_api

# Testcases directory (relative to project root)
TESTCASES_DIR = os.path.join(os.path.dirname(__file__), "..", "testcases")

# Default solver time budget (seconds)
SOLVER_TIME_BUDGET = 29.0


router = APIRouter(prefix="/api/v1")


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ─── Solve (create job) ──────────────────────────────────────────────────────

@router.post("/solve", status_code=202, response_model=JobCreatedResponse)
async def solve(
    bg: BackgroundTasks,
    warehouse: UploadFile = File(...),
    obstacles: UploadFile = File(...),
    ceiling: UploadFile = File(...),
    bay_types: UploadFile = File(...),
):
    """
    Upload 4 CSV files to start an optimization job.
    Returns immediately with a job_id. Use /jobs/{id}/stream for progress.
    """
    # Read CSV contents
    warehouse_csv = (await warehouse.read()).decode("utf-8")
    obstacles_csv = (await obstacles.read()).decode("utf-8")
    ceiling_csv = (await ceiling.read()).decode("utf-8")
    bay_types_csv = (await bay_types.read()).decode("utf-8")

    # Parse CSVs into model objects
    try:
        input_data = parse_all(warehouse_csv, obstacles_csv, ceiling_csv, bay_types_csv)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")

    # Create job
    job = Job(input_data=input_data)
    create_job(job)

    # Run optimizer in background
    bg.add_task(_run_optimizer, job.id, input_data)

    return JobCreatedResponse(job_id=job.id, status=job.status)


# Also support JSON input (for flexibility / testing)
@router.post("/solve/json", status_code=202, response_model=JobCreatedResponse)
async def solve_json(
    bg: BackgroundTasks,
    input_data: OptimizationInput,
):
    """
    Submit optimization input as JSON. Alternative to CSV upload.
    """
    job = Job(input_data=input_data)
    create_job(job)
    bg.add_task(_run_optimizer, job.id, input_data)
    return JobCreatedResponse(job_id=job.id, status=job.status)


# ─── Jobs ─────────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def get_all_jobs():
    """List all jobs, most recent first."""
    jobs = list_jobs()
    return [
        {
            "id": j.id,
            "status": j.status,
            "progress": j.progress,
            "message": j.message,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get full job details."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """Get the optimization result (only available when COMPLETED)."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job is {job.status.value}, not COMPLETED"
        )
    return job.result


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or queued job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise HTTPException(status_code=409, detail="Cannot cancel a finished job")
    update_job(job_id, status=JobStatus.CANCELED)
    queue = get_progress_queue(job_id)
    await queue.put({"event": "job_canceled", "job_id": job_id})
    return {"status": "CANCELED"}


# ─── SSE Streaming ───────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """
    Server-Sent Events stream for real-time job progress.

    Events emitted:
        job_queued, job_started, job_progress, job_completed, job_failed
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If job is already done, send the final event immediately
    if job.status == JobStatus.COMPLETED:
        async def done_generator():
            result_data = job.result.model_dump() if job.result else {}
            yield f"data: {json.dumps({'event': 'job_completed', 'job_id': job_id, 'result': result_data})}\n\n"
        return StreamingResponse(
            done_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if job.status == JobStatus.FAILED:
        async def error_generator():
            yield f"data: {json.dumps({'event': 'job_failed', 'job_id': job_id, 'error': job.error or 'Unknown error'})}\n\n"
        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Stream progress events
    queue = get_progress_queue(job_id)

    async def event_generator():
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("event") in ("job_completed", "job_failed", "job_canceled"):
                    break
            except asyncio.TimeoutError:
                # Keep connection alive with a ping
                yield f"data: {json.dumps({'event': 'ping'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─── Background optimizer runner ──────────────────────────────────────────────

async def _run_optimizer(job_id: str, input_data: OptimizationInput):
    """
    Run the real HybridSolver in a background thread and stream progress.

    Uses timer-based progress updates since the solver doesn't support
    callbacks. We know the time_budget, so we can estimate progress.
    """
    queue = get_progress_queue(job_id)
    await queue.put({"event": "job_started", "job_id": job_id})
    update_job(job_id, status=JobStatus.RUNNING, progress=0)

    # Convert API models → backend CaseData
    case = to_case_data(input_data)

    # Event loop reference for timer-based progress
    loop = asyncio.get_running_loop()

    # Timer-based progress emitter
    progress_task = None
    cancel_progress = asyncio.Event()

    async def emit_progress():
        """Emit smooth progress updates based on time budget."""
        start = time.monotonic()
        while not cancel_progress.is_set():
            elapsed = time.monotonic() - start
            # Progress follows a logarithmic curve: fast at start, slows down
            # Cap at 95% — the final 100% comes from the actual completion
            pct = min(95, int((elapsed / SOLVER_TIME_BUDGET) * 100))
            update_job(job_id, progress=pct, message=f"Solving... ({pct}%)")
            await queue.put({
                "event": "job_progress",
                "job_id": job_id,
                "percent": pct,
                "message": f"Solving... ({pct}%)",
            })
            try:
                await asyncio.wait_for(cancel_progress.wait(), timeout=1.0)
                break
            except asyncio.TimeoutError:
                pass

    try:
        # Start progress emitter
        progress_task = asyncio.create_task(emit_progress())

        # Import and run the real solver in a thread
        from solver.hybrid import HybridSolver

        def run_solver():
            solver = HybridSolver(time_budget=SOLVER_TIME_BUDGET)
            return solver.solve(case)

        start_time = time.monotonic()
        solution = await asyncio.to_thread(run_solver)
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Stop progress emitter
        cancel_progress.set()
        if progress_task:
            await progress_task

        # Convert result
        result = solution_to_api(solution, case, elapsed_ms)

        update_job(job_id, status=JobStatus.COMPLETED, progress=100, result=result)
        await queue.put({
            "event": "job_completed",
            "job_id": job_id,
            "result": result.model_dump(),
        })

    except Exception as e:
        # Stop progress emitter on error
        cancel_progress.set()
        if progress_task:
            await progress_task

        error_msg = str(e)[:500]
        update_job(job_id, status=JobStatus.FAILED, error=error_msg)
        await queue.put({
            "event": "job_failed",
            "job_id": job_id,
            "error": error_msg,
        })

    finally:
        # Clean up queue after a delay (let SSE consumers finish reading)
        await asyncio.sleep(5)
        cleanup_queue(job_id)


# ─── Interactive Scoring (SYNCHRONOUS — optimized for real-time) ──────────────

class ScoreRequest(BaseModel):
    """Request body for the /score endpoint. Sent by the interactive frontend."""
    placed_bays: List[dict]   # [{id, x, y, rotation}, ...]
    bay_types: List[dict]     # [{id, width, depth, height, gap, nLoads, price}, ...]
    warehouse: List[dict]     # [{x, y}, ...]
    obstacles: List[dict] = []
    ceiling: List[dict] = []


@router.post("/score")
async def score(request: ScoreRequest):
    """
    Calculate the Q score and validate a placement.
    SYNCHRONOUS — returns immediately. Designed for real-time interactive use.

    The frontend calls this every time the user modifies a bay position,
    providing instant feedback on the score and any constraint violations.
    """
    result = calculate_score(
        placed_bays=request.placed_bays,
        bay_types=request.bay_types,
        warehouse=request.warehouse,
        obstacles=request.obstacles,
        ceiling=request.ceiling,
    )
    return result


@router.post("/validate")
async def validate(request: ScoreRequest):
    """
    Validate a bay placement against all constraints.
    Returns a list of issues (empty list = valid placement).
    """
    issues = validate_placement(
        placed_bays=request.placed_bays,
        bay_types=request.bay_types,
        warehouse=request.warehouse,
        obstacles=request.obstacles,
        ceiling=request.ceiling,
    )
    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
    }


# ─── Testcases ────────────────────────────────────────────────────────────────

@router.get("/testcases")
async def list_testcases():
    """List available testcases from the testcases/ directory."""
    if not os.path.isdir(TESTCASES_DIR):
        return {"testcases": []}

    cases = []
    for entry in sorted(os.listdir(TESTCASES_DIR)):
        case_dir = os.path.join(TESTCASES_DIR, entry)
        if os.path.isdir(case_dir):
            # Check it has the required CSV files
            has_files = all(
                os.path.exists(os.path.join(case_dir, f))
                for f in ["warehouse.csv", "obstacles.csv", "ceiling.csv", "types_of_bays.csv"]
            )
            if has_files:
                cases.append({"name": entry, "path": case_dir})

    return {"testcases": cases}


@router.get("/testcases/{name}")
async def load_testcase(name: str):
    """
    Load a testcase by name. Returns the parsed warehouse data as JSON.
    The frontend can use this to render the warehouse and bay types.
    """
    case_dir = os.path.join(TESTCASES_DIR, name)
    if not os.path.isdir(case_dir):
        raise HTTPException(status_code=404, detail=f"Testcase '{name}' not found")

    required_files = ["warehouse.csv", "obstacles.csv", "ceiling.csv", "types_of_bays.csv"]
    csvs = {}
    for fname in required_files:
        fpath = os.path.join(case_dir, fname)
        if not os.path.exists(fpath):
            raise HTTPException(status_code=404, detail=f"Missing file: {fname}")
        with open(fpath, "r") as f:
            csvs[fname.replace(".csv", "").replace("types_of_bays", "bay_types")] = f.read()

    try:
        input_data = parse_all(
            csvs["warehouse"],
            csvs["obstacles"],
            csvs["ceiling"],
            csvs["bay_types"],
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")

    return input_data
