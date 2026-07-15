from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from datalens_dev_mcp.runtime_resources import resource_json

CATALOG_RESOURCE = "config/datalens_api_methods.json"
OPENAPI_LOCK_RESOURCE = "schemas/datalens-api/openapi.lock.json"


@dataclass(frozen=True)
class MethodInfo:
    name: str
    mode: str
    description: str


@lru_cache(maxsize=1)
def _catalog() -> dict[str, object]:
    return resource_json(CATALOG_RESOURCE)


@lru_cache(maxsize=1)
def _openapi_lock() -> dict[str, object]:
    return resource_json(OPENAPI_LOCK_RESOURCE)


def _method_index() -> dict[str, dict[str, object]]:
    return {item["method"]: item for item in _catalog().get("methods", [])}  # type: ignore[index]


def list_methods(*, include_guarded_writes: bool = True) -> list[MethodInfo]:
    result: list[MethodInfo] = []
    for name, value in sorted(_method_index().items()):
        mode = str(value["mode"])
        if mode == "guarded_write" and not include_guarded_writes:
            continue
        result.append(MethodInfo(name, mode, str(value.get("description") or value.get("summary") or "")))
    return result


def get_method_schema(name: str) -> dict[str, object]:
    value = _method_index().get(name)
    if value:
        return {
            "name": name,
            "mode": value["mode"],
            "description": value.get("description") or value.get("summary") or "",
            "path": value.get("path"),
            "tag": value.get("tag"),
            "mcp_route": value.get("mcp_route"),
            "mcp_tool": value.get("mcp_tool"),
            "support_status": value.get("support_status"),
            "support_reason": value.get("support_reason"),
            "request_schema_ref": value.get("request_schema_ref"),
            "response_schema_ref": value.get("response_schema_ref"),
            "experimental": value.get("experimental"),
            "trace": {"source": value.get("source"), "doc_url": value.get("doc_url")},
        }
    return {"name": name, "mode": "unknown", "description": "Method is not in the curated v1 catalog."}


def compiled_api_version() -> str:
    value = str(_openapi_lock().get("required_api_header_version") or _catalog().get("required_api_header_version") or "1")
    return value.strip() or "1"


def openapi_lock_hash() -> str:
    return str(_openapi_lock().get("openapi_sha256") or "")


def openapi_lock_summary() -> dict[str, object]:
    lock = _openapi_lock()
    return {
        "openapi_sha256": lock.get("openapi_sha256") or "",
        "required_api_header_version": lock.get("required_api_header_version") or "",
        "operation_count": lock.get("operation_count") or 0,
        "closed_schema_count": lock.get("closed_schema_count") or 0,
    }


def is_readonly_method(name: str) -> bool:
    return _method_index().get(name, {}).get("mode") == "readonly"


def is_write_method(name: str) -> bool:
    return _method_index().get(name, {}).get("mode") == "guarded_write"
