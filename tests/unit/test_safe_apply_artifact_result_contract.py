import json
import tempfile
import unittest
from pathlib import Path


class SafeApplyArtifactResultContractTests(unittest.TestCase):
    def test_load_safe_apply_stage_value_accepts_inline_result(self):
        from datalens_dev_mcp.pipeline.safe_apply import load_safe_apply_stage_value

        action_result = {"inline_results": {"write_result": {"entry": {"entryId": "chart_inline", "revId": "rev_1"}}}}
        loaded = load_safe_apply_stage_value(action_result, "write_result")

        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["source"], "inline")
        self.assertEqual(loaded["value"]["entry"]["entryId"], "chart_inline")

    def test_load_safe_apply_stage_value_accepts_artifact_result(self):
        from datalens_dev_mcp.mcp.response_projection import serialized_metadata, stable_json_text
        from datalens_dev_mcp.pipeline.safe_apply import load_safe_apply_stage_value

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value = {"entry": {"entryId": "chart_artifact", "revId": "rev_2"}}
            metadata = serialized_metadata(value)
            artifact_path = root / "artifacts" / "safe_apply" / "write_result.json"
            artifact_path.parent.mkdir(parents=True)
            artifact_path.write_text(stable_json_text(value) + "\n", encoding="utf-8")
            action_result = {"artifacts": {"write_result": {"path": str(artifact_path), **metadata}}}

            loaded = load_safe_apply_stage_value(action_result, "write_result", project_root=root)

        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["source"], "artifact")
        self.assertEqual(loaded["value"]["entry"]["entryId"], "chart_artifact")

    def test_execute_result_exposes_uniform_result_contract(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply, load_safe_apply_stage_value

        class FakeClient:
            def rpc(self, method, payload):
                object_id = payload.get("chartId") or (payload.get("entry") or {}).get("entryId")
                return {"entry": {"entryId": object_id, "revId": "rev_1", "savedId": "saved_1"}}

        with tempfile.TemporaryDirectory() as tmp:
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": "chart_1", "revId": "rev_1"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_1", "branch": "saved"},
                    }
                ],
            )
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=FakeClient())
            loaded = load_safe_apply_stage_value(result["actions"][0], "write_result", project_root=tmp)

        self.assertEqual(result["result_contract"]["downstream_reader"], "load_safe_apply_stage_value")
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["source"], "artifact")
        self.assertNotIn("write_result", result["actions"][0])


if __name__ == "__main__":
    unittest.main()
