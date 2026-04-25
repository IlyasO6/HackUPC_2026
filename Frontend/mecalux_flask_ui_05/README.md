# Mecalux Flask UI — HackUPC scaffold

Mock-first Flask frontend for the Mecalux warehouse optimizer challenge.

## Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: http://localhost:5000

## What works

- Dashboard
- Project list
- Create project
- Warehouse editor mock canvas
- Add/remove shelves
- Save layout to mock API
- Optimization job page
- POST `/api/jobs`
- GET `/api/jobs/<id>`
- Fake WebSocket progress
- Streaming logs
- Mock final result heatmap

## What this intentionally does not do

- No optimizer logic
- No real backend calls
- No shelf placement validation
- No business logic
