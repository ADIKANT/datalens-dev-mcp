#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any, Callable


def _run_check(name: str, fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "ok": False,
            "error": {"category": exc.__class__.__name__, "message": str(exc)[:500]},
        }
    return {
        "name": name,
        "ok": True,
        "keys": sorted(value) if isinstance(value, dict) else [],
        "metadata": _metadata(value),
    }


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "ok": value.get("ok"),
            "tool_count": value.get("tool_count"),
            "method": value.get("method"),
            "mode": value.get("mode"),
            "result_count": value.get("result_count"),
            "schema_version": value.get("schema_version"),
        }
    return {}


def run_smoke() -> dict[str, Any]:
    from datalens_dev_mcp.api.methods import get_method_schema
    from datalens_dev_mcp.api.request_compiler import compile_method_request
    from datalens_dev_mcp.knowledge.reference import build_reference_response
    from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan, load_wizard_template_registry
    from datalens_dev_mcp.server import JsonRpcServer
    from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

    server = JsonRpcServer(project_root=".")
    checks: list[tuple[str, Callable[[], Any]]] = [
        (
            "initialize",
            lambda: server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) or {},
        ),
        (
            "tools_list",
            lambda: (server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) or {}).get(
                "result",
                {},
            ),
        ),
        ("api_contract_lookup", lambda: get_method_schema("getDashboard")),
        (
            "request_compilation",
            lambda: compile_method_request(
                "updateDashboard",
                {"entry": {"entryId": "dash_1", "data": {"tabs": []}}},
                object_type="dashboard",
                operation="update",
                object_id="dash_1",
            ),
        ),
        (
            "runtime_validator",
            lambda: validate_editor_runtime_contract(
                {"javascript": "module.exports = {render: () => null};"},
                source="portable-runtime-smoke",
            ),
        ),
        ("wizard_registry", load_wizard_template_registry),
        ("wizard_payload_plan", lambda: build_wizard_payload_plan()),
        ("reference_recipe", lambda: build_reference_response(mode="recipe", name="markdown", max_chars=4000)),
    ]
    results = [_run_check(name, fn) for name, fn in checks]
    return {
        "ok": all(item["ok"] for item in results),
        "checks": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke installed datalens-dev-mcp runtime resources.")
    parser.parse_args()
    print(json.dumps(run_smoke(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
