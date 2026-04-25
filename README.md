# HackUPC_2026

Backend focus for the Mecalux warehouse optimizer.

## Backend Notes
- Q is minimized with the corrected formula: `(sum_price / sum_loads) ** (2 - coverage)`.
- Front gaps are one-sided and mandatory: they must stay inside the warehouse and clear of obstacles and other bay bodies.
- The backend keeps the public entrypoints `load_case(...)`, `compute_score(...)`, `validate_solution(...)`, `Solution.to_csv(...)`, and `BaseSolver.solve(...)`.
- The solver now supports `0°` through `180°`, including `180°` as a distinct front-gap direction from `0°`.

## Working Baselines
- `Case0`: `Q <= 2089.13`
- `Case1`: `Q <= 1347.63`
- `Case2`: `Q <= 4146.49`
- `Case3`: finish under `30s` and remain valid
