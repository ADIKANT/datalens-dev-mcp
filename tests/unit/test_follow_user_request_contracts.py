import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class FollowUserRequestContractTests(unittest.TestCase):
    @staticmethod
    def _safe_apply_plan(project_root: str) -> dict:
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan

        return create_safe_apply_plan(
            project_root=project_root,
            approved=True,
            user_request_text="update this chart",
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {
                        "mode": "save",
                        "entry": {"entryId": "chart_contract", "revId": "rev_1"},
                    },
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_contract", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_contract", "branch": "saved"},
                }
            ],
        )

    def test_write_and_save_hard_off_switches_block_before_any_rpc(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply

        class NoRpcClient:
            def __init__(self) -> None:
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                raise AssertionError("runtime hard-off switch must block before RPC")

        cases = (
            (
                DataLensConfig(write_enabled=False, save_enabled=True, publish_enabled=True),
                "write mode is disabled",
            ),
            (
                DataLensConfig(write_enabled=True, save_enabled=False, publish_enabled=True),
                "save execution is disabled",
            ),
        )
        for config, expected_reason in cases:
            with self.subTest(expected_reason=expected_reason), tempfile.TemporaryDirectory() as tmp:
                client = NoRpcClient()
                result = execute_safe_apply(self._safe_apply_plan(tmp), config=config, client=client)

                self.assertFalse(result["executed"])
                self.assertEqual(result["status"], "blocked")
                self.assertTrue(any(expected_reason in reason for reason in result["blocked_reasons"]))
                self.assertEqual(client.calls, [])

    def test_partial_content_removal_is_an_update_and_whole_object_removal_is_delete(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        partial = normalize_user_request("Remove the legend from chart:chart_12345")
        whole = normalize_user_request("Remove chart:chart_12345")

        self.assertEqual(partial.task_intent, "update")
        self.assertEqual(partial.destructive_actions, [])
        self.assertEqual(partial.target_chart_id, "chart_12345")
        self.assertIn("delete", whole.destructive_actions)

    def test_russian_delivery_intent_matches_public_documentation(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        create = normalize_user_request("создай чарт chart:chart_12345")
        save_only = normalize_user_request("исправь чарт chart:chart_12345 и сохрани без публикации")
        plan_only = normalize_user_request("составь план изменения чарта chart:chart_12345")
        partial_delete = normalize_user_request("удали заголовок чарта chart:chart_12345")

        self.assertEqual(create.task_intent, "implement")
        self.assertEqual(create.publish_override, "none")
        self.assertIn(save_only.task_intent, {"implement", "fix", "update"})
        self.assertEqual(save_only.publish_override, "no_publish")
        self.assertEqual(plan_only.publish_override, "plan_only")
        self.assertEqual(partial_delete.task_intent, "update")
        self.assertEqual(partial_delete.destructive_actions, [])

    def test_english_save_without_publish_overrides_implementation_delivery(self):
        from datalens_dev_mcp.pipeline.delivery_intent import DeliveryContext, resolve_delivery_intent
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request("fix chart chart:chart_12345, save without publishing")
        decision = resolve_delivery_intent(
            request,
            DeliveryContext(
                target_known=True,
                writes_enabled=True,
                save_enabled=True,
                publish_enabled=True,
                safe_apply_approved=True,
                fresh_readback_available=True,
                revision_preservation_available=True,
            ),
        )

        self.assertEqual(request.publish_override, "no_publish")
        self.assertEqual(decision.state, "save_only")
        self.assertFalse(decision.publish_expected)
        self.assertTrue(decision.writes_expected)

    def test_documented_english_audit_prompt_is_read_only(self):
        from datalens_dev_mcp.pipeline.delivery_intent import DeliveryContext, resolve_delivery_intent
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        text = (
            "Audit dashboard dashboard_fixture. Read the current saved version, related objects, and their relations. "
            "Show issues and generated report paths. Do not save or publish anything."
        )
        request = normalize_user_request(text)
        decision = resolve_delivery_intent(
            request,
            DeliveryContext(
                target_known=True,
                writes_enabled=True,
                save_enabled=True,
                publish_enabled=True,
                fresh_readback_available=True,
                revision_preservation_available=True,
            ),
        )

        self.assertEqual(request.task_intent, "review")
        self.assertEqual(request.publish_override, "plan_only")
        self.assertIn(decision.state, {"read_only", "plan_only"})
        self.assertFalse(decision.writes_expected)
        self.assertFalse(decision.publish_expected)

    def test_negated_create_with_review_is_not_a_write_intent_in_ru_or_en(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        for text in (
            "Do not create anything; only review the dashboard.",
            "Не создавай ничего, только проверь дашборд.",
        ):
            with self.subTest(text=text):
                request = normalize_user_request(text)
                self.assertEqual(request.task_intent, "review")
                self.assertEqual(request.publish_override, "plan_only")

    def test_whole_object_delete_requires_second_call_for_exact_unchanged_plan(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_retire_project(root)

            first = dl_run_project_live_apply(
                str(root),
                workflow_name="retire_legacy",
                execute_now=True,
                action="retire_legacy_objects",
                delivery_intent_text="delete chart:chart_legacy_1",
            )

            completed = {
                "ok": True,
                "executed": True,
                "status": "completed",
                "action": "retire_legacy_objects",
                "workflow_name": "retire_legacy",
                "workbook_id": "workbook_1",
                "dashboard_ids": [],
            }
            with patch(
                "datalens_dev_mcp.mcp.tools.pipeline.run_project_live_apply",
                return_value=completed,
            ) as run_apply:
                second = dl_run_project_live_apply(
                    str(root),
                    workflow_name="retire_legacy",
                    execute_now=True,
                    action="retire_legacy_objects",
                    delivery_intent_text="delete chart:chart_legacy_1",
                    confirm_delete=True,
                )

        self.assertEqual(first["status"], "delete_confirmation_required")
        self.assertEqual(first["delete_targets"], [{"id": "chart_legacy_1", "type": "editor_chart"}])
        self.assertEqual(len(first["delete_plan_hash"]), 64)
        self.assertTrue(second["delete_confirmation"]["confirmed"])
        self.assertEqual(second["delete_confirmation"]["plan_hash"], first["delete_plan_hash"])
        self.assertTrue(run_apply.call_args.kwargs["confirm_delete"])

    def test_delete_confirmation_does_not_carry_over_to_changed_plan(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_run_project_live_apply

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._write_retire_project(root)
            first = dl_run_project_live_apply(
                str(root),
                workflow_name="retire_legacy",
                execute_now=True,
                action="retire_legacy_objects",
                delivery_intent_text="delete chart:chart_legacy_1",
            )
            manifest["workflows"][0]["retire_legacy_objects"]["objects"][0]["id"] = "chart_legacy_2"
            (root / ".datalens-mcp.json").write_text(json.dumps(manifest), encoding="utf-8")

            with patch("datalens_dev_mcp.mcp.tools.pipeline.run_project_live_apply") as run_apply:
                changed = dl_run_project_live_apply(
                    str(root),
                    workflow_name="retire_legacy",
                    execute_now=True,
                    action="retire_legacy_objects",
                    delivery_intent_text="delete chart:chart_legacy_2",
                    confirm_delete=True,
                )

        self.assertEqual(changed["status"], "delete_confirmation_required")
        self.assertNotEqual(changed["delete_plan_hash"], first["delete_plan_hash"])
        self.assertFalse(changed["confirmation"]["same_plan"])
        run_apply.assert_not_called()

    def test_public_write_schemas_use_plan_path_write_manifest_and_confirm_delete(self):
        from datalens_dev_mcp.server import list_tools

        listed = {tool["name"]: tool for tool in list_tools()}
        forbidden = {"approved", "approval_source", "approved_plan_path"}
        for tool_name, tool in listed.items():
            properties = set(tool["inputSchema"].get("properties") or {})
            self.assertTrue(forbidden.isdisjoint(properties), tool_name)
            if "confirm_delete" in properties:
                self.assertEqual(tool_name, "dl_run_project_live_apply")
            if "write_manifest" in properties:
                self.assertEqual(tool_name, "dl_plan_project_manifest")

        self.assertIn("plan_path", listed["dl_execute_safe_apply"]["inputSchema"]["properties"])
        self.assertIn("confirm_delete", listed["dl_run_project_live_apply"]["inputSchema"]["properties"])
        self.assertIn("write_manifest", listed["dl_plan_project_manifest"]["inputSchema"]["properties"])

    @staticmethod
    def _write_retire_project(root: Path) -> dict:
        (root / "scripts").mkdir()
        (root / "reports").mkdir()
        (root / "artifacts" / "retire").mkdir(parents=True)
        (root / "artifacts" / "retire" / "relation_graph.json").write_text(
            json.dumps({"objects": ["chart_legacy_1"], "references": []}),
            encoding="utf-8",
        )
        (root / "artifacts" / "retire" / "dry_run_plan.json").write_text(
            json.dumps({"dry_run": True, "objects": ["chart_legacy_1"]}),
            encoding="utf-8",
        )
        (root / "artifacts" / "retire" / "request.json").write_text(
            json.dumps({"user_request_quote": "delete chart:chart_legacy_1"}),
            encoding="utf-8",
        )
        (root / "reports" / "retire_summary.json").write_text(
            json.dumps({"workbook_id": "workbook_1", "changed_object_counts": {"retired_objects": 1}}),
            encoding="utf-8",
        )
        (root / "scripts" / "retire.py").write_text("raise SystemExit('patched in contract test')\n", encoding="utf-8")
        retire_spec = {
            "lifecycle_state": "approved",
            "command": [sys.executable, "scripts/retire.py", "deleteEditorChart"],
            "summary_path": "reports/retire_summary.json",
            "workbook_id": "workbook_1",
            "objects": [{"type": "editor_chart", "id": "chart_legacy_1"}],
            "reason": "The exact legacy chart was replaced.",
            "user_request_quote": "delete chart:chart_legacy_1",
            "relation_graph_proof_path": "artifacts/retire/relation_graph.json",
            "saved_no_reference_proof_path": "artifacts/retire/saved_no_reference.json",
            "published_no_reference_proof_path": "artifacts/retire/published_no_reference.json",
            "dry_run_retire_plan_path": "artifacts/retire/dry_run_plan.json",
            "approval_provenance_path": "artifacts/retire/request.json",
            "execution_summary_path": "reports/retire_summary.json",
            "post_retire_readback_paths": ["artifacts/retire/post_retire_readback.json"],
        }
        manifest = {
            "schema_version": "2026-07-15.project_live_workflow_manifest.v5",
            "project_name": "delete_contract",
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
        return manifest


if __name__ == "__main__":
    unittest.main()
