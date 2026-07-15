import json
import tempfile
import unittest
from pathlib import Path


class SourceAvailabilityOrchestratorTests(unittest.TestCase):
    def test_missing_supplied_evidence_is_insufficient(self):
        from datalens_dev_mcp.pipeline.source_availability import build_dashboard_source_availability_matrix

        matrix = build_dashboard_source_availability_matrix()

        self.assertFalse(matrix["ok"])
        self.assertEqual(matrix["status"], "insufficient_evidence")

    def test_conflicting_consumers_block_publish(self):
        from datalens_dev_mcp.pipeline.source_availability import build_dashboard_source_availability_matrix

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inventory.json"
            path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "source_key": "event_log",
                                "environment": "stage",
                                "physical_table_present": True,
                                "row_count": 10,
                                "static_supported": True,
                                "consumer_statuses": {"data_health": "OK", "source_tables": "NO_TABLE"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            matrix = build_dashboard_source_availability_matrix(metadata_fetch_inventory_path=str(path))

        self.assertFalse(matrix["ok"])
        self.assertTrue(matrix["sources"][0]["conflict"])
        self.assertTrue(matrix["sources"][0]["publish_blocking"])

    def test_runtime_param_cannot_expand_static_unsupported_source(self):
        from datalens_dev_mcp.pipeline.source_availability import validate_source_availability_consumers

        matrix = {
            "schema_version": "datalens.delta_v7.source_availability_consumer_matrix.v1",
            "sources": [
                {
                    "source_key": "prod_optional_events",
                    "environment": "prod",
                    "physical_table_present": False,
                    "row_count": "unknown",
                    "static_supported": False,
                    "runtime_param_available": True,
                    "expected_status": "NO_TABLE",
                    "consumer_statuses": {},
                    "conflict": True,
                    "publish_blocking": True,
                }
            ],
        }

        validation = validate_source_availability_consumers(matrix)

        self.assertFalse(validation["ok"])
        self.assertTrue(any("publish_blocking_source_availability" in reason for reason in validation["blocked_reasons"]))


if __name__ == "__main__":
    unittest.main()
