"""FastAPI routes for optimization, live editing, and testcase access."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from api_models import (
    DeleteBayRequest,
    HealthResponse,
    Job,
    JobCreatedResponse,
    JobStatus,
    LayoutResponse,
    MoveBayRequest,
    OptimizationInput,
    RotateBayRequest,
    ScoreRequest,
)
from bridge import solution_to_api, to_case_data
from config import API_VERSION, DEFAULT_SOLVER_TIME_BUDGET_SECONDS
from csv_parser import parse_all
from job_store import (
    cleanup_queue,
    create_job,
    get_job,
    get_progress_queue,
    list_jobs,
    update_job,
)
from layout_session import StatefulLayoutSession
from scorer import calculate_score, validate_placement
from session_store import get_layout_session_store


LOGGER = logging.getLogger(__name__)
TESTCASES_DIR = os.path.join(os.path.dirname(__file__), "..", "testcases")
router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return a basic health payload."""

    return HealthResponse(status="ok", version=API_VERSION)


@router.post("/optimise", response_model=LayoutResponse)
async def optimise(input_data: OptimizationInput) -> LayoutResponse:
    """Run the backend solver and open a live editing session."""

    case = to_case_data(input_data)
    solution, stats, elapsed_ms = await _solve_case(case)
    session = StatefulLayoutSession.from_solution(case, solution)
    await get_layout_session_store().save(session)
    _log_optimization(stats, elapsed_ms)
    return session.snapshot(
        message="Optimization completed.",
        solved_in_ms=elapsed_ms,
    )


@router.post("/optimise/files", response_model=LayoutResponse)
async def optimise_files(
    warehouse: UploadFile = File(...),
    obstacles: UploadFile = File(...),
    ceiling: UploadFile = File(...),
    bay_types: UploadFile = File(...),
) -> LayoutResponse:
    """Run optimization directly from uploaded CSV files."""

    input_data = await _parse_upload_input(
        warehouse=warehouse,
        obstacles=obstacles,
        ceiling=ceiling,
        bay_types=bay_types,
    )
    return await optimise(input_data)


@router.patch("/layout/move", response_model=LayoutResponse)
async def move_layout(request: MoveBayRequest) -> LayoutResponse:
    """Move a bay inside an active live-edit session."""

    session = await _require_session(request.session_id)
    try:
        return await session.move_bay(
            bay_id=request.bay_id,
            x=request.x,
            y=request.y,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc


@router.patch("/layout/rotate", response_model=LayoutResponse)
async def rotate_layout(request: RotateBayRequest) -> LayoutResponse:
    """Rotate a bay inside an active live-edit session."""

    session = await _require_session(request.session_id)
    try:
        return await session.rotate_bay(
            bay_id=request.bay_id,
            rotation=request.rotation,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc


@router.patch("/layout/delete", response_model=LayoutResponse)
async def delete_layout(request: DeleteBayRequest) -> LayoutResponse:
    """Delete a bay inside an active live-edit session."""

    session = await _require_session(request.session_id)
    try:
        return await session.delete_bay(bay_id=request.bay_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc


@router.get("/layout/{session_id}", response_model=LayoutResponse)
async def get_layout(session_id: str) -> LayoutResponse:
    """Return the current layout snapshot for a session."""

    session = await _require_session(session_id)
    return session.snapshot(message="Layout loaded.")


@router.post("/solve", status_code=202, response_model=JobCreatedResponse)
async def solve(
    background_tasks: BackgroundTasks,
    warehouse: UploadFile = File(...),
    obstacles: UploadFile = File(...),
    ceiling: UploadFile = File(...),
    bay_types: UploadFile = File(...),
) -> JobCreatedResponse:
    """Submit uploaded CSV files to the legacy background job API."""

    input_data = await _parse_upload_input(
        warehouse=warehouse,
        obstacles=obstacles,
        ceiling=ceiling,
        bay_types=bay_types,
    )
    job = Job(input_data=input_data)
    create_job(job)
    background_tasks.add_task(_run_optimizer, job.id, input_data)
    return JobCreatedResponse(job_id=job.id, status=job.status)


@router.post("/solve/json", status_code=202, response_model=JobCreatedResponse)
async def solve_json(
    background_tasks: BackgroundTasks,
    input_data: OptimizationInput,
) -> JobCreatedResponse:
    """Submit JSON input to the legacy background job API."""

    job = Job(input_data=input_data)
    create_job(job)
    background_tasks.add_task(_run_optimizer, job.id, input_data)
    return JobCreatedResponse(job_id=job.id, status=job.status)


@router.get("/jobs")
async def get_all_jobs() -> list[dict[str, object]]:
    """List background jobs, newest first."""

    return [
        {
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "created_at": job.created_at.isoformat(),
        }
        for job in list_jobs()
    ]


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> Job:
    """Return the full background-job record."""

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str) -> dict[str, object]:
    """Return the completed result for a background job."""

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED or job.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"Job is {job.status.value}, not COMPLETED",
        )
    return job.result.model_dump()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, str]:
    """Cancel a queued or running background job."""

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise HTTPException(
            status_code=409,
            detail="Cannot cancel a finished job",
        )
    update_job(job_id, status=JobStatus.CANCELED)
    queue = get_progress_queue(job_id)
    await queue.put({"event": "job_canceled", "job_id": job_id})
    return {"status": JobStatus.CANCELED.value}


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    """Stream background-job progress through Server-Sent Events."""

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == JobStatus.COMPLETED and job.result is not None:
        payload = {
            "event": "job_completed",
            "job_id": job_id,
            "result": job.result.model_dump(),
        }

        async def completed_stream() -> object:
            yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(
            completed_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if job.status == JobStatus.FAILED:
        payload = {
            "event": "job_failed",
            "job_id": job_id,
            "error": job.error or "Unknown error",
        }

        async def failed_stream() -> object:
            yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(
            failed_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    queue = get_progress_queue(job_id)

    async def event_generator() -> object:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'event': 'ping'})}\n\n"
                continue
            yield f"data: {json.dumps(message)}\n\n"
            if message.get("event") in {
                "job_completed",
                "job_failed",
                "job_canceled",
            }:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/score")
async def score(request: ScoreRequest) -> dict[str, object]:
    """Legacy synchronous score endpoint used by older clients."""

    return calculate_score(
        placed_bays=request.placed_bays,
        bay_types=request.bay_types,
        warehouse=request.warehouse,
        obstacles=request.obstacles,
        ceiling=request.ceiling,
    )


@router.post("/validate")
async def validate(request: ScoreRequest) -> dict[str, object]:
    """Legacy synchronous validation endpoint used by older clients."""

    issues = validate_placement(
        placed_bays=request.placed_bays,
        bay_types=request.bay_types,
        warehouse=request.warehouse,
        obstacles=request.obstacles,
        ceiling=request.ceiling,
    )
    return {"is_valid": len(issues) == 0, "issues": issues}


@router.get("/testcases")
async def list_testcases() -> dict[str, list[dict[str, str]]]:
    """List available testcase folders."""

    if not os.path.isdir(TESTCASES_DIR):
        return {"testcases": []}

    cases: list[dict[str, str]] = []
    for entry in sorted(os.listdir(TESTCASES_DIR)):
        case_dir = os.path.join(TESTCASES_DIR, entry)
        if not os.path.isdir(case_dir):
            continue
        required_files = {
            "warehouse.csv",
            "obstacles.csv",
            "ceiling.csv",
            "types_of_bays.csv",
        }
        if all(os.path.exists(os.path.join(case_dir, name))
               for name in required_files):
            cases.append({"name": entry, "path": case_dir})
    return {"testcases": cases}


@router.get("/testcases/{name}")
async def load_testcase(name: str) -> OptimizationInput:
    """Load a testcase from ``testcases/<name>``."""

    case_dir = os.path.join(TESTCASES_DIR, name)
    if not os.path.isdir(case_dir):
        raise HTTPException(
            status_code=404,
            detail=f"Testcase '{name}' not found",
        )

    try:
        with open(os.path.join(case_dir, "warehouse.csv"), encoding="utf-8") as fh:
            warehouse_csv = fh.read()
        with open(os.path.join(case_dir, "obstacles.csv"), encoding="utf-8") as fh:
            obstacles_csv = fh.read()
        with open(os.path.join(case_dir, "ceiling.csv"), encoding="utf-8") as fh:
            ceiling_csv = fh.read()
        with open(
            os.path.join(case_dir, "types_of_bays.csv"),
            encoding="utf-8",
        ) as fh:
            bay_types_csv = fh.read()
    except OSError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return parse_all(
        warehouse_csv=warehouse_csv,
        obstacles_csv=obstacles_csv,
        ceiling_csv=ceiling_csv,
        bay_types_csv=bay_types_csv,
    )


async def _parse_upload_input(
    warehouse: UploadFile,
    obstacles: UploadFile,
    ceiling: UploadFile,
    bay_types: UploadFile,
) -> OptimizationInput:
    """Parse uploaded CSV files into ``OptimizationInput``."""

    try:
        warehouse_csv = (await warehouse.read()).decode("utf-8")
        obstacles_csv = (await obstacles.read()).decode("utf-8")
        ceiling_csv = (await ceiling.read()).decode("utf-8")
        bay_types_csv = (await bay_types.read()).decode("utf-8")
        return parse_all(
            warehouse_csv=warehouse_csv,
            obstacles_csv=obstacles_csv,
            ceiling_csv=ceiling_csv,
            bay_types_csv=bay_types_csv,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"CSV parsing error: {exc}",
        ) from exc


async def _require_session(session_id: str) -> StatefulLayoutSession:
    """Fetch a live layout session or raise ``404``."""

    session = await get_layout_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _solve_case(case) -> tuple[object, object, int]:
    """Solve a case in the executor and return solution, stats, and time."""

    loop = asyncio.get_running_loop()

    def run_solver() -> tuple[object, object]:
        from solver.hybrid import HybridSolver

        solver = HybridSolver(
            time_budget=DEFAULT_SOLVER_TIME_BUDGET_SECONDS,
        )
        solution = solver.solve(case)
        return solution, solver.last_run_stats

    started_at = time.perf_counter()
    solution, stats = await loop.run_in_executor(None, run_solver)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000.0)
    return solution, stats, elapsed_ms


def _log_optimization(stats: object, elapsed_ms: int) -> None:
    """Log a completed optimization run."""

    LOGGER.info(
        (
            "optimization_completed duration_ms=%s q_initial=%s q_final=%s "
            "bay_count=%s strategy=%s exact_attempted=%s exact_completed=%s "
            "nodes=%s"
        ),
        elapsed_ms,
        getattr(stats, "q_initial", None),
        getattr(stats, "q_final", None),
        getattr(stats, "bay_count", None),
        getattr(stats, "strategy", None),
        getattr(stats, "exact_search_attempted", None),
        getattr(stats, "exact_search_completed", None),
        getattr(stats, "nodes_explored", None),
    )


async def _run_optimizer(job_id: str, input_data: OptimizationInput) -> None:
    """Execute the legacy background optimization job."""

    queue = get_progress_queue(job_id)
    await queue.put({"event": "job_started", "job_id": job_id})
    update_job(job_id, status=JobStatus.RUNNING, progress=0)

    case = to_case_data(input_data)
    cancel_progress = asyncio.Event()

    async def emit_progress() -> None:
        start = time.monotonic()
        while not cancel_progress.is_set():
            elapsed = time.monotonic() - start
            percent = min(
                95,
                int(
                    (elapsed / DEFAULT_SOLVER_TIME_BUDGET_SECONDS)
                    * 100.0
                ),
            )
            update_job(
                job_id,
                progress=percent,
                message=f"Solving... ({percent}%)",
            )
            await queue.put(
                {
                    "event": "job_progress",
                    "job_id": job_id,
                    "percent": percent,
                    "message": f"Solving... ({percent}%)",
                }
            )
            try:
                await asyncio.wait_for(cancel_progress.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

    progress_task = asyncio.create_task(emit_progress())
    try:
        solution, stats, elapsed_ms = await _solve_case(case)
        cancel_progress.set()
        await progress_task
        _log_optimization(stats, elapsed_ms)
        result = solution_to_api(solution, case, elapsed_ms)
        update_job(
            job_id,
            status=JobStatus.COMPLETED,
            progress=100,
            result=result,
        )
        await queue.put(
            {
                "event": "job_completed",
                "job_id": job_id,
                "result": result.model_dump(),
            }
        )
    except Exception as exc:
        cancel_progress.set()
        await progress_task
        error_message = str(exc)[:500]
        update_job(job_id, status=JobStatus.FAILED, error=error_message)
        await queue.put(
            {
                "event": "job_failed",
                "job_id": job_id,
                "error": error_message,
            }
        )
    finally:
        await asyncio.sleep(5.0)
        cleanup_queue(job_id)
