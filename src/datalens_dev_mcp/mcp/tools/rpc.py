from __future__ import annotations

from collections import Counter
from typing import Any

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensSafetyError
from datalens_dev_mcp.api.methods import get_method_schema, is_readonly_method, list_methods, openapi_lock_summary
from datalens_dev_mcp.api.request_compiler import validate_method_request
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.pipeline.dataset_preview import preview_dataset_data


def dl_list_api_methods(include_guarded_writes: bool = True, limit: int = 50) -> dict[str, Any]:
    if not isinstance(include_guarded_writes, bool):
        return {
            "ok": False,
            "error": {
                "category": "invalid_input",
                "message": "include_guarded_writes must be a boolean.",
            },
        }
    if not isinstance(limit, int) or limit < 1:
        return {
            "ok": False,
            "error": {
                "category": "invalid_input",
                "message": "limit must be a positive integer.",
            },
        }
    methods = list_methods(include_guarded_writes=include_guarded_writes)
    preview_limit = min(limit, 75)
    mode_counts = Counter(item.mode for item in methods)
    return {
        "ok": True,
        "method_count": len(methods),
        "mode_counts": dict(sorted(mode_counts.items())),
        "methods": [{"name": item.name, "mode": item.mode} for item in methods[:preview_limit]],
        "truncated": len(methods) > preview_limit,
        "preview_limit": preview_limit,
        "detail_tool": "dl_get_api_method_schema",
        "source_trace": {
            "catalog_resource": "config/datalens_api_methods.json",
            "compiled_openapi": openapi_lock_summary(),
        },
    }


def dl_get_api_method_schema(method: str) -> dict[str, Any]:
    return get_method_schema(method)


def dl_rpc_readonly(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not is_readonly_method(method):
        raise DataLensSafetyError(f"{method} is not allowed through dl_rpc_readonly")
    client = DataLensApiClient(DataLensConfig.from_env())
    return client.rpc_readonly(method, payload or {})


def dl_rpc_expert(method: str, payload: dict[str, Any] | None = None, client: Any | None = None) -> dict[str, Any]:
    config = DataLensConfig.from_env()
    if not config.expert_rpc_enabled:
        raise DataLensSafetyError("dl_rpc_expert is disabled; set DATALENS_MCP_ENABLE_EXPERT_RPC=1 explicitly")
    method_schema = get_method_schema(method)
    mode = str(method_schema.get("mode") or "unknown")
    if mode != "readonly":
        raise DataLensSafetyError(
            f"{method} is not allowed through dl_rpc_expert; expert RPC is limited to curated read-only methods"
        )
    rpc_payload = payload or {}
    validation = validate_method_request(method, rpc_payload)
    if not validation["ok"]:
        raise DataLensSafetyError(
            f"{method} blocked before HTTP: datalens_validation_error: {'; '.join(validation['issues'])}"
        )
    active_client = client or DataLensApiClient(config)
    return active_client.rpc(method, rpc_payload)


def dl_get_dataset_data(
    dataset_id: str,
    columns: list[str],
    workbook_id: str = "",
    filters: list[dict[str, Any]] | None = None,
    params: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    limit: int = 100,
    offset: int = 0,
    max_pages: int = 1,
    tie_breaker_fields: list[str] | None = None,
    inline_row_limit: int = 20,
    inline_byte_budget: int = 8_000,
    project_root: str = ".",
    artifact_name: str = "dataset-preview",
    client: Any | None = None,
    dataset_readback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Typed internal route for the experimental getDatasetData operation."""
    return preview_dataset_data(
        dataset_id=dataset_id,
        columns=columns,
        workbook_id=workbook_id,
        filters=filters,
        params=params,
        sort=sort,
        limit=limit,
        offset=offset,
        max_pages=max_pages,
        tie_breaker_fields=tie_breaker_fields,
        inline_row_limit=inline_row_limit,
        inline_byte_budget=inline_byte_budget,
        project_root=project_root,
        artifact_name=artifact_name,
        client=client,
        dataset_readback=dataset_readback,
    )
