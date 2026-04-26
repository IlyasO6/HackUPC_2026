# Mecalux Layout Optimizer

> **HackUPC 2026** — Warehouse storage layout optimization with an interactive web editor.

An end-to-end system that solves the Mecalux warehouse packing challenge:
given a warehouse polygon, obstacles, a ceiling profile, and a catalog of
bay types, find the placement of bays that **minimizes** the quality metric:

```
Q = (Σ price / Σ loads) ^ (2 − coverage)
```

The project ships as a single FastAPI application with a Python backend
solver, live session-based editing, and a dark-themed SVG frontend.

---

## Quick Start

```bash
# 1. Install dependencies (Python 3.10+ required)
pip install -r api/requirements.txt

# 2. Start the server
uvicorn main:app --app-dir api --host 0.0.0.0 --port 8000

# 3. Open your browser
#    → http://127.0.0.1:8000/
```

Upload the 4 CSV files (warehouse, obstacles, ceiling, bay types), click
**START**, and the solver runs in the background. Once finished, you're
redirected to the interactive editor where you can move, rotate, delete,
add, or auto-suggest bays in real time.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Browser (Dark-mode SVG editor)                 │
│  dashboard.html → job.html → editor.html        │
└──────────────┬──────────────────────────────────┘
               │ REST + SSE
┌──────────────▼──────────────────────────────────┐
│  FastAPI  (api/)                                │
│  Routes · Pydantic models · Session store       │
│  Bridge · CSV parser · Job store                │
└──────────────┬──────────────────────────────────┘
               │ Python imports
┌──────────────▼──────────────────────────────────┐
│  Backend  (backend/)                            │
│  HybridSolver · Geometry · Validation · Scoring │
│  Models · Parsers · Spatial hash                │
└─────────────────────────────────────────────────┘
```

---

## Solver

The **HybridSolver** runs a 5-phase pipeline within a configurable time
budget (default: 15 seconds):

| Phase | Strategy | Description |
|-------|----------|-------------|
| 1 | Axis Sweep | Fast greedy scan along cardinal directions |
| 2 | Beam Search | Row-bundle construction with beam width 6 |
| 3 | Exact B&B | Branch-and-bound with optimistic pruning |
| 4 | Refinement | Row replacement and filler insertion |
| 5 | Gap Fill | Greedy individual-bay placement |

See [`algorithm_deep_dive.md`](algorithm_deep_dive.md) for the full
algorithm documentation, including the scoring formula analysis, constraint
system, and decision flowcharts.

---

## Live Editor

After optimization, the layout opens in an interactive SVG editor:

- **Click** a bay to select it
- **Drag** to reposition (calls `PATCH /layout/move`)
- **R** key or button to rotate +30°
- **Delete** key or button to remove
- **✨ Suggest** to auto-place the best improving bay
- **+ Place on layout** to manually add a bay at a clicked position

All operations complete in **< 5 ms** using incremental spatial hashing
and neighborhood-only revalidation.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/optimise` | Run solver on JSON input |
| `POST` | `/api/v1/optimise/files` | Run solver on CSV uploads |
| `PATCH` | `/api/v1/layout/move` | Move a bay |
| `PATCH` | `/api/v1/layout/rotate` | Rotate a bay |
| `PATCH` | `/api/v1/layout/delete` | Delete a bay |
| `POST` | `/api/v1/layout/suggest` | AI-suggest optimal placement |
| `POST` | `/api/v1/layout/add` | Manual bay placement |
| `GET` | `/api/v1/layout/{id}` | Get layout snapshot |
| `GET` | `/api/v1/jobs/{id}/stream` | SSE progress stream |
| `GET` | `/api/v1/testcases` | List bundled test cases |

Full endpoint reference in [`project_overview.md`](project_overview.md).

---

## Project Structure

```
HackUPC_2026/
├── backend/                 # Pure Python solver engine
│   ├── models/              # Domain dataclasses (BayType, Warehouse, etc.)
│   ├── geometry/            # SAT overlap, point-in-polygon, containment
│   ├── solver/              # HybridSolver, PlacementTemplate, SpatialHash
│   ├── validation/          # Constraint checking (5 rules)
│   ├── scoring/             # Q-score computation
│   ├── parsers/             # CSV file ingestion
│   └── main.py              # CLI entry point
├── api/                     # FastAPI web application
│   ├── templates/           # Jinja2 pages (dashboard, job, editor)
│   ├── routes.py            # API endpoints
│   ├── layout_session.py    # Live editing session state
│   └── main.py              # App factory
├── testcases/               # Challenge test data (Case0–Case3)
├── algorithm_deep_dive.md   # Full algorithm documentation
└── README.md                # This file
```

---

## Configuration

Key tunables in `backend/config.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEFAULT_TIME_BUDGET_SECONDS` | 15.0 | Solver wall-clock limit |
| `DEFAULT_BEAM_WIDTH` | 6 | States kept per beam iteration |
| `EXACT_NODE_LIMIT` | 3000 | Max branch-and-bound nodes |
| `ANGLE_STEP_DEGREES` | 30.0 | Rotation lattice (challenge rule) |

---

## Requirements

- **Python** ≥ 3.10
- **Dependencies:** `fastapi`, `uvicorn[standard]`, `python-multipart`, `jinja2`
- No external solver libraries — pure Python

---

## CLI Usage (Backend Only)

```bash
cd backend
python main.py ../testcases/Case0 --time-budget 15 --json result.json
```

Output: `solution.csv` + JSON summary + ASCII visualization.

---

## Documentation

| Document | Description |
|----------|-------------|
| [`README.md`](README.md) | Quick-start guide (this file) |
| [`algorithm_deep_dive.md`](algorithm_deep_dive.md) | Scoring formula, solver phases, constraints, improvements |
| [`project_overview.md`](project_overview.md) | Full module-by-module reference |
