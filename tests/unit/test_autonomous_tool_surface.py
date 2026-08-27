from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datalens_dev_mcp.server import (
    AUTONOMOUS_TOOL_NAMES,
    LEGACY_TOOL_NAMES,
    TOOLS,
    JsonRpcServer,
    list_tools,
)
from datalens_dev_mcp.mcp.heavy_response import project_task_tool_response
from datalens_dev_mcp.mcp.tools import tasks
from datalens_dev_mcp.pipeline.artifacts import write_json
from datalens_dev_mcp.pipeline.project_journal import JournalIdentityError, ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import DeliveryContract, WorkspaceContract, create_task_contract


class AutonomousToolSurfaceTests(unittest.TestCase):
    def test_default_surface_is_compact_and_has_no_low_level_duplicates(self) -> None:
        tools = list_tools("autonomous-v2")
        names = {tool["name"] for tool in tools}
        compact_bytes = len(json.dumps({"tools": tools}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        self.assertEqual(names, AUTONOMOUS_TOOL_NAMES)
        self.assertLessEqual(len(tools), 9)
        self.assertLessEqual(compact_bytes, 9_000)
        self.assertFalse(names & LEGACY_TOOL_NAMES)

    def test_legacy_surface_preserves_exact_39_tools_and_expert_is_operator_owned(self) -> None:
        self.assertEqual(len(LEGACY_TOOL_NAMES), 39)
        self.assertEqual({tool["name"] for tool in list_tools("legacy-v1")}, LEGACY_TOOL_NAMES)
        self.assertEqual({tool["name"] for tool in list_tools("expert")}, set(TOOLS))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"DATALENS_MCP_TOOL_SURFACE": "legacy-v1"}, clear=False):
                legacy = JsonRpcServer(project_root=tmp)
                listed = legacy.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
                self.assertEqual(listed["result"]["tool_count"], 39)
            with patch.dict(os.environ, {"DATALENS_MCP_TOOL_SURFACE": "expert"}, clear=False):
                expert = JsonRpcServer(project_root=tmp)
                self.assertEqual(expert.tool_surface, "expert")
            with patch.dict(os.environ, {}, clear=True):
                default = JsonRpcServer(project_root=tmp)
                rejected = default.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "dl_execute_safe_apply", "arguments": {}},
                    }
                )
                self.assertIn("error", rejected)
                self.assertIn("not exposed", rejected["error"]["message"])

    def test_initialization_and_argument_contracts_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            server = JsonRpcServer(project_root=tmp)
            initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertLessEqual(len(initialized["result"]["instructions"].encode("utf-8")), 1_500)
            listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            self.assertEqual(listed["result"]["tool_surface"], "autonomous-v2")
            self.assertEqual(listed["result"]["tool_count"], 8)
            invalid = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "dl_task_status", "arguments": {"task_id": "missing", "extra": True}},
                }
            )
            payload = json.loads(invalid["result"]["content"][0]["text"])
            self.assertTrue(invalid["result"]["isError"])
            self.assertEqual(payload["error"]["category"], "invalid_tool_arguments")
            self.assertEqual(payload["error"]["unknown"], ["extra"])

    def test_oversized_task_response_falls_back_to_resource_binding(self) -> None:
        projected = project_task_tool_response(
            "dl_task_resume",
            {
                "task_id": "task-1",
                "state": "PLAN_VALIDATED",
                "resource_uri": "datalens://tasks/task-1",
                "observed_facts": ["x" * 7_000],
            },
        )
        self.assertTrue(projected["inline_truncated"])
        self.assertEqual(projected["resource_uri"], "datalens://tasks/task-1")
        self.assertNotIn("observed_facts", projected)

    def test_completed_start_cannot_bypass_required_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def execute(**kwargs):
                result = {"ok": True, "status": "completed", "executed": True, "results": []}
                write_json(Path(tmp) / "artifacts" / "safe_apply_result.json", result)
                return result

            safe_plan = {"ok": True, "status": "planned", "actions": [{"method": "updateDashboard"}]}
            with (
                patch.object(tasks.pipeline, "dl_validate_project", return_value={"ok": True, "status": "pass"}),
                patch.object(tasks.pipeline, "dl_create_safe_apply_plan", return_value=safe_plan),
                patch.object(tasks.pipeline, "dl_execute_safe_apply", side_effect=execute),
            ):
                result = tasks.dl_task_start(
                    "Update the current dashboard and publish it",
                    project_root=tmp,
                    run_until="completed",
                )

            self.assertEqual(result["state"], "BLOCKED")
            self.assertEqual(result["blocked_by"]["code"], "BLOCKED_DISCOVERY")

    def test_destructive_resume_requires_persisted_execution_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            safe_plan = {"ok": True, "status": "planned", "actions": [{"method": "deleteDashboard"}]}
            contract = create_task_contract(
                raw_request="Synthetic destructive workflow guard",
                mode="update",
                route="wizard_native",
                workspace=WorkspaceContract(project_root=tmp),
                delivery=DeliveryContract(save=True, publish=False, destructive=True),
            ).to_dict()
            journal = ProjectJournal(tmp, contract["task_id"])
            journal.initialize(contract)
            with self.assertRaisesRegex(JournalIdentityError, "execution authorization is missing"):
                tasks._advance(journal, contract, boundary="plan_ready")

    def test_compiler_question_is_persisted_as_terminal_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            started = tasks.dl_task_start("delete chart:synthetic_chart_18", project_root=tmp)
            resumed = tasks.dl_task_resume(started["task_id"], project_root=tmp)

            self.assertEqual(started["state"], "BLOCKED")
            self.assertEqual(started["next_action"], "")
            self.assertEqual(resumed["state"], "BLOCKED")
            self.assertEqual(resumed["task_revision"], started["task_revision"])


if __name__ == "__main__":
    unittest.main()
