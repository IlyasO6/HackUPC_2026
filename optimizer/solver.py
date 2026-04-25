"""
MOCK Optimizer Solver — Replace with the real optimizer from your teammate.

This mock simulates a 10-second optimization run and returns fake placed bays.
It uses the on_progress callback to emit progress updates for SSE streaming.

CONTRACT:
    solve(warehouse, obstacles, ceiling, bay_types, on_progress) -> dict

    on_progress(percent: int, message: str) is called periodically during solving.

When your teammate's optimizer is ready, replace this file with their implementation
keeping the same function signature.
"""
import time
import random


def solve(
    warehouse: list[dict],
    obstacles: list[dict],
    ceiling: list[dict],
    bay_types: list[dict],
    on_progress: callable = None,
) -> dict:
    """
    Mock optimizer that simulates work and returns a fake result.

    Args:
        warehouse:  List of {x, y} wall points defining the polygon
        obstacles:  List of {x, y, width, depth} obstacles
        ceiling:    List of {x, height} ceiling profile points
        bay_types:  List of {id, width, depth, height, gap, nLoads, price}
        on_progress: Callback(percent: int, message: str) for progress updates

    Returns:
        dict with keys: placed_bays, Q, B, E, coverage, solved_in_ms
    """
    total_steps = 20
    start = time.time()

    for step in range(total_steps + 1):
        time.sleep(0.3)  # Simulate work (~6s total)
        percent = int((step / total_steps) * 100)
        if on_progress:
            on_progress(percent, f"Mock iteration {step}/{total_steps}")

    # Generate some fake placed bays using available bay types
    placed_bays = []
    x_cursor = 0
    for i, bay in enumerate(bay_types[:4]):  # Place up to 4 bays
        placed_bays.append({
            "id": bay["id"] if isinstance(bay, dict) else bay.id,
            "x": x_cursor,
            "y": 0,
            "rotation": random.choice([0, 90]),
        })
        width = bay["width"] if isinstance(bay, dict) else bay.width
        x_cursor += width + 100  # Add some spacing

    elapsed_ms = int((time.time() - start) * 1000)

    return {
        "placed_bays": placed_bays,
        "Q": round(random.uniform(100, 500), 2),
        "B": round(random.uniform(50, 200), 2),
        "E": round(random.uniform(0.5, 2.0), 2),
        "coverage": round(random.uniform(0.3, 0.9), 4),
        "solved_in_ms": elapsed_ms,
    }
