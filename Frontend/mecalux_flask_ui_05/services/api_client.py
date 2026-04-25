from __future__ import annotations

"""Tiny backend switch layer.

For the hackathon UI we run in MOCK mode by default. When the real optimizer
backend is ready, set:

    BACKEND_MODE=real
    BACKEND_URL=http://localhost:8000

The templates and frontend JS keep calling this Flask app. Only this layer has
to change/forward calls to the real backend.
"""

import os
from typing import Any

import requests

from mock_api.data import (
    JOBS,
    LAYOUTS,
    PROJECTS,
    create_job as create_mock_job,
    create_project as create_mock_project,
    create_project_from_layout,
    delete_project as delete_mock_project,
)

BACKEND_MODE = os.getenv("BACKEND_MODE", "mock").lower()
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def using_mock_backend() -> bool:
    return BACKEND_MODE != "real"


def list_projects() -> list[dict[str, Any]]:
    # Projects are UI-owned for now. Later this can be forwarded too if needed.
    return PROJECTS


def create_project(name: str) -> dict[str, Any]:
    return create_mock_project(name)


def import_project(name: str, layout: dict[str, Any], status: str = "uploaded") -> dict[str, Any]:
    # Uploaded challenge cases are UI-owned until the real backend is connected.
    return create_project_from_layout(name, layout, status=status)


def delete_project(project_id: str) -> bool:
    # Projects are still UI-owned; this deletes the local mock layout and related jobs.
    return delete_mock_project(project_id)


def get_layout(project_id: str) -> dict[str, Any] | None:
    return LAYOUTS.get(project_id)


def save_layout(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    # Layout editing is mock/local now; later the same payload can be POSTed to the backend.
    if using_mock_backend():
        LAYOUTS[project_id] = payload
        return {"ok": True, "layout": payload, "mode": "mock"}

    response = requests.post(f"{BACKEND_URL}/api/layouts/{project_id}", json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def create_job(project_id: str) -> dict[str, Any]:
    if using_mock_backend():
        return create_mock_job(project_id)

    response = requests.post(f"{BACKEND_URL}/api/jobs", json={"project_id": project_id}, timeout=10)
    response.raise_for_status()
    return response.json()


def get_job(job_id: str) -> dict[str, Any] | None:
    if using_mock_backend():
        return JOBS.get(job_id)

    response = requests.get(f"{BACKEND_URL}/api/jobs/{job_id}", timeout=10)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def get_result(job_id: str) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job:
        return None
    return job.get("result")
