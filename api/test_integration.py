"""Quick integration test: validates all imports and score matching."""
import json
import os
import sys

def main():
    # Test imports
    try:
        from bridge import to_case_data, solution_to_api, dicts_to_case_data, dicts_to_solution
        print("✓ bridge imports OK")
    except Exception as e:
        print(f"✗ bridge import FAILED: {e}")
        return

    try:
        from api_models import OptimizationInput, SolveResult, PlacedBay, Job
        print("✓ api_models imports OK")
    except Exception as e:
        print(f"✗ api_models import FAILED: {e}")
        return

    try:
        from csv_parser import parse_all
        print("✓ csv_parser imports OK")
    except Exception as e:
        print(f"✗ csv_parser import FAILED: {e}")
        return

    try:
        from job_store import create_job, get_job
        print("✓ job_store imports OK")
    except Exception as e:
        print(f"✗ job_store import FAILED: {e}")
        return

    try:
        from scorer import calculate_score, validate_placement
        print("✓ scorer imports OK")
    except Exception as e:
        print(f"✗ scorer import FAILED: {e}")
        return

    try:
        from routes import router
        print("✓ routes imports OK")
    except Exception as e:
        print(f"✗ routes import FAILED: {e}")
        return

    # Test with Case0
    case_dir = os.path.join(os.path.dirname(__file__), "..", "testcases", "Case0")
    with open(os.path.join(case_dir, "warehouse.csv")) as f:
        wh = f.read()
    with open(os.path.join(case_dir, "obstacles.csv")) as f:
        obs = f.read()
    with open(os.path.join(case_dir, "ceiling.csv")) as f:
        ceil = f.read()
    with open(os.path.join(case_dir, "types_of_bays.csv")) as f:
        bt = f.read()

    input_data = parse_all(wh, obs, ceil, bt)
    case = to_case_data(input_data)
    print(f"✓ Case0 parsed: area={case.warehouse.area}")

    # Score the known backend result
    with open(os.path.join(os.path.dirname(__file__), "..", "backend", "result_case0.json")) as f:
        result_data = json.load(f)

    placements = result_data["placements"]
    bt_dicts = [
        {"id": b.id, "width": b.width, "depth": b.depth, "height": b.height,
         "gap": b.gap, "nLoads": b.nLoads, "price": b.price}
        for b in input_data.bay_types
    ]
    wh_dicts = [{"x": p.x, "y": p.y} for p in input_data.warehouse]
    obs_dicts = [{"x": o.x, "y": o.y, "width": o.width, "depth": o.depth} for o in input_data.obstacles]
    ceil_dicts = [{"x": c.x, "height": c.height} for c in input_data.ceiling]

    score = calculate_score(placements, bt_dicts, wh_dicts, obs_dicts, ceil_dicts)
    backend_q = result_data["score"]

    print(f"\n=== Score Comparison ===")
    print(f"  API Q score    : {score['Q']}")
    print(f"  Backend Q score: {backend_q}")
    match = score['Q'] is not None and abs(score['Q'] - backend_q) < 0.01
    print(f"  Match          : {match}")
    print(f"  Coverage       : {score['coverage']}")
    print(f"  Valid          : {score['is_valid']}")
    print(f"  Issues         : {len(score['issues'])}")
    for issue in score["issues"][:5]:
        print(f"    - {issue['message']}")

    if match:
        print("\n✓ ALL TESTS PASSED")
    else:
        print("\n✗ SCORE MISMATCH")


if __name__ == "__main__":
    main()
