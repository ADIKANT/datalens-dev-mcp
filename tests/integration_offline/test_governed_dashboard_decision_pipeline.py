import tempfile
import unittest
from pathlib import Path


class GovernedDashboardDecisionPipelineTests(unittest.TestCase):
    def test_pipeline_emits_chart_decision_record_and_renderer_spec(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_governance_brief,
            dl_build_payload_plan,
            dl_generate_editor_bundle,
            dl_ingest_requirements_markdown,
            dl_start_pipeline,
            dl_validate_project,
        )

        requirements = """
# Ops KPI dashboard
- Audience/users: operations owner
- Decision/action: monitor current active users
- Source/freshness: product dataset daily
- Metric KPI: active users
- Field attribute: segment
- Chart visual: KPI status
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl_start_pipeline(str(root), dashboard_name="Ops KPI")
            dl_ingest_requirements_markdown(str(root), markdown_text=requirements, source_name="REQ-kpi")
            brief = dl_build_governance_brief(str(root))
            bundle = dl_generate_editor_bundle(
                str(root),
                widget_id="kpi_active_users",
                dataset_alias="active_users_dataset",
                columns=["current_value", "comparator_value", "sparkline"],
            )
            dl_build_payload_plan(str(root), workbook_id="workbook_local_001")
            (root / "datasets").mkdir()
            (root / "datasets" / "active_users.sql").write_text(
                "SELECT segment, created_date, active_users FROM mart.active_users_daily\n",
                encoding="utf-8",
            )
            validation = dl_validate_project(str(root))

            decision = brief["chart_decisions"][0]["chart_decision_record"]
            saved_decision_exists = (root / "artifacts" / "kpi_active_users.chart_decision.json").is_file()

        self.assertEqual(decision["selected_route"], "wizard_native")
        self.assertIn("renderer_visual_spec", decision)
        self.assertEqual(bundle["route"], "wizard_native")
        self.assertEqual(bundle["visualization_id"], "metric")
        self.assertIn("chart_decision_record", bundle)
        self.assertIn("renderer_visual_spec", bundle)
        self.assertTrue(saved_decision_exists)
        self.assertEqual(validation["status"], "pass", validation["issues"])


if __name__ == "__main__":
    unittest.main()
