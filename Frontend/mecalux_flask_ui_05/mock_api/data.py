from __future__ import annotations

import time
import uuid
from typing import Any

PROJECTS: list[dict[str, Any]] = [
    {
        "id": "demo-warehouse",
        "name": "Demo Warehouse",
        "created_at": "HackUPC 2026",
        "status": "ready",
    }
]

LAYOUTS: dict[str, dict[str, Any]] = {
    "demo-warehouse": {
        "warehouse": {
            "width": 10000,
            "height": 6500,
            "polygon": [
                {"x": 0, "y": 0},
                {"x": 10000, "y": 0},
                {"x": 10000, "y": 6500},
                {"x": 0, "y": 6500},
            ],
            "source": "Built-in demo",
        },
        "shelves": [
            {"id": "shelf-1", "x": 800, "y": 800, "w": 1400, "h": 600, "gap": 220, "rotation": 0, "label": "A", "bayTypeId": "A"},
            {"id": "shelf-2", "x": 2600, "y": 800, "w": 1800, "h": 700, "gap": 260, "rotation": 0, "label": "B", "bayTypeId": "B"},
            {"id": "shelf-3", "x": 800, "y": 2300, "w": 800, "h": 1200, "gap": 180, "rotation": 90, "label": "C", "bayTypeId": "C"},
        ],
        "obstacles": [
            {"id": "obs-1", "x": 5200, "y": 2300, "w": 900, "h": 1100},
            {"id": "obs-2", "x": 7600, "y": 4200, "w": 1300, "h": 800},
        ],
        "ceiling": [],
        "bayTypes": [
            {"id": "A", "width": 1400, "depth": 600, "height": 2500, "gap": 220, "nLoads": 20, "price": 1000},
            {"id": "B", "width": 1800, "depth": 700, "height": 2800, "gap": 260, "nLoads": 35, "price": 1800},
            {"id": "C", "width": 800, "depth": 1200, "height": 2400, "gap": 180, "nLoads": 12, "price": 900},
        ],
    }
}

JOBS: dict[str, dict[str, Any]] = {}


def build_mock_result(project_id: str) -> dict[str, Any]:
    """Return a backend-shaped result that the UI can draw.

    The real optimizer is expected to return placed bays in the same spirit as
    the challenge output: id, x, y, rotation. For visualization, we also accept
    optional w/h when available.
    """
    layout = LAYOUTS.get(project_id) or LAYOUTS["demo-warehouse"]
    shelves = layout.get("shelves") or []
    bay_types = layout.get("bayTypes") or []

    if shelves:
        placed_bays = [
            {
                "id": shelf.get("label") or shelf.get("bayTypeId") or shelf.get("id", "A"),
                "x": shelf.get("x", 0),
                "y": shelf.get("y", 0),
                "w": shelf.get("w"),
                "h": shelf.get("h"),
                "gap": shelf.get("gap", 0),
                "bayTypeId": shelf.get("bayTypeId"),
                "rotation": shelf.get("rotation", 0),
            }
            for shelf in shelves
        ]
    else:
        placed_bays = []
        default_type = bay_types[0] if bay_types else {"id": "A", "width": 1200, "depth": 800}
        w = default_type.get("width", 1200)
        h = default_type.get("depth", 800)
        polygon = layout.get("warehouse", {}).get("polygon") or [{"x": 0, "y": 0}]
        min_x = min(p.get("x", 0) for p in polygon)
        min_y = min(p.get("y", 0) for p in polygon)
        for i in range(8):
            placed_bays.append({
                "id": default_type.get("id", "A"),
                "x": min_x + (i % 4) * (w + 250),
                "y": min_y + (i // 4) * (h + 250),
                "w": w,
                "h": h,
                "gap": default_type.get("gap", 0),
                "bayTypeId": default_type.get("id", "A"),
                "rotation": 0,
            })

    return {
        "score": 123.45,
        "coverage": 0.72,
        "baysPlaced": len(placed_bays),
        "placed_bays": placed_bays,
        "heatmap": [
            [0.20, 0.35, 0.65, 0.75, 0.45],
            [0.15, 0.50, 0.90, 0.80, 0.55],
            [0.30, 0.60, 0.95, 0.70, 0.25],
            [0.10, 0.25, 0.45, 0.55, 0.20],
        ],
    }


def create_project(name: str) -> dict[str, Any]:
    project_id = str(uuid.uuid4())[:8]
    project = {
        "id": project_id,
        "name": name or f"Warehouse {project_id}",
        "created_at": time.strftime("%H:%M"),
        "status": "draft",
    }
    PROJECTS.append(project)
    LAYOUTS[project_id] = {
        "warehouse": {
            "width": 10000,
            "height": 6500,
            "polygon": [
                {"x": 0, "y": 0},
                {"x": 10000, "y": 0},
                {"x": 10000, "y": 6500},
                {"x": 0, "y": 6500},
            ],
            "source": "Empty project",
        },
        "shelves": [],
        "obstacles": [],
        "ceiling": [],
        "bayTypes": [],
    }
    return project


def create_project_from_layout(name: str, layout: dict[str, Any], status: str = "uploaded") -> dict[str, Any]:
    project_id = str(uuid.uuid4())[:8]
    project = {
        "id": project_id,
        "name": name or f"Uploaded case {project_id}",
        "created_at": time.strftime("%H:%M"),
        "status": status,
    }
    PROJECTS.append(project)
    LAYOUTS[project_id] = layout
    return project


def delete_project(project_id: str) -> bool:
    project_index = next((index for index, project in enumerate(PROJECTS) if project["id"] == project_id), None)
    if project_index is None:
        return False

    PROJECTS.pop(project_index)
    LAYOUTS.pop(project_id, None)

    for job_id, job in list(JOBS.items()):
        if job.get("project_id") == project_id:
            JOBS.pop(job_id, None)

    return True


def create_job(project_id: str) -> dict[str, Any]:
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
        "project_id": project_id,
        "status": "queued",
        "progress": 0,
        "logs": ["Job queued"],
        "result": None,
    }
    JOBS[job_id] = job
    return job
