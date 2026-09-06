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
from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
from datalens_dev_mcp.authoring.profiles import get_authoring_defaults
from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.dataset.contracts import extract_dataset_fields, validate_dataset_fields
from datalens_dev_mcp.dataset.preview import DatasetPreviewService
from datalens_dev_mcp.editor.validation import validate_editor_draft
from datalens_dev_mcp.objects.read import ObjectReadService

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


def _read_service() -> ObjectReadService:
    config = DataLensConfig.from_env()
    return ObjectReadService(api=DataLensApiClient(config), sdk=SdkAdapter(config))


def dl_workbooks_list(page_size: int = 100, max_pages: int = 100) -> dict[str, Any]:
    return _read_service().workbooks_list(page_size=page_size, max_pages=max_pages)


def dl_workbook_entries(workbook_id: str, page_size: int = 100, max_pages: int = 100) -> dict[str, Any]:
    return _read_service().workbook_entries(workbook_id, page_size=page_size, max_pages=max_pages)


def dl_object_get(
    object_type: str,
    object_id: str,
    branch: str = "saved",
    revision_id: str | None = None,
) -> dict[str, Any]:
    return _read_service().object_get(object_type, object_id, branch=branch, revision_id=revision_id)


def dl_object_relations(object_id: str, page_size: int = 100, max_pages: int = 100) -> dict[str, Any]:
    return _read_service().object_relations(object_id, page_size=page_size, max_pages=max_pages)


def dl_dashboard_snapshot(
    dashboard_id: str,
    branch: str = "saved",
    revision_id: str | None = None,
    reference_dashboard_id: str | None = None,
) -> dict[str, Any]:
    return _read_service().dashboard_snapshot(
        dashboard_id,
        branch=branch,
        revision_id=revision_id,
        reference_dashboard_id=reference_dashboard_id,
    )


def _dataset_fields(dataset_id: str, fields: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if fields is not None:
        return fields
    readback = _read_service().object_get("dataset", dataset_id)
    return extract_dataset_fields(readback["object"])


def dl_dataset_validate(
    dataset_id: str = "",
    fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved = _dataset_fields(dataset_id, fields)
    result = validate_dataset_fields(resolved)
    result["dataset_id"] = dataset_id or None
    if not resolved:
        result["ok"] = False
        result["issues"].append(
            {"code": "dataset_fields_missing", "path": "fields", "message": "no Dataset fields were supplied or read"}
        )
    return result


def dl_dataset_preview(
    dataset_id: str,
    columns: list[str],
    fields: list[dict[str, Any]] | None = None,
    filters: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    params: list[dict[str, Any]] | None = None,
    limit: int = 100,
    offset: int = 0,
    max_pages: int = 1,
    tie_breaker_guids: list[str] | None = None,
) -> dict[str, Any]:
    config = DataLensConfig.from_env()
    return DatasetPreviewService(DataLensApiClient(config)).preview(
        dataset_id=dataset_id,
        fields=_dataset_fields(dataset_id, fields),
        columns=columns,
        filters=filters,
        sort=sort,
        params=params,
        limit=limit,
        offset=offset,
        max_pages=max_pages,
        tie_breaker_guids=tie_breaker_guids,
    )


def dl_authoring_defaults(
    project_root: str | None = None,
    family: str | None = None,
    explicit: dict[str, Any] | None = None,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_authoring_defaults(project_root, family, explicit=explicit, reference=reference)


def dl_compile_recipe(
    recipe_id: str,
    bindings: dict[str, Any],
    presentation: dict[str, Any] | None = None,
    output_dir: str | None = None,
    project_root: str | None = None,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return compile_recipe(
        recipe_id,
        bindings,
        presentation,
        output_dir,
        project_root=project_root,
        reference=reference,
    )


def dl_editor_validate(draft: dict[str, Any]) -> dict[str, Any]:
    return validate_editor_draft(draft)


TOOLS: dict[str, ToolHandler] = {
    "dl_server_info": dl_server_info,
    "dl_auth_check": dl_auth_check,
    "dl_auth_refresh": dl_auth_refresh,
    "dl_method_schema": dl_method_schema,
    "dl_workbooks_list": dl_workbooks_list,
    "dl_workbook_entries": dl_workbook_entries,
    "dl_object_get": dl_object_get,
    "dl_object_relations": dl_object_relations,
    "dl_dashboard_snapshot": dl_dashboard_snapshot,
    "dl_dataset_validate": dl_dataset_validate,
    "dl_dataset_preview": dl_dataset_preview,
    "dl_authoring_defaults": dl_authoring_defaults,
    "dl_compile_recipe": dl_compile_recipe,
    "dl_editor_validate": dl_editor_validate,
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
    {
        "name": "dl_workbooks_list",
        "description": "List DataLens workbooks with bounded pagination and an explicit completeness marker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_size": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_workbook_entries",
        "description": "List compact workbook objects with bounded full pagination and an explicit completeness marker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workbook_id": {"type": "string", "minLength": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            },
            "required": ["workbook_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_object_get",
        "description": "Read one typed DataLens object by exact type, ID, branch and optional revision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_type": {"type": "string", "minLength": 1},
                "object_id": {"type": "string", "minLength": 1},
                "branch": {"type": "string", "enum": ["saved", "published"], "default": "saved"},
                "revision_id": {"type": ["string", "null"]},
            },
            "required": ["object_type", "object_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_object_relations",
        "description": "Read compact direct relations for one exact DataLens object ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "string", "minLength": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            },
            "required": ["object_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_dashboard_snapshot",
        "description": "Read one dashboard and only its direct dependencies; keep an optional style reference separate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dashboard_id": {"type": "string", "minLength": 1},
                "branch": {"type": "string", "enum": ["saved", "published"], "default": "saved"},
                "revision_id": {"type": ["string", "null"]},
                "reference_dashboard_id": {"type": ["string", "null"]},
            },
            "required": ["dashboard_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_dataset_validate",
        "description": "Validate Dataset field GUIDs, calculation levels and known cross-field formula restrictions without mutation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string"},
                "fields": {"type": ["array", "null"], "items": {"type": "object"}},
            },
            "anyOf": [{"required": ["dataset_id"]}, {"required": ["fields"]}],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_dataset_preview",
        "description": "Run a bounded Dataset query by exact field GUIDs; this is data evidence, not chart branch proof.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "minLength": 1},
                "columns": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                "fields": {"type": ["array", "null"], "items": {"type": "object"}},
                "filters": {"type": ["array", "null"], "items": {"type": "object"}},
                "sort": {"type": ["array", "null"], "items": {"type": "object"}},
                "params": {"type": ["array", "null"], "items": {"type": "object"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100000, "default": 100},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "max_pages": {"type": "integer", "minimum": 1, "maximum": 100, "default": 1},
                "tie_breaker_guids": {"type": ["array", "null"], "items": {"type": "string"}},
            },
            "required": ["dataset_id", "columns"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    },
    {
        "name": "dl_authoring_defaults",
        "description": "Resolve compact generic, user, project, reference and explicit authoring defaults for one visual family.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": ["string", "null"]},
                "family": {"type": ["string", "null"]},
                "explicit": {"type": ["object", "null"]},
                "reference": {"type": ["object", "null"]},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "dl_compile_recipe",
        "description": "Compile a typed recipe and canonical packaged assets locally; never access or write DataLens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string", "minLength": 1},
                "bindings": {"type": "object"},
                "presentation": {"type": ["object", "null"]},
                "output_dir": {"type": ["string", "null"]},
                "project_root": {"type": ["string", "null"]},
                "reference": {"type": ["object", "null"]},
            },
            "required": ["recipe_id", "bindings"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": "dl_editor_validate",
        "description": "Validate one Editor variant, required tabs, aliases and known constrained-runtime errors without execution.",
        "inputSchema": {
            "type": "object",
            "properties": {"draft": {"type": "object"}},
            "required": ["draft"],
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
