from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any


DEFAULT_WAREHOUSE = {
    "polygon": [
        {"x": 0.0, "y": 0.0},
        {"x": 10000.0, "y": 0.0},
        {"x": 10000.0, "y": 6500.0},
        {"x": 0.0, "y": 6500.0},
    ],
    "width": 10000.0,
    "height": 6500.0,
    "source": "Empty project",
}

ISSUE_INDEX_PATTERN = re.compile(r"Bay #(\d+)")


@dataclass(frozen=True, slots=True)
class BayTypeRegistry:
    """Deterministic mapping between UI bay type IDs and backend integers."""

    backend_bay_types: list[dict[str, Any]]
    label_to_backend_id: dict[str, int]
    backend_id_to_label: dict[int, str]
    label_to_type: dict[str, dict[str, Any]]


def as_float(value: Any, default: float = 0.0) -> float:
    """Return ``value`` converted to ``float`` with a safe fallback."""

    if value is None or value == "":
        return float(default)
    return float(value)


def as_int(value: Any, default: int = 0) -> int:
    """Return ``value`` converted to ``int`` with a safe fallback."""

    return int(round(as_float(value, default)))


def canonicalize_layout(layout: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize a UI layout so every downstream adapter sees one shape."""

    result = copy.deepcopy(layout or {})
    warehouse = result.get("warehouse") or {}
    polygon = warehouse.get("polygon") or copy.deepcopy(DEFAULT_WAREHOUSE["polygon"])
    if len(polygon) < 3:
        polygon = copy.deepcopy(DEFAULT_WAREHOUSE["polygon"])

    xs = [as_float(point.get("x")) for point in polygon]
    ys = [as_float(point.get("y")) for point in polygon]
    result["warehouse"] = {
        "polygon": [{"x": as_float(point.get("x")), "y": as_float(point.get("y"))}
                     for point in polygon],
        "width": as_float(warehouse.get("width"), max(xs) - min(xs)),
        "height": as_float(warehouse.get("height"), max(ys) - min(ys)),
        "source": warehouse.get("source", DEFAULT_WAREHOUSE["source"]),
    }
    result["obstacles"] = [
        {
            "id": str(obstacle.get("id") or f"obs-{index}"),
            "x": as_float(obstacle.get("x")),
            "y": as_float(obstacle.get("y")),
            "w": as_float(obstacle.get("w", obstacle.get("width"))),
            "h": as_float(obstacle.get("h", obstacle.get("depth"))),
        }
        for index, obstacle in enumerate(result.get("obstacles") or [], start=1)
    ]
    result["ceiling"] = [
        {"x": as_float(point.get("x")), "height": as_float(point.get("height"))}
        for point in (result.get("ceiling") or [])
    ]
    result["bayTypes"] = _merge_bay_types(
        [_normalize_bay_type(entry, index)
         for index, entry in enumerate(result.get("bayTypes") or [], start=1)],
        [
            _normalize_shelf(entry, index)
            for index, entry in enumerate(result.get("shelves") or [], start=1)
        ],
    )
    result["shelves"] = [
        _normalize_shelf(entry, index)
        for index, entry in enumerate(result.get("shelves") or [], start=1)
    ]
    result["rawFiles"] = list(result.get("rawFiles") or [])
    return result


def build_optimization_payload(
    layout: dict[str, Any] | None,
) -> tuple[dict[str, Any], BayTypeRegistry, dict[str, Any]]:
    """Convert a UI layout into the backend ``OptimizationInput`` shape."""

    canonical = canonicalize_layout(layout)
    registry = build_bay_type_registry(canonical)
    payload = {
        "warehouse": warehouse_points(canonical),
        "obstacles": obstacle_points(canonical),
        "ceiling": ceiling_points(canonical),
        "bay_types": registry.backend_bay_types,
    }
    return payload, registry, canonical


def build_score_payload(
    layout: dict[str, Any] | None,
    shelves: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], BayTypeRegistry, dict[str, Any]]:
    """Build the backend payload for score and validate endpoints."""

    canonical = canonicalize_layout(layout)
    if shelves is not None:
        canonical["shelves"] = [
            _normalize_shelf(entry, index)
            for index, entry in enumerate(shelves, start=1)
        ]
        canonical["bayTypes"] = _merge_bay_types(
            canonical["bayTypes"],
            canonical["shelves"],
        )

    registry = build_bay_type_registry(canonical)
    placed_bays = []
    for shelf in canonical["shelves"]:
        label = str(shelf.get("bayTypeId") or shelf.get("id") or shelf["label"])
        backend_id = registry.label_to_backend_id[label]
        placed_bays.append(
            {
                "id": backend_id,
                "x": as_float(shelf.get("x")),
                "y": as_float(shelf.get("y")),
                "rotation": as_float(shelf.get("rotation")),
            }
        )

    payload = {
        "placed_bays": placed_bays,
        "bay_types": registry.backend_bay_types,
        "warehouse": warehouse_points(canonical),
        "obstacles": obstacle_points(canonical),
        "ceiling": ceiling_points(canonical),
    }
    return payload, registry, canonical


def build_bay_type_registry(layout: dict[str, Any]) -> BayTypeRegistry:
    """Assign backend integer bay type IDs deterministically."""

    canonical = canonicalize_layout(layout)
    labels = [str(entry["id"]) for entry in canonical["bayTypes"]]
    label_to_type = {str(entry["id"]): entry for entry in canonical["bayTypes"]}

    label_to_backend_id: dict[str, int] = {}
    backend_id_to_label: dict[int, str] = {}
    used_ids: set[int] = set()

    for label in labels:
        try:
            candidate = int(label)
        except (TypeError, ValueError):
            continue
        if candidate in used_ids:
            continue
        label_to_backend_id[label] = candidate
        backend_id_to_label[candidate] = label
        used_ids.add(candidate)

    next_id = 1
    for label in labels:
        if label in label_to_backend_id:
            continue
        while next_id in used_ids:
            next_id += 1
        label_to_backend_id[label] = next_id
        backend_id_to_label[next_id] = label
        used_ids.add(next_id)

    backend_bay_types = []
    for entry in canonical["bayTypes"]:
        label = str(entry["id"])
        backend_bay_types.append(
            {
                "id": label_to_backend_id[label],
                "width": as_int(entry["width"]),
                "depth": as_int(entry["depth"]),
                "height": as_int(entry["height"]),
                "gap": as_int(entry["gap"]),
                "nLoads": as_int(entry["nLoads"]),
                "price": as_float(entry["price"]),
            }
        )

    return BayTypeRegistry(
        backend_bay_types=backend_bay_types,
        label_to_backend_id=label_to_backend_id,
        backend_id_to_label=backend_id_to_label,
        label_to_type=label_to_type,
    )


def normalize_backend_job(
    payload: dict[str, Any],
    *,
    stream_url: str | None = None,
) -> dict[str, Any]:
    """Normalize backend job payloads for the Flask UI."""

    job_id = str(payload.get("id") or payload.get("job_id") or "")
    status = normalize_status(payload.get("status"))
    raw_progress = payload.get("progress")
    if raw_progress is None:
        progress = 100 if status in {"completed", "failed", "canceled"} else 0
    else:
        progress = as_int(raw_progress, 0)
    normalized = {
        "id": job_id,
        "job_id": job_id,
        "status": status,
        "raw_status": payload.get("status"),
        "progress": progress,
        "message": payload.get("message", ""),
        "stream_url": stream_url,
        "error": payload.get("error"),
    }
    if payload.get("result") is not None:
        normalized["result"] = payload["result"]
    return normalized


def normalize_backend_result(
    payload: dict[str, Any],
    layout: dict[str, Any],
    registry: BayTypeRegistry | None = None,
) -> dict[str, Any]:
    """Convert raw backend solve results into UI-friendly bay objects."""

    canonical = canonicalize_layout(layout)
    registry = registry or build_bay_type_registry(canonical)
    source_types = {str(entry["id"]): entry for entry in canonical["bayTypes"]}

    placed_bays = []
    for index, entry in enumerate(payload.get("placed_bays") or [], start=1):
        backend_id = as_int(entry.get("id", entry.get("bay_type_id")))
        label = registry.backend_id_to_label.get(backend_id, str(backend_id))
        bay_type = source_types.get(label, {})
        placed_bays.append(
            {
                "uid": f"result-{index}",
                "id": label,
                "label": bay_type.get("label", label),
                "bayTypeId": label,
                "backendBayTypeId": backend_id,
                "x": as_float(entry.get("x")),
                "y": as_float(entry.get("y")),
                "w": as_float(bay_type.get("width")),
                "h": as_float(bay_type.get("depth")),
                "width": as_float(bay_type.get("width")),
                "depth": as_float(bay_type.get("depth")),
                "height": as_float(bay_type.get("height")),
                "gap": as_float(bay_type.get("gap")),
                "nLoads": as_float(bay_type.get("nLoads")),
                "price": as_float(bay_type.get("price")),
                "rotation": as_float(entry.get("rotation")),
            }
        )

    return {
        "Q": as_float(payload.get("Q")) if payload.get("Q") is not None else None,
        "score": as_float(payload.get("Q")) if payload.get("Q") is not None else None,
        "coverage": as_float(payload.get("coverage")),
        "solved_in_ms": as_int(payload.get("solved_in_ms")),
        "baysPlaced": len(placed_bays),
        "placed_bays": placed_bays,
        "placed_bays_backend": payload.get("placed_bays") or [],
    }


def enrich_score_response(
    payload: dict[str, Any],
    layout: dict[str, Any],
) -> dict[str, Any]:
    """Attach invalid bay IDs and normalized status to a score response."""

    canonical = canonicalize_layout(layout)
    invalid_ids = invalid_bay_ids(payload.get("issues") or [], canonical["shelves"])
    response = copy.deepcopy(payload)
    response["status"] = "valid" if payload.get("is_valid") else "invalid"
    response["invalid_bay_ids"] = invalid_ids
    response["issue_count"] = len(payload.get("issues") or [])
    return response


def enrich_validation_response(
    payload: dict[str, Any],
    layout: dict[str, Any],
) -> dict[str, Any]:
    """Attach invalid bay IDs and normalized status to a validate response."""

    canonical = canonicalize_layout(layout)
    invalid_ids = invalid_bay_ids(payload.get("issues") or [], canonical["shelves"])
    response = copy.deepcopy(payload)
    response["status"] = "valid" if payload.get("is_valid") else "invalid"
    response["invalid_bay_ids"] = invalid_ids
    response["issue_count"] = len(payload.get("issues") or [])
    return response


def invalid_bay_ids(
    issues: list[dict[str, Any]],
    shelves: list[dict[str, Any]],
) -> list[str]:
    """Map backend issue messages back onto UI shelf IDs."""

    invalid: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        index = issue.get("bay_index")
        if index is None:
            match = ISSUE_INDEX_PATTERN.search(str(issue.get("message") or ""))
            if match:
                index = int(match.group(1))
        if index is None:
            continue
        if 0 <= int(index) < len(shelves):
            shelf_id = str(shelves[int(index)].get("uid") or shelves[int(index)].get("id"))
            if shelf_id not in seen:
                seen.add(shelf_id)
                invalid.append(shelf_id)
    return invalid


def normalize_status(status: Any) -> str:
    """Normalize backend job statuses for the UI."""

    text = str(status or "").strip().lower()
    mapping = {
        "queued": "queued",
        "running": "running",
        "completed": "completed",
        "failed": "failed",
        "canceled": "canceled",
        "cancelled": "canceled",
    }
    return mapping.get(text, text or "unknown")


def warehouse_points(layout: dict[str, Any]) -> list[dict[str, float]]:
    """Return the warehouse polygon in backend request format."""

    canonical = canonicalize_layout(layout)
    return [
        {"x": as_float(point["x"]), "y": as_float(point["y"])}
        for point in canonical["warehouse"]["polygon"]
    ]


def obstacle_points(layout: dict[str, Any]) -> list[dict[str, float]]:
    """Return obstacles in backend request format."""

    canonical = canonicalize_layout(layout)
    return [
        {
            "x": as_float(obstacle["x"]),
            "y": as_float(obstacle["y"]),
            "width": as_float(obstacle["w"]),
            "depth": as_float(obstacle["h"]),
        }
        for obstacle in canonical["obstacles"]
    ]


def ceiling_points(layout: dict[str, Any]) -> list[dict[str, float]]:
    """Return ceiling points in backend request format."""

    canonical = canonicalize_layout(layout)
    return [
        {"x": as_float(point["x"]), "height": as_float(point["height"])}
        for point in canonical["ceiling"]
    ]


def _normalize_bay_type(entry: dict[str, Any], index: int) -> dict[str, Any]:
    """Return one normalized bay type entry."""

    bay_id = str(entry.get("id") or entry.get("label") or f"bay-type-{index}")
    return {
        "id": bay_id,
        "label": str(entry.get("label") or bay_id),
        "width": as_float(entry.get("width", entry.get("w"))),
        "depth": as_float(entry.get("depth", entry.get("h"))),
        "height": as_float(entry.get("height")),
        "gap": as_float(entry.get("gap")),
        "nLoads": as_float(entry.get("nLoads", entry.get("loads"))),
        "price": as_float(entry.get("price")),
    }


def _normalize_shelf(entry: dict[str, Any], index: int) -> dict[str, Any]:
    """Return one normalized shelf or placed-bay entry."""

    shelf_id = str(entry.get("id") or entry.get("uid") or f"shelf-{index}")
    bay_type_id = str(
        entry.get("bayTypeId")
        or entry.get("typeId")
        or entry.get("backendBayTypeId")
        or entry.get("id")
        or shelf_id
    )
    label = str(entry.get("label") or entry.get("id") or bay_type_id)
    return {
        "id": shelf_id,
        "uid": str(entry.get("uid") or shelf_id),
        "label": label,
        "bayTypeId": bay_type_id,
        "backendBayTypeId": entry.get("backendBayTypeId"),
        "x": as_float(entry.get("x")),
        "y": as_float(entry.get("y")),
        "w": as_float(entry.get("w", entry.get("width"))),
        "h": as_float(entry.get("h", entry.get("depth"))),
        "width": as_float(entry.get("w", entry.get("width"))),
        "depth": as_float(entry.get("h", entry.get("depth"))),
        "height": as_float(entry.get("height")),
        "gap": as_float(entry.get("gap")),
        "nLoads": as_float(entry.get("nLoads", entry.get("loads"))),
        "price": as_float(entry.get("price")),
        "rotation": as_float(entry.get("rotation")),
    }


def _merge_bay_types(
    bay_types: list[dict[str, Any]],
    shelves: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure every placed shelf has a corresponding bay type definition."""

    merged = [copy.deepcopy(entry) for entry in bay_types]
    by_id = {str(entry["id"]): entry for entry in merged}

    for shelf in shelves:
        bay_type_id = str(shelf.get("bayTypeId") or shelf.get("id"))
        if bay_type_id in by_id:
            existing = by_id[bay_type_id]
            if not existing.get("width"):
                existing["width"] = as_float(shelf.get("w"))
            if not existing.get("depth"):
                existing["depth"] = as_float(shelf.get("h"))
            if not existing.get("height"):
                existing["height"] = as_float(shelf.get("height"))
            if not existing.get("gap"):
                existing["gap"] = as_float(shelf.get("gap"))
            if not existing.get("nLoads"):
                existing["nLoads"] = as_float(shelf.get("nLoads"))
            if not existing.get("price"):
                existing["price"] = as_float(shelf.get("price"))
            continue

        derived = {
            "id": bay_type_id,
            "label": str(shelf.get("label") or bay_type_id),
            "width": as_float(shelf.get("w")),
            "depth": as_float(shelf.get("h")),
            "height": as_float(shelf.get("height")),
            "gap": as_float(shelf.get("gap")),
            "nLoads": as_float(shelf.get("nLoads")),
            "price": as_float(shelf.get("price")),
        }
        merged.append(derived)
        by_id[bay_type_id] = derived

    return merged
