from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.backend_adapter import (  # noqa: E402
    build_optimization_payload,
    build_score_payload,
    normalize_backend_result,
)


def sample_layout() -> dict[str, object]:
    return {
        "warehouse": {
            "polygon": [
                {"x": 0, "y": 0},
                {"x": 9000, "y": 0},
                {"x": 9000, "y": 6000},
                {"x": 0, "y": 6000},
            ]
        },
        "obstacles": [
            {"id": "obs-1", "x": 1200, "y": 800, "w": 400, "h": 600},
        ],
        "ceiling": [
            {"x": 0, "height": 5000},
            {"x": 9000, "height": 5000},
        ],
        "bayTypes": [
            {
                "id": "rack-a",
                "label": "Rack A",
                "width": 1200,
                "depth": 800,
                "height": 2500,
                "gap": 200,
                "nLoads": 10,
                "price": 800,
            },
            {
                "id": "7",
                "label": "Rack Seven",
                "width": 1500,
                "depth": 900,
                "height": 2600,
                "gap": 300,
                "nLoads": 14,
                "price": 1200,
            },
        ],
        "shelves": [
            {
                "uid": "bay-1",
                "id": "bay-1",
                "label": "Rack A",
                "bayTypeId": "rack-a",
                "x": 100,
                "y": 200,
                "w": 1200,
                "h": 800,
                "gap": 200,
                "rotation": 30,
                "nLoads": 10,
                "price": 800,
            },
            {
                "uid": "bay-2",
                "id": "bay-2",
                "label": "Rack Seven",
                "bayTypeId": "7",
                "x": 2200,
                "y": 1200,
                "w": 1500,
                "h": 900,
                "gap": 300,
                "rotation": 90,
                "nLoads": 14,
                "price": 1200,
            },
        ],
    }


class BackendAdapterTests(unittest.TestCase):
    def test_build_optimization_payload_maps_frontend_contract(self) -> None:
        payload, registry, canonical = build_optimization_payload(sample_layout())

        self.assertEqual(
            payload["warehouse"],
            canonical["warehouse"]["polygon"],
        )
        self.assertEqual(
            payload["obstacles"],
            [{"x": 1200.0, "y": 800.0, "width": 400.0, "depth": 600.0}],
        )
        self.assertEqual(
            payload["ceiling"],
            [{"x": 0.0, "height": 5000.0}, {"x": 9000.0, "height": 5000.0}],
        )
        self.assertEqual(registry.label_to_backend_id["7"], 7)
        self.assertEqual(registry.label_to_backend_id["rack-a"], 1)

    def test_build_score_payload_uses_deterministic_backend_bay_ids(self) -> None:
        payload, registry, _ = build_score_payload(sample_layout())

        self.assertEqual(
            payload["placed_bays"],
            [
                {"id": registry.label_to_backend_id["rack-a"], "x": 100.0,
                 "y": 200.0, "rotation": 30.0},
                {"id": registry.label_to_backend_id["7"], "x": 2200.0,
                 "y": 1200.0, "rotation": 90.0},
            ],
        )
        self.assertEqual(registry.backend_id_to_label[1], "rack-a")
        self.assertEqual(registry.backend_id_to_label[7], "7")

    def test_normalize_backend_result_restores_ui_labels_and_dims(self) -> None:
        _, registry, canonical = build_optimization_payload(sample_layout())
        normalized = normalize_backend_result(
            {
                "Q": 12.5,
                "coverage": 0.25,
                "placed_bays": [
                    {"id": 1, "x": 300, "y": 400, "rotation": 60},
                    {"id": 7, "x": 600, "y": 700, "rotation": 120},
                ],
            },
            canonical,
            registry,
        )

        self.assertEqual(normalized["Q"], 12.5)
        self.assertEqual(normalized["baysPlaced"], 2)
        self.assertEqual(normalized["placed_bays"][0]["bayTypeId"], "rack-a")
        self.assertEqual(normalized["placed_bays"][0]["w"], 1200.0)
        self.assertEqual(normalized["placed_bays"][1]["bayTypeId"], "7")
        self.assertEqual(normalized["placed_bays"][1]["gap"], 300.0)


if __name__ == "__main__":
    unittest.main()
