from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from datalens_dev_mcp import __version__
from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError, safe_error_text
from datalens_dev_mcp.api.schemas import OperationRegistry
from datalens_dev_mcp.config import DataLensConfig

MCP_PROTOCOL_VERSION = "2025-06-18"
ToolHandler = Callable[..., dict[str, Any]]


def dl_server_info() -> dict[str, Any]:
    return {
        "ok": True,
        "name": "datalens-dev-mcp",
        "version": __version__,
        "architecture": "domain-plugin",
        "execution_path": "typed-domain-services",
    }


def dl_auth_check() -> dict[str, Any]:
    config = DataLensConfig.from_env()
    report = config.credential_report()
    if not config.iam_token or not config.org_id:
        return {"ok": False, "status": "not_configured", "credentials": report}
    try:
        DataLensApiClient(config).read("getWorkbooksList", {"pageSize": 1})
    except DataLensApiError as exc:
        return {
            "ok": False,
            "status": "probe_failed",
            "credentials": report,
            "error": f"{type(exc).__name__}: {safe_error_text(exc)}",
        }
    return {"ok": True, "status": "healthy", "credentials": report}


def dl_auth_refresh() -> dict[str, Any]:
    token = refresh_iam_token_with_yc()
    os.environ["DATALENS_IAM_TOKEN"] = token
    return {"ok": True, "status": "refreshed", "token_exposed": False}


def dl_method_schema(method: str) -> dict[str, Any]:
    return {"ok": True, "operation": OperationRegistry.load().get(method)}


TOOLS: dict[str, ToolHandler] = {
    "dl_server_info": dl_server_info,
    "dl_auth_check": dl_auth_check,
    "dl_auth_refresh": dl_auth_refresh,
    "dl_method_schema": dl_method_schema,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "dl_server_info",
        "description": "Return the installed backend version and architecture without accessing DataLens or the project.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "dl_auth_check",
        "description": "Run one harmless DataLens authentication probe and return a secret-free status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_auth_refresh",
        "description": "Refresh the process IAM credential once through the configured yc profile without returning the token.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    },
    {
        "name": "dl_method_schema",
        "description": "Return the versioned backend and effect contract for one supported DataLens operation.",
        "inputSchema": {
            "type": "object",
            "properties": {"method": {"type": "string", "minLength": 1}},
            "required": ["method"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
]


def list_tools() -> list[dict[str, Any]]:
    return deepcopy(TOOL_SCHEMAS)


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    handler = TOOLS.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    result = handler(**dict(arguments or {}))
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, sort_keys=True)}],
        "structuredContent": result,
        "isError": not bool(result.get("ok", True)),
    }


def _success(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    if method == "notifications/initialized":
        return None
    message_id = request.get("id")
    if method == "initialize":
        return _success(
            message_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "datalens-dev-mcp", "version": __version__},
                "instructions": "Direct DataLens domain operations; no internal task orchestrator.",
            },
        )
    if method == "ping":
        return _success(message_id, {})
    if method == "tools/list":
        return _success(message_id, {"tools": list_tools()})
    if method == "tools/call":
        params = request.get("params") or {}
        try:
            return _success(message_id, call_tool(str(params.get("name") or ""), params.get("arguments")))
        except (TypeError, ValueError) as exc:
            return _error(message_id, -32602, str(exc))
        except Exception as exc:  # noqa: BLE001 - MCP must return an error instead of terminating stdio.
            return _error(message_id, -32603, f"tool call failed: {type(exc).__name__}: {safe_error_text(exc)}")
    if method == "resources/list":
        return _success(message_id, {"resources": []})
    if method == "prompts/list":
        return _success(message_id, {"prompts": []})
    return _error(message_id, -32601, f"method not found: {method}")


def serve_stdio() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = handle_request(request)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            response = _error(None, -32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    del argv
    serve_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
