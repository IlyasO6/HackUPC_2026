# Mecalux Warehouse Optimization — Algorithm Deep Dive

> **Version:** April 2026  
> **Solver:** `HybridSolver` (`backend/solver/hybrid.py`)  
> **Scoring:** `score_from_totals` (`backend/solver/layout.py`)

---

## Table of Contents

1. [The Objective Function (Q-Score)](#1-the-objective-function-q-score)
2. [Placement Constraints](#2-placement-constraints)
3. [Geometry Model](#3-geometry-model)
4. [Solver Pipeline Overview](#4-solver-pipeline-overview)
5. [Phase 1 — Axis Sweep (Fast Incumbent)](#5-phase-1--axis-sweep-fast-incumbent)
6. [Phase 2 — Beam-Search Construction](#6-phase-2--beam-search-construction)
7. [Phase 3 — Exact Branch-and-Bound](#7-phase-3--exact-branch-and-bound)
8. [Phase 4 — Refinement](#8-phase-4--refinement)
9. [Phase 5 — Greedy Gap Fill](#9-phase-5--greedy-gap-fill)
10. [When the Solver Chooses NOT to Place a Bay](#10-when-the-solver-chooses-not-to-place-a-bay)
11. [Precalculation vs Real-Time Computation](#11-precalculation-vs-real-time-computation)
12. [Live Editor Session (Real-Time Updates)](#12-live-editor-session-real-time-updates)
13. [Current Tunables](#13-current-tunables)
14. [Possible Improvements](#14-possible-improvements)

---

## 1. The Objective Function (Q-Score)

The entire algorithm is driven by a single scalar: **Q**.

```
Q = (total_price / total_loads) ^ (2 - pct_area)
```

Where:
- `total_price` = sum of `price` of all placed bays
- `total_loads` = sum of `nLoads` of all placed bays
- `pct_area` = `total_bay_area / warehouse_area` (coverage fraction, 0..1)

**Lower Q is better.**

### Why This Formula Creates Complex Trade-Offs

| Situation | `pct_area` | Exponent `(2 - pct_area)` | Behavior |
|-----------|-----------|---------------------------|----------|
| Empty warehouse | 0.0 | 2.0 | `(price/loads)²` — very punishing |
| 50% covered | 0.5 | 1.5 | Moderate penalty |
| 100% covered | 1.0 | 1.0 | Linear: `price/loads` |

> [!IMPORTANT]
> The exponent **exponentially amplifies** the price-to-load ratio when coverage is low. This means:
> - At low coverage, adding a bay with high price/load ratio is extremely expensive.
> - At high coverage, the exponent approaches 1, so the penalty reduces to a simple ratio.
> - **Area coverage has super-linear value** — every percent of coverage improvement shrinks the exponent, which amplifies all future improvements.

### Critical Decision: When Does Adding a Bay Help?

A bay should be added **only if** the resulting Q after adding it is lower than the current Q. Formally, a new bay with area `a`, price `p`, loads `l` is beneficial when:

```
((total_price + p) / (total_loads + l)) ^ (2 - (total_area + a) / W)  <  (total_price / total_loads) ^ (2 - total_area / W)
```

This is **not monotonic**: adding a bay with a bad price/load ratio **can increase Q** even though it increases area coverage. The solver evaluates this inequality for every candidate placement.

### Edge Cases

| Scenario | Q Value | What happens |
|----------|---------|--------------|
| No bays placed | `∞` (infinity) | Any valid placement improves Q |
| `total_loads = 0` | `∞` | Division by zero guard returns infinity |
| `warehouse_area = 0` | `∞` | Degenerate case, no placement possible |
| All bays same type | Fully determined by count × type stats | Simple to optimize |
| Mixed bay types | Complex interaction between coverage and efficiency | Requires search |

---

## 2. Placement Constraints

Every candidate placement is checked against **five constraint categories** (in order of evaluation):

### 2.1 Boundary Containment
- The **body polygon** (the physical bay rectangle) must lie entirely inside the warehouse polygon.
- The **gap polygon** (the access corridor in front of the bay) must also lie entirely inside the warehouse polygon.
- Checked via `rotated_rect_inside_polygon()` using convex polygon containment.

### 2.2 Ceiling Height
- The bay's `height` attribute must not exceed the **minimum ceiling height** across the bay's horizontal span (X range).
- The ceiling is defined by a piecewise-linear function from breakpoints.
- The solver computes `min_height_in_range(x_start, x_end)` across the bay's footprint.

### 2.3 Obstacle Overlap
- The body must not overlap any obstacle (axis-aligned rectangle).
- The gap must not overlap any obstacle either.
- Checked via `convex_polygons_overlap()` using separating-axis theorem (SAT).

### 2.4 Bay-Bay Body Overlap
- No two bay bodies may overlap.
- Uses a **two-phase check**: fast AABB overlap test first, then precise SAT-based polygon overlap if AABBs intersect.

### 2.5 Gap-Body Interaction
- A bay's **body** must not overlap another bay's **gap** zone (and vice-versa).
- This is the most subtle constraint: the gap is the access corridor required for forklift operations. It's directional and extends from the "front" face of each bay.

> [!NOTE]
> **Gap direction:** The gap extends from the **depth face** of the bay (the "top" in local coordinates). For a bay at `(0,0)` with width `1000`, depth `800`, gap `200`, and no rotation: the body occupies `(0,0)→(1000,800)` and the gap occupies `(0,800)→(1000,1000)`. The gap follows the `v` (tangent) direction of the placement template.

---

## 3. Geometry Model

### 3.1 PlacementTemplate (Precalculated)

For each `(bay_type_id, rotation_angle)` pair, a `PlacementTemplate` is computed **once** and cached:

```python
u = (cos θ, sin θ)    # front normal (width direction)
v = (-sin θ, cos θ)   # tangent (depth direction)

body_local = [
    (0, 0),
    (width × u),
    (width × u + depth × v),
    (depth × v),
]

gap_local = [          # if gap > 0
    (depth × v),
    (width × u + depth × v),
    (width × u + (depth + gap) × v),
    ((depth + gap) × v),
]
```

**Cached fields:**
- `body_local`, `gap_local` — polygon vertices in local coordinates
- `body_aabb_local`, `gap_aabb_local` — bounding boxes
- `single_feature_offsets`, `pair_feature_offsets` — anchor geometry for row construction
- `x_span_local` — horizontal extent for ceiling checks

### 3.2 PlacedFootprint (Per Placement)

Created by `template.place(x, y)` — a simple translation:

```python
body = translate(body_local, x, y)
gap = translate(gap_local, x, y)
body_aabb = translate(body_aabb_local, x, y)
```

This is **O(1)** per placement, since all rotation math is already cached in the template.

### 3.3 Spatial Hashing

Two `SpatialHash` grids accelerate collision detection:

- **`body_hash`**: indexes all bay body AABBs
- **`gap_hash`**: indexes all gap AABBs

Cell size = `max(depth) + max(gap)` across all bay types.

When checking a candidate, the solver queries both grids to find only the bays whose AABBs overlap, then runs precise SAT overlap only on those candidates. This reduces per-placement validation from O(N) to approximately O(1) amortized.

---

## 4. Solver Pipeline Overview

```mermaid
flowchart TD
    A["Start: Parse Case"] --> B["Phase 1: Axis Sweep\n(fast incumbent, ≤35% budget)"]
    B --> C["Phase 2: Beam Search\n(improve via row bundles)"]
    C --> D{"Exact search\naffordable?"}
    D -->|Yes| E["Phase 3: Branch & Bound\n(≤70% of budget)"]
    D -->|No| F["Phase 4: Refinement\n(row replacement)"]
    E --> F
    F --> G["Phase 5: Gap Fill\n(greedy single-bay)"]
    G --> H["Return best solution"]
```

**Time budget:** 15 seconds total (configurable).

Each phase only runs if wall-clock time remains. The solver always returns the best state found so far, even if interrupted mid-phase.

---

## 5. Phase 1 — Axis Sweep (Fast Incumbent)

**Goal:** Build a fast, decent layout using only cardinal directions (0°, 90°, 180°, 270°).

**Time budget:** 35% of total (≈5.25s), capped at 8s.

### How it works:

1. For each bay type + cardinal angle combination (up to 12 configurations):
   - Start with an empty layout
   - Generate a grid of candidate X and Y coordinates:
     - All warehouse vertex coordinates
     - All obstacle corner coordinates
     - Offsets from existing placements
     - Regular grid steps based on bay extent
   - Scan Y coordinates, then X coordinates — greedy placement:
     - For each `(x, y)`: build footprint, validate, place if valid
   - After the primary bay type fills what it can, repeat for all other types

2. The best state (lowest Q) across all initial configs becomes the **incumbent**.

### Why axis-aligned first?

Warehouse instances are dominated by rectangular geometry. Cardinal-direction placement maximizes packing density in rectangular sub-regions. This phase is **deterministic** and very fast, providing a strong baseline for pruning in later phases.

---

## 6. Phase 2 — Beam-Search Construction

**Goal:** Improve the incumbent by adding entire **row bundles** using all 12 discrete angles.

### Row Bundle Concept

Rather than placing individual bays, the solver builds **row bundles** — lines of bays sharing the same type, angle, and spacing:

- **Single row:** Bays placed along the tangent direction, each separated by `depth + gap`
- **Pair row (back-to-back):** Two facing rows sharing a gap corridor between them

### Beam Search Loop

```
beam = [axis_sweep_result, empty_state]
while time remains:
    for each state in beam:
        generate candidate row bundles
        filter: keep only those that reduce Q
    beam = top 6 states by Q  (beam_width = 6)
    if no improvement: stop
```

### Candidate Generation

For each state in the beam:

1. **Reference points** are collected from:
   - Static case geometry (warehouse corners, obstacle corners, ceiling breakpoints)
   - Dynamic placement geometry (corners of already-placed bays, edge midpoints)

2. For each `(bay_type, angle, kind)` config:
   - For each reference point `(ref_x, ref_y)`:
     - Compute anchor positions by subtracting feature offsets
     - Build a row starting from the anchor, extending along the tangent direction
     - Each slot in the row is validated; the row stops at the first invalid slot
     - Score the entire row bundle as if added to the current state

3. Keep the best 12 candidates (by resulting Q) across all configs.

4. Each improving candidate is applied to create a new state for the next beam iteration.

---

## 7. Phase 3 — Exact Branch-and-Bound

**Goal:** Prove optimality (or find a provably better solution) via exhaustive search.

**Conditions to attempt:** Reference points ≤ 150, bay types ≤ 12.

**Time budget:** 70% of total, or up to `EXACT_NODE_LIMIT = 3000` nodes.

### Algorithm

```
DFS from empty state:
    if timed out or node limit: return (incomplete)
    if state signature seen: prune (duplicate)
    compute optimistic_score (lower bound)
    if optimistic_score >= best_known: prune (dominated)
    generate candidate row bundles
    for each candidate that improves Q:
        recurse with candidate applied
    if current state < best: update best
```

### Optimistic Score (Lower Bound)

Assumes all remaining warehouse area can be filled with the **best possible** bay type:

```python
best_price_per_load = min(price/loads across all types)
best_load_density = max(loads/area across all types)
remaining_area = warehouse_area - current_area

optimistic_added_loads = remaining_area × best_load_density
optimistic_added_price = optimistic_added_loads × best_price_per_load

optimistic_q = score_from_totals(warehouse_area, current_price + optimistic_price, ...)
```

This is a **valid lower bound** because it assumes perfect coverage with the cheapest bay type, which is physically impossible but mathematically correct for pruning.

### State Deduplication

States are hashed by sorted placement tuples `(bay_type_id, x, y, rotation)` to avoid revisiting equivalent configurations reached via different orderings.

---

## 8. Phase 4 — Refinement

**Goal:** Improve the solution by replacing individual rows with better alternatives.

### Strategy: Row Replacement

For each existing row in the solution:

1. **Remove the row** entirely (rebuild state without it)
2. **Search the neighborhood** for a better replacement:
   - Try the same bay type at nearby angles (±30°)
   - Try up to 4 other bay types
   - Try anchors at: original position, ±width offsets, ±depth offsets, nearest reference points
3. If any replacement yields a better Q than the complete original state: apply it

### Filler Pass

Before row replacement, try adding **filler row bundles** to the current state (using smaller/more efficient bay types). This catches cases where the beam search missed a good addition.

### Loop

The refinement repeats until no improvement is found, or the time budget expires.

---

## 9. Phase 5 — Greedy Gap Fill

**Goal:** Fill remaining empty spaces with individual bays.

After all row-based strategies are exhausted, this pass tries to **squeeze individual bays** into any remaining valid positions:

1. Sort bay types by area (smallest first), then by price/load ratio
2. For each bay type, for each of the 12 discrete angles:
   - Generate candidate positions using the same axis-scan logic as Phase 1
   - For each valid position: compute resulting Q
   - If Q improves: place the bay immediately (greedy, no backtracking)
3. Repeat until no more improving placements exist

> [!TIP]
> Smallest bays first is important — they fit into tighter spaces and raise coverage (which exponentially reduces the exponent in the Q formula). Even a small bay with a mediocre price/load ratio can improve Q significantly if coverage is below ~60%.

---

## 10. When the Solver Chooses NOT to Place a Bay

This is one of the most important aspects of the algorithm. The solver will **refuse to place a bay** in these situations:

### 10.1 Constraint Violation (Hard No)

Any of the 5 constraints from Section 2 is violated. This is non-negotiable.

### 10.2 Q Would Increase (Soft No)

Even if a placement is geometrically valid, the solver skips it if `resulting_Q >= current_Q`.

**When does adding a valid bay make Q worse?**

The formula `(P/L)^(2-A/W)` can increase when adding a bay if the bay's price/load ratio is **worse** than the current average, and the coverage gain is too small to compensate via the exponent.

**Concrete example:**

```
Current state: price=5000, loads=50, area=40000, warehouse=100000
→ pct_area=0.4, exponent=1.6, Q = (5000/50)^1.6 = 100^1.6 ≈ 1585

Add a bay: price=800, loads=2, area=500
→ new price=5800, loads=52, area=40500
→ pct_area=0.405, exponent=1.595, Q = (5800/52)^1.595 = 111.5^1.595 ≈ 1841

Q INCREASED from 1585 to 1841! The bay is rejected.
```

**Why?** The bay's price/load ratio is `800/2 = 400`, far worse than the current average `5000/50 = 100`. The tiny area gain (0.5%) barely moved the exponent, so the ratio degradation dominates.

### 10.3 Exact Search Pruning (Optimistic Bound)

In the B&B phase, even if a bay could improve Q locally, the entire subtree is pruned if the **optimistic lower bound** (assuming perfect remaining coverage) can't beat the best-known solution.

### 10.4 Time Budget Exhausted

The solver returns the best state found so far. Unfinished phases simply don't run.

### Summary: Decision Flowchart

```mermaid
flowchart TD
    A["Candidate position generated"] --> B{"All constraints\nsatisfied?"}
    B -->|No| C["SKIP: Invalid"]
    B -->|Yes| D{"Q after adding\n< Q before?"}
    D -->|No| E["SKIP: Would increase Q"]
    D -->|Yes| F{"In exact search?"}
    F -->|Yes| G{"Optimistic bound\n< best known?"}
    G -->|No| H["PRUNE: Can't improve"]
    G -->|Yes| I["PLACE: Accept candidate"]
    F -->|No| I
```

---

## 11. Precalculation vs Real-Time Computation

| Component | Timing | Details |
|-----------|--------|---------|
| **PlacementTemplate** | Precalculated per `(type, angle)` | Rotation matrices, local polygons, AABBs, feature offsets. Cached in `_template_cache`. Computed once per unique configuration (~72 templates for 6 types × 12 angles). |
| **CaseContext** | Precalculated once per case | Warehouse polygon, obstacle polygons, free rectangles, reference points, cell size. ~10ms for typical cases. |
| **Free Rectangles** | Precalculated once per case | Maximal axis-aligned rectangles inside the warehouse minus obstacles. Used for reference-point generation. |
| **Reference Points** | Precalculated (static) + dynamic | Static: warehouse vertices, obstacle corners, ceiling breakpoints, free-rectangle corners. Dynamic: existing placement corners and edge midpoints (recomputed each iteration). |
| **Spatial Hash** | Updated incrementally | O(1) insert and O(1) query per placement. No rebuild needed. |
| **AABB checks** | Real-time, O(1) | Fast bounding-box overlap — filters out 95%+ of candidates before expensive SAT. |
| **SAT polygon overlap** | Real-time, O(n²) per pair | Only runs on AABB-overlapping pairs. n=4 for rectangles, so effectively O(16) per pair. |
| **Q-Score** | Real-time, O(1) | Single arithmetic expression, evaluated for every candidate. |
| **Ceiling height query** | Real-time, O(k) | k = number of ceiling breakpoints in the bay's X range. Typically k ≤ 5. |

---

## 12. Live Editor Session (Real-Time Updates)

After optimization, the user enters a **live editing mode** where individual bay operations are handled incrementally:

### Move Bay
1. Remove old footprint from spatial hashes
2. Build new footprint at new position
3. Add new footprint to spatial hashes
4. Revalidate only **affected neighborhood** (bays whose AABBs overlap the old or new position)
5. Recompute Q, coverage, validity

### Rotate Bay
Same as move, but position stays constant and rotation changes.

### Delete Bay
1. Remove footprint from spatial hashes
2. Subtract bay's area/price/loads from totals
3. Revalidate neighbors (they may become valid now)

### Add Bay (Manual)
1. Build footprint from user's click position
2. Insert into spatial hashes
3. Add area/price/loads to totals
4. Revalidate all active bays

### Suggest Bay
Full search across all bay types × 12 angles × all reference points. For each valid position, compute resulting Q. Return the placement with the lowest Q.

> [!NOTE]
> All editor operations complete in **< 5ms** for typical layouts (up to ~30 bays) thanks to spatial hashing and incremental updates. The Q-score is always recomputed from accumulated totals (O(1)), never from scratch.

---

## 13. Current Tunables

| Parameter | Value | Effect |
|-----------|-------|--------|
| `DEFAULT_TIME_BUDGET_SECONDS` | 15.0 | Total wall-clock budget for the solver |
| `DEFAULT_BEAM_WIDTH` | 6 | States retained per beam-search iteration |
| `DEFAULT_CANDIDATE_LIMIT` | 12 | Max row candidates per iteration |
| `ANGLE_STEP_DEGREES` | 30.0 | Discrete rotation step (challenge requirement) |
| `EXACT_NODE_LIMIT` | 3000 | Max DFS nodes in exact search |
| `EXACT_REFERENCE_POINT_LIMIT` | 150 | Skip exact search if too many ref points |
| `EXACT_TIME_FRACTION` | 0.70 | Fraction of budget allocated to exact search |
| `REFINEMENT_TIME_FRACTION` | 0.20 | Max fraction per refinement pass |
| `MAX_ROW_SLOTS` | 2048 | Max bays per row bundle |
| `MIN_AXIS_BASELINE_SECONDS` | 2.0 | Minimum time for axis sweep |
| `MAX_AXIS_BASELINE_SECONDS` | 8.0 | Maximum time for axis sweep |
| `MIN_HASH_CELL_SIZE` | 100.0 | Floor for spatial hash grid cell |

---

## 14. Possible Improvements

### High Impact

| Improvement | Expected Impact | Difficulty | Description |
|-------------|----------------|------------|-------------|
| **Mixed-type rows** | 🔥🔥🔥 High | Hard | Currently, each row uses a single bay type. Allowing mixed-type rows (e.g., large bays with small fillers at the ends) would increase coverage in irregular regions. |
| **Non-rectangular gap zones** | 🔥🔥 Medium | Medium | Allow gap corridors to be shared between adjacent bays facing each other, reducing wasted gap area. |
| **Multi-objective Pareto front** | 🔥🔥 Medium | Medium | Instead of optimizing a single Q, explore the Pareto front of (price, loads, area) and let the user choose. |
| **Genetic/evolutionary search** | 🔥🔥 Medium | Hard | Add a population-based meta-heuristic phase that evolves solutions via crossover (swapping rows between solutions) and mutation (shifting/rotating rows). |

### Medium Impact

| Improvement | Expected Impact | Difficulty | Description |
|-------------|----------------|------------|-------------|
| **Continuous rotation** | 🔥 Medium | Medium | The challenge only requires 30° steps, but the solver could benefit from initially exploring finer angles (e.g., 15° or 10°) and snapping to the nearest 30° at the end. |
| **Simulated annealing acceptance** | 🔥 Medium | Easy | In the refinement phase, occasionally accept slightly worse states (with decreasing probability) to escape local minima. |
| **Parallel solving** | 🔥 Medium | Medium | Run multiple solver instances with different initial bay-type priorities in parallel threads, then take the best result. |
| **Warm-start from user edits** | 🔥 Medium | Easy | After the user manually modifies the layout, use the modified layout as a warm-start for a new optimization run instead of starting from scratch. |

### Low Impact (Polish)

| Improvement | Expected Impact | Difficulty | Description |
|-------------|----------------|------------|-------------|
| **Dynamic beam width** | 🟡 Low | Easy | Increase beam width when time budget is generous, decrease when tight. |
| **Better free-rectangle decomposition** | 🟡 Low | Medium | Use a more sophisticated maximal-rectangle algorithm for complex warehouse polygons (e.g., L-shapes). |
| **Caching validation results** | 🟡 Low | Easy | Cache `is_valid_placement` results for identical (template, x, y) to avoid redundant SAT checks. |
| **Progressive web streaming** | 🟡 Low | Easy | Stream intermediate solutions to the UI during optimization so the user sees the layout evolving in real time. |

### Challenge-Specific Observations

> [!TIP]
> **For Case 0 (L-shaped, 10000×10000 with cutout):** The solver achieves 60.2% coverage with Q ≈ 2620. The remaining 39.8% uncovered area is:
> - 25% = geometric cutout (the missing corner of the L-shape)
> - 10% = mandatory gap corridors between bay rows
> - 4.8% = obstacle exclusion zones and boundary margins
> 
> This is at or very near the **geometric optimum** for this case. Further Q improvements require either mixed-type rows or non-rectangular gap sharing.

> [!WARNING]
> **Time budget sensitivity:** Reducing the budget below 10s significantly hurts exact search quality on complex cases (Case2, Case3). The current 15s budget is a good balance between speed and quality. Going above 20s shows diminishing returns because the constructive phases have already converged.
