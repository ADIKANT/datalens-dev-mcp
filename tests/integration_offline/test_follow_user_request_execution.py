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


class SavePublishClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.saved = False

    def rpc(self, method, payload):
        self.calls.append((method, payload))
        if method == "getEditorChart" and payload.get("branch") == "saved":
            return self._chart("rev_saved" if self.saved else "rev_0", saved_id="saved_1" if self.saved else "")
        if method == "updateEditorChart" and payload.get("mode") == "save":
            self.saved = True
            return self._chart("rev_saved", saved_id="saved_1")
        if method == "updateEditorChart" and payload.get("mode") == "publish":
            return self._chart("rev_published", saved_id="")
        if method == "getEditorChart" and payload.get("branch") == "published":
            return self._chart("rev_published", saved_id="")
        raise AssertionError(f"unexpected RPC: {method} {payload}")

    @staticmethod
    def _chart(rev_id: str, *, saved_id: str) -> dict:
        entry = {
            "entryId": "chart_follow_request",
            "scope": "editor_chart",
            "displayKey": "Follow request",
            "revId": rev_id,
            "data": {"title": "Follow request"},
        }
        if saved_id:
            entry["savedId"] = saved_id
        return {"chart": {"entry": entry}}


class FollowUserRequestExecutionTests(unittest.TestCase):
    def _write_plan(self, root: Path, *, approved: bool, request_text: str = "") -> None:
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        plan = create_safe_apply_plan(
            project_root=str(root),
            approved=approved,
            user_request_text=request_text,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {
                        "mode": "save",
                        "entry": {"entryId": "chart_follow_request", "revId": "rev_0"},
                    },
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_follow_request", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_follow_request", "branch": "saved"},
                }
            ],
        )
        plan["target_lock"] = create_target_lock(
            request_text or "fix chart",
            target_chart_id="chart_follow_request",
        ).to_dict()
        plan_path = root / "artifacts" / "safe_apply_plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

    def _execute(self, root: Path, client: SavePublishClient, delivery_intent_text: str | None = None) -> dict:
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.mcp.tools.pipeline import dl_execute_safe_apply
        from datalens_dev_mcp.pipeline.safe_apply import execute_safe_apply as real_execute

        def execute_with_client(plan_arg, *, config):
            effective_config = DataLensConfig(
                write_enabled=config.write_enabled,
                save_enabled=config.save_enabled,
                publish_enabled=config.publish_enabled,
            )
            return real_execute(plan_arg, config=effective_config, client=client)

        kwargs = {} if delivery_intent_text is None else {"delivery_intent_text": delivery_intent_text}
        with patch("datalens_dev_mcp.mcp.tools.pipeline.execute_safe_apply", side_effect=execute_with_client):
            return dl_execute_safe_apply(str(root), **kwargs)

    def test_implementation_request_authorizes_save_and_publish_without_approval_input(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=True):
            root = Path(tmp)
            self._write_plan(root, approved=False)
            client = SavePublishClient()

            result = self._execute(root, client, "fix this chart")

        self.assertTrue(result["executed"], result)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["delivery_result"]["saved"]["passed"])
        self.assertTrue(result["delivery_result"]["published"]["passed"])
        self.assertEqual(
            [(method, payload.get("mode")) for method, payload in client.calls if method == "updateEditorChart"],
            [("updateEditorChart", "save"), ("updateEditorChart", "publish")],
        )

    def test_save_only_request_stops_after_saved_readback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=True):
            root = Path(tmp)
            self._write_plan(root, approved=False)
            client = SavePublishClient()

            result = self._execute(root, client, "fix this chart, save only")

        self.assertTrue(result["executed"], result)
        self.assertEqual(result["delivery_intent_decision"]["state"], "save_only")
        self.assertTrue(result["delivery_result"]["saved"]["passed"])
        self.assertFalse(result["delivery_result"]["published"]["passed"])
        self.assertEqual(
            [(method, payload.get("mode")) for method, payload in client.calls if method == "updateEditorChart"],
            [("updateEditorChart", "save")],
        )

    def test_explicit_plan_and_review_override_previously_authorized_plan(self):
        cases = (("plan only", "plan_only"), ("review this chart", "read_only"))
        for request_text, expected_state in cases:
            with self.subTest(request_text=request_text), tempfile.TemporaryDirectory() as tmp, patch.dict(
                os.environ,
                WRITE_ENV,
                clear=True,
            ):
                root = Path(tmp)
                self._write_plan(root, approved=True, request_text="fix this chart")
                client = SavePublishClient()

                result = self._execute(root, client, request_text)

                self.assertFalse(result["executed"], result)
                self.assertEqual(result["delivery_intent_decision"]["state"], expected_state)
                self.assertEqual(client.calls, [])

    def test_execution_without_new_text_inherits_implementation_intent_from_plan(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=True):
            root = Path(tmp)
            self._write_plan(root, approved=True, request_text="fix this chart")
            client = SavePublishClient()

            result = self._execute(root, client)

        self.assertTrue(result["executed"], result)
        self.assertEqual(result["delivery_intent_decision"]["state"], "save_then_publish")
        self.assertTrue(result["delivery_result"]["published"]["passed"])
        self.assertEqual(
            [(method, payload.get("mode")) for method, payload in client.calls if method == "updateEditorChart"],
            [("updateEditorChart", "save"), ("updateEditorChart", "publish")],
        )

    def test_publish_kill_switch_preserves_save_and_reports_saved_not_published(self):
        env = {**WRITE_ENV, "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "0"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
            root = Path(tmp)
            self._write_plan(root, approved=False)
            client = SavePublishClient()

            result = self._execute(root, client, "fix this chart")

        self.assertTrue(result["executed"], result)
        self.assertEqual(result["status"], "saved_not_published")
        self.assertEqual(result["publish_blocked_reasons"], ["publish_enabled"])
        self.assertTrue(result["delivery_result"]["saved"]["passed"])
        self.assertFalse(result["delivery_result"]["published"]["passed"])
        self.assertEqual(
            [(method, payload.get("mode")) for method, payload in client.calls if method == "updateEditorChart"],
            [("updateEditorChart", "save")],
        )


if __name__ == "__main__":
    unittest.main()
