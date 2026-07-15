import unittest
import tempfile
from pathlib import Path


class SourceRouteResolverTests(unittest.TestCase):
    def test_excel_dataset_requirement_blocks_embedded_fallback(self):
        from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

        result = validate_source_route_decision(
            {
                "requirements_text": "Build dataset-backed charts from the uploaded Excel workbook.",
                "source_file_name": "orders.xlsx",
                "source_mode": "embedded",
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["decision"]["selected_route"], "manual_upload_handoff")
        self.assertIn("embedded_fallback_without_explicit_static_mode", result["findings"])

    def test_existing_dataset_blocks_embedded_fallback(self):
        from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

        result = validate_source_route_decision(
            {
                "source_file_name": "orders.csv",
                "available_datasets": [{"id": "ds_orders", "name": "orders.csv"}],
                "source_mode": "dataset_backed",
            }
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["decision"]["embedded_fallback_allowed"])
        self.assertEqual(result["decision"]["selected_route"], "dataset_backed")

    def test_uploaded_file_to_embedded_without_static_approval_fails(self):
        from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

        result = validate_source_route_decision({"source_file_name": "orders.csv", "user_uploaded_file": True, "source_mode": "embedded"})

        self.assertFalse(result["ok"])
        self.assertIn("embedded_fallback_without_explicit_static_mode", result["findings"])

    def test_unsupported_file_upload_creates_manual_handoff(self):
        from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

        result = validate_source_route_decision(
            {
                "source_file_path": "/tmp/processed/orders.csv",
                "source_file_name": "orders.csv",
                "workbook_id": "workbook_1",
                "expected_schema": [{"name": "order_id", "type": "string"}],
                "source_mode": "dataset_backed",
            }
        )

        self.assertTrue(result["ok"], result)
        decision = result["decision"]
        self.assertEqual(decision["status"], "manual_handoff")
        self.assertEqual(decision["selected_route"], "manual_upload_handoff")
        self.assertEqual(decision["manual_upload_handoff"]["processed_file_path"], "/tmp/processed/orders.csv")
        self.assertEqual(decision["manual_upload_handoff"]["required_workbook_id"], "workbook_1")
        self.assertEqual(decision["manual_upload_handoff"]["expected_schema"][0]["name"], "order_id")

    def test_static_acceptance_allows_labeled_static_fallback(self):
        from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

        result = validate_source_route_decision(
            {
                "source_file_name": "orders.csv",
                "source_mode": "embedded",
                "explicit_static_embedded_approval": True,
            }
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["decision"]["selected_route"], "explicit_static_embedded_mode")
        self.assertEqual(result["decision"]["static_fallback_label"], "static_reference_mock")
        self.assertTrue(result["decision"]["embedded_fallback_allowed"])

    def test_accepted_degraded_empty_source_does_not_invent_mappings(self):
        from datalens_dev_mcp.pipeline.source_route_resolver import validate_source_route_decision

        blocked = validate_source_route_decision(
            {"required_fields": ["orders"], "source_fields": [], "source_empty": True}
        )
        accepted = validate_source_route_decision(
            {
                "required_fields": ["orders"],
                "source_fields": [],
                "source_empty": True,
                "accepted_degraded": True,
            }
        )

        self.assertFalse(blocked["ok"])
        self.assertIn("source_fields_missing_or_empty", blocked["findings"])
        self.assertTrue(accepted["ok"], accepted)
        self.assertTrue(accepted["decision"]["accepted_degraded"])
        self.assertEqual(accepted["decision"]["field_mappings"], [])
        self.assertEqual(accepted["decision"]["dataset_field_contract"]["field_mappings"], [])

    def test_requirements_ingestion_writes_source_route_artifacts(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_ingest_requirements

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "orders.csv"
            data.write_text("order_id,amount\n1,10\n", encoding="utf-8")

            result = dl_ingest_requirements(
                str(root),
                requirements_text="Build dataset-backed charts from this CSV file.",
                data_path=str(data),
            )

            decision_path = root / "artifacts" / "source_route_decision.json"
            handoff_path = root / "reports" / "manual_upload_handoff.md"
            contract_path = root / "requirements" / "dataset_field_contract.json"

            self.assertIn("source_route_decision", result)
            self.assertTrue(decision_path.is_file())
            self.assertTrue(handoff_path.is_file())
            self.assertTrue(contract_path.is_file())
            self.assertIn("Processed file path", handoff_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
