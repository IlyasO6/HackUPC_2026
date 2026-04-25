from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import api_client  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, object] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload

    def close(self) -> None:
        return None


def sample_layout() -> dict[str, object]:
    return {
        "warehouse": {
            "polygon": [
                {"x": 0, "y": 0},
                {"x": 8000, "y": 0},
                {"x": 8000, "y": 5000},
                {"x": 0, "y": 5000},
            ]
        },
        "obstacles": [{"id": "obs-1", "x": 600, "y": 700, "w": 300, "h": 400}],
        "ceiling": [],
        "bayTypes": [
            {
                "id": "rack-a",
                "label": "Rack A",
                "width": 1200,
                "depth": 800,
                "height": 2400,
                "gap": 250,
                "nLoads": 12,
                "price": 1000,
            }
        ],
        "shelves": [
            {
                "uid": "bay-1",
                "id": "bay-1",
                "label": "Rack A",
                "bayTypeId": "rack-a",
                "x": 250,
                "y": 350,
                "w": 1200,
                "h": 800,
                "gap": 250,
                "rotation": 30,
                "nLoads": 12,
                "price": 1000,
            }
        ],
    }


class ApiClientRealModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_mode = api_client.BACKEND_MODE
        self.original_url = api_client.BACKEND_URL
        self.original_layouts = copy.deepcopy(api_client.LAYOUTS)
        self.original_contexts = copy.deepcopy(api_client.REAL_JOB_CONTEXTS)
        api_client.BACKEND_MODE = "real"
        api_client.BACKEND_URL = "http://backend.test"
        api_client.REAL_JOB_CONTEXTS.clear()
        api_client.LAYOUTS.clear()

    def tearDown(self) -> None:
        api_client.BACKEND_MODE = self.original_mode
        api_client.BACKEND_URL = self.original_url
        api_client.LAYOUTS.clear()
        api_client.LAYOUTS.update(self.original_layouts)
        api_client.REAL_JOB_CONTEXTS.clear()
        api_client.REAL_JOB_CONTEXTS.update(self.original_contexts)

    @patch("services.api_client.requests.request")
    def test_create_job_posts_to_fastapi_json_solve_and_normalizes(self, mock_request) -> None:
        project_id = "project-real"
        api_client.LAYOUTS[project_id] = sample_layout()
        mock_request.return_value = FakeResponse(
            202,
            {"job_id": "job-123", "status": "QUEUED"},
        )

        job = api_client.create_job(project_id)

        self.assertEqual(job["id"], "job-123")
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["stream_url"], "/api/jobs/job-123/stream")
        self.assertIn("job-123", api_client.REAL_JOB_CONTEXTS)

        method, url = mock_request.call_args.args[:2]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "http://backend.test/api/v1/solve/json")
        self.assertIn("json", mock_request.call_args.kwargs)

    @patch("services.api_client.requests.request")
    def test_get_job_uses_fastapi_status_endpoint_and_defaults_progress(self, mock_request) -> None:
        mock_request.return_value = FakeResponse(
            200,
            {"id": "job-7", "status": "COMPLETED", "message": "Done"},
        )

        job = api_client.get_job("job-7")

        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["progress"], 100)
        method, url = mock_request.call_args.args[:2]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "http://backend.test/api/v1/jobs/job-7")

    @patch("services.api_client.requests.request")
    def test_get_result_normalizes_backend_placed_bays(self, mock_request) -> None:
        project_id = "project-real"
        api_client.LAYOUTS[project_id] = sample_layout()
        api_client.REAL_JOB_CONTEXTS["job-9"] = {
            "project_id": project_id,
            "layout": sample_layout(),
            "registry": api_client.build_optimization_payload(sample_layout())[1],
        }
        mock_request.return_value = FakeResponse(
            200,
            {
                "Q": 9.75,
                "coverage": 0.12,
                "placed_bays": [{"id": 1, "x": 400, "y": 600, "rotation": 90}],
            },
        )

        result = api_client.get_result("job-9")

        self.assertIsNotNone(result)
        self.assertEqual(result["placed_bays"][0]["bayTypeId"], "rack-a")
        self.assertEqual(result["placed_bays"][0]["rotation"], 90.0)
        method, url = mock_request.call_args.args[:2]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "http://backend.test/api/v1/jobs/job-9/result")

    @patch("services.api_client.requests.request")
    def test_score_and_validate_use_real_endpoints_and_enrich_issues(self, mock_request) -> None:
        layout = sample_layout()
        mock_request.side_effect = [
            FakeResponse(
                200,
                {
                    "Q": 7.5,
                    "coverage": 0.2,
                    "num_bays": 1,
                    "total_loads": 12,
                    "total_bay_area": 960000,
                    "warehouse_area": 40000000,
                    "is_valid": True,
                    "issues": [],
                },
            ),
            FakeResponse(
                200,
                {
                    "is_valid": False,
                    "issues": [{"message": "Bay #0: Furniture bodies cannot overlap."}],
                },
            ),
        ]

        score = api_client.score_layout(layout)
        validation = api_client.validate_layout(layout)

        self.assertEqual(score["status"], "valid")
        self.assertEqual(validation["status"], "invalid")
        self.assertEqual(validation["invalid_bay_ids"], ["bay-1"])
        self.assertEqual(mock_request.call_args_list[0].args[1],
                         "http://backend.test/api/v1/score")
        self.assertEqual(mock_request.call_args_list[1].args[1],
                         "http://backend.test/api/v1/validate")


if __name__ == "__main__":
    unittest.main()
