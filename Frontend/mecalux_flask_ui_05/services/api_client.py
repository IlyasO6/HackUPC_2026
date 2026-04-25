from __future__ import annotations

"""Backend switch layer for the Flask UI."""

import copy
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
from services.backend_adapter import (
    build_optimization_payload,
    build_score_payload,
    canonicalize_layout,
    enrich_score_response,
    enrich_validation_response,
    normalize_backend_job,
    normalize_backend_result,
    normalize_status,
)


BACKEND_MODE = os.getenv("BACKEND_MODE", "mock").lower()
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

REQUEST_TIMEOUT_SECONDS = 20
REAL_JOB_CONTEXTS: dict[str, dict[str, Any]] = {}


class ApiClientError(RuntimeError):
    """Raised when the real backend returns an error or is unavailable."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def using_mock_backend() -> bool:
    """Return whether the UI should use local mock behavior."""

    return BACKEND_MODE != "real"


def list_projects() -> list[dict[str, Any]]:
    """Return locally stored UI projects."""

    return copy.deepcopy(PROJECTS)


def create_project(name: str) -> dict[str, Any]:
    """Create a new local UI project."""

    return create_mock_project(name)


def import_project(
    name: str,
    layout: dict[str, Any],
    status: str = "uploaded",
) -> dict[str, Any]:
    """Create a local project from uploaded case data."""

    return create_project_from_layout(
        name,
        canonicalize_layout(layout),
        status=status,
    )


def delete_project(project_id: str) -> bool:
    """Delete a local project and any related mock jobs."""

    return delete_mock_project(project_id)


def get_layout(project_id: str) -> dict[str, Any] | None:
    """Return a local project layout."""

    layout = LAYOUTS.get(project_id)
    if layout is None:
        return None
    return canonicalize_layout(layout)


def save_layout(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the current layout locally for both mock and real mode."""

    layout = canonicalize_layout(payload)
    LAYOUTS[project_id] = layout
    return {
        "ok": True,
        "layout": copy.deepcopy(layout),
        "mode": "mock" if using_mock_backend() else "real",
    }


def create_job(project_id: str) -> dict[str, Any]:
    """Create a new optimization job."""

    if using_mock_backend():
        return create_mock_job(project_id)

    layout = get_layout(project_id)
    if layout is None:
        raise ApiClientError("Project layout not found.", 404)

    payload, registry, layout_snapshot = build_optimization_payload(layout)
    response = _request_json(
        "post",
        "/api/v1/solve/json",
        operation="Create optimization job",
        json=payload,
    )
    job = normalize_backend_job(
        response,
        stream_url=f"/api/jobs/{response['job_id']}/stream",
    )
    REAL_JOB_CONTEXTS[job["id"]] = {
        "project_id": project_id,
        "layout": layout_snapshot,
        "registry": registry,
    }
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    """Return job state from the local mock store or the real backend."""

    if using_mock_backend():
        job = JOBS.get(job_id)
        return copy.deepcopy(job) if job else None

    response = _request_json(
        "get",
        f"/api/v1/jobs/{job_id}",
        operation="Fetch job status",
        allow_404=True,
    )
    if response is None:
        return None
    return normalize_backend_job(
        response,
        stream_url=f"/api/jobs/{job_id}/stream",
    )


def get_result(job_id: str) -> dict[str, Any] | None:
    """Return the normalized optimization result when available."""

    if using_mock_backend():
        job = JOBS.get(job_id)
        if not job:
            return None
        return copy.deepcopy(job.get("result"))

    context = REAL_JOB_CONTEXTS.get(job_id)
    response = _request_json(
        "get",
        f"/api/v1/jobs/{job_id}/result",
        operation="Fetch job result",
        allow_404=True,
    )
    if response is None:
        return None
    if context is None:
        return response
    return normalize_backend_result(
        response,
        context["layout"],
        context["registry"],
    )


def score_layout(layout: dict[str, Any]) -> dict[str, Any]:
    """Score and validate a layout through the real backend."""

    if using_mock_backend():
        return _mock_score_response(layout)

    payload, _, canonical = build_score_payload(layout)
    response = _request_json(
        "post",
        "/api/v1/score",
        operation="Score layout",
        json=payload,
    )
    return enrich_score_response(response, canonical)


def validate_layout(layout: dict[str, Any]) -> dict[str, Any]:
    """Validate a layout through the real backend."""

    if using_mock_backend():
        score = _mock_score_response(layout)
        return {
            "is_valid": score["is_valid"],
            "issues": score["issues"],
            "status": score["status"],
            "invalid_bay_ids": score["invalid_bay_ids"],
            "issue_count": score["issue_count"],
        }

    payload, _, canonical = build_score_payload(layout)
    response = _request_json(
        "post",
        "/api/v1/validate",
        operation="Validate layout",
        json=payload,
    )
    return enrich_validation_response(response, canonical)


def open_job_stream(job_id: str) -> requests.Response:
    """Open the backend SSE stream for a job."""

    if using_mock_backend():
        raise ApiClientError("SSE streaming is only available in real mode.", 400)

    try:
        response = requests.get(
            f"{BACKEND_URL}/api/v1/jobs/{job_id}/stream",
            headers={"Accept": "text/event-stream"},
            stream=True,
            timeout=(REQUEST_TIMEOUT_SECONDS, None),
        )
    except requests.RequestException as exc:
        raise ApiClientError(
            f"Could not open the backend stream: {exc}",
            502,
        ) from exc

    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        response.close()
        raise ApiClientError(
            f"Could not open the backend stream: {detail}",
            response.status_code,
        )
    return response


def normalize_stream_event(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize one SSE payload from the real backend."""

    event = str(payload.get("event") or "").strip().lower()
    context = REAL_JOB_CONTEXTS.get(job_id)
    normalized: dict[str, Any] = {"event": event, "job_id": job_id}

    if event == "job_started":
        normalized.update(
            {
                "status": "running",
                "progress": 0,
                "message": payload.get("message", "Optimization started."),
            }
        )
        return normalized

    if event == "job_progress":
        normalized.update(
            {
                "status": "running",
                "progress": int(payload.get("percent", 0)),
                "message": payload.get("message", ""),
            }
        )
        return normalized

    if event == "job_completed":
        normalized.update({"status": "completed", "progress": 100})
        result = payload.get("result") or {}
        if context is not None:
            normalized["result"] = normalize_backend_result(
                result,
                context["layout"],
                context["registry"],
            )
        else:
            normalized["result"] = result
        normalized["message"] = "Optimization completed."
        return normalized

    if event == "job_failed":
        error_message = payload.get("error") or "Optimization failed."
        normalized.update(
            {
                "status": "failed",
                "progress": 100,
                "message": error_message,
                "error": error_message,
            }
        )
        return normalized

    if event == "job_canceled":
        normalized.update(
            {
                "status": "canceled",
                "progress": 100,
                "message": "Optimization canceled.",
            }
        )
        return normalized

    if event == "ping":
        return normalized

    if "status" in payload:
        normalized.update(
            {
                "status": normalize_status(payload.get("status")),
                "progress": int(payload.get("progress", 0)),
                "message": payload.get("message", ""),
            }
        )
    return normalized


def _request_json(
    method: str,
    path: str,
    *,
    operation: str,
    allow_404: bool = False,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Send one JSON request to the real backend and normalize errors."""

    try:
        response = requests.request(
            method.upper(),
            f"{BACKEND_URL}{path}",
            timeout=kwargs.pop("timeout", REQUEST_TIMEOUT_SECONDS),
            **kwargs,
        )
    except requests.RequestException as exc:
        raise ApiClientError(
            f"{operation} failed because the backend is unreachable: {exc}",
            502,
        ) from exc

    if allow_404 and response.status_code == 404:
        return None

    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        raise ApiClientError(f"{operation} failed: {detail}", response.status_code)

    try:
        return response.json()
    except ValueError as exc:
        raise ApiClientError(
            f"{operation} failed: backend returned invalid JSON.",
            502,
        ) from exc


def _extract_error_detail(response: requests.Response) -> str:
    """Extract a readable error message from a backend response."""

    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return "; ".join(str(item) for item in detail)
    if detail is not None:
        return str(detail)
    if isinstance(payload, dict) and "error" in payload:
        return str(payload["error"])
    return response.text.strip() or f"HTTP {response.status_code}"


def _mock_score_response(layout: dict[str, Any]) -> dict[str, Any]:
    """Provide a lightweight local score response for mock mode."""

    canonical = canonicalize_layout(layout)
    shelves = canonical["shelves"]
    polygon = canonical["warehouse"]["polygon"]
    warehouse_area = _polygon_area(polygon)

    total_bay_area = sum(as_float(shelf.get("w")) * as_float(shelf.get("h"))
                         for shelf in shelves)
    total_price = sum(as_float(shelf.get("price")) for shelf in shelves)
    total_loads = sum(as_float(shelf.get("nLoads")) for shelf in shelves)
    coverage = (total_bay_area / warehouse_area) if warehouse_area else 0.0
    q_value = None
    if total_loads > 0 and warehouse_area > 0:
        q_value = round((total_price / total_loads) ** (2.0 - coverage), 6)

    return {
        "Q": q_value,
        "coverage": coverage,
        "num_bays": len(shelves),
        "total_loads": total_loads,
        "total_bay_area": total_bay_area,
        "warehouse_area": warehouse_area,
        "is_valid": True,
        "issues": [],
        "status": "valid",
        "invalid_bay_ids": [],
        "issue_count": 0,
    }


def _polygon_area(points: list[dict[str, Any]]) -> float:
    """Return polygon area using the shoelace formula."""

    if len(points) < 3:
        return 0.0
    area = 0.0
    for index, point in enumerate(points):
        other = points[(index + 1) % len(points)]
        area += as_float(point["x"]) * as_float(other["y"])
        area -= as_float(other["x"]) * as_float(point["y"])
    return abs(area) / 2.0
