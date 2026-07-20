#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _rpc(message_id: int, method: str, params: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload, separators=(",", ":")) + "\n"


def _parse_stdout(stdout: str, expected_lines: int) -> list[dict[str, Any]]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != expected_lines:
        raise RuntimeError(f"expected {expected_lines} JSON-RPC stdout lines, got {len(lines)}")
    responses = []
    for index, line in enumerate(lines, start=1):
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"stdout line {index} is not JSON: {line[:200]!r}") from exc
        if response.get("jsonrpc") != "2.0":
            raise RuntimeError(f"stdout line {index} is not a JSON-RPC 2.0 response")
        responses.append(response)
    return responses


def main() -> int:
    started = time.perf_counter()
    requests = [
        _rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}, separators=(",", ":")) + "\n",
        _rpc(2, "tools/list"),
        _rpc(3, "tools/call", {"name": "dl_get_local_config", "arguments": {}}),
        _rpc(4, "prompts/list"),
        _rpc(5, "prompts/get", {"name": "datalens.develop_dashboard"}),
        _rpc(6, "resources/list"),
        _rpc(7, "resources/read", {"uri": "datalens://routes/contract"}),
        _rpc(8, "unknown/method"),
        "{malformed json}\n",
    ]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess_started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-m", "datalens_dev_mcp.server", "--project-root", str(ROOT)],
        cwd=ROOT,
        input="".join(requests),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
        timeout=10,
    )
    subprocess_duration_ms = round((time.perf_counter() - subprocess_started) * 1000, 3)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode

    validation_started = time.perf_counter()
    try:
        responses = _parse_stdout(proc.stdout, expected_lines=9)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        return 1

    if responses[0]["result"].get("protocolVersion") != "2025-06-18":
        print("initialize did not return the expected protocol version", file=sys.stderr)
        return 1
    tools = {tool["name"] for tool in responses[1]["result"]["tools"]}
    tool_payload_bytes = len(json.dumps({"tools": responses[1]["result"]["tools"]}, separators=(",", ":")).encode("utf-8"))
    if responses[1]["result"].get("tool_surface") != "standard":
        print("tools/list did not report the standard surface", file=sys.stderr)
        return 1
    if len(tools) != 38:
        print(f"tools/list returned {len(tools)} tools instead of 38", file=sys.stderr)
        return 1
    if tool_payload_bytes > 25_000:
        print(f"tools/list payload exceeds budget: {tool_payload_bytes} bytes", file=sys.stderr)
        return 1
    if "dl_get_local_config" not in tools:
        print("tools/list did not expose dl_get_local_config", file=sys.stderr)
        return 1
    if not all("name" in tool and "description" in tool and "inputSchema" in tool for tool in responses[1]["result"]["tools"]):
        print("tools/list returned a tool without name, description, or inputSchema", file=sys.stderr)
        return 1
    if responses[2].get("error"):
        print(json.dumps(responses[2]["error"], indent=2), file=sys.stderr)
        return 1
    if responses[2]["result"].get("isError") is not False:
        print("tools/call did not return isError=false", file=sys.stderr)
        return 1
    if not responses[2]["result"].get("content"):
        print("tools/call did not return content", file=sys.stderr)
        return 1
    prompts = {prompt["name"] for prompt in responses[3]["result"]["prompts"]}
    if "datalens.develop_dashboard" not in prompts:
        print("prompts/list did not expose datalens.develop_dashboard", file=sys.stderr)
        return 1
    if not responses[4]["result"].get("messages"):
        print("prompts/get did not return messages", file=sys.stderr)
        return 1
    resources = {resource["uri"] for resource in responses[5]["result"]["resources"]}
    if "datalens://routes/contract" not in resources:
        print("resources/list did not expose datalens://routes/contract", file=sys.stderr)
        return 1
    if "Operational routes are closed" not in responses[6]["result"]["contents"][0]["text"]:
        print("resources/read did not return route contract text", file=sys.stderr)
        return 1
    if responses[7].get("error", {}).get("code") != -32601:
        print("invalid method did not return -32601", file=sys.stderr)
        return 1
    if responses[8].get("error", {}).get("code") != -32700:
        print("malformed JSON did not return -32700", file=sys.stderr)
        return 1

    validation_duration_ms = round((time.perf_counter() - validation_started) * 1000, 3)
    total_duration_ms = round((time.perf_counter() - started) * 1000, 3)
    print(
        json.dumps(
            {
                "ok": True,
                "tools": len(tools),
                "tool_payload_bytes": tool_payload_bytes,
                "prompts": len(prompts),
                "resources": len(resources),
                "stdout_jsonrpc_lines": len(responses),
                "notification_responses": 0,
                "duration_ms": total_duration_ms,
                "timings": {
                    "subprocess_ms": subprocess_duration_ms,
                    "validation_ms": validation_duration_ms,
                    "total_ms": total_duration_ms,
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
