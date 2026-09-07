from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SKILLS = {
    "datalens-inspect",
    "datalens-dataset-wizard",
    "datalens-editor",
    "datalens-dashboard",
    "datalens-maintenance",
}
REMOVED_TASK_TOOLS = {
    "dl_task_start",
    "dl_task_resume",
    "dl_task_status",
    "dl_plan",
    "dl_execute",
    "dl_verify",
    "dl_evidence",
}


def _rpc(message_id: int, method: str, params: dict | None = None) -> str:
    payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload) + "\n"


def test_plugin_manifest_loads_bundled_skills_and_stdio_backend() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "datalens-dev-mcp"
    assert manifest["version"] == "1.0.0"
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"

    server_map = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert server_map == {"mcpServers": {"datalens": {"command": "datalens-dev-mcp", "args": ["stdio"]}}}
    assert {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")} == EXPECTED_SKILLS


def test_stdio_starts_without_writing_to_arbitrary_project(tmp_path: Path) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "datalens_dev_mcp.cli", "stdio"],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    requests = [
        _rpc(
            1,
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "l01-test", "version": "1"},
            },
        ),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n",
        _rpc(2, "tools/list"),
        _rpc(3, "tools/call", {"name": "dl_server_info", "arguments": {}}),
    ]
    proc.stdin.write("".join(requests))
    proc.stdin.flush()
    responses = [json.loads(proc.stdout.readline()) for _ in range(3)]
    proc.stdin.close()
    proc.terminate()
    proc.wait(timeout=5)

    assert responses[0]["result"]["serverInfo"] == {
        "name": "datalens-dev-mcp",
        "version": "1.0.0",
    }
    names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert "dl_server_info" in names
    assert not names & REMOVED_TASK_TOOLS
    info = json.loads(responses[2]["result"]["content"][0]["text"])
    assert info["version"] == "1.0.0"
    assert info["architecture"] == "domain-plugin"
    assert list(tmp_path.iterdir()) == []
