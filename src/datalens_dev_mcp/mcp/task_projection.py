from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.task_state_projection import public_task_state, task_state_etag
from datalens_dev_mcp.pipeline.workflow_replay import read_event_chain
from datalens_dev_mcp.pipeline.workflow_state import WorkflowState


def project_task_summary(
    *,
    contract: dict[str, Any],
    state: WorkflowState,
    events_path: str | Path,
    resource_uri: str,
    performed_after: int = 0,
    target_binding: dict[str, Any] | None = None,
    style_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events, corrupt_tail = read_event_chain(events_path)
    selected = [event for event in events if int(event.get("event_id") or 0) > performed_after]
    performed = [str(event.get("transition") or "") for event in selected if event.get("status") == "success"]
    observed = _observed_facts(selected)
    blocker = state.blocker or None
    terminal = state.current_state in {"COMPLETED", "BLOCKED", "BLOCKED_CONFLICT", "FAILED"}
    projected = {
        "task_id": state.task_id,
        "state": public_task_state(state.current_state),
        "task_revision": state.revision,
        "contract_revision": int(contract.get("contract_revision") or 1),
        "scope_revision": int(contract.get("scope_revision") or 1),
        "authorization_revision": int(contract.get("authorization_revision") or 1),
        "contract_hash": str(contract.get("contract_hash") or ""),
        "state_etag": task_state_etag(state),
        "observed_facts": observed,
        "route": _resolved_route(contract, target_binding=target_binding, style_binding=style_binding),
        "operation_kind": str(contract.get("operation_kind") or "inspect"),
        "effect": contract.get("effect") or {},
        "verification": _verification_projection(contract),
        "route_reason": (
            "bound to fresh target/style evidence"
            if target_binding or style_binding
            else "compiled from the immutable task contract"
        ),
        "target_binding_hash": str((target_binding or {}).get("binding_hash") or ""),
        "style_binding_hash": str((style_binding or {}).get("binding_hash") or ""),
        "decision_context_hash": str((style_binding or {}).get("decision_context_hash") or ""),
        "project_profile_hash": str((style_binding or {}).get("project_profile_hash") or ""),
        "accepted_exemplar_hash": str((style_binding or {}).get("accepted_exemplar_hash") or ""),
        "performed": performed,
        "result": _result_summary(state),
        "not_performed": _not_performed(contract, state),
        "blocked_by": blocker,
        "risk": _risk_summary(contract, state, corrupt_tail=corrupt_tail),
        "next_action": "" if terminal else _next_action(state, contract),
        "resource_uri": resource_uri,
    }
    projected["execution_brief"] = compact_execution_brief(
        contract,
        state,
        project_root=str((contract.get("workspace") or {}).get("project_root") or ""),
        state_etag=projected["state_etag"],
        target_binding=target_binding,
    )
    return projected


def compact_task_status(
    contract: dict[str, Any],
    state: WorkflowState,
    *,
    resource_uri: str,
    target_binding: dict[str, Any] | None = None,
    style_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    terminal = state.current_state in {"COMPLETED", "BLOCKED", "BLOCKED_CONFLICT", "FAILED"}
    projected = {
        "task_id": state.task_id,
        "state": public_task_state(state.current_state),
        "task_revision": state.revision,
        "contract_revision": int(contract.get("contract_revision") or 1),
        "scope_revision": int(contract.get("scope_revision") or 1),
        "authorization_revision": int(contract.get("authorization_revision") or 1),
        "contract_hash": str(contract.get("contract_hash") or ""),
        "state_etag": task_state_etag(state),
        "route": _resolved_route(contract, target_binding=target_binding, style_binding=style_binding),
        "operation_kind": str(contract.get("operation_kind") or "inspect"),
        "effect": contract.get("effect") or {},
        "verification": _verification_projection(contract),
        "target_binding_hash": str((target_binding or {}).get("binding_hash") or ""),
        "style_binding_hash": str((style_binding or {}).get("binding_hash") or ""),
        "decision_context_hash": str((style_binding or {}).get("decision_context_hash") or ""),
        "project_profile_hash": str((style_binding or {}).get("project_profile_hash") or ""),
        "accepted_exemplar_hash": str((style_binding or {}).get("accepted_exemplar_hash") or ""),
        "blocked_by": state.blocker or None,
        "next_action": "" if terminal else _next_action(state, contract),
        "resource_uri": resource_uri,
    }
    projected["execution_brief"] = compact_execution_brief(
        contract,
        state,
        project_root=str((contract.get("workspace") or {}).get("project_root") or ""),
        state_etag=projected["state_etag"],
        target_binding=target_binding,
    )
    return projected


def compact_execution_brief(
    contract: dict[str, Any],
    state: WorkflowState,
    *,
    project_root: str,
    state_etag: str,
    plan_hash: str = "",
    missing_fields: list[str] | None = None,
    target_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project one authoritative, schema-ready model execution brief."""

    target = dict(contract.get("target") or {})
    live_target = target_binding or {}
    for key in ("workbook_id", "dashboard_id", "object_ids", "object_types", "technology"):
        if live_target.get(key):
            target[key] = live_target[key]
    reference = contract.get("reference") or {}
    delivery = contract.get("delivery") or {}
    diagnostics = contract.get("data_diagnostics") or {}
    browser = contract.get("browser_policy") or {}
    confirmation = contract.get("confirmation") or {}
    public_state = public_task_state(state.current_state)
    terminal = state.current_state in {"COMPLETED", "BLOCKED", "BLOCKED_CONFLICT", "FAILED"}
    confirmation_already_consumed = state.current_state in {
        "SAVED", "SAVED_READBACK", "PUBLISHED", "PUBLISHED_READBACK", "QA_COMPLETED", "COMPLETED",
    }
    confirmation_required = bool(confirmation.get("required") and not confirmation_already_consumed)
    needs_confirmation = bool(confirmation_required and state.current_state == "VALIDATED")
    missing = list(dict.fromkeys(str(item) for item in (missing_fields or []) if str(item)))
    if state.current_state == "VALIDATED" and not plan_hash:
        missing.append("plan_hash")
    if state.current_state == "BLOCKED":
        missing.extend(str(item) for item in (state.blocker or {}).get("missing_facts") or [])
    missing = list(dict.fromkeys(missing))
    next_call: dict[str, Any] | None = None
    if not terminal and not missing:
        if state.current_state == "VALIDATED" and confirmation_required:
            next_call = None
        elif state.current_state == "VALIDATED" and bool(
            delivery.get("save") or delivery.get("publish") or delivery.get("destructive")
        ):
            execute_arguments = {
                "task_id": state.task_id,
                "plan_hash": plan_hash,
                "project_root": project_root,
                "stop_after": "completed",
            }
            if delivery.get("destructive"):
                execute_arguments["destructive_token"] = f"DELETE:{state.task_id}:{plan_hash[:12]}"
            next_call = {
                "tool": "dl_execute",
                "arguments": execute_arguments,
            }
        elif state.current_state == "VALIDATED":
            next_call = {
                "tool": "dl_verify",
                "arguments": {
                    "task_id": state.task_id,
                    "proof_target": "completion",
                    "project_root": project_root,
                },
            }
        else:
            next_call = {
                "tool": "dl_task_resume",
                "arguments": {
                    "task_id": state.task_id,
                    "project_root": project_root,
                    "expected_state": public_state,
                    "expected_hash": state_etag,
                    "expected_contract_revision": int(contract.get("contract_revision") or 1),
                    "run_until": "completed",
                },
            }
    confirmation_action: dict[str, Any] | None = None
    if needs_confirmation and not missing:
        confirmation_action = {
            "tool": "dl_task_resume",
            "fixed_arguments": {
                "task_id": state.task_id,
                "project_root": project_root,
                "expected_state": public_state,
                "expected_hash": state_etag,
                "expected_contract_revision": int(contract.get("contract_revision") or 1),
                "run_until": "completed",
            },
            "user_confirmation_field": "follow_up",
        }
    return {
        "status": (
            "needs_input" if missing else
            "needs_confirmation" if needs_confirmation else
            "blocked" if terminal and state.blocker else
            "ready"
        ),
        "task_kind": str(contract.get("task_kind") or "inspect_dashboard"),
        "project_root": project_root,
        "target": {
            "workbook_id": str(target.get("workbook_id") or ""),
            "dashboard_id": str(target.get("dashboard_id") or ""),
            "object_ids": list(target.get("object_ids") or []),
            "object_types": list(target.get("object_types") or []),
        },
        "references": ([reference] if reference.get("locator") else []),
        "technology": str(target.get("technology") or contract.get("route") or ""),
        "requested_outcome": str(contract.get("requested_outcome") or ""),
        "planned_changes": _planned_changes(contract),
        "preserve": list((contract.get("scope") or {}).get("forbidden_changes") or []),
        "read_scope": list(target.get("object_ids") or []),
        "delivery": {
            "save": bool(delivery.get("save")),
            "publish": bool(delivery.get("publish")),
        },
        "data_checks": list(diagnostics.get("reason_classes") or []) if diagnostics.get("required") else [],
        "visual_checks": [str(browser.get("purpose") or "")] if browser.get("mode") == "required" else [],
        "confirmation_required": confirmation_required,
        "confirmation_kind": str(confirmation.get("kind") or "none"),
        "confirmation_action": confirmation_action,
        "missing_fields": missing,
        "next_call": next_call,
    }


def _planned_changes(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in contract.get("acceptance") or []:
        if not isinstance(item, dict) or item.get("kind") != "semantic_change":
            continue
        try:
            import json

            value = json.loads(str(item.get("statement") or ""))
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        rows.append(
            {
                key: value[key]
                for key in ("target_id", "object_id", "tab", "slot_id", "category", "operation")
                if key in value
            }
        )
    return rows[:20]


def _observed_facts(events: list[dict[str, Any]]) -> list[str]:
    facts: list[str] = []
    for event in events:
        details = event.get("details") or {}
        for fact in details.get("observed_facts") or []:
            text = str(fact).strip()
            if text and text not in facts:
                facts.append(text)
    return facts[:20]


def _result_summary(state: WorkflowState) -> dict[str, Any]:
    return {
        "status": public_task_state(state.current_state).lower(),
        "completed_transition_count": len(state.completed_transitions),
        "receipt_count": len(state.receipt_uris),
    }


def _not_performed(contract: dict[str, Any], state: WorkflowState) -> list[str]:
    delivery = contract.get("delivery") or {}
    rows: list[str] = []
    if not delivery.get("save"):
        rows.append("save")
    if not delivery.get("publish"):
        rows.append("publish")
    if state.current_state not in {"COMPLETED", "PUBLISHED", "PUBLISHED_READBACK", "QA_COMPLETED"}:
        rows.append("remaining workflow transitions")
    return rows


def _risk_summary(contract: dict[str, Any], state: WorkflowState, *, corrupt_tail: bool) -> str:
    if corrupt_tail:
        return "The last event was corrupt and excluded from replay."
    if state.blocker:
        return str(state.blocker.get("reason") or "Task is blocked.")
    if (contract.get("delivery") or {}).get("destructive"):
        return "Destructive scope requires an exact task-bound token."
    return "No unresolved workflow risk is recorded."


def _next_action(state: WorkflowState, contract: dict[str, Any]) -> str:
    if state.current_state == "VALIDATED":
        return "dl_execute" if (contract.get("delivery") or {}).get("save") else "dl_verify"
    return "dl_task_resume"


def _resolved_route(
    contract: dict[str, Any],
    *,
    target_binding: dict[str, Any] | None,
    style_binding: dict[str, Any] | None,
) -> str:
    contract_route = str(contract.get("route") or "")
    if int(contract.get("contract_revision") or 1) > 1 and contract_route:
        return contract_route
    return str(
        (style_binding or {}).get("technology")
        or (target_binding or {}).get("technology")
        or contract_route
        or ""
    )


def _verification_projection(contract: dict[str, Any]) -> dict[str, Any]:
    verification = contract.get("verification") or {}
    return {
        "required_live_reads": list(verification.get("required_live_reads") or []),
        "acceptance_count": len(contract.get("acceptance") or []),
        "remediation_enabled": bool(verification.get("remediation_enabled", False)),
        "remediation_requires_new_user_scope": bool(
            verification.get("remediation_requires_new_user_scope", True)
        ),
    }
