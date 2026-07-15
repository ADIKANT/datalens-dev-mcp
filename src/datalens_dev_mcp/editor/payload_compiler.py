from __future__ import annotations

import json
from typing import Any

from datalens_dev_mcp.api.client import compact_rpc_payload
from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT
from datalens_dev_mcp.validators.datalens_names import sanitize_datalens_internal_name
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from datalens_dev_mcp.validators.route_validator import validate_route_payload


def compile_editor_payload(
    bundle: dict[str, Any],
    *,
    workbook_id: str,
    mode: str = "save",
    existing_entry: dict[str, Any] | None = None,
    allow_fixture_source: bool = False,
) -> dict[str, Any]:
    validation = validate_route_payload(bundle)
    if not validation.ok:
        raise ValueError("; ".join(validation.issues))
    if mode != "save":
        raise ValueError("Payload compiler defaults to save; publish requires safe-apply approval.")
    route = bundle["route"]
    spec = ROUTE_CONTRACT.spec(route)
    data = _normalize_editor_data_tabs({_editor_tab_key(tab_name): tab_value for tab_name, tab_value in bundle["tabs"].items()})
    entry = dict(existing_entry or {})
    internal_name = sanitize_datalens_internal_name(bundle.get("name") or bundle["widget_id"])
    entry.update(
        {
            "workbookId": workbook_id,
            "name": internal_name,
            "type": spec.entry_type,
            "data": data,
        }
    )
    payload = {"entry": entry, "mode": mode}
    compiled = compact_rpc_payload(payload, method="updateEditorChart") or payload
    runtime_validation = validate_editor_runtime_contract(
        compiled,
        source=f"compiled_editor_payload:{bundle.get('widget_id') or internal_name}",
        allow_unknown_warnings=True,
    )
    if not runtime_validation["ok"]:
        details = []
        for finding in runtime_validation["findings"]:
            if finding["severity"] != "error":
                continue
            details.append(f"{finding['rule']} at {finding['path']}:line {finding['line']}")
        raise ValueError("compiled Editor payload failed runtime contract: " + "; ".join(details))
    generation_status = str(bundle.get("generation_status") or "")
    if generation_status == "fixture_only" and allow_fixture_source:
        pass
    elif generation_status and generation_status != "ready":
        blocking_issues = bundle.get("blocking_issues") or (bundle.get("source_contract") or {}).get("issues") or []
        messages = [str(issue.get("message") or issue.get("code") or issue) for issue in blocking_issues]
        detail = "; ".join(messages) or generation_status
        raise ValueError(f"Editor bundle generation is blocked ({generation_status}): {detail}")
    return compiled


def _editor_tab_key(tab_name: str) -> str:
    name = str(tab_name)
    for suffix in (".json", ".js"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _normalize_editor_data_tabs(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    meta = normalized.get("meta")
    if isinstance(meta, str) and meta.strip().startswith("{"):
        try:
            parsed = json.loads(meta)
        except json.JSONDecodeError:
            return normalized
        if isinstance(parsed, dict):
            for key in ("title", "hint"):
                parsed.pop(key, None)
            normalized["meta"] = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return normalized
