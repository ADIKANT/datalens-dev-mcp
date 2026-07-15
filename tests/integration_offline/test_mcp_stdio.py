import json
import os
import subprocess
import sys
import unittest


def rpc(message_id, method, params=None):
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload) + "\n"


class McpStdioSmokeTests(unittest.TestCase):
    def test_smoke_script_rejects_stdout_pollution(self):
        result = subprocess.run(
            [sys.executable, "scripts/smoke_mcp_stdio.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["stdout_jsonrpc_lines"], 9)
        self.assertEqual(payload["notification_responses"], 0)

    def test_lists_prompts_resources_tools_and_calls_readonly_tool(self):
        proc = subprocess.Popen(
            [sys.executable, "-m", "datalens_dev_mcp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "PYTHONPATH": "src",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            text=True,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        requests = [
            rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n",
            rpc(2, "tools/list"),
            rpc(3, "resources/list"),
            rpc(4, "prompts/list"),
            rpc(
                5,
                "tools/call",
                {
                    "name": "dl_validate_editor_runtime_contract",
                    "arguments": {"sections": {"prepare": "const root = document.createElement('div');"}},
                },
            ),
            rpc(
                6,
                "tools/call",
                {
                    "name": "dl_get_api_method_schema",
                    "arguments": {
                        "method": "getWorkbookEntries",
                    },
                },
            ),
            rpc(7, "resources/read", {"uri": "datalens://routes/contract"}),
        ]
        proc.stdin.write("".join(requests))
        proc.stdin.flush()

        responses = [json.loads(proc.stdout.readline()) for _ in range(len(requests) - 1)]
        proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)
        proc.stdout.close()
        assert proc.stderr is not None
        proc.stderr.close()

        self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "datalens-dev-mcp")
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("standard tool surface", responses[0]["result"]["instructions"])
        tools = {tool["name"] for tool in responses[1]["result"]["tools"]}
        resources = {item["uri"] for item in responses[2]["result"]["resources"]}
        prompts = {item["name"] for item in responses[3]["result"]["prompts"]}
        self.assertIn("dl_snapshot_dashboard", tools)
        self.assertIn("dl_read_object", tools)
        self.assertTrue(all("title" in tool for tool in responses[1]["result"]["tools"]))
        self.assertIn("dl_get_api_method_schema", tools)
        self.assertIn("datalens://routes/contract", resources)
        self.assertIn("datalens.develop_dashboard", prompts)
        self.assertIn("datalens.visual_review", prompts)
        self.assertIn("datalens.live_diagnostics", prompts)
        self.assertIn("editor_runtime_contract", responses[4]["result"]["content"][0]["text"])
        self.assertIn("getWorkbookEntries", responses[5]["result"]["content"][0]["text"])
        self.assertIn("Operational routes are closed", responses[6]["result"]["contents"][0]["text"])


if __name__ == "__main__":
    unittest.main()
