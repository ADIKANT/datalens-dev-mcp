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


class SafeApplyExecuteAutoPublishFromSavedReadbackTests(unittest.TestCase):
    def test_execute_safe_apply_continues_to_publish_from_saved_readback(self):
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
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
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
            plan["target_lock"] = create_target_lock("fix chart", target_chart_id="chart_publish").to_dict()
            for action in plan["actions"]:
                action["target_lock_hash"] = plan["target_lock"]["lock_hash"]
            plan_path = root / "artifacts" / "safe_apply_plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            client = SavePublishClient()

            def execute_with_client(plan_arg, *, config):
                return real_execute(plan_arg, config=DataLensConfig(write_enabled=config.write_enabled), client=client)

            with patch("datalens_dev_mcp.mcp.tools.pipeline.execute_safe_apply", side_effect=execute_with_client):
                result = dl_execute_safe_apply(tmp, delivery_intent_text="fix this chart")
            saved_path = root / "artifacts" / "readback" / "chart.saved.latest.json"
            published_path = root / "artifacts" / "readback" / "chart.published.latest.json"
            saved_readback_exists = saved_path.is_file()
            published_readback_exists = published_path.is_file()

        self.assertTrue(result["executed"], result)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["delivery_result"]["saved"]["passed"])
        self.assertTrue(result["delivery_result"]["published"]["passed"])
        self.assertTrue(
            result["publish_results"][0]["result"]["actions"][0]["readback_verification"][
                "publish_source_revision_matched"
            ]
        )
        self.assertFalse(
            result["publish_results"][0]["result"]["actions"][0]["readback_verification"][
                "revision_advanced"
            ]
        )
        self.assertEqual(len(result["saved_readback_paths"]), 1)
        self.assertEqual(len(result["published_readback_paths"]), 1)
        self.assertTrue(result["delivery_intent_decision"]["saved_readback_path"])
        self.assertTrue(result["delivery_intent_decision"]["published_readback_path"])
        self.assertIn("save_readback", result["proof_levels"])
        self.assertIn("publish_readback", result["proof_levels"])
        self.assertTrue(saved_readback_exists)
        self.assertTrue(published_readback_exists)
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


if __name__ == "__main__":
    unittest.main()
