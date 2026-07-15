import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class PromptPackAvailabilityContractsTests(unittest.TestCase):
    def test_runtime_param_cannot_enable_statically_unsupported_source(self):
        from datalens_dev_mcp.pipeline.source_availability import effective_availability

        matrix = {
            "schema_version": "datalens.dashboard-source-availability.v1",
            "project": "generic",
            "sources": {
                "optional_events": {
                    "physical_tables": ["warehouse.analytics.optional_events"],
                    "environments": {
                        "prod": {
                            "static_supported": False,
                            "table_present": False,
                            "expected_exception": True,
                        }
                    },
                }
            },
        }

        decision = effective_availability(matrix, "optional_events", "prod", ["1"])

        self.assertFalse(decision.effective_available)
        self.assertFalse(decision.runtime_available)
        self.assertEqual(decision.classification, "expected_unavailable")

    def test_present_empty_is_no_data_not_no_table(self):
        from datalens_dev_mcp.pipeline.source_availability import effective_availability

        matrix = {
            "schema_version": "datalens.dashboard-source-availability.v1",
            "project": "generic",
            "sources": {
                "event_log": {
                    "physical_tables": ["warehouse.analytics.event_log"],
                    "environments": {"stage": {"static_supported": True, "table_present": True}},
                }
            },
        }

        decision = effective_availability(matrix, "event_log", "stage", None, row_count=0)

        self.assertTrue(decision.effective_available)
        self.assertEqual(decision.classification, "present_empty")

    def test_dashboard_chart_validation_uses_same_availability_matrix(self):
        from datalens_dev_mcp.pipeline.dashboard_chart_validation import build_dashboard_chart_validation

        matrix = {
            "schema_version": "datalens.dashboard-source-availability.v1",
            "project": "generic",
            "sources": {
                "source_a": {
                    "physical_tables": ["db.table_a"],
                    "environments": {"stage": {"static_supported": True, "table_present": True}},
                }
            },
        }

        artifact = build_dashboard_chart_validation(
            dashboard_id="dash",
            workbook_id="workbook",
            branch="saved",
            charts=[{"entry_id": "chart_a", "path": "Source Tables/a", "source_keys": ["source_a"]}],
            source_availability_matrix=matrix,
            environments=["stage"],
            browser_status="browser_auth_required",
        )

        result = artifact["charts"][0]["environment_results"]["stage"]
        self.assertEqual(artifact["schema_version"], "datalens.dashboard-chart-validation.v1")
        self.assertEqual(result["sql_status"], "compiled")
        self.assertEqual(result["render_status"], "browser_auth_required")


class PromptPackGraphBudgetAndQaTests(unittest.TestCase):
    def test_active_graph_hydrates_external_selector_dependency(self):
        from datalens_dev_mcp.pipeline.active_graph import build_active_dashboard_graph

        graph = build_active_dashboard_graph(
            dashboard_id="dash",
            workbook_id="workbook",
            requested_tab="qZy",
            dashboard={
                "tabs": [
                    {
                        "id": "qZy",
                        "items": [
                            {"id": "gantt", "type": "widget", "chartId": "chart_main"},
                            {"id": "0J7", "type": "control", "external_entry_id": "selector_shared"},
                        ],
                    }
                ]
            },
            workbook_entries=[
                {"entryId": "chart_main", "type": "editor_chart"},
                {"entryId": "selector_shared", "type": "control_node"},
                {"entryId": "old_chart", "type": "editor_chart"},
            ],
        )

        by_id = {entry["entry_id"]: entry for entry in graph["entries"]}
        self.assertEqual(by_id["selector_shared"]["role"], "shared_dependency")
        self.assertTrue(by_id["selector_shared"]["hydrated"])
        self.assertEqual(by_id["old_chart"]["role"], "dormant")

    def test_editor_source_budget_hard_limits_and_high_fanout(self):
        from datalens_dev_mcp.pipeline.performance_budget import build_editor_source_budget_evidence

        evidence = build_editor_source_budget_evidence(
            [
                {
                    "source_key": "periodData",
                    "estimated_single_source_bytes": 60 * 1024 * 1024,
                    "estimated_source_time_ms": 96_000,
                    "physical_rows_before": 10_000_000,
                    "business_grain_rows_after": 250,
                    "fix_strategy": "server_side_filter_and_group",
                }
            ],
            dashboard_id="dash",
        )

        row = evidence["sources"][0]
        self.assertEqual(evidence["schema_version"], "datalens.source-performance-budget.v1")
        self.assertEqual(row["source_budget_status"], "fail")
        self.assertIn("single_source_50mb_limit_exceeded", row["blocked_reasons"])
        self.assertIn("single_source_95s_limit_exceeded", row["blocked_reasons"])
        self.assertIn("high_fanout_candidate", row["warnings"])

    def test_browser_pass_requires_rendered_artifact(self):
        from datalens_dev_mcp.pipeline.browser_qa import browser_qa_evidence

        evidence = browser_qa_evidence(status="browser_pass")

        self.assertEqual(evidence["status"], "not_checked")
        self.assertFalse(evidence["browser_verified"])
        self.assertIn("browser_pass_requires_rendered_artifact", evidence["blocked_reasons"])


class PromptPackPlanningContractsTests(unittest.TestCase):
    def test_evidence_mode_selects_lightest_sufficient_mode(self):
        from datalens_dev_mcp.pipeline.evidence_mode import choose_evidence_mode

        self.assertEqual(choose_evidence_mode("rename a title").evidence_mode, "api_only")
        self.assertEqual(choose_evidence_mode("fix NO TABLE in Source Tables").evidence_mode, "source_matrix")
        self.assertEqual(choose_evidence_mode("502 source timeout for periodData").evidence_mode, "targeted_data_evidence")
        self.assertEqual(choose_evidence_mode("validate every tab and chart").evidence_mode, "full_dashboard_audit")

    def test_existing_object_update_safe_apply_plan_is_first_class(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                "os.environ",
                {
                    "DATALENS_ENV_FILE": "",
                    "DATALENS_MCP_ENABLE_WRITES": "1",
                    "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
                },
                clear=True,
            ):
                result = dl_create_safe_apply_plan(
                    tmp,
                    approved=True,
                    delivery_intent_text="fix the shared selector",
                    existing_update_actions=[
                        {
                            "object_type": "control_node",
                            "object_id": "selector_shared",
                            "base_revision": "rev_1",
                            "changed_sections": ["data.sources"],
                            "payload": {
                                "entry": {
                                    "entryId": "selector_shared",
                                    "revId": "rev_1",
                                    "data": {"sources": "", "prepare": "", "config": ""},
                                }
                            },
                        }
                    ],
                )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "existing_object_update_plan_created")
        self.assertEqual(result["actions"][0]["method"], "updateEditorChart")
        self.assertEqual(result["existing_object_update_plan"]["actions"][0]["base_revision"], "rev_1")
        self.assertTrue(result["existing_object_update_plan"]["actions"][0]["requires_publish_readback"])
        self.assertEqual(result["delivery_intent_decision"]["state"], "save_then_publish")

    def test_project_live_apply_defaults_to_publish_for_known_target(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            manifest = {
                "schema_version": "2026-07-07.project_live_workflow_manifest.v5",
                "project_name": "default_publish",
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
                "json.dump({'dashboard_id':'dashboard_live','saved':True,"
                "'saved_readback_path':'artifacts/readback/dashboard.saved.latest.json'}, open('reports/apply.json','w'))\n",
                encoding="utf-8",
            )
            (root / "scripts" / "publish.py").write_text(
                "import json\nfrom pathlib import Path\nPath('reports').mkdir(exist_ok=True)\n"
                "json.dump({'dashboard_id':'dashboard_live','published':True,"
                "'published_readback_path':'artifacts/readback/dashboard.published.latest.json'}, open('reports/publish.json','w'))\n",
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {
                    "DATALENS_ENV_FILE": "",
                    "DATALENS_MCP_ENABLE_WRITES": "1",
                    "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
                    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
                },
                clear=True,
            ):
                result = dl_run_project_live_apply(str(root), workflow_name="layout", execute_now=True, approved=True)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["delivery_intent_decision"]["state"], "save_then_publish")
        self.assertEqual(result["delivery_intent_decision"]["publish_stage_status"], "completed")
        self.assertTrue(result["project_live_delivery"]["published"]["passed"])


class PromptPackDocsOpenApiContractsTests(unittest.TestCase):
    def test_docs_openapi_reconciliation_tracks_get_permissions_bulk(self):
        root = Path(__file__).resolve().parents[2]
        assets = root / "src" / "datalens_dev_mcp" / "assets"
        catalog = json.loads((assets / "config" / "datalens_api_methods.json").read_text(encoding="utf-8"))
        api_schemas = assets / "schemas" / "datalens-api"
        lock = json.loads((api_schemas / "openapi.lock.json").read_text(encoding="utf-8"))
        schemas = json.loads((api_schemas / "selected-openapi-schema-refs.json").read_text(encoding="utf-8"))

        methods = {item["method"]: item for item in catalog["methods"]}
        bulk_args = schemas["GetPermissionsBulkArgs"]["properties"]

        self.assertEqual(catalog["operation_count"], 88)
        self.assertEqual(lock["operation_count"], 88)
        self.assertEqual(lock["component_schema_count"], 483)
        self.assertEqual(methods["getPermissionsBulk"]["mcp_tool"], "dl_rpc_readonly")
        self.assertEqual(methods["getPermissionsBulk"]["support_status"], "EXECUTABLE_TOOL_SUPPORTED")
        for key in ("entryIds", "workbookIds", "collectionIds"):
            self.assertEqual(bulk_args[key]["minItems"], 1)
            self.assertEqual(bulk_args[key]["maxItems"], 1000)


class PromptPackSourceDiagnosticsTests(unittest.TestCase):
    def test_source_error_classification_covers_log_regressions(self):
        from datalens_dev_mcp.validators.source_diagnostics import classify_datalens_source_error

        cases = {
            "missing_table_or_bad_availability_guard": {"message": "DB::Exception Code: 60 UNKNOWN_TABLE"},
            "schema_mismatch": {"message": "UNKNOWN_IDENTIFIER column x"},
            "source_timeout_or_high_fanout_candidate": {"message": "502 Bad Gateway sourceType: bi_connections"},
            "stale_availability_param": {
                "message": "query emitted",
                "query": "select * from warehouse.analytics.optional_events",
                "statically_unsupported_tables": ["warehouse.analytics.optional_events"],
            },
        }
        for expected, payload in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(classify_datalens_source_error(payload)["category"], expected)


if __name__ == "__main__":
    unittest.main()
