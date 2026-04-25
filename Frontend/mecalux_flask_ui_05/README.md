# Mecalux Flask UI - HackUPC frontend

Flask remains the UI host for the HackUPC warehouse optimizer. The UI supports
two modes:

| Mode | Flask behavior | Backend behavior |
| --- | --- | --- |
| `mock` | Uses local mock projects, jobs, and Socket.IO progress events | No FastAPI calls |
| `real` | Keeps layout/project state in Flask, then bridges solve/score/validate to FastAPI | Calls `http://localhost:8000/api/v1/*` and consumes SSE progress |

## Run

### Mock mode

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: `http://localhost:5000`

### Real mode

Start the FastAPI backend first on port `8000`, then run Flask with:

```bash
BACKEND_MODE=real
BACKEND_URL=http://localhost:8000
python app.py
```

On Windows PowerShell:

```powershell
$env:BACKEND_MODE = "real"
$env:BACKEND_URL = "http://localhost:8000"
python app.py
```

Open: `http://localhost:5000`

## Real mode flow

1. The editor saves layout state in Flask through `/api/layouts/<project_id>`.
2. Clicking `Run optimization` posts the current browser layout to
   Flask `/api/jobs`.
3. Flask bridges the solve request to FastAPI `POST /api/v1/solve/json`.
4. The job page consumes progress from Flask `/api/jobs/<job_id>/stream`,
   which proxies FastAPI SSE from `/api/v1/jobs/<job_id>/stream`.
5. Manual edits on the job page call Flask `/api/score` and `/api/validate`,
   which bridge to FastAPI `/api/v1/score` and `/api/v1/validate`.

## What works

- Dashboard and project list
- Case upload into Flask project state
- Measurement-based bay creation in the editor and job pages
- Local save in both modes
- Real solve bridge to FastAPI `/api/v1/solve/json`
- Real SSE progress bridge for optimization jobs
- Real score and validate bridge for interactive edits
- Mock mode job flow preserved with fake Socket.IO progress

## Notes

- The Flask UI no longer calls nonexistent backend `/api/jobs` or
  `/api/layouts` endpoints in real mode.
- The UI snaps rotation to 30-degree steps before sending edits.
- In both pages the striped front gap may overlap only other gaps and does not
  count toward covered area.
