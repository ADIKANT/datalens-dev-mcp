import json
import tempfile
import unittest
from pathlib import Path


class DataEvidenceTests(unittest.TestCase):
    def test_truncated_inventory_cannot_prove_absence(self):
        from datalens_dev_mcp.pipeline.data_evidence import evaluate_data_evidence

        result = evaluate_data_evidence(
            table_ref="analytics.orders_fact",
            inventory={"truncated": True, "tables": ["analytics.orders_summary"]},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "INCONCLUSIVE_TRUNCATED")
        self.assertIn("targeted table_discovery", " ".join(result["next_steps"]))

    def test_targeted_table_discovery_overrides_aggregate_inventory(self):
        from datalens_dev_mcp.pipeline.data_evidence import evaluate_data_evidence

        result = evaluate_data_evidence(
            table_ref="analytics.orders_fact",
            inventory={"truncated": False, "tables": ["analytics.orders_summary"]},
            targeted_evidence={
                "probe_operation": "table_discovery",
                "table_ref": "analytics.orders_fact",
                "status": "AVAILABLE",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["evidence_level"], "targeted_table_discovery")

    def test_prod_sample_rejects_select_star(self):
        from datalens_dev_mcp.pipeline.data_evidence import build_data_evidence_probe_plan

        result = build_data_evidence_probe_plan(
            probe_operation="bounded_sample",
            table_ref="warehouse.analytics.orders_fact",
            columns=["*"],
            environment="prod",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "PROBE_BLOCKED")
        self.assertIn("SELECT *", result["error"]["message"])

    def test_probe_artifact_redacts_sensitive_values(self):
        from datalens_dev_mcp.pipeline.data_evidence import record_data_evidence

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = record_data_evidence(
                project_root=root,
                artifact_name="auth-redaction",
                evidence={
                    "probe_operation": "table_discovery",
                    "table_ref": "analytics.orders_fact",
                    "status": "AVAILABLE",
                    "Authorization": "Bearer secret-token-value",
                    "nested": {"iam_token": "y0_syntheticplaceholderwithmanycharacters"},
                    "message": "Authorization Bearer secret-token-value",
                },
            )
            payload = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
            dumped = json.dumps(payload, ensure_ascii=False)

        self.assertTrue(result["ok"])
        self.assertNotIn("secret-token-value", dumped)
        self.assertNotIn("y0_syntheticplaceholderwithmanycharacters", dumped)
        self.assertIn("<redacted>", dumped)

    def test_internal_data_evidence_helpers_are_not_in_public_docs(self):
        from datalens_dev_mcp.server import list_tools

        tool_names = {tool["name"] for tool in list_tools("dq")}
        default_names = {tool["name"] for tool in list_tools()}
        docs = Path("docs/mcp/tools.md").read_text(encoding="utf-8")

        for name in [
            "dl_build_data_evidence_probe_plan",
            "dl_record_data_evidence",
            "dl_evaluate_data_evidence",
        ]:
            self.assertIn(name, tool_names)
            self.assertNotIn(name, docs)
            self.assertNotIn(name, default_names)


if __name__ == "__main__":
    unittest.main()
