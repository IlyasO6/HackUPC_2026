from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any
from werkzeug.datastructures import FileStorage


def _read_csv_rows(raw: bytes, fallback_headers: list[str] | None = None) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:1024]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","

    if fallback_headers:
        raw_rows = [
            row for row in csv.reader(io.StringIO(text), delimiter=delimiter)
            if any((value or "").strip() for value in row)
        ]
        if not raw_rows:
            return []

        known_headers = {header.lower() for header in fallback_headers}
        first_row_names = {str(value).strip().lower() for value in raw_rows[0]}
        if first_row_names.isdisjoint(known_headers):
            rows = []
            for row in raw_rows:
                padded = [*row, *([""] * max(0, len(fallback_headers) - len(row)))]
                rows.append(dict(zip(fallback_headers, padded)))
            return rows

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [dict(row) for row in reader if any((v or "").strip() for v in row.values())]


def _num(row: dict[str, str], *names: str, default: float = 0) -> float:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip() != "":
            return float(str(value).strip().replace(",", "."))
    return default


def _str(row: dict[str, str], *names: str, default: str = "") -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def _layout_from_files(name: str, files: dict[str, bytes]) -> dict[str, Any]:
    warehouse_rows = _read_csv_rows(files.get("warehouse.csv", b"x,y\n0,0\n10000,0\n10000,7000\n0,7000\n"), ["x", "y"])
    polygon = [{"x": _num(r, "x"), "y": _num(r, "y")} for r in warehouse_rows]

    obstacle_rows = _read_csv_rows(files.get("obstacles.csv", b"x,y,width,depth\n"), ["x", "y", "width", "depth"]) if files.get("obstacles.csv") else []
    obstacles = []
    for idx, row in enumerate(obstacle_rows, start=1):
        obstacles.append({
            "id": _str(row, "id", default=f"obs-{idx}"),
            "x": _num(row, "x"),
            "y": _num(row, "y"),
            "w": _num(row, "width", "w"),
            "h": _num(row, "depth", "height", "h"),
        })

    ceiling_rows = _read_csv_rows(files.get("ceiling.csv", b"x,height\n"), ["x", "height"]) if files.get("ceiling.csv") else []
    ceiling = [{"x": _num(r, "x"), "height": _num(r, "height", "h")} for r in ceiling_rows]

    bay_rows = _read_csv_rows(files.get("types_of_bays.csv", b"id,width,depth,height,gap,nLoads,price\n"), ["id", "width", "depth", "height", "gap", "nLoads", "price"]) if files.get("types_of_bays.csv") else []
    bay_types = []
    for idx, row in enumerate(bay_rows, start=1):
        bay_types.append({
            "id": _str(row, "id", default=f"bay-type-{idx}"),
            "width": _num(row, "width", "w"),
            "depth": _num(row, "depth", "d"),
            "height": _num(row, "height", "h"),
            "gap": _num(row, "gap"),
            "nLoads": _num(row, "nLoads", "nloads", "loads"),
            "price": _num(row, "price"),
        })

    xs = [p["x"] for p in polygon] or [0, 10000]
    ys = [p["y"] for p in polygon] or [0, 7000]

    return {
        "warehouse": {
            "polygon": polygon,
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys),
            "source": name,
        },
        "obstacles": obstacles,
        "shelves": [],
        "ceiling": ceiling,
        "bayTypes": bay_types,
        "rawFiles": sorted(files.keys()),
    }


def parse_json_case(file: FileStorage) -> tuple[str, dict[str, Any]]:
    import json

    name = Path(file.filename or "uploaded-case.json").stem
    data = json.loads(file.read().decode("utf-8-sig"))
    # Accept either a full layout or a wrapper with layout/project keys.
    layout = data.get("layout", data)
    layout.setdefault("warehouse", {"width": 1000, "height": 650})
    layout.setdefault("shelves", [])
    layout.setdefault("obstacles", [])
    layout.setdefault("bayTypes", [])
    return name, layout


def parse_csv_case(name: str, uploaded_files: dict[str, FileStorage]) -> tuple[str, dict[str, Any]]:
    files = {filename: storage.read() for filename, storage in uploaded_files.items() if storage and storage.filename}
    return name or "Uploaded CSV case", _layout_from_files(name or "Uploaded CSV case", files)


def parse_zip_cases(file: FileStorage) -> list[tuple[str, dict[str, Any]]]:
    raw = file.read()
    cases: dict[str, dict[str, bytes]] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            filename = Path(info.filename).name
            if filename not in {"warehouse.csv", "obstacles.csv", "ceiling.csv", "types_of_bays.csv"}:
                continue
            parts = Path(info.filename).parts
            case_name = parts[-2] if len(parts) > 1 else Path(file.filename or "Zip case").stem
            cases.setdefault(case_name, {})[filename] = zf.read(info)

    parsed = []
    for case_name, files in sorted(cases.items()):
        safe_name = re.sub(r"[_-]+", " ", case_name).strip() or f"Case {uuid.uuid4().hex[:4]}"
        parsed.append((safe_name, _layout_from_files(safe_name, files)))
    return parsed
