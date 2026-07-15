"""Offline integration coverage for the generic downstream project workflow."""

import tempfile
import unittest
from pathlib import Path


class ProjectWorkflowTests(unittest.TestCase):
    def test_documented_project_workflow_writes_temp_artifacts_without_credentials(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import (
            dl_create_connector_plan,
            dl_create_dataset_field_plan,
            dl_create_dataset_plan,
        )
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_build_dashboard_blueprint_plan,
            dl_build_governance_brief,
            dl_build_payload_plan,
            dl_create_safe_apply_plan,
            dl_generate_editor_bundle,
            dl_ingest_requirements_markdown,
            dl_init_requirements_workspace,
            dl_populate_dashboard_map_canvas,
            dl_readback_and_report,
            dl_start_pipeline,
            dl_validate_project,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl_start_pipeline(str(root), scenario="new_dashboard", dashboard_name="Sample Ops")
            workspace = dl_init_requirements_workspace(str(root))
            dl_ingest_requirements_markdown(
                str(root),
                markdown_text=(
                    "# Sample Ops\n\n"
                    "Need trend by month, segment selector, detail table, connector and dataset plan."
                ),
                source_name="project_fixture",
                role="dashboard",
            )
            brief = dl_build_governance_brief(str(root))
            canvas = dl_populate_dashboard_map_canvas(
                str(root),
                source_text="Sample Ops dashboard with monthly trend and segment selector.",
                source_name="project_fixture",
            )
            blueprint = dl_build_dashboard_blueprint_plan(str(root))
            connector_plan = dl_create_connector_plan({"name": "sample_connection", "type": "clickhouse"})
            dataset_plan = dl_create_dataset_plan({"name": "sample_dataset", "source": "sample_connection"})
            field_plan = dl_create_dataset_field_plan({"name": "order_count", "type": "integer"})
            bundle = dl_generate_editor_bundle(
                str(root),
                widget_id="sample_widget",
                dataset_alias="sample_dataset",
                columns=["bucket", "metric", "value"],
            )
            payload_plan = dl_build_payload_plan(str(root), workbook_id="workbook_placeholder")
            (root / "datasets").mkdir()
            (root / "datasets" / "sample_ops.sql").write_text(
                "SELECT segment, month, order_count FROM sample_ops_daily\n",
                encoding="utf-8",
            )
            validation = dl_validate_project(str(root))
            safe_apply = dl_create_safe_apply_plan(str(root), approved=False, readback_mode="minimal")
            report = dl_readback_and_report(str(root), target="dashboard_placeholder")

            self.assertTrue(Path(workspace["requirements_root"]).is_dir())
            self.assertTrue(brief["chart_decisions"])
            self.assertEqual(canvas["ok"], True)
            self.assertEqual(blueprint["schema_version"], "2026-07-13.requirements_dashboard_blueprint_plan.v2")
            self.assertTrue(blueprint["chart_plan"])
            self.assertTrue(connector_plan["ok"])
            self.assertEqual(connector_plan["method"], "createConnection")
            self.assertFalse(connector_plan["execute_now"])
            self.assertTrue(dataset_plan["ok"])
            self.assertEqual(dataset_plan["method"], "createDataset")
            self.assertFalse(dataset_plan["execute_now"])
            self.assertFalse(field_plan["implemented"])
            self.assertEqual(field_plan["error"]["category"], "unavailable_api_method")
            self.assertEqual(bundle["entry_type"], "wizard_chart")
            self.assertEqual(bundle["route"], "wizard_native")
            self.assertEqual(validation["status"], "pass")
            self.assertTrue(payload_plan["payloads"])
            self.assertFalse(safe_apply["approved"])
            self.assertFalse(report["deployment_report"]["write_executed"])

            expected_files = [
                "requirements/dashboard_requirements.md",
                "requirements/dashboard_map.md",
                "requirements/dashboard_canvas.md",
                "requirements/charts.md",
                "requirements/object_relations.md",
                "artifacts/sample_widget.wizard_payload_plan.json",
                "artifacts/dashboard_brief.json",
                "artifacts/dashboard_object_relations.json",
                "artifacts/payload_plan.json",
                "artifacts/safe_apply_plan.json",
                "artifacts/deployment_report.json",
                "docs/datalens/implemented_charts.md",
            ]
            for rel in expected_files:
                self.assertTrue((root / rel).is_file(), rel)
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / "memory-bank").exists())


if __name__ == "__main__":
    unittest.main()
