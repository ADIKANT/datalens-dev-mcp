import tempfile
import unittest
from pathlib import Path


class OnePromptPipelineTests(unittest.TestCase):
    def test_full_offline_pipeline_creates_expected_artifacts_without_writes(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_governance_brief,
            dl_build_payload_plan,
            dl_create_safe_apply_plan,
            dl_generate_editor_bundle,
            dl_ingest_requirements,
            dl_readback_and_report,
            dl_start_pipeline,
            dl_validate_project,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl_start_pipeline(str(root), scenario="new_dashboard", dashboard_name="Synthetic Ops")
            dl_ingest_requirements(
                str(root),
                requirements_text="Synthetic Ops dashboard with trend, table details, and segment selector.",
            )
            brief = dl_build_governance_brief(str(root))
            bundle = dl_generate_editor_bundle(
                str(root),
                widget_id="widget_001",
                dataset_alias="synthetic_ops_dataset",
                columns=["bucket", "metric", "value"],
            )
            payload_plan = dl_build_payload_plan(str(root), workbook_id="workbook_local_001")
            (root / "datasets").mkdir()
            (root / "datasets" / "synthetic_ops.sql").write_text(
                "SELECT segment, created_month, issue_count FROM synthetic_ops_daily\n",
                encoding="utf-8",
            )
            validation = dl_validate_project(str(root))
            safe_apply = dl_create_safe_apply_plan(str(root), delivery_intent_text="plan only")
            report = dl_readback_and_report(str(root), target="dashboard_local")

            self.assertEqual(brief["chart_decisions"][0]["route"], "wizard_native")
            self.assertEqual(brief["chart_decisions"][0]["governance_decision"]["chart_family_decided_by"], "datalens-dataviz-governance")
            self.assertEqual(bundle["entry_type"], "wizard_chart")
            self.assertIn("source_gallery", bundle)
            self.assertEqual(bundle["source_kind"], "committed_canonical_template")
            self.assertTrue(bundle["validation"]["ok"])
            self.assertEqual(validation["status"], "pass")
            self.assertEqual(payload_plan["payloads"][0]["method"], "createWizardChart")
            self.assertEqual(safe_apply["delivery_intent_decision"]["state"], "plan_only")
            self.assertFalse(report["deployment_report"]["write_executed"])
            self.assertTrue((root / "artifacts" / "deployment_report.json").is_file())
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / "memory-bank").exists())

    def test_readback_uses_live_client_when_dashboard_id_is_supplied(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report

        class FakeClient:
            def rpc(self, method, payload):
                return {
                    "method": method,
                    "payload": payload,
                    "entry": {"entryId": payload.get("dashboardId") or payload.get("chartId"), "revId": "rev_1"},
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = dl_readback_and_report(
                str(root),
                target="dashboard_local",
                dashboard_id="dashboard_local",
                chart_ids=["chart_local"],
                client=FakeClient(),
            )

            readback = report["readback"]
            self.assertTrue(readback["live_readback"])
            self.assertEqual(readback["dashboard"]["summary"]["identity"]["id"], "dashboard_local")
            self.assertEqual(readback["charts"][0]["summary"]["identity"]["id"], "chart_local")


if __name__ == "__main__":
    unittest.main()
