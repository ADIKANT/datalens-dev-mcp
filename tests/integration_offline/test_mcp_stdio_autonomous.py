from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


def rpc(message_id: int, method: str, params: dict | None = None) -> str:
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload) + "\n"


class AutonomousStdioSurfaceTests(unittest.TestCase):
    def test_default_surface_has_eight_task_tools_and_rejects_hidden_call(self) -> None:
        env = {**os.environ, "PYTHONPATH": "src", "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("DATALENS_MCP_TOOL_SURFACE", None)
        proc = subprocess.Popen(
            [sys.executable, "-m", "datalens_dev_mcp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        assert proc.stdin and proc.stdout
        requests = [
            rpc(1, "initialize", {}),
            rpc(2, "tools/list", {}),
            rpc(3, "tools/call", {"name": "dl_validate_editor_runtime_contract", "arguments": {}}),
        ]
        proc.stdin.write("".join(requests))
        proc.stdin.flush()
        responses = [json.loads(proc.stdout.readline()) for _ in requests]
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)
        self.assertIn("autonomous-v2 surface: 8 tools", responses[0]["result"]["instructions"])
        listed = responses[1]["result"]
        self.assertEqual(listed["tool_surface"], "autonomous-v2")
        self.assertEqual(listed["tool_count"], 8)
        self.assertNotIn("dl_validate_editor_runtime_contract", {item["name"] for item in listed["tools"]})
        self.assertIn("not exposed", responses[2]["error"]["message"])


if __name__ == "__main__":
    unittest.main()
