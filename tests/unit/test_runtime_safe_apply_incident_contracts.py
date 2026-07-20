from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]


class RuntimeDeliveryStageTests(unittest.TestCase):
    def test_delivery_stage_uses_exact_five_stage_lattice(self):
        from datalens_dev_mcp.pipeline.live_maintenance import _delivery_stage

        empty = {"verified": False}
        saved = {"verified": True}
        published = {"verified": True}
        cases = [
            (empty, empty, empty, "not_run", "not_run", False, "planned"),
            (saved, empty, empty, "not_run", "not_run", False, "saved"),
            (saved, empty, empty, "passed", "not_run", True, "saved_runtime_passed"),
            (saved, published, published, "passed", "not_run", True, "published"),
            (saved, published, published, "passed", "passed", True, "published_runtime_passed"),
        ]
        for saved_evidence, publish_evidence, published_evidence, saved_gate, published_gate, allowed, expected in cases:
            with self.subTest(expected=expected):
                stage = _delivery_stage(
                    completion_evidence={
                        "saved_readback": saved_evidence,
                        "publish_from_saved": publish_evidence,
                        "published_readback": published_evidence,
                    },
                    saved_runtime_gate={"status": saved_gate},
                    published_runtime_gate={"status": published_gate},
                    publish_allowed=allowed,
                )
                self.assertEqual(stage, expected)

    def test_out_of_order_publish_evidence_cannot_advance_stage(self):
        from datalens_dev_mcp.pipeline.live_maintenance import _delivery_stage

        stage = _delivery_stage(
            completion_evidence={
                "saved_readback": {"verified": True},
                "publish_from_saved": {"verified": True},
                "published_readback": {"verified": True},
            },
            saved_runtime_gate={"status": "blocked"},
            published_runtime_gate={"status": "passed"},
            publish_allowed=False,
        )

        self.assertEqual(stage, "saved")

    def test_legacy_runtime_alias_is_published_and_warns(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        with tempfile.TemporaryDirectory() as tmp:
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dashboard_1",
                target_tab_id="overview",
                target_url="https://datalens.example/dashboard_1",
                publish=False,
                runtime_gate_evidence={"status": "browser_auth_required", "blocked_reason": "SSO"},
            )
            run = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))

        self.assertIn("deprecated", " ".join(result["warnings"]))
        self.assertEqual(run["runtime_gates"]["published"]["status"], "blocked")
        self.assertEqual(run["runtime_gates"]["saved"]["status"], "not_run")

    def test_saved_only_sso_keeps_saved_stage_and_publish_not_ready(self):
        from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update

        completion = {
            "phase": {"name": "completion_evidence", "status": "verified", "artifact_paths": []},
            "completion_ready": True,
            "missing_evidence": [],
            "blocked_reasons": [],
            "safe_apply_execution": {"verified": True, "artifact_paths": []},
            "saved_readback": {
                "verified": True,
                "supplied": True,
                "artifact_paths": [],
                "object_revisions": {"dashboard_1": "rev_saved"},
            },
            "publish_from_saved": {"verified": False, "supplied": False, "artifact_paths": []},
            "published_readback": {"verified": False, "supplied": False, "artifact_paths": []},
        }
        with tempfile.TemporaryDirectory() as tmp, patch(
            "datalens_dev_mcp.pipeline.live_maintenance._completion_evidence_phase",
            return_value=completion,
        ):
            result = run_live_maintenance_update(
                project_root=tmp,
                workbook_id="workbook_1",
                dashboard_id="dashboard_1",
                target_tab_id="overview",
                target_url="https://datalens.example/dashboard_1",
                approved=True,
                publish=False,
                saved_runtime_gate_evidence={"status": "browser_auth_required", "blocked_reason": "SSO"},
            )

        self.assertEqual(result["status"], "runtime_not_verified")
        self.assertEqual(result["delivery_stage"], "saved")
        self.assertFalse(result["publish_allowed"])


class SafeApplyIncidentTests(unittest.TestCase):
    def test_conflicts_and_unknown_write_outcome_are_structured(self):
        from datalens_dev_mcp.pipeline.safe_apply import _classify_safe_apply_error

        locked = _classify_safe_apply_error(
            RuntimeError(
                'ENTRY_IS_LOCKED retry_after: 3 lock_until: "2026-07-13T12:30:00Z"'
            ),
            write_attempted=True,
        )
        unique = _classify_safe_apply_error(
            RuntimeError("UNIQUE_VIOLATION displayKey already exists"),
            write_attempted=True,
        )
        unknown = _classify_safe_apply_error(RuntimeError("connection reset"), write_attempted=True)

        self.assertEqual((locked["category"], locked["remote_code"]), ("conflict_no_write", "ENTRY_IS_LOCKED"))
        self.assertEqual(locked["retry_after"], 3)
        self.assertEqual(locked["lock_until"], "2026-07-13T12:30:00Z")
        self.assertEqual((unique["category"], unique["remote_code"]), ("conflict_no_write", "UNIQUE_VIOLATION"))
        self.assertTrue(unique["reconciliation_required"])
        self.assertEqual(unknown["category"], "write_outcome_unknown")
        self.assertFalse(unknown["retry_safe"])

    def test_conflict_resume_retries_lock_but_reconciles_unique(self):
        from datalens_dev_mcp.pipeline.safe_apply import _retry_resume_summary

        plan = {"actions": [{"method": "updateEditorChart"}, {"method": "updateEditorChart"}]}
        locked = _retry_resume_summary(
            plan,
            [{"index": 0, "write_attempted": True, "error": {"write_outcome": "no_write", "retry_safe": True}}],
            failed_index=0,
        )
        unique = _retry_resume_summary(
            plan,
            [
                {
                    "index": 0,
                    "write_attempted": True,
                    "error": {
                        "write_outcome": "no_write",
                        "retry_safe": False,
                        "reconciliation_required": True,
                    },
                }
            ],
            failed_index=0,
        )

        self.assertEqual(locked["safe_unfinished_action_indices"], [0, 1])
        self.assertEqual(locked["resume_policy"], "rerun_fresh_read_then_retry_same_action")
        self.assertEqual(unique["safe_unfinished_action_indices"], [])
        self.assertTrue(unique["requires_partial_create_reconciliation"])

    def test_transaction_group_publish_requires_saved_readback(self):
        from datalens_dev_mcp.pipeline.safe_apply import _publish_transaction_group_error

        save = {
            "method": "updateEditorChart",
            "transaction_group_id": "visible_patch",
            "payload": {"mode": "save"},
            "readback_contract": {"required": True, "branch": "saved"},
        }
        publish = {
            "method": "updateEditorChart",
            "transaction_group_id": "visible_patch",
            "payload": {"mode": "publish"},
        }
        plan = {"actions": [save, publish]}
        missing = _publish_transaction_group_error(
            plan=plan,
            results=[{"index": 0, "executed": True, "artifacts": {}}],
            action_index=1,
            action=publish,
            payload=publish["payload"],
        )
        complete = _publish_transaction_group_error(
            plan=plan,
            results=[
                {
                    "index": 0,
                    "executed": True,
                    "artifacts": {"readback": {"path": "saved.json"}},
                    "readback_verification": {"verified": True},
                }
            ],
            action_index=1,
            action=publish,
            payload=publish["payload"],
        )

        self.assertEqual(missing["category"], "transaction_group_incomplete")
        self.assertIsNone(complete)

    def test_saved_published_identity_divergence_requires_publish_even_when_unchanged(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive

        action = {
            "action": "update_editor_chart",
            "method": "updateEditorChart",
            "changed": False,
            "savedId": "saved_2",
            "publishedId": "published_1",
            "payload": {"mode": "save", "entry": {"entryId": "chart_1", "revId": "rev_1"}},
            "fresh_read_method": "getEditorChart",
            "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
            "readback_method": "getEditorChart",
            "readback_payload": {"chartId": "chart_1", "branch": "saved"},
        }
        plan = create_safe_apply_plan(project_root=".", actions=[action], approved=True)
        preflight = validate_safe_apply_plan_exhaustive(plan)

        self.assertTrue(plan["actions"][0]["publish_required"])
        self.assertNotIn("safe apply plan has no changed actions", preflight["issues"])
        self.assertEqual(plan["actions"][0]["transaction_group_id"], "delivery")
        self.assertEqual(plan["actions"][0]["change_scope"], "content")

    def test_content_scope_merges_overlay_onto_fresh_geometry_and_unknown_fields(self):
        from datalens_dev_mcp.pipeline.safe_apply import apply_desired_overlay_to_fresh_readback

        fresh = {
            "tabs": [
                {
                    "id": "overview",
                    "items": [{"id": "existing", "type": "widget", "unknown_live_field": {"keep": True}}],
                    "layout": [{"i": "existing", "x": 0, "y": 0, "w": 12, "h": 6}],
                }
            ]
        }
        proposed = {
            "tabs": [
                {
                    "id": "overview",
                    "items": [{"id": "existing", "type": "widget"}],
                    "layout": [{"i": "existing", "x": 1, "y": 0, "w": 12, "h": 7}],
                }
            ]
        }

        result = apply_desired_overlay_to_fresh_readback(
            action={
                "action": "update_dashboard",
                "method": "updateDashboard",
                "change_scope": "content",
                "desired_overlay": proposed,
            },
            planned_payload=proposed,
            fresh_readback=fresh,
        )

        self.assertTrue(result["ok"], result)
        tab = result["payload"]["tabs"][0]
        self.assertEqual(tab["layout"][0], {"i": "existing", "x": 0, "y": 0, "w": 12, "h": 6})
        self.assertEqual(tab["items"][0]["unknown_live_field"], {"keep": True})

    def test_generic_update_merges_overlay_onto_fresh_unknown_fields(self):
        from datalens_dev_mcp.pipeline.safe_apply import apply_desired_overlay_to_fresh_readback

        fresh = {
            "entry": {
                "entryId": "chart_1",
                "revId": "rev_1",
                "data": {"content": "old", "unknown_live_field": {"keep": True}},
            }
        }
        planned = {
            "mode": "save",
            "entry": {"entryId": "chart_1", "revId": "rev_1", "data": {"content": "new"}},
        }

        result = apply_desired_overlay_to_fresh_readback(
            action={
                "action": "update_editor_chart",
                "method": "updateEditorChart",
                "desired_overlay": planned,
            },
            planned_payload=planned,
            fresh_readback=fresh,
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["payload"]["entry"]["data"]["content"], "new")
        self.assertEqual(result["payload"]["entry"]["data"]["unknown_live_field"], {"keep": True})
        self.assertEqual(result["payload"]["mode"], "save")

    def test_layout_scope_requires_and_verifies_explicit_geometry_contract(self):
        from datalens_dev_mcp.pipeline.safe_apply import (
            _geometry_scope_contract_issues,
            apply_desired_overlay_to_fresh_readback,
        )

        fresh = {"layout": [{"i": "widget_1", "x": 0, "y": 0, "w": 12, "h": 6}]}
        proposed = {"layout": [{"i": "widget_1", "x": 12, "y": 0, "w": 12, "h": 6}]}
        action = {
            "action": "update_dashboard",
            "method": "updateDashboard",
            "change_scope": "layout",
            "desired_overlay": proposed,
            "geometry_expectations": [
                {
                    "item_id": "widget_1",
                    "expected_old": {"x": 0, "y": 0, "w": 12, "h": 6},
                    "expected_new": {"x": 12, "y": 0, "w": 12, "h": 6},
                }
            ],
        }

        issues = _geometry_scope_contract_issues(
            {**action, "geometry_expectations": []},
            index=0,
        )
        self.assertEqual(issues[0].split()[2], "change_scope=layout")
        self.assertTrue(
            apply_desired_overlay_to_fresh_readback(
                action=action,
                planned_payload=proposed,
                fresh_readback=fresh,
            )["ok"]
        )
        stale = {"layout": [{"i": "widget_1", "x": 1, "y": 0, "w": 12, "h": 6}]}
        mismatch = apply_desired_overlay_to_fresh_readback(
            action=action,
            planned_payload=proposed,
            fresh_readback=stale,
        )
        self.assertEqual(mismatch["error"]["category"], "geometry_expectation_mismatch")

    def test_semantic_role_mapping_is_injective_unless_shared_explicitly(self):
        from datalens_dev_mcp.pipeline.dashboard_object_granularity import validate_semantic_role_object_mapping

        payload = {
            "items": [
                {
                    "id": "state_count",
                    "type": "widget",
                    "data": {"tabs": [{"id": "count", "chartId": "chart_shared"}]},
                },
                {
                    "id": "state_hours",
                    "type": "widget",
                    "data": {"tabs": [{"id": "hours", "chartId": "chart_shared"}]},
                },
            ]
        }
        findings = validate_semantic_role_object_mapping(payload)
        payload["items"][0]["shared_object_key"] = "shared_state"
        payload["items"][1]["shared_object_key"] = "shared_state"
        shared_findings = validate_semantic_role_object_mapping(payload)

        self.assertIn("semantic_role_object_mapping_not_injective", {item.rule for item in findings})
        self.assertEqual(shared_findings, [])

    def test_non_map_wizard_update_preserves_fresh_visualization_token(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class WizardClient:
            def __init__(self):
                self.calls = []
                self.saved_payload = {}

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "getWizardChart" and len(self.calls) == 1:
                    return {
                        "entryId": "chart_1",
                        "revId": "rev_1",
                        "template": "datalens",
                        "data": {
                            "visualization": {"id": "column100p"},
                            "unknown_live_field": {"keep": True},
                        },
                    }
                if method == "updateWizardChart":
                    self.saved_payload = payload
                    return {"entryId": "chart_1", "revId": "rev_2"}
                return {
                    "entryId": "chart_1",
                    "revId": "rev_2",
                    "template": self.saved_payload["template"],
                    "data": self.saved_payload["data"],
                }

        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "entryId": "chart_1",
                "revId": "rev_1",
                "template": "datalens",
                "mode": "save",
                "data": {"visualization": {"id": "column100p"}, "title": "Updated"},
            }
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[
                    {
                        "action": "update_wizard_chart",
                        "method": "updateWizardChart",
                        "object_id": "chart_1",
                        "payload": payload,
                        "fresh_read_method": "getWizardChart",
                        "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                        "readback_method": "getWizardChart",
                        "readback_payload": {"chartId": "chart_1", "branch": "saved"},
                    }
                ],
            )
            client = WizardClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertTrue(result["executed"], result)
        write_payload = next(payload for method, payload in client.calls if method == "updateWizardChart")
        self.assertEqual(write_payload["data"]["visualization"]["id"], "column100p")
        self.assertEqual(write_payload["data"]["unknown_live_field"], {"keep": True})

    def test_non_map_wizard_update_rejects_guessed_or_unbound_token(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import (
            _wizard_live_readback_contract_issues,
            create_safe_apply_plan,
            execute_safe_apply,
        )

        class MismatchWizardClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "getWizardChart":
                    return {
                        "entryId": "chart_1",
                        "revId": "rev_1",
                        "data": {"visualization": {"id": "column100p"}},
                    }
                raise AssertionError("mismatched visualization token must block the write")

        unbound_issues = _wizard_live_readback_contract_issues(
            {"method": "updateWizardChart", "fresh_read_method": "getEditorChart"},
            {"entryId": "chart_1", "template": "datalens", "mode": "save", "data": {}},
            index=0,
        )
        self.assertTrue(any("fresh getWizardChart" in issue for issue in unbound_issues))
        self.assertTrue(any("saved-branch" in issue for issue in unbound_issues))

        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "entryId": "chart_1",
                "revId": "rev_1",
                "template": "datalens",
                "mode": "save",
                "data": {"visualization": {"id": "guessed_column"}},
            }
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[
                    {
                        "action": "update_wizard_chart",
                        "method": "updateWizardChart",
                        "object_id": "chart_1",
                        "payload": payload,
                        "fresh_read_method": "getWizardChart",
                        "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                        "readback_method": "getWizardChart",
                        "readback_payload": {"chartId": "chart_1", "branch": "saved"},
                    }
                ],
            )
            client = MismatchWizardClient()
            result = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=client,
            )

        self.assertFalse(result["executed"])
        self.assertEqual(result["actions"][0]["error"]["category"], "wizard_visualization_token_mismatch")
        self.assertEqual([method for method, _ in client.calls], ["getWizardChart"])

    def test_wizard_lifecycle_update_requires_saved_readback_and_create_is_supported(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import (
            dl_create_wizard_chart_plan,
            dl_update_wizard_chart_plan,
        )

        entry = {
            "entryId": "chart_1",
            "revId": "rev_1",
            "template": "datalens",
            "data": {"visualization": {"id": "column100p"}},
        }
        guessed = dl_update_wizard_chart_plan(entry)
        derived = dl_update_wizard_chart_plan(
            {"branch": "saved", "entry": entry},
            source_adapter="saved_entry",
        )
        create = dl_create_wizard_chart_plan(
            {
                "workbookId": "workbook_fixture",
                "name": "Supported",
                "data": {"visualization": {"id": "column100p"}},
            }
        )

        self.assertEqual(guessed["error"]["category"], "fresh_saved_readback_required")
        self.assertTrue(derived["ok"], derived)
        self.assertEqual(derived["source_adapter"], "saved_entry")
        self.assertEqual(derived["payload"]["data"]["visualization"]["id"], "column100p")
        self.assertTrue(create["ok"], create)
        self.assertEqual(create["method"], "createWizardChart")


class ValidationIncidentTests(unittest.TestCase):
    def test_lead_in_frame_requires_nullable_and_explicit_null_default(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        unsafe = lint_editor_sql_text("SELECT leadInFrame(event_at) OVER (ORDER BY event_at) FROM events")
        nullable_only = lint_editor_sql_text(
            "SELECT leadInFrame(toNullable(event_at)) OVER (ORDER BY event_at) FROM events"
        )
        default_only = lint_editor_sql_text(
            "SELECT leadInFrame(event_at, 1, NULL) OVER (ORDER BY event_at) FROM events"
        )
        safe = lint_editor_sql_text(
            "SELECT leadInFrame(toNullable(event_at), 1, NULL) OVER (ORDER BY event_at) FROM events"
        )

        self.assertIn("lead_in_frame_requires_nullable_and_null_default", {item.rule for item in unsafe.issues})
        self.assertIn("lead_in_frame_requires_nullable_and_null_default", {item.rule for item in nullable_only.issues})
        self.assertIn("lead_in_frame_requires_nullable_and_null_default", {item.rule for item in default_only.issues})
        self.assertNotIn("lead_in_frame_requires_nullable_and_null_default", {item.rule for item in safe.issues})
        boundary = json.loads(
            (REPO_ROOT / "tests/fixtures/incidents/lead_in_frame_partition_boundary.reference.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIsNone(boundary["partition_last_row_expected"])
        self.assertNotEqual(boundary["partition_last_row_expected"], boundary["forbidden_boundary_value"])

    def test_visible_flat_table_hint_intent_is_error(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_visual_dataset_contract

        result = validate_wizard_visual_dataset_contract(
            {
                "visualization": {
                    "id": "flatTable",
                    "require_visible_hints": True,
                    "placeholders": [
                        {"items": [{"guid": "quality", "description": "Explain quality statuses"}]}
                    ],
                },
                "datasetsPartialFields": [{"guid": "quality"}],
            }
        )

        finding = next(item for item in result.findings if item.rule == "wizard_flat_table_hint_not_enabled")
        self.assertEqual(finding.severity, "error")
        self.assertFalse(result.ok)

        missing_description = validate_wizard_visual_dataset_contract(
            {
                "visualization": {
                    "id": "flatTable",
                    "require_visible_hints": True,
                    "placeholders": [{"items": [{"guid": "quality", "hintSettings": {"enabled": True, "text": "Quality"}}]}],
                },
                "datasetsPartialFields": [{"guid": "quality"}],
            }
        )
        missing_finding = next(
            item for item in missing_description.findings if item.rule == "wizard_flat_table_hint_not_enabled"
        )
        self.assertEqual(missing_finding.severity, "error")
        self.assertIn("description", missing_finding.message)

    def test_exact_code184_and_column100p_reference_fixtures(self):
        from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_text

        sql = (REPO_ROOT / "tests/fixtures/incidents/code184_payment_at.sql").read_text(encoding="utf-8")
        reference = json.loads(
            (REPO_ROOT / "tests/fixtures/incidents/column100p.reference.json").read_text(encoding="utf-8")
        )
        result = lint_editor_sql_text(sql)

        self.assertIn("aggregate_alias_shadows_input", {item.rule for item in result.issues})
        self.assertEqual(reference["visualization_id"], "column100p")
        self.assertEqual(reference["fixture_kind"], "wizard_native_creation_and_saved_update_regression")
        self.assertEqual(reference["creation_route"], "wizard_native")

    def test_tracked_source_snapshot_detects_read_only_workflow_mutation(self):
        from datalens_dev_mcp.pipeline.project_live_workflows import (
            _tracked_source_mutation_result,
            _tracked_source_snapshot,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            source = root / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "source.py"], check=True)
            before = _tracked_source_snapshot(root)
            source.write_text("value = 2\n", encoding="utf-8")
            result = _tracked_source_mutation_result(root, before)
            restored = source.read_bytes()

        self.assertTrue(result["mutated"])
        self.assertEqual(result["changed_paths"], ["source.py"])
        self.assertTrue(result["restored"])
        self.assertEqual(restored, b"value = 1\n")

    def test_guarded_dry_run_restores_tracked_source_bytes(self):
        from datalens_dev_mcp.pipeline.project_live_workflows import run_project_live_dry_run

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "reports").mkdir()
            source = root / "source.sql"
            source.write_bytes(b"SELECT 1\n")
            (root / "scripts" / "dry.py").write_text(
                "from pathlib import Path\n"
                "import json\n"
                "Path('source.sql').write_text('SELECT 2\\n')\n"
                "json.dump({'dashboard_id': 'dashboard_1', 'changed_object_counts': {'dashboards': 0}}, "
                "open('reports/dry.json', 'w'))\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": "2026-06-25.project_live_workflow_manifest.v3",
                "project_name": "mutation_guard",
                "workflows": [
                    {
                        "name": "dry",
                        "may_execute_command": True,
                        "dry_run": {
                            "command": [sys.executable, "scripts/dry.py"],
                            "summary_path": "reports/dry.json",
                        },
                    }
                ],
            }
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)

            result = run_project_live_dry_run(root, workflow_name="dry", execute_now=True)

            self.assertEqual(result["status"], "tracked_source_mutation_blocked")
            self.assertFalse(result["ok"])
            self.assertTrue(result["tracked_source_mutation_guard"]["restored"])
            self.assertEqual(source.read_bytes(), b"SELECT 1\n")


if __name__ == "__main__":
    unittest.main()
