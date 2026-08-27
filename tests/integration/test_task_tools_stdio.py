from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datalens_dev_mcp.server import JsonRpcServer


def _call(server: JsonRpcServer, request_id: int, name: str, arguments: dict) -> dict:
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    assert response["result"]["isError"] is False, response
    return json.loads(response["result"]["content"][0]["text"])


class TaskToolsStdioTests(unittest.TestCase):
    def test_discovery_blocker_survives_server_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            first = JsonRpcServer(project_root=tmp)
            started = _call(
                first,
                1,
                "dl_task_start",
                {
                    "request": "Review and plan the current dashboard; plan only",
                    "project_root": tmp,
                    "run_until": "plan_ready",
                },
            )
            self.assertEqual(started["state"], "BLOCKED")
            self.assertEqual(started["blocked_by"]["code"], "BLOCKED_DISCOVERY")
            task_id = started["task_id"]

            restarted = JsonRpcServer(project_root=tmp)
            status = _call(restarted, 2, "dl_task_status", {"task_id": task_id, "project_root": tmp})
            self.assertEqual(status["state"], "BLOCKED")
            resumed = _call(
                restarted,
                3,
                "dl_task_resume",
                {
                    "task_id": task_id,
                    "project_root": tmp,
                    "expected_state": status["state"],
                    "expected_hash": status["state_etag"],
                    "run_until": "completed",
                },
            )
            self.assertEqual(resumed["state"], "BLOCKED")
            self.assertEqual(resumed["task_revision"], started["task_revision"])

            task_resource = restarted.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "resources/read",
                    "params": {"uri": f"datalens://tasks/{task_id}"},
                }
            )
            resource_payload = json.loads(task_resource["result"]["contents"][0]["text"])
            self.assertEqual(resource_payload["state"], "BLOCKED")

    def test_evidence_reads_only_one_bounded_task_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            server = JsonRpcServer(project_root=tmp)
            started = _call(
                server,
                1,
                "dl_task_start",
                {"request": "Review this dashboard; plan only", "project_root": tmp},
            )
            task_id = started["task_id"]
            evidence_path = Path(tmp) / ".datalens-mcp" / "tasks" / task_id / "evidence" / "large.txt"
            evidence_path.write_text("evidence-line\n" * 2_000, encoding="utf-8")
            evidence = _call(
                server,
                2,
                "dl_evidence",
                {
                    "task_id": task_id,
                    "project_root": tmp,
                    "resource_uri": f"datalens://tasks/{task_id}/evidence/large.txt",
                    "limit": 500,
                },
            )
            self.assertEqual(evidence["returned_chars"], 500)
            self.assertTrue(evidence["truncated"])
            self.assertEqual(evidence["resource_uri"], f"datalens://tasks/{task_id}/evidence/large.txt")


if __name__ == "__main__":
    unittest.main()
