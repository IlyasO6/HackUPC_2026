"""Integration test for the optimize-and-edit workflow."""

from __future__ import annotations

import os
import sys
import unittest

from fastapi.testclient import TestClient


sys.path.insert(0, os.path.dirname(__file__))
from main import app


TINY_CASE = {
    "warehouse": [
        {"x": 0, "y": 0},
        {"x": 2000, "y": 0},
        {"x": 2000, "y": 1000},
        {"x": 0, "y": 1000},
    ],
    "obstacles": [],
    "ceiling": [
        {"x": 0, "height": 5000},
        {"x": 2000, "height": 5000},
    ],
    "bay_types": [
        {
            "id": 1,
            "width": 500,
            "depth": 1000,
            "height": 1000,
            "gap": 0,
            "nLoads": 10,
            "price": 100,
        }
    ],
}


class LayoutSessionIntegrationTest(unittest.TestCase):
    """Verify optimize and live move behavior on a tiny exact case."""

    def test_optimize_then_move_collision(self) -> None:
        """POST /optimise and PATCH /layout/move should stay consistent."""

        with TestClient(app) as client:
            optimize_response = client.post("/api/v1/optimise", json=TINY_CASE)
            self.assertEqual(optimize_response.status_code, 200)

            optimized = optimize_response.json()
            self.assertTrue(optimized["valid"])
            self.assertEqual(optimized["bay_count"], 4)
            self.assertAlmostEqual(optimized["Q"], 10.0, places=6)

            first_bay = optimized["bays"][0]
            second_bay = optimized["bays"][1]
            move_response = client.patch(
                "/api/v1/layout/move",
                json={
                    "session_id": optimized["session_id"],
                    "bay_id": first_bay["instance_id"],
                    "x": second_bay["x"],
                    "y": second_bay["y"],
                },
            )
            self.assertEqual(move_response.status_code, 200)

            moved = move_response.json()
            self.assertFalse(moved["valid"])
            self.assertAlmostEqual(moved["Q"], 10.0, places=6)
            self.assertGreaterEqual(
                sum(1 for bay in moved["bays"] if not bay["valid"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
