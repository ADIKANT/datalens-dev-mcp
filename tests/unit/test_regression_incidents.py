import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.mcp.response_projection import dashboard_summary, project_dataset_response
from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_update_dataset_plan
from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan


FIXTURE_PATH = Path("tests/fixtures/regression_contracts/incident_fixtures.json")


def load_fixtures():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class IncidentRegressionTests(unittest.TestCase):
    def test_dashboard_summary_counts_nested_container_chart_items(self):
        response = {
            "entry": {
                "entryId": "dash_nested",
                "data": {
                    "tabs": [
                        {
                            "id": "overview",
                            "items": [
                                {
                                    "id": "container_1",
                                    "type": "container",
                                    "items": [
                                        {"id": "w1", "type": "chart", "chartId": "chart_1"},
                                        {"id": "w2", "type": "chart", "chartId": "chart_2"},
                                    ],
                                },
                                {
                                    "id": "section_1",
                                    "type": "section",
                                    "widgets": [{"id": "w3", "type": "chart", "chartId": "chart_3"}],
                                },
                            ],
                        }
                    ]
                },
            }
        }

        summary = dashboard_summary(response)

        self.assertEqual(summary["counts"]["tabs"], 1)
        self.assertEqual(summary["counts"]["linked_objects"], 3)
        self.assertEqual(summary["linked_object_ids"], ["chart_1", "chart_2", "chart_3"])

    def test_dataset_rpc_wrapper_preserves_identity_and_revision(self):
        fixtures = load_fixtures()
        response = fixtures["dataset_readback_wrappers"]["rpc_response_with_revision"]

        projected = project_dataset_response(response, response_mode="summary")
        identity = projected["summary"]["identity"]

        self.assertEqual(identity["id"], "dataset_event_records")
        self.assertEqual(identity["rev_id"], "rev_dataset_rpc")

    def test_publish_plan_rejects_duplicate_saved_readback_object_ids(self):
        fixtures = load_fixtures()
        readback = fixtures["publish_readback_cases"]["shuffled_unrelated_missing_duplicate"]
        duplicate_id = readback["duplicate_object_id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved.json"
            path.write_text(json.dumps(readback), encoding="utf-8")
            plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="chart",
                object_type="editor_chart",
                object_id=duplicate_id,
                saved_readback_path=str(path),
                approved=True,
            )

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["error"]["category"], "duplicate_saved_readback")

    def test_generic_dataset_update_plan_requires_explicit_mutation_adapter(self):
        fixtures = load_fixtures()
        raw_readback = fixtures["dataset_readback_wrappers"]["raw_dataset"]

        result = dl_update_dataset_plan(raw_readback)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["category"], "explicit_adapter_required")


if __name__ == "__main__":
    unittest.main()
