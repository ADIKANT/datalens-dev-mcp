import json
import tempfile
import unittest
from pathlib import Path


def saved_editor_chart_readback() -> dict:
    return {
        "branch": "saved",
        "chart": {
            "entry": {
                "entryId": "chart_publish",
                "scope": "editor_chart",
                "displayKey": "Publish me",
                "revId": "rev_saved",
                "savedId": "saved_snapshot",
                "data": {
                    "title": "Publish me",
                    "sources": [{"id": "source_1", "query": "select 1"}],
                    "javascript": "module.exports = {render: () => null};",
                    "css": ".root { color: #111; }",
                },
            }
        },
    }


class SafeApplySavePublishTraceTests(unittest.TestCase):
    def test_publish_from_saved_trace_preserves_saved_then_published_readback(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import (
            create_publish_safe_apply_plan,
            execute_safe_apply,
            load_safe_apply_stage_value,
            validate_safe_apply_plan,
        )

        class PublishClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                entry = json.loads(json.dumps(saved_editor_chart_readback()["chart"]["entry"]))
                return {"entry": entry}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved_path = root / "artifacts" / "readback" / "chart.saved.latest.json"
            saved_path.parent.mkdir(parents=True)
            saved_path.write_text(json.dumps(saved_editor_chart_readback()), encoding="utf-8")

            plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="chart",
                object_type="editor_chart",
                object_id="chart_publish",
                saved_readback_path=str(saved_path),
                approved=True,
            )
            validation = validate_safe_apply_plan(plan)
            client = PublishClient()
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)
            published_stage = load_safe_apply_stage_value(result["actions"][0], "readback", project_root=tmp)

        self.assertTrue(plan["ok"])
        self.assertTrue(validation.ok, validation.issues)
        self.assertTrue(result["executed"])
        self.assertEqual(
            [(method, payload.get("branch")) for method, payload in client.calls],
            [("getEditorChart", "saved"), ("updateEditorChart", None), ("getEditorChart", "published")],
        )
        self.assertEqual(plan["publish_source"]["branch"], "saved")
        self.assertEqual(plan["actions"][0]["readback_payload"]["branch"], "published")
        self.assertTrue(published_stage["ok"])
        self.assertEqual(published_stage["value"]["entry"]["revId"], "rev_saved")
        self.assertTrue(result["actions"][0]["readback_verification"]["publish_source_revision_matched"])
        self.assertFalse(result["actions"][0]["readback_verification"]["revision_advanced"])

    def test_stale_saved_revision_blocks_publish_before_write(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan, execute_safe_apply

        class StaleClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "getEditorChart":
                    return {"entry": {"entryId": "chart_publish", "revId": "rev_new", "savedId": "saved_snapshot"}}
                raise AssertionError("publish write must not be attempted")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            saved_path = root / "artifacts" / "readback" / "chart.saved.latest.json"
            saved_path.parent.mkdir(parents=True)
            saved_path.write_text(json.dumps(saved_editor_chart_readback()), encoding="utf-8")
            plan = create_publish_safe_apply_plan(
                project_root=tmp,
                target="chart",
                object_type="editor_chart",
                object_id="chart_publish",
                saved_readback_path=str(saved_path),
                approved=True,
            )
            client = StaleClient()
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)

        self.assertFalse(result["executed"])
        self.assertEqual(result["actions"][0]["error"]["category"], "stale_revision")
        self.assertFalse(result["actions"][0]["write_attempted"])
        self.assertEqual([method for method, _payload in client.calls], ["getEditorChart"])


if __name__ == "__main__":
    unittest.main()
