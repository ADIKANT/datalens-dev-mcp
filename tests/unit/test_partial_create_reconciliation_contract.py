import json
import tempfile
import unittest
from pathlib import Path


class PartialCreateReconciliationContractTests(unittest.TestCase):
    def test_reconciliation_classifies_existing_and_missing_planned_creates(self):
        from datalens_dev_mcp.pipeline.reconciliation import reconcile_partial_creates

        result = reconcile_partial_creates(
            workbook_id="workbook_1",
            planned_objects=[
                {"object_type": "editor_chart", "internal_name": "existing_chart", "display_title": "Existing Chart"},
                {"object_type": "editor_chart", "internal_name": "missing_chart", "display_title": "Missing Chart"},
            ],
            entries_payload={
                "entries": [
                    {
                        "entryId": "entry_existing",
                        "scope": "editor_chart",
                        "name": "existing_chart",
                        "displayKey": "Existing Chart",
                    }
                ]
            },
        )

        statuses = [item["status"] for item in result["objects"]]
        self.assertEqual(statuses, ["existing", "missing"])
        self.assertEqual(result["reuse_existing_objects"][0]["existing_object_id"], "entry_existing")
        self.assertEqual(result["missing_objects"][0]["planned"]["internal_name"], "missing_chart")
        self.assertFalse(result["delete_attempted"])

    def test_safe_apply_plan_requires_reconciliation_before_partial_create_retry(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_dir = root / "artifacts" / "payloads"
            payload_dir.mkdir(parents=True)
            existing_payload = payload_dir / "existing.json"
            missing_payload = payload_dir / "missing.json"
            existing_payload.write_text(
                json.dumps(
                    {
                        "entry": {
                            "workbookId": "workbook_1",
                            "name": "existing_chart",
                            "data": {"title": "Existing Chart"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            missing_payload.write_text(
                json.dumps(
                    {
                        "entry": {
                            "workbookId": "workbook_1",
                            "name": "missing_chart",
                            "data": {"title": "Missing Chart"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "artifacts" / "payload_plan.json").write_text(
                json.dumps(
                    {
                        "workbook_id": "workbook_1",
                        "payloads": [
                            {"method": "createEditorChart", "payload_path": str(existing_payload), "widget_id": "existing"},
                            {"method": "createEditorChart", "payload_path": str(missing_payload), "widget_id": "missing"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            entries_payload = {
                "entries": [
                    {
                        "entryId": "entry_existing",
                        "scope": "editor_chart",
                        "name": "existing_chart",
                        "displayKey": "Existing Chart",
                    }
                ]
            }

            plan = dl_create_safe_apply_plan(str(root), entries_payload=entries_payload)

        self.assertTrue(plan["ok"])
        self.assertEqual(len(plan["actions"]), 1)
        self.assertEqual(plan["reconciliation"]["objects"][0]["status"], "existing")
        self.assertEqual(plan["reconciliation"]["objects"][1]["status"], "missing")
        self.assertEqual(plan["reused_existing_objects"][0]["existing_object_id"], "entry_existing")
        self.assertTrue(plan["result_contract"]["partial_create_retry_requires_reconciliation"])


if __name__ == "__main__":
    unittest.main()
