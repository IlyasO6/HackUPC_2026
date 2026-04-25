from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.bay_type import BayType
from models.case_data import CaseData
from models.ceiling import CeilingProfile
from models.obstacle import Obstacle
from models.solution import PlacedBay, Solution
from models.warehouse import Point, Warehouse
from solver.hybrid import HybridSolver
from solver.layout import PlacementTemplate, build_empty_state
from validation.rules import build_case_context, is_valid_placement
from validation.validator import validate_solution


def make_case(
    warehouse_vertices: list[tuple[int, int]],
    bay_types: list[BayType] | None = None,
    obstacles: list[Obstacle] | None = None,
    ceiling: list[tuple[int, int]] | None = None,
) -> CaseData:
    return CaseData(
        warehouse=Warehouse([Point(x, y) for x, y in warehouse_vertices]),
        obstacles=obstacles or [],
        ceiling=CeilingProfile(ceiling or [(0, 100)]),
        bay_types=bay_types or [BayType(1, 4, 2, 1, 1, 10, 10)],
    )


class GeometryRegressionTests(unittest.TestCase):
    def test_front_gap_is_one_sided(self) -> None:
        case = make_case([(0, 0), (20, 0), (20, 10), (0, 10)])
        solution = Solution(
            placements=[
                PlacedBay(1, 5.0, 1.0, 0.0),
                PlacedBay(1, 5.0, 3.0, 180.0),
            ]
        )
        result = validate_solution(solution, case)
        self.assertTrue(result.is_valid, result.violations)

    def test_back_to_back_with_180_is_valid(self) -> None:
        case = make_case([(0, 0), (20, 0), (20, 10), (0, 10)])
        solution = Solution(
            placements=[
                PlacedBay(1, 5.0, 1.0, 0.0),
                PlacedBay(1, 5.0, 3.0, 180.0),
            ]
        )
        result = validate_solution(solution, case)
        self.assertTrue(result.is_valid, result.violations)

    def test_gap_must_stay_inside_warehouse(self) -> None:
        case = make_case([(0, 0), (10, 0), (10, 10), (0, 10)])
        result = validate_solution(Solution([PlacedBay(1, 6.0, 1.0, 0.0)]), case)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("front gap extends outside warehouse" in msg for msg in result.violations))

    def test_gap_must_not_overlap_obstacle(self) -> None:
        case = make_case(
            [(0, 0), (20, 0), (20, 10), (0, 10)],
            obstacles=[Obstacle(9, 1, 1, 2)],
        )
        result = validate_solution(Solution([PlacedBay(1, 5.0, 1.0, 0.0)]), case)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("front gap overlaps obstacle" in msg for msg in result.violations))

    def test_touching_boundaries_are_allowed(self) -> None:
        case = make_case([(0, 0), (20, 0), (20, 10), (0, 10)])
        result = validate_solution(
            Solution([PlacedBay(1, 1.0, 1.0, 0.0), PlacedBay(1, 1.0, 3.0, 0.0)]),
            case,
        )
        self.assertTrue(result.is_valid, result.violations)

    def test_rotated_non_cardinal_placement_is_valid(self) -> None:
        case = make_case([(0, 0), (20, 0), (20, 20), (0, 20)])
        ctx = build_case_context(case)
        state = build_empty_state(case.warehouse.area, ctx.cell_size)
        template = PlacementTemplate(case.bay_types[0], 45.0)
        self.assertTrue(is_valid_placement(template.place(8.0, 8.0), ctx, state.footprints, state=state))

    def test_rotated_x_span_respects_ceiling(self) -> None:
        bay_type = BayType(1, 4, 4, 3, 1, 10, 10)
        case = make_case(
            [(0, 0), (20, 0), (20, 20), (0, 20)],
            bay_types=[bay_type],
            ceiling=[(0, 5), (11, 2)],
        )
        result = validate_solution(Solution([PlacedBay(1, 9.0, 5.0, 45.0)]), case)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("exceeds ceiling" in msg for msg in result.violations))

    def test_zero_and_180_have_different_gap_directions(self) -> None:
        case = make_case(
            [(0, 0), (20, 0), (20, 10), (0, 10)],
            obstacles=[Obstacle(9, 1, 1, 2)],
        )
        result_zero = validate_solution(Solution([PlacedBay(1, 5.0, 1.0, 0.0)]), case)
        result_180 = validate_solution(Solution([PlacedBay(1, 5.0, 3.0, 180.0)]), case)
        self.assertFalse(result_zero.is_valid)
        self.assertTrue(result_180.is_valid, result_180.violations)


class SolverContractTests(unittest.TestCase):
    def test_fixed_step_angle_mode_uses_full_30_degree_lattice(self) -> None:
        case = make_case([(0, 0), (20, 0), (20, 20), (0, 20)])
        solver = HybridSolver(angle_mode="fixed-step", angle_step=30.0, time_budget=1.0)
        angles = solver._select_search_angles()
        self.assertEqual(
            angles,
            [
                0.0,
                30.0,
                60.0,
                90.0,
                120.0,
                150.0,
                180.0,
                210.0,
                240.0,
                270.0,
                300.0,
                330.0,
            ],
        )


if __name__ == "__main__":
    unittest.main()
