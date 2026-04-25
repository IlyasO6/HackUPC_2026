# HackUPC_2026

Integrated Mecalux warehouse layout optimizer with:

- a Python backend solver using the shared geometric validation rules
- a FastAPI layer that stores optimized layouts in a live in-memory session
- a static frontend served by the same FastAPI app for drag, rotate, and
  delete interactions

## Run

Start the whole stack with one command from the repository root:

```bash
uvicorn main:app --app-dir api --host 0.0.0.0 --port 8000
```

Then open `http://127.0.0.1:8000/`.

## Notes

- Q is minimized with the challenge formula
  `(sum_price / sum_loads) ** (2 - coverage)`.
- Live edits never call the heavy solver again; they update the in-memory
  session and revalidate only the affected neighborhood.
- Rotations are snapped to the discrete challenge lattice
  `{0, 30, 60, ..., 330}`.
- The solver performs an exact branch-and-bound pass on tiny candidate
  frontiers and deterministic constructive refinement on larger cases.
