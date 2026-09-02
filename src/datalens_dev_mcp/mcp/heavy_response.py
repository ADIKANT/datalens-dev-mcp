from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.mcp.response_projection import (
    normalize_response_mode,
    project_active_results,
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
COMPACT_ONLY_HEAVY_TOOL_NAMES = frozenset(
    {
        "dl_generate_editor_bundle",
        "dl_execute_safe_apply",
    }
)
PROJECTED_HEAVY_TOOL_NAMES = HEAVY_TOOL_NAMES | COMPACT_ONLY_HEAVY_TOOL_NAMES
DEFAULT_HEAVY_INLINE_CHAR_BUDGET = 15_000
TASK_TOOL_NAMES = frozenset(
    {
        "dl_task_start",
        "dl_task_resume",
        "dl_task_status",
        "dl_inspect",
        "dl_plan",
        "dl_execute",
        "dl_verify",
        "dl_evidence",
    }
)
DEFAULT_TASK_INLINE_CHAR_BUDGET = 6_000
MAX_TASK_EVIDENCE_INLINE_CHAR_BUDGET = 24_000


def project_task_tool_response(tool_name: str, output: Any) -> Any:
    """Keep autonomous replies compact while preserving task resource bindings."""

    if tool_name not in TASK_TOOL_NAMES or not isinstance(output, dict):
        return output
    sanitized = sanitize_response(output)
    if isinstance(sanitized.get("result_ledger"), list):
        sanitized["active_results"] = project_active_results(sanitized["result_ledger"])
        sanitized["result_ledger_count"] = len(sanitized["result_ledger"])
        sanitized.pop("result_ledger", None)
    budget = MAX_TASK_EVIDENCE_INLINE_CHAR_BUDGET if tool_name == "dl_evidence" else DEFAULT_TASK_INLINE_CHAR_BUDGET
    if serialized_metadata(sanitized)["serialized_chars"] <= budget:
        return sanitized
    resource_uri = str(sanitized.get("resource_uri") or "")
    compact_keys = (
        "ok",
        "task_id",
        "state",
        "task_revision",
        "state_etag",
        "route",
        "route_reason",
        "result",
        "blocked_by",
        "risk",
        "next_action",
        "status",
        "execution_brief",
        "confirmation_action",
        "next_call",
        "missing_fields",
        "plan_hash",
        "plan_resource_uri",
        "safe_apply_ready",
    )
    compact = {key: sanitized[key] for key in compact_keys if key in sanitized}
    compact["resource_uri"] = resource_uri
    compact["inline_truncated"] = True
    compact["full_response"] = serialized_metadata(sanitized)
    return compact


def project_heavy_tool_response(
    tool_name: str,
    output: Any,
    *,
    response_mode: str,
    inline_char_budget: int,
    project_root: str | Path,
    run_id: str = "",
) -> Any:
    if tool_name not in PROJECTED_HEAVY_TOOL_NAMES or not isinstance(output, dict):
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
    active_sanitized = sanitized
    if isinstance(sanitized.get("result_ledger"), list):
        active_sanitized = dict(sanitized)
        active_sanitized["active_results"] = project_active_results(sanitized["result_ledger"])
        active_sanitized["result_ledger_count"] = len(sanitized["result_ledger"])
        active_sanitized.pop("result_ledger", None)
    envelope: dict[str, Any] = {
        "ok": bool(active_sanitized.get("ok", True)),
        "status": str(active_sanitized.get("status") or ""),
        "tool": tool_name,
        "response_mode": mode,
        "requested_response_mode": mode,
        "canonical_artifact": artifact,
        "full_response": metadata,
    }
    for key in ("approved", "request_intent", "delivery_intent_decision", "target_lock", "plan_path"):
        if key in active_sanitized:
            envelope[key] = active_sanitized[key]
    if mode == "artifact":
        return envelope
    envelope["summary"] = _heavy_summary(tool_name, active_sanitized)
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


def _heavy_summary(tool_name: str, value: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "dl_generate_editor_bundle":
        return _editor_bundle_summary(value)
    if tool_name == "dl_execute_safe_apply":
        return _safe_apply_execution_summary(value)
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
        "generation_status",
        "route",
        "family",
        "widget_id",
        "display_title",
        "source_template",
        "source_contract",
        "authoring_profile",
        "render_contract",
        "batch_summary",
        "browser_qa_plan",
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
        action_contracts = []
        for item in actions[:100]:
            if not isinstance(item, dict):
                continue
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            action_contracts.append(
                {
                    "method": str(item.get("method") or item.get("action") or ""),
                    "safety_guard_mode": str(item.get("mode") or ""),
                    "write_mode": str(payload.get("mode") or ""),
                    "readback_branch": str(
                        item.get("readback_branch")
                        or payload.get("readback_branch")
                        or ("published" if payload.get("mode") == "publish" else "saved" if payload.get("mode") == "save" else "")
                    ),
                }
            )
        summary["action_contracts"] = action_contracts
        summary["write_modes"] = sorted({item["write_mode"] for item in action_contracts if item["write_mode"]})
        summary["readback_branches"] = sorted(
            {item["readback_branch"] for item in action_contracts if item["readback_branch"]}
        )
        if any(item["safety_guard_mode"] == "save" and item["write_mode"] == "publish" for item in action_contracts):
            summary["top_level_mode_contract"] = "safety_guard_save; payload.mode controls the publish RPC"
    for key in ("expected_artifacts", "evidence_paths", "saved_readback_paths", "published_readback_paths"):
        rows = value.get(key)
        if isinstance(rows, list):
            summary[key] = rows[:100]
    tabs = value.get("tabs") if isinstance(value.get("tabs"), dict) else {}
    if tabs:
        summary["tab_names"] = sorted(tabs)
        summary["tab_count"] = len(tabs)
    results = value.get("results") if isinstance(value.get("results"), list) else []
    if results:
        summary["result_count"] = len(results)
        summary["results"] = [
            {
                key: item[key]
                for key in (
                    "widget_id",
                    "ok",
                    "generation_status",
                    "route",
                    "family",
                    "bundle_path",
                    "compiled_tabs_sha256",
                )
                if key in item
            }
            for item in results[:100]
            if isinstance(item, dict)
        ]
    return summary


def _editor_bundle_summary(value: dict[str, Any]) -> dict[str, Any]:
    profile = value.get("authoring_profile") if isinstance(value.get("authoring_profile"), dict) else {}
    render_contract = value.get("render_contract") if isinstance(value.get("render_contract"), dict) else {}
    source_contract = value.get("source_contract") if isinstance(value.get("source_contract"), dict) else {}
    provenance = value.get("template_provenance") if isinstance(value.get("template_provenance"), dict) else {}
    browser_plan = value.get("browser_qa_plan") if isinstance(value.get("browser_qa_plan"), dict) else {}
    results = value.get("results") if isinstance(value.get("results"), list) else []
    summary: dict[str, Any] = {
        key: value[key]
        for key in (
            "ok",
            "status",
            "generation_status",
            "widget_id",
            "display_title",
            "route",
            "family",
            "source_template",
            "manifest_path",
            "full_bundles",
            "batch_summary",
        )
        if key in value
    }
    tabs = value.get("tabs") if isinstance(value.get("tabs"), dict) else {}
    if tabs:
        summary["tabs"] = sorted(tabs)
        summary["tab_count"] = len(tabs)
    if profile:
        summary["authoring_profile"] = {
            key: profile[key]
            for key in (
                "id",
                "enforced",
                "exact_template_reused",
                "template_set_sha256",
                "style_contract_sha256",
            )
            if key in profile
        }
    if render_contract:
        summary["render_contract"] = {
            key: render_contract[key]
            for key in (
                "profile_id",
                "adapter_id",
                "density",
                "composite_sha256",
            )
            if key in render_contract
        }
    if source_contract:
        summary["source_contract"] = {
            "status": source_contract.get("status"),
            "production_ready": source_contract.get("production_ready"),
            "issue_count": len(source_contract.get("issues") or []),
            "missing_output_columns": list(source_contract.get("missing_output_columns") or [])[:20],
        }
    if provenance:
        summary["compiled_tabs_sha256"] = provenance.get("compiled_tabs_sha256")
    if browser_plan:
        summary["browser_qa_plan"] = {
            key: browser_plan[key]
            for key in ("schema_id", "plan_sha256", "artifact_path", "max_browser_calls")
            if key in browser_plan
        }
    if results:
        summary["results"] = [
            {
                key: item[key]
                for key in (
                    "widget_id",
                    "ok",
                    "generation_status",
                    "route",
                    "family",
                    "bundle_path",
                    "compiled_tabs_sha256",
                    "render_contract_sha256",
                )
                if key in item
            }
            for item in results[:100]
            if isinstance(item, dict)
        ]
    return summary


def _safe_apply_execution_summary(value: dict[str, Any]) -> dict[str, Any]:
    delivery = value.get("delivery_result") if isinstance(value.get("delivery_result"), dict) else {}
    save_results = value.get("results") if isinstance(value.get("results"), list) else []
    publish_results = (
        delivery.get("publish_results")
        if isinstance(delivery.get("publish_results"), list)
        else value.get("publish_results")
        if isinstance(value.get("publish_results"), list)
        else []
    )
    summary: dict[str, Any] = {
        key: value[key]
        for key in (
            "ok",
            "status",
            "executed",
            "plan_path",
            "safe_apply_id",
            "saved_readback_paths",
            "published_readback_paths",
            "saved_readback_errors",
            "published_readback_errors",
            "publish_blocked_reasons",
            "proof_levels",
            "execution_metrics",
        )
        if key in value
    }
    summary["counts"] = {
        "save_results": len(save_results),
        "publish_results": len(publish_results),
        "saved_readbacks": len(value.get("saved_readback_paths") or []),
        "published_readbacks": len(value.get("published_readback_paths") or []),
        "errors": len(value.get("errors") or [])
        + len(value.get("saved_readback_errors") or [])
        + len(value.get("published_readback_errors") or []),
    }
    if delivery:
        summary["delivery"] = {
            key: delivery[key]
            for key in (
                "state",
                "saved",
                "published",
                "publish_blocked_reasons",
                "approval_reuse",
            )
            if key in delivery
        }
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
