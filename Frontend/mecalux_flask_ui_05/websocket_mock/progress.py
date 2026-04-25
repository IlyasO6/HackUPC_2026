from __future__ import annotations

import random
import time
from typing import Any

from mock_api.data import JOBS, build_mock_result

LOG_STEPS = [
    "Reading mocked warehouse layout...",
    "Checking obstacles and shelf dimensions...",
    "Generating candidate placements...",
    "Running mocked optimizer iteration 1...",
    "Running mocked optimizer iteration 2...",
    "Improving layout score...",
    "Preparing heatmap visualization...",
    "Final validation complete.",
]


def run_fake_job(socketio: Any, job_id: str) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    socketio.emit("job_update", job, room=job_id)

    progress = 0
    for step in LOG_STEPS:
        time.sleep(0.55)
        progress = min(100, progress + random.randint(9, 16))
        job["progress"] = progress
        job["logs"].append(step)
        socketio.emit("job_log", {"job_id": job_id, "message": step}, room=job_id)
        socketio.emit("job_update", job, room=job_id)

    time.sleep(0.4)
    job["progress"] = 100
    job["status"] = "completed"
    result = build_mock_result(job.get("project_id", "demo-warehouse"))
    job["result"] = result
    job["logs"].append("Optimization completed successfully.")
    socketio.emit("job_log", {"job_id": job_id, "message": "Optimization completed successfully."}, room=job_id)
    socketio.emit("job_update", job, room=job_id)
    socketio.emit("job_result", {"job_id": job_id, "result": result}, room=job_id)
