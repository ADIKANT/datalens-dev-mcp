import tempfile
import unittest


class DeltaV7LiveMaintenanceWorkflowTests(unittest.TestCase):
    def test_simple_update_uses_high_level_workflow_and_writes_artifact(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_object_ids=["chart_1"],
                approved=False,
                publish=False,
                browser_runtime_required=False,
                non_rendering_exemption="plan-only unit fixture",
                baseline_dashboard={"tabs": [{"items": [{"chartId": "chart_1", "type": "widget"}]}]},
                proposed_dashboard={"tabs": [{"items": [{"chartId": "chart_1", "type": "widget"}]}]},
                changed_objects=[{"object_id": "chart_1", "change_type": "update"}],
            )

        self.assertEqual(result["status"], "planned")
        self.assertFalse(result["execution_performed"])
        self.assertEqual(result["tool_role"], "plan_and_validate_supplied_evidence")
        self.assertTrue(result["artifact_path"].endswith(".json"))
        self.assertIn("safe_apply", {row["name"] for row in result["phase_statuses"]})

    def test_missing_browser_proof_is_runtime_not_verified_not_done(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_object_ids=["chart_1"],
                approved=True,
                publish=False,
                browser_runtime_required=True,
            )

        self.assertEqual(result["status"], "runtime_not_verified")

    def test_create_without_necessity_proof_blocks(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_object_ids=["chart_1"],
                changed_objects=[{"object_id": "chart_new", "change_type": "create"}],
                allow_create=True,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("create_requires_necessity_proof", result["blocked_reasons"])

    def test_baseline_drop_blocks(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_object_ids=["chart_1"],
                baseline_dashboard={"tabs": [{"items": [{"chartId": "chart_1", "type": "widget"}]}]},
                proposed_dashboard={"tabs": [{"items": []}]},
                changed_objects=[{"object_id": "chart_1", "change_type": "remove"}],
            )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("broad_rebuild_or_object_drop_requires_explicit_authorization", result["blocked_reasons"])

    def test_source_budget_blocker_propagates(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dash_1",
                target_object_ids=["chart_1"],
                source_budget_evidence={
                    "schema_version": "datalens.delta_v7.editor_source_budget_evidence.v1",
                    "entry_id": "chart_1",
                    "source_key": "weekly_events",
                    "decision": "block",
                },
            )

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("source_budget" in reason for reason in result["blocked_reasons"]))


if __name__ == "__main__":
    unittest.main()
