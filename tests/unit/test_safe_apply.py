import json
import tempfile
import unittest
from pathlib import Path


class SafeApplyTests(unittest.TestCase):
    def full_editor_data(self):
        return {
            "meta": "{}",
            "params": "{}",
            "sources": "[]",
            "controls": "{}",
            "prepare": "module.exports = {}",
        }

    def test_plan_requires_approval_and_write_enablement(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        plan = create_safe_apply_plan(
            project_root="/tmp/synthetic-project",
            actions=[
                {
                    "action": "update_editor_chart",
                    "object_id": "entry_synthetic_001",
                    "method": "updateEditorChart",
                    "mode": "save",
                    "requires_fresh_read": True,
                }
            ],
        )

        self.assertFalse(plan["approved"])
        self.assertEqual(plan["default_mode"], "save")
        self.assertTrue(plan["read_only_default"])

        result = execute_safe_apply(
            plan,
            config=DataLensConfig(write_enabled=False, save_enabled=False, publish_enabled=False),
        )

        self.assertFalse(result["executed"])
        self.assertIn("write mode is disabled", result["blocked_reasons"][0])

    def test_rejects_destructive_publish_and_blind_write(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan

        plan = create_safe_apply_plan(
            project_root="/tmp/synthetic-project",
            actions=[
                {"action": "delete_dashboard", "method": "deleteDashboard", "object_id": "dash_synthetic_001"},
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "object_id": "entry_synthetic_001",
                    "mode": "publish",
                    "requires_fresh_read": False,
                },
            ],
            approved=True,
        )

        result = validate_safe_apply_plan(plan)

        self.assertFalse(result.ok)
        self.assertTrue(any("destructive" in issue.lower() for issue in result.issues))
        self.assertTrue(any("publish" in issue.lower() for issue in result.issues))
        self.assertTrue(any("fresh read" in issue.lower() for issue in result.issues))

    def test_guarded_execution_performs_fresh_read_write_and_readback(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class FakeClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                object_id = payload.get("chartId") or (payload.get("entry") or {}).get("entryId") or "chart_local"
                return {"method": method, "payload": payload, "entry": {"entryId": object_id, "revId": "rev_1"}}

        client = FakeClient()
        plan = create_safe_apply_plan(
            project_root="/tmp/local-project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {"mode": "save", "entry": {"entryId": "chart_local", "revId": "rev_1"}},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_local", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_local", "branch": "saved"},
                }
            ],
        )

        result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)

        self.assertTrue(result["executed"])
        self.assertEqual([call[0] for call in client.calls], ["getEditorChart", "updateEditorChart", "getEditorChart"])
        self.assertEqual(client.calls[1][1]["mode"], "save")
        self.assertNotIn("result", result["actions"][0])
        self.assertIn("write_result", result["actions"][0]["artifacts"])

    def test_expected_revision_requires_revision_in_fresh_read(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class MissingRevisionClient:
            def rpc(self, method, payload):
                if method == "getEditorChart":
                    return {"entry": {"entryId": "chart_local"}}
                raise AssertionError("write must not be attempted")

        plan = create_safe_apply_plan(
            project_root="/tmp/local-project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {"mode": "save", "entry": {"entryId": "chart_local", "revId": "rev_old"}},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_local", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_local", "branch": "saved"},
                }
            ],
        )

        result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=MissingRevisionClient())

        self.assertFalse(result["executed"])
        self.assertEqual(result["actions"][0]["error"]["category"], "missing_fresh_revision")
        self.assertFalse(result["actions"][0]["write_attempted"])

    def test_update_requires_non_empty_fresh_read_before_write(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class EmptyFreshClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if method == "getEditorChart":
                    return {}
                raise AssertionError("write must not be attempted after an empty fresh read")

        with tempfile.TemporaryDirectory() as tmp:
            client = EmptyFreshClient()
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": "chart_local", "revId": "rev_old"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_local", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_local", "branch": "saved"},
                    }
                ],
            )
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)

        self.assertFalse(result["executed"])
        self.assertEqual(result["actions"][0]["error"]["category"], "fresh_read_required")
        self.assertFalse(result["actions"][0]["write_attempted"])
        self.assertEqual([method for method, _payload in client.calls], ["getEditorChart"])

    def test_update_requires_matching_fresh_identity_and_target_lock(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import (
            create_safe_apply_plan,
            execute_safe_apply,
            validate_safe_apply_plan_exhaustive,
        )

        class MissingIdentityClient:
            def rpc(self, method, payload):
                if method == "getEditorChart":
                    return {"entry": {"revId": "rev_old"}}
                raise AssertionError("write must not be attempted without fresh identity")

        with tempfile.TemporaryDirectory() as tmp:
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": "chart_local", "revId": "rev_old"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_local", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_local", "branch": "saved"},
                    }
                ],
            )
            missing_identity = execute_safe_apply(
                plan,
                config=DataLensConfig(write_enabled=True),
                client=MissingIdentityClient(),
            )
            mismatched_lock = json.loads(json.dumps(plan))
            mismatched_lock["actions"][0]["target_lock_hash"] = "0" * 64
            lock_preflight = validate_safe_apply_plan_exhaustive(mismatched_lock)

        self.assertEqual(missing_identity["actions"][0]["error"]["category"], "missing_fresh_identity")
        self.assertFalse(missing_identity["actions"][0]["write_attempted"])
        self.assertFalse(lock_preflight["ok"])
        self.assertIn("target_lock_hash does not match", "\n".join(lock_preflight["issues"]))

    def test_post_write_readback_must_match_intended_content_and_advance_revision(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class StaleReadbackClient:
            def __init__(self, *, content_updated: bool):
                self.calls = []
                self.content_updated = content_updated

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if len(self.calls) == 1:
                    return {
                        "entry": {
                            "entryId": "chart_local",
                            "revId": "rev_old",
                            "data": {"title": "Old"},
                        }
                    }
                if method == "updateEditorChart":
                    return {"status": "saved"}
                return {
                    "entry": {
                        "entryId": "chart_local",
                        "revId": "rev_old",
                        "data": {"title": "New" if self.content_updated else "Old"},
                    }
                }

        def run(client):
            with tempfile.TemporaryDirectory() as tmp:
                plan = create_safe_apply_plan(
                    project_root=tmp,
                    approved=True,
                    actions=[
                        {
                            "action": "update_editor_chart",
                            "method": "updateEditorChart",
                            "payload": {
                                "mode": "save",
                                "entry": {
                                    "entryId": "chart_local",
                                    "revId": "rev_old",
                                    "data": {"title": "New"},
                                },
                            },
                            "fresh_read_method": "getEditorChart",
                            "fresh_read_payload": {"chartId": "chart_local", "branch": "saved"},
                            "readback_method": "getEditorChart",
                            "readback_payload": {"chartId": "chart_local", "branch": "saved"},
                        }
                    ],
                )
                return execute_safe_apply(
                    plan,
                    config=DataLensConfig(write_enabled=True),
                    client=client,
                )

        stale_content = run(StaleReadbackClient(content_updated=False))
        stale_revision = run(StaleReadbackClient(content_updated=True))

        self.assertEqual(stale_content["actions"][0]["error"]["category"], "readback_content_mismatch")
        self.assertEqual(stale_revision["actions"][0]["error"]["category"], "readback_revision_not_advanced")
        self.assertFalse(stale_content["actions"][0]["executed"])
        self.assertFalse(stale_revision["actions"][0]["executed"])
        self.assertFalse(stale_content["publish_allowed"])
        self.assertFalse(stale_revision["publish_allowed"])

    def test_post_write_readback_identity_mismatch_fails_action(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class MismatchReadbackClient:
            def __init__(self):
                self.calls = []

            def rpc(self, method, payload):
                self.calls.append((method, payload))
                if len(self.calls) == 1:
                    return {"entry": {"entryId": "chart_local", "revId": "rev_old"}}
                if len(self.calls) == 2:
                    return {"entry": {"entryId": "chart_local", "revId": "rev_new"}}
                return {"entry": {"entryId": "chart_WRONG", "revId": "rev_new"}}

        client = MismatchReadbackClient()
        plan = create_safe_apply_plan(
            project_root="/tmp/local-project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {"mode": "save", "entry": {"entryId": "chart_local", "revId": "rev_old"}},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_local", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_local", "branch": "saved"},
                }
            ],
        )

        result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=client)

        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["actions"][0]["error"]["category"], "readback_object_id_mismatch")
        self.assertTrue(result["actions"][0]["write_attempted"])

    def test_safe_apply_exception_message_uses_shared_redaction(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        secret = "Bearer " + "abcdefghijklmnop" + "qrstuvwxyz123456"

        class ExplodingClient:
            def rpc(self, method, payload):
                if method == "getEditorChart":
                    return {"entry": {"entryId": "chart_local", "revId": "rev_old"}}
                raise RuntimeError(f"write failed with {secret}")

        plan = create_safe_apply_plan(
            project_root="/tmp/local-project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {"mode": "save", "entry": {"entryId": "chart_local", "revId": "rev_old"}},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_local", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_local", "branch": "saved"},
                }
            ],
        )

        result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=ExplodingClient())
        message = result["actions"][0]["error"]["message"]

        self.assertFalse(result["executed"])
        self.assertIn("<redacted>", message)
        self.assertNotIn(secret, message)

    def test_compact_execution_persists_sanitized_envelopes_for_seven_editor_charts(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class LargeFakeClient:
            def __init__(self):
                self.saved_revisions = {}

            def rpc(self, method, payload):
                object_id = payload.get("chartId") or (payload.get("entry") or {}).get("entryId") or "chart_unknown"
                if method == "updateEditorChart":
                    self.saved_revisions[object_id] = f"rev_updateEditorChart_{object_id}"
                revision = self.saved_revisions.get(object_id, f"rev_getEditorChart_{object_id}")
                return {
                    "status": "ok",
                    "entry": {"entryId": object_id, "revId": revision, "savedId": "saved_1"},
                    "data": {"sources": [{"query": "select 1"}], "prepare": "prepare_payload_" * 500},
                    "Authorization": "Bearer fixtureTokenValue12345",
                }

        with tempfile.TemporaryDirectory() as tmp:
            actions = []
            for index in range(7):
                chart_id = f"chart_{index}"
                actions.append(
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": chart_id, "revId": f"rev_getEditorChart_{chart_id}"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": chart_id, "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": chart_id, "branch": "saved"},
                    }
                )
            plan = create_safe_apply_plan(project_root=tmp, approved=True, actions=actions)
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=LargeFakeClient())
            serialized = json.dumps(result, sort_keys=True)
            artifact_paths = [
                Path(action["artifacts"][key]["path"])
                for action in result["actions"]
                for key in ("pre_write", "write_result", "readback")
            ]
            artifact_files_exist = all(path.is_file() for path in artifact_paths)
            artifact_texts = [path.read_text(encoding="utf-8") for path in artifact_paths]

        self.assertTrue(result["executed"])
        self.assertEqual(len(result["actions"]), 7)
        self.assertNotIn("prepare_payload_", serialized)
        self.assertEqual(len(artifact_paths), 21)
        self.assertTrue(artifact_files_exist)
        self.assertTrue(all("<redacted>" in text for text in artifact_texts))
        self.assertTrue(all("Bearer fixtureTokenValue12345" not in text for text in artifact_texts))
        self.assertTrue(all(action["revisions"]["write"] for action in result["actions"]))

    def test_debug_readback_mode_has_hard_inline_cap(self):
        from datalens_dev_mcp.config import DataLensConfig
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

        class DebugFakeClient:
            def rpc(self, method, payload):
                object_id = payload.get("chartId") or (payload.get("entry") or {}).get("entryId") or "chart_debug"
                return {
                    "entry": {"entryId": object_id, "revId": "rev_debug", "savedId": "saved_debug"},
                    "data": {"prepare": "debug_payload_" * 1000},
                }

        with tempfile.TemporaryDirectory() as tmp:
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[
                    {
                        "action": "update_editor_chart",
                        "method": "updateEditorChart",
                        "payload": {"mode": "save", "entry": {"entryId": "chart_debug", "revId": "rev_debug"}},
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_debug", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_debug", "branch": "saved"},
                        "readback_mode": "debug",
                    }
                ],
            )
            result = execute_safe_apply(plan, config=DataLensConfig(write_enabled=True), client=DebugFakeClient())

        summary = result["actions"][0]["summaries"]["readback"]
        self.assertTrue(summary["debug_truncated"])
        self.assertLessEqual(len(summary["debug_excerpt"]), summary["debug_inline_char_cap"])

    def test_publish_from_published_branch_readback_fails(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifacts" / "readback" / "dashboard.published.latest.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "branch": "published",
                        "dashboard": {"entry": {"entryId": "dash_1", "revId": "rev_pub", "savedId": "saved_1"}},
                    }
                ),
                encoding="utf-8",
            )

            plan = create_publish_safe_apply_plan(
                project_root=str(root),
                target="dashboard",
                object_type="dashboard",
                saved_readback_path=str(path),
                approved=True,
            )

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "publish_blocked")
        self.assertIn("saved branch", plan["error"]["message"])

    def test_publish_plan_from_saved_readback_carries_revision_guard(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan, validate_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifacts" / "readback" / "dashboard.saved.latest.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "dashboard": {
                            "entry": {
                                "entryId": "dash_1",
                                "revId": "rev_saved",
                                "savedId": "saved_123",
                                "data": {"counter": 1, "salt": "s", "schemeVersion": 8, "tabs": [], "settings": {}},
                                "meta": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            plan = create_publish_safe_apply_plan(
                project_root=str(root),
                target="dashboard",
                object_type="dashboard",
                approved=True,
            )
            validation = validate_safe_apply_plan(plan)

        self.assertTrue(plan["ok"])
        self.assertTrue(validation.ok, validation.issues)
        action = plan["actions"][0]
        self.assertEqual(action["mode"], "save")
        self.assertEqual(action["payload"]["mode"], "publish")
        self.assertEqual(action["expected_saved_rev_id"], "rev_saved")
        self.assertEqual(action["expected_saved_id"], "saved_123")
        self.assertNotIn("savedId", action["payload"]["entry"])
        self.assertEqual(action["fresh_read_payload"]["branch"], "saved")
        self.assertEqual(action["readback_payload"]["branch"], "published")

    def test_publish_validation_matches_saved_readback_by_object_id(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifacts" / "readback" / "charts.saved.latest.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "charts": [
                            {
                                "entry": {
                                    "entryId": "chart_a",
                                    "revId": "rev_a",
                                    "savedId": "saved_a",
                                    "type": "advanced-chart_node",
                                    "data": self.full_editor_data(),
                                    "meta": {},
                                }
                            },
                            {
                                "entry": {
                                    "entryId": "chart_b",
                                    "revId": "rev_b",
                                    "savedId": "saved_b",
                                    "type": "advanced-chart_node",
                                    "data": self.full_editor_data(),
                                    "meta": {},
                                }
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            plan = create_safe_apply_plan(
                project_root=str(root),
                approved=True,
                actions=[
                    {
                        "action": "publish_object",
                        "method": "updateEditorChart",
                        "mode": "save",
                        "publish": True,
                        "source_branch": "saved",
                        "saved_readback_path": str(path),
                        "expected_saved_rev_id": "rev_b",
                        "expected_saved_id": "saved_b",
                        "requires_fresh_read": True,
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_b", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_b", "branch": "published"},
                        "payload": {
                            "mode": "publish",
                            "entry": {"entryId": "chart_b", "revId": "rev_b", "savedId": "saved_b"},
                        },
                    }
                ],
            )
            valid = validate_safe_apply_plan(plan).ok
            plan["actions"][0]["payload"]["entry"]["entryId"] = "chart_missing"
            invalid = validate_safe_apply_plan(plan).ok

        self.assertTrue(valid)
        self.assertFalse(invalid)

    def test_publish_plan_requires_full_saved_entry_not_revision_summary(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_publish_safe_apply_plan, validate_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifacts" / "readback" / "chart.saved.latest.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "branch": "saved",
                        "chart": {"entry": {"entryId": "chart_1", "revId": "rev_saved", "savedId": "saved_1"}},
                    }
                ),
                encoding="utf-8",
            )

            plan = create_publish_safe_apply_plan(
                project_root=str(root),
                target="chart",
                object_type="editor_chart",
                object_id="chart_1",
                saved_readback_path=str(path),
                approved=True,
            )

            manual_plan = {
                "approved": True,
                "project_root": str(root),
                "actions": [
                    {
                        "action": "publish_object",
                        "method": "updateEditorChart",
                        "mode": "save",
                        "publish": True,
                        "source_branch": "saved",
                        "saved_readback_path": str(path),
                        "expected_saved_rev_id": "rev_saved",
                        "expected_saved_id": "saved_1",
                        "requires_fresh_read": True,
                        "fresh_read_method": "getEditorChart",
                        "fresh_read_payload": {"chartId": "chart_1", "branch": "saved"},
                        "readback_method": "getEditorChart",
                        "readback_payload": {"chartId": "chart_1", "branch": "published"},
                        "readback_required": True,
                        "payload": {"mode": "publish", "entry": {"entryId": "chart_1", "revId": "rev_saved"}},
                    }
                ],
            }
            validation = validate_safe_apply_plan(manual_plan)

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["error"]["category"], "incomplete_saved_entry")
        self.assertFalse(validation.ok)
        self.assertTrue(any("full saved entry.data" in issue for issue in validation.issues))

    def test_plan_only_validator_catches_dashboard_preflight_and_unsafe_names(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan_exhaustive

        with tempfile.TemporaryDirectory() as tmp:
            plan = create_safe_apply_plan(
                project_root=tmp,
                approved=True,
                actions=[
                    {
                        "action": "update_dashboard",
                        "method": "updateDashboard",
                        "payload": {
                            "mode": "save",
                            "entry": {"entryId": "dash_1", "name": "Unsafe Name"},
                            "blocks": [{"id": "block_1", "tabs": [{"id": "a"}, {"id": "b"}]}],
                        },
                        "fresh_read_method": "getDashboard",
                        "fresh_read_payload": {"dashboardId": "dash_1", "branch": "saved"},
                        "readback_method": "getDashboard",
                        "readback_payload": {"dashboardId": "dash_1", "branch": "saved"},
                    }
                ],
            )
            result = validate_safe_apply_plan_exhaustive(plan)

        joined = "\n".join(result["issues"])
        self.assertFalse(result["ok"])
        self.assertIn("unsafe DataLens internal names", joined)
        self.assertIn("missing_native_title_hint", joined)

    def test_branch_artifact_names_cannot_collide(self):
        from datalens_dev_mcp.pipeline.safe_apply import readback_artifact_name, readback_artifact_path

        with tempfile.TemporaryDirectory() as tmp:
            saved = readback_artifact_path(tmp, "dashboard", "saved")
            published = readback_artifact_path(tmp, "dashboard", "published")

        self.assertEqual(readback_artifact_name("dashboard", "saved"), "dashboard.saved.latest.json")
        self.assertEqual(readback_artifact_name("dashboard", "published"), "dashboard.published.latest.json")
        self.assertNotEqual(saved, published)

    def test_partial_create_retry_reuses_existing_and_empty_actions_are_not_success(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_path = root / "artifacts" / "payloads" / "chart.json"
            payload_path.parent.mkdir(parents=True)
            payload_path.write_text(
                json.dumps({"entry": {"name": "existing_chart", "data": {"title": "Existing Chart"}}}),
                encoding="utf-8",
            )
            (root / "artifacts" / "payload_plan.json").write_text(
                json.dumps(
                    {
                        "workbook_id": "workbook_1",
                        "payloads": [{"method": "createEditorChart", "payload_path": str(payload_path), "widget_id": "chart_1"}],
                    }
                ),
                encoding="utf-8",
            )
            entries_payload = {
                "entries": [
                    {
                        "entryId": "entry_existing",
                        "scope": "editor_chart",
                        "name": "existing_chart",
                        "displayKey": "Existing Chart",
                    }
                ]
            }

            plan = dl_create_safe_apply_plan(str(root), entries_payload=entries_payload)

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "no_changed_actions")
        self.assertEqual(plan["reused_existing_objects"][0]["existing_object_id"], "entry_existing")
        self.assertEqual(plan["reconciliation"]["objects"][0]["status"], "existing")
        self.assertEqual(plan["actions"], [])

    def test_duplicate_partial_create_candidate_stops_plan(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_create_safe_apply_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_path = root / "artifacts" / "payloads" / "chart.json"
            payload_path.parent.mkdir(parents=True)
            payload_path.write_text(
                json.dumps({"entry": {"name": "duplicate_chart", "data": {"title": "Duplicate Chart"}}}),
                encoding="utf-8",
            )
            (root / "artifacts" / "payload_plan.json").write_text(
                json.dumps(
                    {
                        "workbook_id": "workbook_1",
                        "payloads": [{"method": "createEditorChart", "payload_path": str(payload_path), "widget_id": "chart_1"}],
                    }
                ),
                encoding="utf-8",
            )
            entries_payload = {
                "entries": [
                    {"entryId": "entry_a", "scope": "editor_chart", "name": "duplicate_chart", "displayKey": "Duplicate Chart"},
                    {"entryId": "entry_b", "scope": "editor_chart", "name": "duplicate_chart", "displayKey": "Duplicate Chart"},
                ]
            }

            plan = dl_create_safe_apply_plan(str(root), entries_payload=entries_payload)

        self.assertFalse(plan["ok"])
        self.assertEqual(plan["status"], "manual_review")
        self.assertEqual(plan["error"]["category"], "duplicate_partial_create")
        self.assertEqual(plan["reconciliation"]["objects"][0]["status"], "duplicate")


if __name__ == "__main__":
    unittest.main()
