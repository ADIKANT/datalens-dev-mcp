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

    def test_two_objects_are_preflighted_then_published_as_one_group(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.mcp.tools.pipeline import dl_execute_safe_apply
        from datalens_dev_mcp.pipeline.safe_apply import (
            create_safe_apply_plan,
            execute_safe_apply as real_execute,
        )
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        class GroupedClient:
            def __init__(self):
                self.calls = []
                self.saved = set()

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                object_id = payload.get("chartId") or (payload.get("entry") or {}).get("entryId")
                if method == "getEditorChart":
                    branch = payload.get("branch")
                    return self._chart(
                        object_id,
                        "rev_saved" if object_id in self.saved else "rev_0",
                        saved_id="saved_snapshot" if branch == "saved" and object_id in self.saved else "",
                    )
                if method == "updateEditorChart":
                    if payload.get("mode") == "save":
                        self.saved.add(object_id)
                        return self._chart(object_id, "rev_saved", saved_id="saved_snapshot")
                    if payload.get("mode") == "publish":
                        return self._chart(object_id, "rev_saved", saved_id="")
                raise AssertionError(f"unexpected rpc call {method} {payload}")

            @staticmethod
            def _chart(object_id, rev_id, *, saved_id):
                entry = {
                    "entryId": object_id,
                    "scope": "editor_chart",
                    "displayKey": object_id,
                    "revId": rev_id,
                    "data": {"title": object_id},
                }
                if saved_id:
                    entry["savedId"] = saved_id
                return {"chart": {"entry": entry}}

        object_ids = ["editor_one", "editor_two"]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, WRITE_ENV, clear=False):
            root = Path(tmp)
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                user_request_text="fix both existing editors",
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": object_id, "revId": "rev_0"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": object_id, "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": object_id, "branch": "saved"},
                    }
                    for object_id in object_ids
                ],
            )
            plan["target_lock"] = create_target_lock(
                "fix both existing editors",
                target_workbook_id="workbook_synthetic",
                target_objects=[
                    {"method": "updateEditorChart", "object_id": object_id}
                    for object_id in object_ids
                ],
            ).to_dict()
            for action in plan["actions"]:
                action["target_lock_hash"] = plan["target_lock"]["lock_hash"]
            plan_path = root / "artifacts" / "safe_apply_plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            client = GroupedClient()

            def execute_with_client(plan_arg, *, config):
                return real_execute(
                    plan_arg,
                    config=DataLensConfig(write_enabled=config.write_enabled),
                    client=client,
                )

            with patch(
                "datalens_dev_mcp.mcp.tools.pipeline.execute_safe_apply",
                side_effect=execute_with_client,
            ):
                result = dl_execute_safe_apply(
                    tmp,
                    delivery_intent_text="fix both existing editors",
                )

        self.assertTrue(result["executed"], result)
        self.assertEqual(len(result["publish_results"]), 1)
        grouped_plan = result["publish_results"][0]["plan"]
        self.assertEqual(grouped_plan["status"], "grouped_publish_plan_created")
        self.assertEqual(grouped_plan["object_count"], 2)
        self.assertTrue(grouped_plan["grouped_preflight"]["ok"], grouped_plan)
        modes = [payload.get("mode") for _method, payload in client.calls]
        first_publish = modes.index("publish")
        self.assertEqual(modes[:first_publish].count("save"), 2)
        self.assertEqual(modes[first_publish:].count("publish"), 2)
        self.assertLessEqual(len(client.calls), 12)
        self.assertFalse(
            {"getWorkbookEntries", "snapshotDashboard"}
            & {method for method, _payload in client.calls}
        )
        self.assertEqual(len(result["saved_readback_paths"]), 2)
        self.assertEqual(len(result["published_readback_paths"]), 2)

    def test_invalid_second_saved_artifact_blocks_every_publish_rpc(self):
        from datalens_dev_mcp.mcp.tools.pipeline import _execute_publish_after_save
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan
        from datalens_dev_mcp.pipeline.target_lock import create_target_lock

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid_path = root / "first.saved.json"
            invalid_path = root / "second.saved.json"
            valid_path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "chart": {
                            "entry": {
                                "entryId": "editor_one",
                                "revId": "rev_saved",
                                "savedId": "saved_one",
                                "data": {"title": "Editor one"},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            invalid_path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "chart": {
                            "entry": {
                                "entryId": "editor_two",
                                "data": {"title": "Editor two"},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                user_request_text="fix both existing editors",
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": object_id, "revId": "rev_0"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": object_id, "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": object_id, "branch": "saved"},
                    }
                    for object_id in ("editor_one", "editor_two")
                ],
            )
            plan["target_lock"] = create_target_lock(
                "fix both existing editors",
                target_workbook_id="workbook_synthetic",
                target_objects=[
                    {"method": "updateEditorChart", "object_id": "editor_one"},
                    {"method": "updateEditorChart", "object_id": "editor_two"},
                ],
            ).to_dict()
            saved_items = {
                "items": [
                    {
                        "target": "chart_editor_one",
                        "object_type": "editor_chart",
                        "object_id": "editor_one",
                        "path": str(valid_path),
                        "readback_mode": "minimal",
                    },
                    {
                        "target": "chart_editor_two",
                        "object_type": "editor_chart",
                        "object_id": "editor_two",
                        "path": str(invalid_path),
                        "readback_mode": "minimal",
                    },
                ],
                "errors": [],
            }
            with (
                patch(
                    "datalens_dev_mcp.mcp.tools.pipeline._persist_result_readbacks",
                    return_value=saved_items,
                ),
                patch(
                    "datalens_dev_mcp.mcp.tools.pipeline.execute_safe_apply"
                ) as execute_mock,
            ):
                result = _execute_publish_after_save(
                    root=root,
                    plan=plan,
                    save_result={"status": "completed", "executed": True},
                    config=object(),
                    delivery_intent_text="fix both existing editors",
                    plan_path=root / "artifacts" / "safe_apply_plan.json",
                )

        execute_mock.assert_not_called()
        self.assertEqual(result["publish_stage_status"], "blocked")
        self.assertTrue(
            any("missing" in reason for reason in result["publish_blocked_reasons"]),
            result,
        )


if __name__ == "__main__":
    unittest.main()
