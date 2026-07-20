import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


WRITE_ENV = {
    "DATALENS_ENV_FILE": "",
    "DATALENS_MCP_ENABLE_WRITES": "1",
    "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
}


class DeliveryIntentToolWiringTests(unittest.TestCase):
    def test_safe_apply_plan_uses_delivery_intent_policy_for_fix_with_known_target(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=False):
            root = Path(tmp)
            payload_path = root / "artifacts" / "payloads" / "chart.payload.json"
            payload_path.parent.mkdir(parents=True)
            payload_path.write_text(
                json.dumps({"entry": {"name": "chart_1", "data": {"name": "chart_1", "title": "Chart"}}}),
                encoding="utf-8",
            )
            (root / "artifacts" / "payload_plan.json").write_text(
                json.dumps(
                    {
                        "workbook_id": "workbook_live_1",
                        "payloads": [{"widget_id": "chart_1", "method": "createEditorChart", "payload_path": str(payload_path)}],
                    }
                ),
                encoding="utf-8",
            )

            plan = dl_create_safe_apply_plan(str(root), delivery_intent_text="fix this chart")

        decision = plan["delivery_intent_decision"]
        self.assertEqual(decision["intent"], "save_and_publish_delivery")
        self.assertEqual(decision["state"], "save_then_publish")
        self.assertTrue(decision["publish_expected"])
        self.assertEqual(decision["target_branch"], "published")
        self.assertIn("Create publish-from-saved plan.", decision["next_actions"])
        for key in ("state", "reason", "required_gates", "satisfied_gates", "next_action", "proof_path"):
            self.assertIn(key, decision)

    def test_execute_safe_apply_chains_save_readback_publish_and_published_readback(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.mcp.tools.pipeline import dl_execute_safe_apply
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply as real_execute
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        class SavePublishClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "getEditorChart" and payload.get("branch") == "saved":
                    return self._chart("rev_0" if len(self.calls) == 1 else "rev_saved", saved_id="saved_snapshot")
                if method == "getEditorChart" and payload.get("branch") == "published":
                    return self._chart("rev_saved", saved_id="")
                if method == "updateEditorChart" and payload.get("mode") == "save":
                    return self._chart("rev_saved", saved_id="saved_snapshot")
                if method == "updateEditorChart" and payload.get("mode") == "publish":
                    return self._chart("rev_saved", saved_id="")
                raise AssertionError(f"unexpected rpc call {method} {payload}")

            @staticmethod
            def _chart(rev_id, *, saved_id):
                entry = {
                    "entryId": "chart_publish",
                    "scope": "editor_chart",
                    "displayKey": "Publish me",
                    "revId": rev_id,
                    "data": {"title": "Publish me"},
                }
                if saved_id:
                    entry["savedId"] = saved_id
                return {"chart": {"entry": entry}}

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=False):
            root = Path(tmp)
            target_lock = create_target_lock("fix chart", target_chart_id="chart_publish").to_dict()
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=False,
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": "chart_publish", "revId": "rev_0"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_publish", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_publish", "branch": "saved"},
                    }
                ],
            )
            plan["target_lock"] = target_lock
            for action in plan["actions"]:
                action["target_lock_hash"] = target_lock["lock_hash"]
            plan_path = root / "artifacts" / "safe_apply_plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            client = SavePublishClient()

            def execute_with_client(plan_arg, *, config):
                return real_execute(plan_arg, config=DataLensConfig(write_enabled=config.write_enabled), client=client)

            with patch("datalens_dev_mcp.mcp.tools.pipeline.execute_safe_apply", side_effect=execute_with_client):
                result = dl_execute_safe_apply(tmp, delivery_intent_text="fix this chart")
            saved_readback_exists = (root / "artifacts" / "readback" / "chart.saved.latest.json").is_file()
            published_readback_exists = (root / "artifacts" / "readback" / "chart.published.latest.json").is_file()

        self.assertTrue(result["executed"], result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["delivery_intent_decision"]["state"], "save_then_publish")
        self.assertEqual(result["delivery_intent_decision"]["save_stage_status"], "completed")
        self.assertEqual(result["delivery_intent_decision"]["publish_stage_status"], "completed")
        self.assertEqual(result["delivery_result"]["publish_blocked_reasons"], [])
        self.assertTrue(result["delivery_result"]["saved"]["passed"])
        self.assertTrue(result["delivery_result"]["published"]["passed"])
        self.assertIn("save_readback", result["proof_levels"])
        self.assertIn("publish_readback", result["proof_levels"])
        self.assertEqual(
            [(method, payload.get("branch"), payload.get("mode")) for method, payload in client.calls],
            [
                ("getEditorChart", "saved", None),
                ("updateEditorChart", None, "save"),
                ("getEditorChart", "saved", None),
                ("getEditorChart", "saved", None),
                ("updateEditorChart", None, "publish"),
                ("getEditorChart", "published", None),
            ],
        )
        self.assertTrue(saved_readback_exists)
        self.assertTrue(published_readback_exists)

    def test_review_and_draft_do_not_publish_even_when_write_flags_are_on(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_build_payload_plan, dl_create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=False):
            root = Path(tmp)
            review_plan = dl_build_payload_plan(
                str(root),
                workbook_id="workbook_live_1",
                delivery_intent_text="audit the dashboard",
            )
            payload_path = root / "artifacts" / "payloads" / "chart.payload.json"
            payload_path.parent.mkdir(parents=True, exist_ok=True)
            payload_path.write_text(
                json.dumps({"entry": {"name": "chart_1", "data": {"name": "chart_1", "title": "Chart"}}}),
                encoding="utf-8",
            )
            (root / "artifacts" / "payload_plan.json").write_text(
                json.dumps(
                    {
                        "workbook_id": "workbook_live_1",
                        "payloads": [{"widget_id": "chart_1", "method": "createEditorChart", "payload_path": str(payload_path)}],
                    }
                ),
                encoding="utf-8",
            )
            draft_plan = dl_create_safe_apply_plan(str(root), delivery_intent_text="fix this chart, save only")

        self.assertEqual(review_plan["delivery_intent_decision"]["intent"], "read_only_review")
        self.assertEqual(review_plan["delivery_intent_decision"]["state"], "read_only")
        self.assertFalse(review_plan["delivery_intent_decision"]["publish_expected"])
        self.assertEqual(draft_plan["delivery_intent_decision"]["intent"], "save_only_draft")
        self.assertEqual(draft_plan["delivery_intent_decision"]["state"], "save_only")
        self.assertFalse(draft_plan["delivery_intent_decision"]["publish_expected"])
        self.assertNotIn(
            "approv",
            json.dumps(draft_plan.get("suggested_records") or [], ensure_ascii=False).lower(),
        )

    def test_publish_plan_requires_saved_readback_but_still_reports_delivery_decision(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_publish_from_saved_plan

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=False):
            root = Path(tmp)
            published_path = root / "artifacts" / "readback" / "dashboard.published.latest.json"
            published_path.parent.mkdir(parents=True)
            published_path.write_text(
                json.dumps(
                    {
                        "branch": "published",
                        "dashboard": {"entry": {"entryId": "dash_1", "revId": "rev_pub", "savedId": "saved_1"}},
                    }
                ),
                encoding="utf-8",
            )

            plan = dl_create_publish_from_saved_plan(
                str(root),
                target="dashboard",
                object_type="dashboard",
                saved_readback_path=str(published_path),
                delivery_intent_text="implement the dashboard fix",
            )

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "publish_blocked")
        self.assertEqual(plan["delivery_intent_decision"]["state"], "blocked")
        self.assertIn("saved_readback_fresh", plan["delivery_intent_decision"]["blocked_reasons"])
        self.assertTrue(plan["delivery_intent_decision"]["publish_expected"])

    def test_object_update_planner_reports_delivery_intent(self):
        from datalens_dev_mcp.mcp.tools.object_lifecycle import dl_plan_object_update

        payload = {
            "entryId": "dash_1",
            "revId": "rev_1",
            "data": {"tabs": [], "settings": {}},
            "meta": {},
        }
        with patch.dict(os.environ, WRITE_ENV, clear=False):
            plan = dl_plan_object_update(
                "dashboard",
                payload,
                source_adapter="canonical_object_payload",
                delivery_intent_text="enhance this dashboard",
            )

        self.assertTrue(plan["ok"], plan)
        decision = plan["delivery_intent_decision"]
        self.assertEqual(decision["state"], "save_then_publish")
        self.assertTrue(decision["publish_expected"])


if __name__ == "__main__":
    unittest.main()
