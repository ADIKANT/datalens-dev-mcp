import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "regression_hardening"


@contextmanager
def patched_env(values, *, clear=False):
    old_env = dict(os.environ)
    if clear:
        os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_env)


class ProjectLiveWorkflowTests(unittest.TestCase):
    def test_manifest_detection_and_plan_do_not_execute(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_detect_project_live_workflows,
            dl_list_project_live_workflows,
            dl_plan_project_live_workflow,
            dl_run_project_live_dry_run,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            sentinel = root / "reports" / "ran.txt"
            manifest = {
                "schema_version": "2026-06-05.project_live_workflow_manifest.v1",
                "project_name": "synthetic_project",
                "workbook_id": "workbook_synthetic",
                "dashboard_ids": ["dashboard_synthetic"],
                "workbook_id": "workbook_1",
                "dashboard_ids": ["dashboard_1"],
                "required_env_names": ["DATALENS_ORG_ID"],
                "workflows": [
                    {
                        "name": "source_tables",
                        "may_execute_command": True,
                        "allow_publish": False,
                        "required_env_names": ["DATALENS_IAM_TOKEN"],
                        "affected_objects": [{"type": "dashboard", "id": "dashboard_1"}],
                        "expected_artifacts": ["reports/dry_run_summary.json"],
                        "evidence_checks": ["dashboard_payload_preflight", "static_sql_lint"],
                        "safe_constraints": {"save_first": True, "publish_default": False},
                        "expected_changed_object_groups": ["dashboards", "editor_charts"],
                        "dry_run": {
                            "command": [sys.executable, "scripts/write_sentinel.py"],
                            "summary_path": "reports/dry_run_summary.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "write_sentinel.py").write_text(
                "from pathlib import Path\nPath('reports').mkdir(exist_ok=True)\nPath('reports/ran.txt').write_text('ran')\n",
                encoding="utf-8",
            )

            detected = dl_detect_project_live_workflows(str(root))
            listed = dl_list_project_live_workflows(str(root))
            plan = dl_plan_project_live_workflow(str(root), workflow_name="source_tables", action="dry_run")
            result = dl_run_project_live_dry_run(str(root), workflow_name="source_tables", execute_now=False)

        self.assertTrue(detected["ok"])
        self.assertEqual(detected["adapter"], "repo_live_workflow_manifest")
        self.assertIn("source_tables", listed["workflow_names"])
        self.assertEqual(detected["manifest"]["project_name"], "synthetic_project")
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["required_env_names"], ["DATALENS_IAM_TOKEN", "DATALENS_ORG_ID"])
        self.assertEqual(plan["affected_objects"], [{"type": "dashboard", "id": "dashboard_1"}])
        self.assertIn("dashboard_payload_preflight", plan["evidence_checks"])
        self.assertTrue(plan["safe_constraints"]["save_first"])
        self.assertIn("delivery_intent_decision", plan)
        self.assertEqual(plan["delivery_intent_decision"]["state"], "plan_only")
        self.assertIn("delivery_intent_decision", result)
        self.assertEqual(result["delivery_intent_decision"]["state"], "plan_only")
        self.assertFalse(result["executed"])
        self.assertFalse(sentinel.exists())

    def test_manifest_apply_respects_save_kill_switch_without_approval_prompt(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-06-11.project_live_workflow_manifest.v2",
                "project_name": "synthetic_project",
                "workbook_id": "workbook_synthetic",
                "dashboard_ids": ["dashboard_synthetic"],
                "workflows": [
                    {
                        "name": "apply_layout",
                        "may_execute_command": True,
                        "allow_publish": False,
                        "dry_run": {
                            "command": [sys.executable, "scripts/apply.py"],
                            "summary_path": "reports/dry.json",
                        },
                        "apply": {
                            "command": [sys.executable, "scripts/apply.py"],
                            "summary_path": "reports/apply.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "apply.py").write_text("raise SystemExit('should not run')\n", encoding="utf-8")

            with patched_env({"DATALENS_MCP_LIVE_ALLOW_SAVE": "0"}, clear=True):
                result = dl_run_project_live_apply(str(root), workflow_name="apply_layout", execute_now=True)

        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "blocked")
        self.assertIn("save_enabled", result["blocked_reasons"])

    def test_unknown_custom_layout_returns_adapter_required(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_detect_project_adapter, dl_detect_project_live_workflows

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "publish_dashboard.py").write_text("print('dry run only')\n", encoding="utf-8")
            (root / "scripts" / "apply_dataset_fix.py").write_text("print('validate')\n", encoding="utf-8")

            adapter = dl_detect_project_adapter(str(root))
            result = dl_detect_project_live_workflows(str(root))

        self.assertFalse(adapter["ok"])
        self.assertEqual(adapter["adapter"], "dataset_update_workflow")
        self.assertEqual(adapter["status"], "adapter_required")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "adapter_required")
        self.assertIn(".datalens-mcp.json", json.dumps(result["suggested_manifest"], ensure_ascii=False))
        self.assertTrue(result["detected_script_patterns"])

    def test_project_manifest_generator_previews_and_writes_when_requested(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_plan_project_manifest

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "datalens_dry_run.py").write_text("print('dry')\n", encoding="utf-8")
            (root / "dashboard" / "quality_table").mkdir(parents=True)
            (root / "dashboard" / "quality_table" / "bundle.json").write_text("{}", encoding="utf-8")

            preview = dl_plan_project_manifest(
                str(root),
                target_workbook_id="workbook_quality",
                dashboard_id="dashboard_quality",
            )
            manifest_path = root / ".datalens-mcp.json"
            written = dl_plan_project_manifest(
                str(root),
                write_manifest=True,
                target_workbook_id="workbook_quality",
                dashboard_id="dashboard_quality",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["status"], "preview")
        self.assertFalse(preview["written"])
        self.assertIn("local_object_registry", preview["proposed_manifest"])
        self.assertIn("allowed_live_operations", preview["proposed_manifest"])
        self.assertTrue(written["written"])
        self.assertEqual(manifest["target"]["workbook_id"], "workbook_quality")
        self.assertEqual(manifest["target"]["dashboard_ids"], ["dashboard_quality"])
        self.assertFalse(manifest["allowed_live_operations"]["save"])

    def test_standard_bundle_adapter_is_supported(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_detect_project_adapter

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dashboard" / "chart_a").mkdir(parents=True)
            (root / "dashboard" / "chart_a" / "bundle.json").write_text("{}", encoding="utf-8")

            result = dl_detect_project_adapter(str(root))

        self.assertTrue(result["ok"])
        self.assertEqual(result["adapter"], "standard_bundle")
        self.assertIn("standard_bundle", result["adapter_registry"])

    def test_dry_run_executes_declared_command_and_redacts_tokens(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_read_project_live_summary, dl_run_project_live_dry_run

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            manifest = {
                "schema_version": "2026-06-05.project_live_workflow_manifest.v1",
                "project_name": "synthetic_project",
                "workbook_id": "workbook_synthetic",
                "dashboard_ids": ["dashboard_synthetic"],
                "workbook_id": "workbook_1",
                "dashboard_ids": ["dashboard_1"],
                "workflows": [
                    {
                        "name": "apply_layout",
                        "may_execute_command": True,
                        "allow_publish": False,
                        "dry_run": {
                            "command": [sys.executable, "scripts/dry_run.py"],
                            "summary_path": "reports/dry_run_summary.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "dry_run.py").write_text(
                "import json, os\n"
                "print('token=' + os.environ.get('DATALENS_IAM_TOKEN', ''))\n"
                "json.dump({"
                "'workbook_id': os.environ.get('DATALENS_ORG_ID', ''),"
                "'dashboard_id': 'dashboard_1',"
                "'saved': True,"
                "'published': False,"
                "'changed_object_counts': {'dashboards': 1, 'editor_charts': 3},"
                "'evidence_paths': ['reports/readback.json'],"
                "'remaining_drift': []"
                "}, open('reports/dry_run_summary.json', 'w'))\n",
                encoding="utf-8",
            )
            env = {
                "DATALENS_IAM_TOKEN": "secret-token-value",
                "DATALENS_ORG_ID": "org_1",
                "DATALENS_API_BASE_URL": "https://api.datalens.tech",
                "DATALENS_API_VERSION": "1",
            }
            with patched_env(env, clear=True):
                result = dl_run_project_live_dry_run(str(root), workflow_name="apply_layout", execute_now=True)
                summary = dl_read_project_live_summary(str(root), workflow_name="apply_layout")

        dumped = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["executed"])
        self.assertNotIn("secret-token-value", dumped)
        self.assertIn("<redacted>", dumped)
        self.assertEqual(summary["changed_object_counts"], {"dashboards": 1, "editor_charts": 3})
        self.assertEqual(summary["dashboard_id"], "dashboard_1")

    def test_project_live_env_allowlist_blocks_parent_secret_and_redacts_output(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_dry_run

        unrelated_secret_value = "UNRELATED_SECRET_" + "VALUE"
        hardcoded_bearer = "Bearer " + "abc.def.ghi"
        hardcoded_url = "https://user:" + "pass@example.test/path"
        hardcoded_api_key = "sk-" + "a" * 24
        hardcoded_password = "super" + "secretvalue"
        parent_bearer = "Bearer " + "parent.secret.value"
        parent_url = "https://parent:" + "password@example.test/path"
        parent_api_key = "sk-" + "b" * 24
        parent_password = "parent-password-value-" + "12345"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            manifest = {
                "schema_version": "2026-06-25.project_live_workflow_manifest.v3",
                "project_name": "env_isolation",
                "workflows": [
                    {
                        "name": "dry_layout",
                        "may_execute_command": True,
                        "dry_run": {
                            "command": [sys.executable, "scripts/dry.py"],
                            "summary_path": "reports/dry.json",
                            "required_env_names": ["SAFE_REQUIRED_FLAG"],
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "dry.py").write_text(
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "Path('reports').mkdir(exist_ok=True)\n"
                "for name in ['SAFE_REQUIRED_FLAG', 'UNRELATED_SECRET', 'UNRELATED_BEARER', "
                "'UNRELATED_URL', 'UNRELATED_API_KEY', 'UNRELATED_PASSWORD']:\n"
                "    print(os.environ.get(name, '<missing>'))\n"
                f"print('hardcoded bearer={hardcoded_bearer}')\n"
                f"print('hardcoded url={hardcoded_url}', file=sys.stderr)\n"
                f"print('hardcoded api_key={hardcoded_api_key}', file=sys.stderr)\n"
                f"print('hardcoded password={hardcoded_password}', file=sys.stderr)\n"
                "json.dump({"
                "'dashboard_id': 'dashboard_1',"
                "'changed_object_counts': {'dashboards': 0},"
                "'safe': os.environ.get('SAFE_REQUIRED_FLAG', '<missing>'),"
                "'unrelated_secret': os.environ.get('UNRELATED_SECRET', '<missing>'),"
                "'unrelated_api_key': os.environ.get('UNRELATED_API_KEY', '<missing>')"
                "}, open('reports/dry.json', 'w'))\n",
                encoding="utf-8",
            )
            env = {
                "SAFE_REQUIRED_FLAG": "visible-required-value",
                "UNRELATED_SECRET": unrelated_secret_value,
                "UNRELATED_BEARER": parent_bearer,
                "UNRELATED_URL": parent_url,
                "UNRELATED_API_KEY": parent_api_key,
                "UNRELATED_PASSWORD": parent_password,
            }
            with patched_env(env, clear=True):
                result = dl_run_project_live_dry_run(str(root), workflow_name="dry_layout", execute_now=True)

            artifact_text = (root / "reports" / "dry.json").read_text(encoding="utf-8")

        dumped = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["env_summary"]["ambient_env_inherited"])
        self.assertEqual(result["env_summary"]["parent_required_env_names"], ["SAFE_REQUIRED_FLAG"])
        self.assertIn("visible-required-value", dumped)
        self.assertIn("visible-required-value", artifact_text)
        for raw_secret in (
            unrelated_secret_value,
            parent_bearer,
            parent_url,
            parent_api_key,
            parent_password,
            hardcoded_bearer,
            hardcoded_url,
            hardcoded_api_key,
            hardcoded_password,
        ):
            self.assertNotIn(raw_secret, dumped)
            self.assertNotIn(raw_secret, artifact_text)
        self.assertIn("<redacted>", dumped)
        self.assertNotIn("UNRELATED_SECRET", json.dumps(result["env_summary"], ensure_ascii=False))

    def test_project_live_rejects_suspicious_required_env_names(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_plan_project_live_workflow

        unrelated_secret_value = "UNRELATED_SECRET_" + "VALUE"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            manifest = {
                "schema_version": "2026-06-25.project_live_workflow_manifest.v3",
                "project_name": "bad_env",
                "required_env_names": ["UNRELATED_SECRET"],
                "workflows": [
                    {
                        "name": "dry_layout",
                        "may_execute_command": True,
                        "dry_run": {"command": [sys.executable, "scripts/dry.py"], "summary_path": "reports/dry.json"},
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "dry.py").write_text("", encoding="utf-8")
            with patched_env({"UNRELATED_SECRET": unrelated_secret_value}, clear=True):
                plan = dl_plan_project_live_workflow(str(root), workflow_name="dry_layout", action="dry_run")

        dumped = json.dumps(plan, ensure_ascii=False)
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["required_env_names"], [])
        self.assertEqual(plan["rejected_required_env_names"][0]["name"], "<redacted-env-name>")
        self.assertNotIn(unrelated_secret_value, dumped)
        self.assertNotIn("UNRELATED_SECRET", dumped)

    def test_generic_exception_wrappers_redact_secret_values(self):
        from datalens_dev_mcp.pipeline.safe_apply import _concise_error
        from datalens_dev_mcp.server import _safe_error

        api_key = "sk-" + "c" * 24
        unrelated_secret_value = "UNRELATED_SECRET_" + "VALUE"
        bearer = "Bearer " + "abc.def.ghi"
        url = "https://user:" + "pass@example.test/path"
        message = (
            f"boom {unrelated_secret_value} Authorization: {bearer} "
            f"api_key={api_key} {url}"
        )
        with patched_env({"UNRELATED_SECRET": unrelated_secret_value}, clear=True):
            server_error = _safe_error(RuntimeError(message))
            safe_apply_error = _concise_error(RuntimeError(message))["message"]

        for text in (server_error, safe_apply_error):
            self.assertNotIn(unrelated_secret_value, text)
            self.assertNotIn(bearer, text)
            self.assertNotIn(api_key, text)
            self.assertNotIn(url, text)
            self.assertIn("<redacted>", text)

    def test_read_summary_disambiguates_dry_run_apply_and_explicit_path(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_read_project_live_summary, dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            (root / "reports" / "dry.json").write_text(
                json.dumps({"dashboard_id": "dry_dash", "saved": False, "changed_object_counts": {"dashboards": 0}}),
                encoding="utf-8",
            )
            manifest = {
                "schema_version": "2026-06-25.project_live_workflow_manifest.v3",
                "project_name": "summary_actions",
                "workbook_id": "workbook_summary",
                "dashboard_ids": ["dashboard_summary"],
                "workflows": [
                    {
                        "name": "apply_layout",
                        "may_execute_command": True,
                        "allow_publish": False,
                        "dry_run": {
                            "command": [sys.executable, "scripts/apply.py"],
                            "summary_path": "reports/dry.json",
                        },
                        "apply": {
                            "command": [sys.executable, "scripts/apply.py"],
                            "summary_path": "reports/apply.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "apply.py").write_text(
                "import json\n"
                "from pathlib import Path\n"
                "Path('reports').mkdir(exist_ok=True)\n"
                "Path('artifacts/readback').mkdir(parents=True, exist_ok=True)\n"
                "Path('artifacts/readback/dashboard.saved.json').write_text('{}')\n"
                "json.dump({'workbook_id': 'workbook_summary', 'dashboard_id': 'apply_dash', "
                "'dashboard_ids': ['apply_dash'], "
                "'target_ids': {'dashboard_ids': ['apply_dash']}, 'branch_status': 'saved', "
                "'saved': True, 'changed_object_counts': {'dashboards': 1}, "
                "'evidence_paths': ['artifacts/readback/dashboard.saved.json']}, "
                "open('reports/apply.json', 'w'))\n",
                encoding="utf-8",
            )
            env = {"DATALENS_MCP_ENABLE_WRITES": "1", "DATALENS_MCP_LIVE_ALLOW_SAVE": "1"}
            with patched_env(env, clear=True):
                result = dl_run_project_live_apply(
                    str(root),
                    workflow_name="apply_layout",
                    execute_now=True,
                    delivery_intent_text="save only",
                )
                dry_summary = dl_read_project_live_summary(str(root), workflow_name="apply_layout", action="dry_run")
                apply_summary = dl_read_project_live_summary(str(root), workflow_name="apply_layout", action="apply")
                explicit_summary = dl_read_project_live_summary(
                    str(root),
                    workflow_name="apply_layout",
                    action="apply",
                    summary_path="reports/apply.json",
                )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"]["action"], "apply")
        self.assertFalse(result["summary"]["publish_requested"])
        self.assertEqual(result["summary"]["dashboard_id"], "apply_dash")
        self.assertTrue(result["summary"]["summary_path"].endswith("reports/apply.json"))
        self.assertEqual(result["summary"]["checked_artifact_counts"]["dashboard_payload_preflight"], 0)
        self.assertEqual(dry_summary["dashboard_id"], "dry_dash")
        self.assertEqual(dry_summary["action"], "dry_run")
        self.assertEqual(apply_summary["dashboard_id"], "apply_dash")
        self.assertEqual(explicit_summary["dashboard_id"], "apply_dash")

    def test_publish_run_reads_publish_summary_when_present(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            (root / "reports" / "dry.json").write_text(json.dumps({"dashboard_id": "dry_dash"}), encoding="utf-8")
            (root / "reports" / "apply.json").write_text(json.dumps({"dashboard_id": "apply_dash"}), encoding="utf-8")
            manifest = {
                "schema_version": "2026-06-25.project_live_workflow_manifest.v3",
                "project_name": "summary_actions",
                "workbook_id": "workbook_summary",
                "dashboard_ids": ["dashboard_summary"],
                "workflows": [
                    {
                        "name": "publish_layout",
                        "may_execute_command": True,
                        "allow_publish": True,
                        "dry_run": {
                            "command": [sys.executable, "scripts/publish.py"],
                            "summary_path": "reports/dry.json",
                        },
                        "apply": {
                            "command": [sys.executable, "scripts/publish.py"],
                            "summary_path": "reports/apply.json",
                        },
                        "publish": {
                            "command": [sys.executable, "scripts/publish.py"],
                            "summary_path": "reports/publish.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "publish.py").write_text(
                "import json\n"
                "from pathlib import Path\n"
                "Path('reports').mkdir(exist_ok=True)\n"
                "Path('artifacts/readback').mkdir(parents=True, exist_ok=True)\n"
                "Path('artifacts/readback/dashboard.published.json').write_text('{}')\n"
                "json.dump({'workbook_id': 'workbook_summary', 'dashboard_id': 'publish_dash', "
                "'dashboard_ids': ['publish_dash'], "
                "'target_ids': {'dashboard_ids': ['publish_dash']}, 'branch_status': 'published', "
                "'saved': True, 'published': True, 'changed_object_counts': {'dashboards': 1}, "
                "'evidence_paths': ['artifacts/readback/dashboard.published.json']}, "
                "open('reports/publish.json', 'w'))\n",
                encoding="utf-8",
            )
            env = {
                "DATALENS_MCP_ENABLE_WRITES": "1",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
            }
            with patched_env(env, clear=True):
                result = dl_run_project_live_apply(
                    str(root),
                    workflow_name="publish_layout",
                    execute_now=True,
                    publish=True,
                )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["publish_requested"])
        self.assertEqual(result["summary"]["action"], "publish")
        self.assertTrue(result["summary"]["publish_requested"])
        self.assertEqual(result["summary"]["dashboard_id"], "publish_dash")
        self.assertTrue(result["summary"]["published"])
        self.assertTrue(result["summary"]["summary_path"].endswith("reports/publish.json"))

    def test_project_live_apply_auto_runs_publish_for_implementation_intent(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-02.project_live_workflow_manifest.v4",
                "project_name": "auto_publish",
                "workbook_id": "workbook_live",
                "dashboard_ids": ["dashboard_live"],
                "workflows": [
                    {
                        "name": "layout",
                        "may_execute_command": True,
                        "allow_publish": True,
                        "apply": {"command": [sys.executable, "scripts/apply.py"], "summary_path": "reports/apply.json"},
                        "publish": {"command": [sys.executable, "scripts/publish.py"], "summary_path": "reports/publish.json"},
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "apply.py").write_text(
                "import json\nfrom pathlib import Path\nPath('reports').mkdir(exist_ok=True)\n"
                "Path('artifacts/readback').mkdir(parents=True, exist_ok=True)\n"
                "Path('artifacts/readback/dashboard.saved.latest.json').write_text('{}')\n"
                "json.dump({'workbook_id': 'workbook_live', 'dashboard_ids': ['dashboard_live'], "
                "'target_ids': {'dashboard_ids': ['dashboard_live']}, 'branch_status': 'saved', "
                "'saved': True, 'changed_object_counts': {'dashboards': 1}, "
                "'evidence_paths': ['artifacts/readback/dashboard.saved.latest.json'], "
                "'saved_readback_path': 'artifacts/readback/dashboard.saved.latest.json'}, "
                "open('reports/apply.json', 'w'))\n",
                encoding="utf-8",
            )
            (root / "scripts" / "publish.py").write_text(
                "import json\nfrom pathlib import Path\nPath('reports').mkdir(exist_ok=True)\n"
                "Path('artifacts/readback').mkdir(parents=True, exist_ok=True)\n"
                "Path('artifacts/readback/dashboard.published.latest.json').write_text('{}')\n"
                "json.dump({'workbook_id': 'workbook_live', 'dashboard_ids': ['dashboard_live'], "
                "'target_ids': {'dashboard_ids': ['dashboard_live']}, 'branch_status': 'published', "
                "'published': True, 'changed_object_counts': {'dashboards': 1}, "
                "'evidence_paths': ['artifacts/readback/dashboard.published.latest.json'], "
                "'published_readback_path': 'artifacts/readback/dashboard.published.latest.json'}, "
                "open('reports/publish.json', 'w'))\n",
                encoding="utf-8",
            )
            env = {
                "DATALENS_MCP_ENABLE_WRITES": "1",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
            }
            with patched_env(env, clear=True):
                result = dl_run_project_live_apply(
                    str(root),
                    workflow_name="layout",
                    execute_now=True,
                    delivery_intent_text="fix this dashboard",
                )

        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["project_live_delivery"]["saved"]["passed"])
        self.assertTrue(result["project_live_delivery"]["published"]["passed"])
        self.assertTrue(result["approval_reuse_for_publish"])
        self.assertEqual(result["delivery_intent_decision"]["state"], "save_then_publish")
        self.assertEqual(result["delivery_intent_decision"]["publish_stage_status"], "completed")

    def test_project_live_apply_blocks_missing_publish_path_for_implementation_intent(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-02.project_live_workflow_manifest.v4",
                "project_name": "missing_publish",
                "workbook_id": "workbook_live",
                "dashboard_ids": ["dashboard_live"],
                "workflows": [
                    {
                        "name": "layout",
                        "may_execute_command": True,
                        "allow_publish": True,
                        "apply": {"command": [sys.executable, "scripts/apply.py"], "summary_path": "reports/apply.json"},
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "apply.py").write_text(
                "import json\nfrom pathlib import Path\nPath('reports').mkdir(exist_ok=True)\n"
                "Path('artifacts/readback').mkdir(parents=True, exist_ok=True)\n"
                "Path('artifacts/readback/dashboard.saved.json').write_text('{}')\n"
                "json.dump({'workbook_id': 'workbook_live', 'dashboard_ids': ['dashboard_live'], "
                "'target_ids': {'dashboard_ids': ['dashboard_live']}, 'branch_status': 'saved', "
                "'saved': True, 'changed_object_counts': {'dashboards': 1}, "
                "'evidence_paths': ['artifacts/readback/dashboard.saved.json']}, "
                "open('reports/apply.json', 'w'))\n",
                encoding="utf-8",
            )
            env = {
                "DATALENS_MCP_ENABLE_WRITES": "1",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
            }
            with patched_env(env, clear=True):
                result = dl_run_project_live_apply(
                    str(root),
                    workflow_name="layout",
                    execute_now=True,
                    delivery_intent_text="fix this dashboard",
                )

        self.assertEqual(result["status"], "partial")
        self.assertIn("missing_publish_path_for_save_then_publish", result["publish_blocked_reasons"])
        self.assertFalse(result["project_live_delivery"]["published"]["passed"])
        self.assertEqual(result["delivery_intent_decision"]["publish_stage_status"], "blocked")

    def test_apply_does_not_accept_dry_run_only_summary(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            (root / "reports" / "dry.json").write_text(json.dumps({"dashboard_id": "dry_dash"}), encoding="utf-8")
            manifest = {
                "schema_version": "2026-06-25.project_live_workflow_manifest.v3",
                "project_name": "summary_actions",
                "workbook_id": "workbook_summary",
                "dashboard_ids": ["dashboard_summary"],
                "workflows": [
                    {
                        "name": "apply_layout",
                        "may_execute_command": True,
                        "allow_publish": False,
                        "dry_run": {
                            "command": [sys.executable, "scripts/noop.py"],
                            "summary_path": "reports/dry.json",
                        },
                        "apply": {
                            "command": [sys.executable, "scripts/noop.py"],
                            "summary_path": "reports/apply.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "noop.py").write_text("", encoding="utf-8")
            env = {"DATALENS_MCP_ENABLE_WRITES": "1", "DATALENS_MCP_LIVE_ALLOW_SAVE": "1"}
            with patched_env(env, clear=True):
                result = dl_run_project_live_apply(
                    str(root),
                    workflow_name="apply_layout",
                    execute_now=True,
                    delivery_intent_text="save only",
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "summary_blocked")
        self.assertIn("project live action summary was not found", result["blocked_reasons"])
        self.assertEqual(result["summary"]["status"], "summary_not_found")
        self.assertEqual(result["summary"]["action"], "apply")
        self.assertIn("reports/apply.json", result["summary"]["summary_candidates"][0])
        self.assertNotIn("dry_dash", json.dumps(result["summary"], ensure_ascii=False))

    def test_missing_apply_summary_prevents_publish_command(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-02.project_live_workflow_manifest.v4",
                "project_name": "missing_apply_summary",
                "workbook_id": "workbook_live",
                "dashboard_ids": ["dashboard_live"],
                "workflows": [
                    {
                        "name": "layout",
                        "may_execute_command": True,
                        "allow_publish": True,
                        "apply": {
                            "command": [sys.executable, "scripts/apply.py"],
                            "summary_path": "reports/apply.json",
                        },
                        "publish": {
                            "command": [sys.executable, "scripts/publish.py"],
                            "summary_path": "reports/publish.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "apply.py").write_text("", encoding="utf-8")
            (root / "scripts" / "publish.py").write_text(
                "import json\nfrom pathlib import Path\n"
                "Path('publish-ran').write_text('ran')\n"
                "Path('reports').mkdir(exist_ok=True)\n"
                "json.dump({'dashboard_id':'dashboard_live','published':True}, open('reports/publish.json','w'))\n",
                encoding="utf-8",
            )
            env = {
                "DATALENS_MCP_ENABLE_WRITES": "1",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
            }
            with patched_env(env, clear=True):
                result = dl_run_project_live_apply(
                    str(root),
                    workflow_name="layout",
                    execute_now=True,
                    delivery_intent_text="fix this dashboard",
                )
            publish_ran = (root / "publish-ran").exists()

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "summary_blocked")
        self.assertIsNone(result["publish_result"])
        self.assertFalse(publish_ran)
        self.assertFalse(result["project_live_delivery"]["saved"]["passed"])
        self.assertFalse(result["project_live_delivery"]["published"]["passed"])
        self.assertIn("project live action summary was not found", result["publish_blocked_reasons"])

    def test_blocked_apply_summary_prevents_publish_command(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-02.project_live_workflow_manifest.v4",
                "project_name": "blocked_apply_summary",
                "workbook_id": "workbook_live",
                "dashboard_ids": ["dashboard_live"],
                "workflows": [
                    {
                        "name": "layout",
                        "may_execute_command": True,
                        "allow_publish": True,
                        "apply": {
                            "command": [sys.executable, "scripts/apply.py"],
                            "summary_path": "reports/apply.json",
                            "evidence_checks": ["readback"],
                        },
                        "publish": {
                            "command": [sys.executable, "scripts/publish.py"],
                            "summary_path": "reports/publish.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "apply.py").write_text(
                "import json\nfrom pathlib import Path\n"
                "Path('reports').mkdir(exist_ok=True)\n"
                "json.dump({'dashboard_id':'dashboard_live','saved':True,"
                "'readback_evidence_paths':['artifacts/readback/missing.json']}, open('reports/apply.json','w'))\n",
                encoding="utf-8",
            )
            (root / "scripts" / "publish.py").write_text(
                "from pathlib import Path\nPath('publish-ran').write_text('ran')\n",
                encoding="utf-8",
            )
            env = {
                "DATALENS_MCP_ENABLE_WRITES": "1",
                "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
            }
            with patched_env(env, clear=True):
                result = dl_run_project_live_apply(
                    str(root),
                    workflow_name="layout",
                    execute_now=True,
                    delivery_intent_text="fix this dashboard",
                )
            publish_ran = (root / "publish-ran").exists()

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "summary_blocked")
        self.assertFalse(result["summary"]["ok"])
        self.assertEqual(result["summary"]["status"], "summary_blocked")
        self.assertIsNone(result["publish_result"])
        self.assertFalse(publish_ran)
        self.assertTrue(
            any(issue["rule"] == "zero_coverage" for issue in result["summary"]["blocking_issues"])
        )

    def test_declared_project_live_evidence_zero_coverage_blocks_summary(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_read_project_live_summary

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reports").mkdir()
            manifest = {
                "schema_version": "2026-06-25.project_live_workflow_manifest.v3",
                "project_name": "zero_coverage",
                "workflows": [
                    {
                        "name": "dry_layout",
                        "may_execute_command": True,
                        "dry_run": {
                            "command": [sys.executable, "scripts/dry.py"],
                            "summary_path": "reports/dry.json",
                            "expected_artifacts": [
                                "artifacts/dashboard_payload.json",
                                "artifacts/source_sql.sql",
                                "artifacts/semantic_sql.json",
                                "artifacts/readback.json",
                                "artifacts/target_lock.json",
                            ],
                            "evidence_checks": [
                                "dashboard_payload_preflight",
                                "static_sql_lint",
                                "semantic_sql",
                                "readback",
                                "target_evidence",
                            ],
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "reports" / "dry.json").write_text(
                json.dumps(
                    {
                        "dashboard_payload_paths": [],
                        "editor_sql_paths": [],
                        "semantic_sql_paths": [],
                        "readback_evidence_paths": [],
                        "target_evidence_paths": [],
                    }
                ),
                encoding="utf-8",
            )

            summary = dl_read_project_live_summary(str(root), workflow_name="dry_layout", action="dry_run")

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["status"], "summary_blocked")
        zero_checks = {issue["check"] for issue in summary["blocking_issues"] if issue["rule"] == "zero_coverage"}
        self.assertEqual(
            zero_checks,
            {"dashboard_payload_preflight", "static_sql_lint", "semantic_sql", "readback", "target_evidence"},
        )
        self.assertEqual(summary["checked_artifact_counts"]["dashboard_payload_preflight"], 0)
        self.assertEqual(summary["checked_artifact_counts"]["static_sql_lint"], 0)
        self.assertTrue(summary["missing_declared_artifacts"])

    def test_normal_publish_with_delete_legacy_token_is_blocked(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_plan_project_live_workflow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
                "project_name": "hidden_delete",
                "workbook_id": "workbook_1",
                "workflows": [
                    {
                        "name": "publish_layout",
                        "may_execute_command": True,
                        "allow_publish": True,
                        "publish": {
                            "command": [sys.executable, "scripts/publish.py", "--delete-legacy"],
                            "summary_path": "reports/publish.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "publish.py").write_text("", encoding="utf-8")

            plan = dl_plan_project_live_workflow(str(root), workflow_name="publish_layout", action="publish")

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("retire_legacy_objects", json.dumps(plan["blocked_reasons"], ensure_ascii=False))
        self.assertIn("--delete-legacy", json.dumps(plan["blocked_reasons"], ensure_ascii=False))

    def test_normal_workflow_rejects_string_command_and_destructive_constraint(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_detect_project_live_workflows

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {
                "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
                "project_name": "bad_manifest",
                "workflows": [
                    {
                        "name": "bad_layout",
                        "may_execute_command": True,
                        "safe_constraints": {"delete_move_permission_operations": True},
                        "dry_run": {
                            "command": f"{sys.executable} scripts/dry.py --dry-run",
                            "summary_path": "reports/dry.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")

            detected = dl_detect_project_live_workflows(str(root))

        self.assertFalse(detected["ok"])
        self.assertEqual(detected["status"], "invalid_manifest")
        self.assertIn("argv array", json.dumps(detected["errors"], ensure_ascii=False))

    def test_normal_workflow_rejects_destructive_constraint_flag(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_plan_project_live_workflow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
                "project_name": "bad_constraint",
                "workflows": [
                    {
                        "name": "bad_layout",
                        "may_execute_command": True,
                        "safe_constraints": {"delete_move_permission_operations": True},
                        "dry_run": {
                            "command": [sys.executable, "scripts/dry.py"],
                            "summary_path": "reports/dry.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "scripts" / "dry.py").write_text("", encoding="utf-8")

            plan = dl_plan_project_live_workflow(str(root), workflow_name="bad_layout", action="dry_run")

        self.assertFalse(plan["ok"])
        self.assertIn("delete_move_permission_operations", json.dumps(plan["blocked_reasons"], ensure_ascii=False))
        self.assertIn("retire_legacy_objects", json.dumps(plan["blocked_reasons"], ensure_ascii=False))

    def test_explicit_retire_with_exact_ids_passes_planning(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_plan_project_live_workflow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            retire_spec = self._write_retire_manifest(root)

            plan = dl_plan_project_live_workflow(str(root), workflow_name="retire_legacy", action="retire_legacy_objects")

        self.assertTrue(plan["ok"], plan["blocked_reasons"])
        self.assertEqual(plan["action"], "retire_legacy_objects")
        self.assertEqual(plan["retire_lifecycle"]["object_count"], 2)
        self.assertEqual(plan["retire_lifecycle"]["workbook_id"], "workbook_1")
        self.assertEqual(retire_spec["objects"][0]["id"], "chart_legacy_1")

    def test_retire_missing_relation_graph_proof_fails_planning(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_plan_project_live_workflow

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_retire_manifest(root, write_relation_proof=False)

            plan = dl_plan_project_live_workflow(str(root), workflow_name="retire_legacy", action="retire_legacy_objects")

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("relation_graph_proof", json.dumps(plan["blocked_reasons"], ensure_ascii=False))

    def test_retire_summary_requires_saved_published_no_reference_and_post_readback(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_read_project_live_summary

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_retire_manifest(root)

            summary = dl_read_project_live_summary(
                str(root),
                workflow_name="retire_legacy",
                action="retire_legacy_objects",
            )

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["status"], "summary_blocked")
        zero_checks = {issue["check"] for issue in summary["blocking_issues"] if issue["rule"] == "zero_coverage"}
        self.assertIn("saved_no_reference_proof", zero_checks)
        self.assertIn("published_no_reference_proof", zero_checks)
        self.assertIn("post_retire_readback", zero_checks)

    @staticmethod
    def _write_retire_manifest(root: Path, *, write_relation_proof: bool = True) -> dict:
        (root / "scripts").mkdir()
        (root / "reports").mkdir()
        (root / "artifacts" / "retire").mkdir(parents=True)
        if write_relation_proof:
            (root / "artifacts" / "retire" / "relation_graph.json").write_text(
                json.dumps({"objects": ["chart_legacy_1", "dash_legacy_1"], "references": []}),
                encoding="utf-8",
            )
        (root / "artifacts" / "retire" / "dry_run_plan.json").write_text(
            json.dumps({"dry_run": True, "objects": ["chart_legacy_1", "dash_legacy_1"]}),
            encoding="utf-8",
        )
        (root / "artifacts" / "retire" / "approval.json").write_text(
            json.dumps({"decision_id": "DEC-RETIRE-001", "approved_by": "operator"}),
            encoding="utf-8",
        )
        (root / "reports" / "retire_summary.json").write_text(
            json.dumps(
                {
                    "workbook_id": "workbook_1",
                    "dashboard_id": "dash_current",
                    "changed_object_counts": {"retired_objects": 2},
                }
            ),
            encoding="utf-8",
        )
        (root / "scripts" / "retire.py").write_text("", encoding="utf-8")
        retire_spec = {
            "lifecycle_state": "approved",
            "command": [sys.executable, "scripts/retire.py", "deleteEditorChart", "deleteDashboard"],
            "summary_path": "reports/retire_summary.json",
            "workbook_id": "workbook_1",
            "objects": [
                {"type": "editor_chart", "id": "chart_legacy_1"},
                {"type": "dashboard", "id": "dash_legacy_1"},
            ],
            "reason": "Named legacy objects were replaced and are unnecessary.",
            "user_request_quote": "remove chart_legacy_1 and dash_legacy_1",
            "decision_id": "DEC-RETIRE-001",
            "relation_graph_proof_path": "artifacts/retire/relation_graph.json",
            "saved_no_reference_proof_path": "artifacts/retire/saved_no_reference.json",
            "published_no_reference_proof_path": "artifacts/retire/published_no_reference.json",
            "dry_run_retire_plan_path": "artifacts/retire/dry_run_plan.json",
            "approval_provenance_path": "artifacts/retire/approval.json",
            "execution_summary_path": "reports/retire_summary.json",
            "post_retire_readback_paths": ["artifacts/retire/post_retire_readback.json"],
        }
        manifest = {
            "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
            "project_name": "retire_project",
            "workbook_id": "workbook_1",
            "workflows": [
                {
                    "name": "retire_legacy",
                    "may_execute_command": True,
                    "retire_legacy_objects": retire_spec,
                }
            ],
        }
        (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
        return retire_spec


class DashboardPayloadPreflightTests(unittest.TestCase):
    def test_duplicate_nested_widget_tab_id_is_blocked_and_reflow_fixes_it(self):
        from datalens_dev_mcp.validators.dashboard_payload import (
            rewrite_duplicate_nested_tab_ids,
            validate_dashboard_payload,
        )

        payload = {
            "dashboardId": "dashboard_1",
            "blocks": [
                {"id": "widget_a", "type": "widget", "tabs": [{"id": "duplicate_tab", "chartId": "chart_a"}]},
                {"id": "widget_b", "type": "widget", "tabs": [{"id": "duplicate_tab", "chartId": "chart_b"}]},
            ],
        }

        result = validate_dashboard_payload(payload)
        fixed = rewrite_duplicate_nested_tab_ids(payload)
        fixed_result = validate_dashboard_payload(fixed)

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "duplicate_nested_tab_id" for issue in result.issues))
        self.assertTrue(fixed_result.ok, [issue.message for issue in fixed_result.issues])

    def test_source_tables_grouped_tabs_and_preserved_global_selector_pass(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        current = {"items": [{"id": "global_period", "type": "selector", "pinned": True}]}
        payload = {
            "dashboardId": "dashboard_1",
            "items": [
                {"id": "global_period", "type": "selector", "pinned": True, "labelPlacement": "left", "width": "24%"},
                {
                    "id": "source_tables_block",
                    "type": "widget",
                    "native_title": "Source Tables",
                    "native_hint": "Grouped source-table diagnostics.",
                    "tabs": [
                        {"id": "source_tables_primary", "chartId": "chart_primary", "default": True},
                        {"id": "source_tables_details", "chartId": "chart_details"},
                    ],
                },
            ],
            "selector_rows": [[{"id": "global_period", "width": "24%"}, {"id": "source_filter", "width": "70%"}]],
        }

        result = validate_dashboard_payload(payload, current_dashboard=current, preserved_control_ids=["global_period"])

        self.assertTrue(result.ok, [issue.message for issue in result.issues])

    def test_advanced_editor_inline_title_warns_when_native_title_is_required(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        payload = {
            "id": "chart_1",
            "type": "advanced_editor",
            "native_title": "Event diagnostics",
            "native_hint": "Use dashboard metadata.",
            "tabs": {"prepare.js": "return '<h1>Event diagnostics</h1><table></table>';"},
        }

        result = validate_dashboard_payload(payload, strict=False)

        self.assertTrue(any(issue.rule == "duplicate_inline_title" and issue.severity == "warning" for issue in result.issues))

    def test_named_dashboard_incident_fixtures_are_covered(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        duplicate = json.loads((FIXTURE_ROOT / "dashboard_duplicate_tabs.json").read_text(encoding="utf-8"))
        grouped = json.loads((FIXTURE_ROOT / "source_tables_grouped_tabs.json").read_text(encoding="utf-8"))

        duplicate_result = validate_dashboard_payload(duplicate)
        grouped_result = validate_dashboard_payload(grouped, preserved_control_ids=["global_period"])

        self.assertFalse(duplicate_result.ok)
        self.assertTrue(any(issue.rule == "duplicate_nested_tab_id" for issue in duplicate_result.issues))
        self.assertTrue(grouped_result.ok, [issue.message for issue in grouped_result.issues])

    def test_unchanged_legacy_widget_metadata_is_preserved(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        legacy_widget = {
            "id": "legacy_sources",
            "type": "widget",
            "tabs": [{"id": "source_a", "chartId": "chart_a"}, {"id": "source_b", "chartId": "chart_b"}],
        }
        current = {"items": [legacy_widget]}
        proposed = {"items": [legacy_widget, {"id": "new_chart", "type": "chart", "title": "Visible / Title"}]}

        result = validate_dashboard_payload(proposed, current_dashboard=current)

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])

    def test_debug_widget_is_blocked_from_publish_layout(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        payload = {"items": [{"id": "debug_payload_probe", "type": "widget", "title": "Debug payload probe"}]}

        result = validate_dashboard_payload(payload)

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "debug_widget_in_publish_layout" for issue in result.issues))

    def test_date_range_selector_contract_blocks_old_preset_control(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        payload = {
            "items": [
                {
                    "id": "global_period",
                    "type": "selector",
                    "controlType": "preset",
                    "defaultValue": "last_30_days",
                    "labelPlacement": "left",
                    "width": "94%",
                }
            ]
        }

        result = validate_dashboard_payload(payload, project_contract={"date_range_selector": "date-range control"})

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "date_range_selector_regression" for issue in result.issues))

    def test_selector_impact_tabs_ids_must_reference_known_tabs(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        payload = {
            "tabs": [{"id": "overview"}],
            "items": [
                {
                    "id": "global_period",
                    "type": "selector",
                    "labelPlacement": "left",
                    "width": "94%",
                    "impactTabsIds": ["overview", "missing_tab"],
                }
            ],
        }

        result = validate_dashboard_payload(payload)

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "selector_impact_tabs_scope" for issue in result.issues))

    def test_available_source_evidence_blocks_stale_no_table_default(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        payload = {"items": [{"id": "availability", "type": "widget", "defaultValue": "NO TABLE"}]}

        result = validate_dashboard_payload(payload, project_contract={"availability_evidence": {"status": "AVAILABLE"}})

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "stale_no_table_default" for issue in result.issues))

    def test_visible_title_can_keep_slash_while_internal_name_is_blocked(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        payload = {
            "entry": {"name": "Entity Status / configuration history"},
            "data": {"title": "Entity Status / configuration history"},
        }

        result = validate_dashboard_payload(payload)

        self.assertFalse(result.ok)
        self.assertTrue(any(issue.rule == "unsafe_internal_name" and issue.path == "entry.name" for issue in result.issues))
        self.assertFalse(any(issue.path == "data.title" for issue in result.issues))


class EditorSqlStaticLintTests(unittest.TestCase):
    def test_known_clickhouse_failures_are_errors(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        text = r"""
        SELECT record_item[1], audit_item[2]
        FROM arrayJoin(arrayZip(extractAll(payload, 'a=(\d+)'), extractAll(payload, 'b=(\d+)'))) record_item
        LEFT JOIN entity_state s ON s.entity_id = event.entity_id
        WHERE extract(raw, '\\'broken') != ''
        SELECT ifNull(entity_id, '') AS entity_id, ifNull(source_available, 0) AS source_available
        const columns = [{name: 'raw_payload_json', visible: true}, {name: 'detail_json'}];
        """

        result = lint_editor_sql_text(text, path="sources.js")
        rules = {issue.rule for issue in result.issues if issue.severity == "error"}

        self.assertFalse(result.ok)
        self.assertIn("tuple_indexing", rules)
        self.assertIn("arrayzip_independent_regex_lists", rules)
        self.assertIn("unsafe_single_quote_regex_escape", rules)
        self.assertIn("no_common_type_prone_ifnull", rules)
        self.assertIn("no_common_type_prone_join", rules)
        self.assertIn("raw_payload_default_visible", rules)
        self.assertIn("availability_default_regression", rules)

    def test_safe_clickhouse_patterns_pass(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        text = r"""
        SELECT tupleElement(record_item, 1) AS event_id
        FROM arrayJoin(extractAllGroups(payload, 'id=([0-9]+);status=([^;]+)')) record_item
        LEFT JOIN events event ON event.event_id = tupleElement(record_item, 1)
        LEFT JOIN entity_state s ON toString(s.entity_id) = toString(event.entity_id)
        WHERE extract(raw, '\\x27safe') != ''
        SELECT ifNull(toString(entity_id), '') AS entity_id, 1 AS source_available
        const columns = [{name: 'raw_payload_json', visible: false}, {name: 'detail_json', hidden: true}];
        """

        result = lint_editor_sql_text(text, path="sources.js")

        self.assertTrue(result.ok, [issue.message for issue in result.issues])

    def test_additional_logged_sql_antipatterns_are_errors(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        text = """
        WITH rollup AS (
          SELECT order_id, sum(net_amount) AS net_amount FROM analytics.orders_fact GROUP BY order_id
        )
        SELECT round(sum(net_amount), 2) AS net_amount
        FROM rollup
        LEFT JOIN analytics.order_components c ON c.order_id = rollup.order_id OR c.parent_order_id = rollup.order_id
        WHERE EXISTS (
          SELECT 1 FROM analytics.order_links link
          WHERE link.source_order_id = orders.order_id
        )
        AND orderLinks.order_id IS NOT NULL
        """

        result = lint_editor_sql_text(text, path="sources.js")
        rules = {issue.rule for issue in result.issues if issue.severity == "error"}

        self.assertIn("correlated_subquery_unsupported", rules)
        self.assertIn("unknown_alias_reference", rules)
        self.assertIn("aggregate_alias_shadows_input", rules)
        self.assertIn("or_join_memory_explosion", rules)
        self.assertIn("rollup_final_join_shape", rules)

    def test_materialized_cte_aggregate_can_be_rolled_up_again(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        text = """
        WITH rollup AS (
          SELECT order_id, sum(net_amount) AS net_amount_sum
          FROM analytics.orders_fact
          GROUP BY order_id
        )
        SELECT sum(net_amount_sum) AS total_net_amount
        FROM rollup
        """

        result = lint_editor_sql_text(text, path="sources.js")
        rules = {issue.rule for issue in result.issues if issue.severity == "error"}

        self.assertNotIn("aggregate_alias_reaggregated", rules)
        self.assertNotIn("aggregate_alias_shadows_input", rules)

    def test_early_filter_and_prod_select_star_are_enforced_when_configured(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        text = "SELECT * FROM analytics.orders_fact WHERE created_dt >= today() - 365"

        result = lint_editor_sql_text(
            text,
            path="probe.sql",
            required_early_filters=["order_key"],
            environment="prod",
        )
        rules = {issue.rule for issue in result.issues if issue.severity == "error"}

        self.assertIn("missing_early_filter", rules)
        self.assertIn("select_star_prod_probe", rules)

    def test_legal_scalar_formatting_of_aggregate_is_not_rejected(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        result = lint_editor_sql_text("SELECT round(sum(revenue), 2) AS revenue FROM sales", path="legal.sql")

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])

    def test_same_type_join_passes_with_metadata_evidence(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        result = lint_editor_sql_text(
            "SELECT a.user_id FROM a JOIN b ON a.user_id = b.user_id",
            path="typed.sql",
            field_types={"a.user_id": "String", "b.user_id": "Nullable(String)"},
        )

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])

    def test_explicit_prod_source_blocks_select_star_without_environment_hint(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        result = lint_editor_sql_text("SELECT * FROM prod.fact_events", path="probe.sql")

        self.assertIn("select_star_prod_probe", {issue.rule for issue in result.issues if issue.severity == "error"})

    def test_separate_safe_order_links_source_passes(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        text = """
        WITH scoped_orders AS (
          SELECT order_id, order_key
          FROM analytics.orders_fact
          WHERE order_key IN ('ORD-001', 'ORD-002')
        ),
        order_links_source AS (
          SELECT toString(source_order_id) AS order_id, toString(target_order_id) AS linked_order_id
          FROM analytics.order_links
          WHERE toString(source_order_id) IN (SELECT toString(order_id) FROM scoped_orders)
          UNION ALL
          SELECT toString(target_order_id) AS order_id, toString(source_order_id) AS linked_order_id
          FROM analytics.order_links
          WHERE toString(target_order_id) IN (SELECT toString(order_id) FROM scoped_orders)
        )
        SELECT scoped_orders.order_key, count(order_links_source.linked_order_id) AS link_count
        FROM scoped_orders
        LEFT JOIN order_links_source ON toString(order_links_source.order_id) = toString(scoped_orders.order_id)
        GROUP BY scoped_orders.order_key
        """

        result = lint_editor_sql_text(text, path="safe_order_links.sql", required_early_filters=["order_key"])

        self.assertTrue(result.ok, [issue.to_dict() for issue in result.issues])

    def test_cte_stage_probe_plan_is_plan_only_evidence(self):
        from datalens_dev_mcp.pipeline.data_evidence import build_data_evidence_probe_plan

        result = build_data_evidence_probe_plan(
            probe_operation="cte_stage_count",
            cte_sql="scoped_orders AS (SELECT order_id FROM analytics.orders_fact WHERE order_key IN ('ORD-001'))",
            graph_config={"stage_name": "scoped_orders"},
            environment="prod",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence_level"], "probe_plan_only")
        self.assertFalse(result["execute_now"])
        self.assertIn("SELECT count(*)", result["sql"])

    def test_named_synthetic_sql_regression_files_are_covered(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_file

        cases = {
            "tuple_and_array.js": (
                "SELECT record_item[1] FROM arrayJoin(arrayZip(extractAll(payload, 'a=(\\d+)'), "
                "extractAll(payload, 'b=(\\d+)'))) record_item",
                {"tuple_indexing", "arrayzip_independent_regex_lists"},
            ),
            "quote_escape.sql": (
                r"SELECT extract(detail_json, '\\'itemId\\':\\'([^\\']+)\\'') AS item_id",
                {"unsafe_single_quote_regex_escape"},
            ),
            "id_cast.sql": (
                "SELECT ifNull(entity_id, '') AS entity_id FROM events e "
                "LEFT JOIN entity_state s ON s.entity_id = e.entity_id",
                {"no_common_type_prone_ifnull", "no_common_type_prone_join"},
            ),
            "availability.sql": (
                "SELECT ifNull(source_available, 0) AS source_available",
                {"availability_default_regression"},
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for filename, (sql, expected) in cases.items():
                with self.subTest(filename=filename):
                    path = root / filename
                    path.write_text(sql, encoding="utf-8")
                    result = lint_editor_sql_file(path)
                    rules = {issue.rule for issue in result.issues if issue.severity == "error"}
                    self.assertTrue(expected.issubset(rules), rules)


class ValidationEvidenceModelTests(unittest.TestCase):
    def test_blocked_runtime_sql_execution_is_honest_with_static_fallbacks(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_build_validation_evidence_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "artifacts").mkdir()
            (root / "artifacts" / "editor_sql_lint.json").write_text(
                json.dumps({"ok": True, "issues": [], "checked_paths": ["dashboard/widget/sources.js"]}),
                encoding="utf-8",
            )
            (root / "artifacts" / "dashboard_payload_preflight.json").write_text(
                json.dumps({"ok": True, "issues": [], "checked_paths": ["artifacts/dashboard.payload.json"]}),
                encoding="utf-8",
            )

            report = dl_build_validation_evidence_report(str(root))

        self.assertEqual(report["direct_sql_execution"]["status"], "blocked_runtime_sql_execution")
        self.assertEqual(report["engine_probe"]["status"], "BLOCKED_ENGINE_PROBE")
        self.assertTrue(report["ok"])
        self.assertIn("source_static", report["proof_levels"])
        self.assertIn("installed_static", report["proof_levels"])
        self.assertEqual(report["ok_proof_context"]["proof_levels"], report["proof_levels"])
        self.assertEqual(report["static_sql_lint"]["proof_level"], "source_static")
        self.assertIn("static_sql_lint", report["fallback_evidence"])
        self.assertIn("manual UI smoke", " ".join(report["remaining_manual_checks"]))

    def test_evidence_report_fails_on_zero_coverage_artifacts(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_build_validation_evidence_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "artifacts").mkdir()
            (root / "artifacts" / "editor_sql_lint.json").write_text(
                json.dumps({"ok": True, "issues": [], "checked_paths": []}),
                encoding="utf-8",
            )
            (root / "artifacts" / "dashboard_payload_preflight.json").write_text(
                json.dumps({"ok": True, "issues": [], "checked_paths": []}),
                encoding="utf-8",
            )

            report = dl_build_validation_evidence_report(str(root))

        self.assertFalse(report["ok"])
        self.assertEqual(report["confidence_level"], "blocked")
        self.assertIn("zero_static_sql_lint_coverage", report["failing_rules"])
        self.assertIn("zero_dashboard_payload_preflight_coverage", report["failing_rules"])

    def test_evidence_report_fails_on_static_sql_or_dashboard_preflight_errors(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_build_validation_evidence_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "artifacts").mkdir()
            (root / "artifacts" / "editor_sql_lint.json").write_text(
                json.dumps({"ok": False, "issues": [{"severity": "error", "rule": "tuple_indexing"}]}),
                encoding="utf-8",
            )
            (root / "artifacts" / "dashboard_payload_preflight.json").write_text(
                json.dumps({"ok": False, "issues": [{"severity": "error", "rule": "duplicate_nested_tab_id"}]}),
                encoding="utf-8",
            )

            report = dl_build_validation_evidence_report(str(root))

        self.assertFalse(report["ok"])
        self.assertEqual(report["confidence_level"], "blocked")
        self.assertIn("tuple_indexing", json.dumps(report, ensure_ascii=False))
        self.assertIn("duplicate_nested_tab_id", json.dumps(report, ensure_ascii=False))


class PostLiveToolSurfaceTests(unittest.TestCase):
    def test_new_hardening_tools_are_registered(self):
        from datalens_dev_mcp.server import list_tools

        tools = {tool["name"] for tool in list_tools()}

        self.assertTrue(
            {
                "dl_detect_project_live_workflows",
                "dl_plan_project_manifest",
                "dl_plan_project_live_workflow",
                "dl_run_project_live_dry_run",
                "dl_run_project_live_apply",
                "dl_read_project_live_summary",
                "dl_build_validation_evidence_report",
            }.issubset(tools)
        )


if __name__ == "__main__":
    unittest.main()
