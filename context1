# HackUPC 2026 - Mecalux Warehouse Optimizer (Current Backend Context)

This document is the current backend handoff for the project. It reflects the codebase after the hybrid solver refactor, the stricter gap-rule implementation, the shared geometry/validation layer, and the benchmark/regression tooling now in the repository.

## 1. Problem Summary

Goal: place storage bays inside an axis-aligned warehouse polygon to minimize:

`Q = (sum_price / sum_loads) ^ (2 - coverage)`

where:
- `coverage = total_bay_area / warehouse_area`
- `total_bay_area` uses each bay footprint `width * depth`

Lower Q is better.

Inputs per case:
1. `warehouse.csv`: warehouse boundary polygon
2. `obstacles.csv`: unusable axis-aligned rectangles
3. `ceiling.csv`: step-function ceiling profile by X coordinate
4. `types_of_bays.csv`: catalog `[id, width, depth, height, gap, n_loads, price]`

Output:
- CSV rows: `Id, X, Y, Rotation`
- `X, Y` are the bay local origin on the `x = 0` back side
- `Rotation` is in degrees in `[0, 180]`

## 2. Rules and Current Interpretation

The backend currently enforces the following:

1. Bay type id must exist.
2. Bay body must stay fully inside the warehouse polygon.
3. Bay body cannot overlap obstacles.
4. Bay bodies cannot overlap each other; boundary touching is allowed.
5. Bay height must fit the minimum ceiling across the full rotated X-span.
6. Front gap is one-sided and mandatory:
   - local front face is the edge at `x = width`
   - the gap extends outward by `gap`
   - the gap must stay inside the warehouse
   - the gap must not overlap obstacles
   - the gap must not overlap any other bay body
7. `180 deg` is treated as distinct from `0 deg` because the front gap flips sides.

Important practical note:
- The sample warehouses are strongly orthogonal, so many best-scoring sample solutions are still mostly `0 deg` / `90 deg`, with `180 deg` appearing when front-gap polarity helps.
- Arbitrary-angle support is still real and implemented in the backend: geometry, validator, fixed-step angle search, non-cardinal candidate generation, and regression tests all support non-cardinal rotations.

## 3. Current Backend Architecture

Backend is Python 3.11+ with no heavy dependency stack.

Key files:

```text
backend/
├── main.py
├── benchmark.py
├── models/
│   ├── bay_type.py
│   ├── case_data.py
│   ├── ceiling.py
│   ├── obstacle.py
│   ├── solution.py
│   └── warehouse.py
├── geometry/
│   ├── obb.py
│   ├── polygon.py
│   └── spatial.py
├── scoring/
│   └── scorer.py
├── solver/
│   ├── base.py
│   ├── greedy.py      # compatibility shim
│   ├── hybrid.py      # real solver implementation
│   ├── layout.py      # cached placement/state primitives
│   └── spatial_hash.py
├── validation/
│   ├── rules.py       # shared placement rules
│   └── validator.py
└── tests/
    └── test_regressions.py
```

### Shared placement/state layer

`backend/solver/layout.py` contains:
- `PlacementTemplate`: cached geometry for `(bay_type, angle)`
- `PlacedFootprint`: placed body/gap polygons with cached AABBs and rotated X-span
- `RowCandidate`, `RowBundle`, `LayoutState`
- shared score-from-totals helper

`backend/solver/spatial_hash.py` provides the broad-phase spatial index used by solver/validator logic.

`backend/validation/rules.py` is the shared rule engine used by both the solver and the final validator. This was added specifically to avoid solver/validator drift.

## 4. Current Solver

The real solver is now `HybridSolver` in `backend/solver/hybrid.py`.

`backend/solver/greedy.py` still exists only as a compatibility shim that aliases `HybridSolver` for any older imports.

### Current search pipeline

1. **Axis sweep baseline**
   - fast constructive pass over `0 deg`, `90 deg`, `180 deg`
   - designed to exploit the strongly orthogonal nature of the real sample warehouses
   - usually produces the best density-to-runtime baseline

2. **Seeded row search**
   - beam-search row constructor
   - starts from the axis baseline and also keeps an empty-layout challenger
   - uses cached `PlacementTemplate`s and shared validation rules
   - candidate anchors come from:
     - warehouse vertices
     - obstacle corners
     - ceiling breakpoints
     - existing row anchors
     - existing placed-body / gap polygon corners

3. **Angle search**
   - hybrid mode does a coarse angle pass first
   - then refines around promising angles
   - fixed-step mode is also available through CLI flags

4. **Refinement**
   - deterministic local improvement pass
   - can extend/fill layouts after the constructive phase
   - includes an explicit non-cardinal probe stage so non-cardinal candidates are not silently ignored when they improve Q

### Why sample outputs are still often orthogonal

The warehouses, obstacles, and bay catalog all heavily favor long orthogonal strips. Because Q strongly rewards dense packing with good price/load efficiency, the best sample solutions often remain axis-aligned even though non-cardinal placement is supported. This is now an optimization outcome, not a missing feature.

## 5. CLI and Tooling

`backend/main.py` now runs `HybridSolver`, not the old greedy solver implementation.

Current CLI options:
- `--time-budget`
- `--angle-mode`
- `--angle-step`
- `--seed`
- `--output`
- `--json`
- visualization toggles

JSON summaries include:
- solver name
- validity
- Q
- coverage
- elapsed time
- counts by bay type
- counts by rotation

`backend/benchmark.py` runs all testcases in memory and prints one JSON line per case.

## 6. Regression Coverage

`backend/tests/test_regressions.py` currently checks:
- one-sided front-gap behavior
- back-to-back validity with `180 deg`
- gap-inside-warehouse rule
- gap-vs-obstacle rule
- touching boundaries allowed
- non-cardinal rotated placement validity
- ceiling checked across rotated X-span
- `0 deg` and `180 deg` producing different gap directions
- fixed-step angle mode includes non-cardinal angles

## 7. Current Sample-Case Status

Recent solver runs with `time_budget = 29s` produced valid solutions for all sample cases.

Representative results from the current backend:
- `Case0`: Q about `1448.1180`, coverage about `69.33%`
- `Case1`: Q about `856.9837`, coverage about `85.00%`
- `Case2`: Q about `2810.4739`, coverage about `65.70%`
- `Case3`: Q about `1829.7774`, coverage about `72.06%`

Angle mix observed in current sample outputs:
- `Case0`: `0 deg`, `90 deg`
- `Case1`: `0 deg`, `90 deg`
- `Case2`: `0 deg`, `90 deg`
- `Case3`: `0 deg`, `90 deg`, `180 deg`

So the backend now definitely handles the full rule set, but the current real sample geometries still mostly optimize best with orthogonal placements.

## 8. Current Reality Check / Outstanding Work

What is already solid:
- corrected Q formula
- strict front-gap handling
- shared solver/validator rule engine
- spatial hashing
- hybrid solver entrypoint in main CLI
- regression coverage for geometry/rules
- benchmark runner for backend-only iteration

What still needs improvement if we want more score:
- stronger non-cardinal packing wins on real samples
- better row replacement / rearrangement once an axis baseline exists
- more aggressive pocket-filling around obstacles and concave boundaries
- possibly a richer local-search neighborhood that can remove and rebuild groups of rows, not only add/replace one at a time

## 9. Recommended Next Backend Iteration

If backend work continues, the best next step is:

1. add a remove-and-repack neighborhood around obstacle-adjacent regions
2. let refinement rebuild a small cluster of rows instead of only one row at a time
3. explicitly score non-cardinal angle candidates in residual pockets against cardinal fillers on the same local region
4. keep using the current shared validation/rule engine as the single source of truth
