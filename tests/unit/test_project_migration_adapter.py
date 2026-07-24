"""Regression coverage for generic project migration adapters."""

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "project_adapters"
TEMPLATE_ROOT = REPO_ROOT / "templates" / "project_live_workflows"


class Goal10ProjectMigrationAdapterTests(unittest.TestCase):
    def test_fixture_projects_produce_deterministic_adapter_output(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_detect_project_adapter

        expected = {
            "standard_bundle": ("standard_bundle", "supported", True),
            "manifest_live_workflow": ("repo_live_workflow_manifest", "supported", True),
            "dataset_update_workflow": ("dataset_update_workflow", "adapter_required", False),
            "advanced_editor_project": ("advanced_editor_project", "adapter_required", False),
            "legacy_direct_rpc_quarantine": ("legacy_direct_rpc_quarantine", "quarantined", False),
        }
        for fixture_name, (adapter, status, ok) in expected.items():
            with self.subTest(fixture_name=fixture_name):
                result = dl_detect_project_adapter(str(FIXTURE_ROOT / fixture_name))

                self.assertEqual(result["adapter"], adapter)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["ok"], ok)
                self.assertIn(adapter, result["adapter_registry"])
                self.assertIn("manifest_requirements", result)
                self.assertIn("migration_guidance", result)

    def test_legacy_direct_rpc_is_quarantined_and_gets_manifest_guidance(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_detect_project_adapter,
            dl_detect_project_live_workflows,
        )

        root = FIXTURE_ROOT / "legacy_direct_rpc_quarantine"
        adapter = dl_detect_project_adapter(str(root))
        workflows = dl_detect_project_live_workflows(str(root))

        self.assertFalse(adapter["ok"])
        self.assertEqual(adapter["adapter"], "legacy_direct_rpc_quarantine")
        self.assertEqual(adapter["status"], "quarantined")
        self.assertIn("direct updateDashboard", " ".join(adapter["blocked_operations"]))
        self.assertTrue(adapter["direct_rpc_evidence"])
        self.assertEqual(workflows["status"], "adapter_required")
        self.assertEqual(workflows["adapter"], "legacy_direct_rpc_quarantine")
        workflow = workflows["suggested_manifest"]["workflows"][0]
        self.assertFalse(workflow["may_execute_command"])
        self.assertFalse(workflow["allow_publish"])
        self.assertIn("summary_requirements", workflow["dry_run"])
        self.assertIn("evidence_checks", workflow["dry_run"])

    def test_manifest_plan_exposes_summary_requirements_and_dry_run_default(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_plan_project_live_workflow,
            dl_run_project_live_dry_run,
        )

        root = FIXTURE_ROOT / "manifest_live_workflow"
        plan = dl_plan_project_live_workflow(str(root), workflow_name="dry_run_dashboard_change", action="dry_run")
        run = dl_run_project_live_dry_run(str(root), workflow_name="dry_run_dashboard_change", execute_now=True)

        self.assertEqual(plan["status"], "planned")
        self.assertFalse(plan["may_execute_command"])
        self.assertEqual(plan["workbook_id"], "workbook_fixture")
        self.assertEqual(plan["dashboard_ids"], ["dashboard_fixture"])
        self.assertEqual(plan["summary_requirements"]["branch_status"], "dry_run")
        self.assertIn("changed_object_counts", plan["summary_requirements"]["required_fields"])
        self.assertFalse(run["executed"])
        self.assertEqual(run["status"], "blocked")
        self.assertIn("workflow manifest does not allow command execution", run["blocked_reasons"])

    def test_plan_project_manifest_defaults_to_dry_run_only(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_plan_project_manifest

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "publish_dashboard.py").write_text(
                "client.call('updateDashboard', {})\n",
                encoding="utf-8",
            )

            preview = dl_plan_project_manifest(
                str(root),
                target_workbook_id="workbook_preview",
                dashboard_id="dashboard_preview",
            )

        manifest = preview["proposed_manifest"]
        workflow = manifest["workflows"][0]
        self.assertEqual(preview["status"], "preview")
        self.assertFalse(preview["written"])
        self.assertFalse(workflow["may_execute_command"])
        self.assertFalse(workflow["allow_publish"])
        self.assertFalse(manifest["allowed_live_operations"]["save"])
        self.assertEqual(manifest["target"]["workbook_id"], "workbook_preview")
        self.assertEqual(manifest["target"]["dashboard_ids"], ["dashboard_preview"])
        self.assertIn("summary_requirements", workflow["dry_run"])

    def test_sample_manifest_templates_are_schema_valid_and_non_executable(self):
        schema = json.loads((REPO_ROOT / "schemas" / "project-live-workflow-manifest.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        paths = sorted(TEMPLATE_ROOT.glob("*_manifest.json"))
        self.assertEqual(
            {path.name for path in paths},
            {
                "dry_run_manifest.json",
                "validate_summary_manifest.json",
                "save_manifest.json",
                "saved_readback_manifest.json",
                "publish_manifest.json",
                "published_readback_manifest.json",
            },
        )
        for path in paths:
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

                self.assertEqual(errors, [])
                workflow = payload["workflows"][0]
                self.assertFalse(workflow["may_execute_command"])
                self.assertFalse(workflow["allow_publish"])
                action_steps = [
                    workflow[action]
                    for action in ("validate", "dry_run", "apply", "publish", "readback")
                    if action in workflow
                ]
                self.assertTrue(action_steps)
                for step in action_steps:
                    self.assertIn("summary_path", step)
                    self.assertIn("evidence_checks", step)
                    self.assertIn("summary_requirements", step)
                    self.assertIn("target_ids", step["summary_requirements"]["required_fields"])

    def test_summary_requirements_block_missing_branch_counts_and_target_ids(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_read_project_live_summary

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_summary_requirement_manifest(root)
            (root / "reports").mkdir()
            (root / "reports" / "dry.json").write_text(
                json.dumps({"workbook_id": "workbook_1", "dashboard_ids": ["dashboard_1"]}),
                encoding="utf-8",
            )

            summary = dl_read_project_live_summary(str(root), workflow_name="dry_layout", action="dry_run")

        fields = {
            issue.get("field")
            for issue in summary["blocking_issues"]
            if issue.get("rule") == "missing_summary_required_field"
        }
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["status"], "summary_blocked")
        self.assertIn("branch_status", fields)
        self.assertIn("changed_object_counts", fields)
        self.assertNotIn("target_ids", fields)
        self.assertEqual(
            summary["target_ids"],
            {"workbook_id": "workbook_1", "dashboard_ids": ["dashboard_1"]},
        )

    def test_summary_requirements_pass_with_declared_evidence(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_read_project_live_summary

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_summary_requirement_manifest(root)
            (root / "reports").mkdir()
            (root / "artifacts").mkdir()
            (root / "artifacts" / "dashboard.json").write_text(json.dumps({"items": []}), encoding="utf-8")
            (root / "artifacts" / "source.sql").write_text("SELECT 1 AS fixture_id\n", encoding="utf-8")
            (root / "artifacts" / "readback.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
            (root / "artifacts" / "target.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
            (root / "reports" / "dry.json").write_text(
                json.dumps(
                    {
                        "workbook_id": "workbook_1",
                        "dashboard_ids": ["dashboard_1"],
                        "target_ids": {"workbook_id": "workbook_1", "dashboard_ids": ["dashboard_1"]},
                        "branch_status": "dry_run",
                        "changed_object_counts": {"dashboards": 0, "editor_charts": 0},
                        "evidence_paths": ["artifacts/readback.json"],
                        "dashboard_payload_paths": ["artifacts/dashboard.json"],
                        "editor_sql_paths": ["artifacts/source.sql"],
                        "readback_evidence_paths": ["artifacts/readback.json"],
                        "target_evidence_paths": ["artifacts/target.json"],
                    }
                ),
                encoding="utf-8",
            )

            summary = dl_read_project_live_summary(str(root), workflow_name="dry_layout", action="dry_run")

        self.assertTrue(summary["ok"], summary["blocking_issues"])
        self.assertEqual(summary["branch_status"], "dry_run")
        self.assertEqual(summary["target_ids"]["workbook_id"], "workbook_1")
        self.assertEqual(summary["checked_artifact_counts"]["dashboard_payload_preflight"], 1)
        self.assertEqual(summary["checked_artifact_counts"]["static_sql_lint"], 1)

    @staticmethod
    def _write_summary_requirement_manifest(root: Path) -> None:
        manifest = {
            "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
            "project_name": "summary_requirement_fixture",
            "workbook_id": "workbook_1",
            "dashboard_ids": ["dashboard_1"],
            "workflows": [
                {
                    "name": "dry_layout",
                    "may_execute_command": False,
                    "allow_publish": False,
                    "dry_run": {
                        "command": ["python3", "scripts/dry.py"],
                        "summary_path": "reports/dry.json",
                        "evidence_checks": [
                            "dashboard_payload_preflight",
                            "static_sql_lint",
                            "readback",
                            "target_evidence",
                        ],
                        "summary_requirements": {
                            "branch_status": "dry_run",
                            "required_fields": [
                                "workbook_id",
                                "dashboard_ids",
                                "target_ids",
                                "branch_status",
                                "changed_object_counts",
                                "evidence_paths",
                            ],
                        },
                    },
                }
            ],
        }
        (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
