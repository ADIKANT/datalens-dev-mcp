from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.mcp.response_projection import (
    normalize_response_mode,
    sanitize_response,
    serialized_metadata,
    write_full_artifact,
)


HEAVY_TOOL_NAMES = frozenset(
    {
        "dl_create_safe_apply_plan",
        "dl_create_publish_from_saved_plan",
        "dl_compile_guarded_rpc_request",
        "dl_plan_project_live_workflow",
        "dl_run_project_live_dry_run",
        "dl_run_project_live_apply",
        "dl_read_project_live_summary",
    }
)
DEFAULT_HEAVY_INLINE_CHAR_BUDGET = 15_000


def project_heavy_tool_response(
    tool_name: str,
    output: Any,
    *,
    response_mode: str,
    inline_char_budget: int,
    project_root: str | Path,
    run_id: str = "",
) -> Any:
    if tool_name not in HEAVY_TOOL_NAMES or not isinstance(output, dict):
        return output
    mode = normalize_response_mode(response_mode)
    sanitized = sanitize_response(output)
    metadata = serialized_metadata(sanitized)
    artifact = write_full_artifact(
        kind=tool_name.removeprefix("dl_"),
        response=sanitized,
        project_root=project_root,
        run_id=run_id or f"{tool_name.removeprefix('dl_')}_{metadata['sha256'][:12]}",
        full_hash=metadata["sha256"],
    )
    if mode == "full":
        return {
            **sanitized,
            "response_mode": "full",
            "requested_response_mode": mode,
            "canonical_artifact": artifact,
            "full_response": metadata,
        }
    envelope: dict[str, Any] = {
        "ok": bool(sanitized.get("ok", True)),
        "status": str(sanitized.get("status") or ""),
        "tool": tool_name,
        "response_mode": mode,
        "requested_response_mode": mode,
        "canonical_artifact": artifact,
        "full_response": metadata,
    }
    for key in ("approved", "request_intent", "delivery_intent_decision", "target_lock", "plan_path"):
        if key in sanitized:
            envelope[key] = sanitized[key]
    if mode == "artifact":
        return envelope
    envelope["summary"] = _heavy_summary(sanitized)
    if mode == "structure":
        envelope["structure"] = {
            "top_level_keys": sorted(sanitized),
            "top_level_types": {
                key: _json_type_name(value)
                for key, value in sorted(sanitized.items())
            },
        }
    budget = max(1000, int(inline_char_budget or DEFAULT_HEAVY_INLINE_CHAR_BUDGET))
    if serialized_metadata(envelope)["serialized_chars"] > budget:
        envelope["summary"] = _minimal_heavy_summary(sanitized)
        envelope["inline_truncated"] = True
    if serialized_metadata(envelope)["serialized_chars"] > budget:
        artifact_backed_fields = []
        for key in ("request_intent", "delivery_intent_decision", "target_lock"):
            if key in envelope:
                envelope.pop(key)
                artifact_backed_fields.append(key)
            if serialized_metadata(envelope)["serialized_chars"] <= budget:
                break
        if artifact_backed_fields:
            envelope["artifact_backed_fields"] = artifact_backed_fields
            if serialized_metadata(envelope)["serialized_chars"] > budget:
                envelope.pop("artifact_backed_fields")
                envelope["artifact_backed_field_count"] = len(artifact_backed_fields)
    return envelope


def _heavy_summary(value: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ok",
        "status",
        "summary",
        "executed",
        "returncode",
        "target",
        "target_lock",
        "plan_path",
        "safe_apply_id",
        "workflow_name",
        "action",
        "publish",
        "summary_path",
        "saved_readback_path",
        "published_readback_path",
        "blocked_reasons",
        "blockers",
        "warnings",
        "errors",
        "next_actions",
        "delivery_intent_decision",
    )
    summary = {key: value[key] for key in keys if key in value}
    actions = value.get("actions") if isinstance(value.get("actions"), list) else []
    if actions:
        summary["action_count"] = len(actions)
        summary["methods"] = [
            str(item.get("method") or item.get("action") or "")
            for item in actions
            if isinstance(item, dict)
        ][:100]
    for key in ("expected_artifacts", "evidence_paths", "saved_readback_paths", "published_readback_paths"):
        rows = value.get(key)
        if isinstance(rows, list):
            summary[key] = rows[:100]
    return summary


def _minimal_heavy_summary(value: dict[str, Any]) -> dict[str, Any]:
    actions = value.get("actions") if isinstance(value.get("actions"), list) else []
    return {
        key: value[key]
        for key in ("ok", "status", "executed", "returncode", "plan_path", "summary_path")
        if key in value
    } | {
        "action_count": len(actions),
        "warning_count": len(value.get("warnings") or []),
        "error_count": len(value.get("errors") or []),
        "blocker_count": len(value.get("blockers") or value.get("blocked_reasons") or []),
    }


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int | float):
        return "number"
    return type(value).__name__
