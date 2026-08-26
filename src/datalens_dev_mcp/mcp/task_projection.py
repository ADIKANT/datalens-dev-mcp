from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.pipeline.workflow_replay import read_event_chain
from datalens_dev_mcp.pipeline.workflow_state import WorkflowState


PUBLIC_STATE_ALIASES = {"VALIDATED": "PLAN_VALIDATED"}


def public_task_state(state: str) -> str:
    return PUBLIC_STATE_ALIASES.get(state, state)


def task_state_etag(state: WorkflowState) -> str:
    return canonical_hash(state.to_dict())


def project_task_summary(
    *,
    contract: dict[str, Any],
    state: WorkflowState,
    events_path: str | Path,
    resource_uri: str,
    performed_after: int = 0,
) -> dict[str, Any]:
    events, corrupt_tail = read_event_chain(events_path)
    selected = [event for event in events if int(event.get("event_id") or 0) > performed_after]
    performed = [str(event.get("transition") or "") for event in selected if event.get("status") == "success"]
    observed = _observed_facts(selected)
    blocker = state.blocker or None
    terminal = state.current_state in {"COMPLETED", "BLOCKED", "BLOCKED_CONFLICT", "FAILED"}
    return {
        "task_id": state.task_id,
        "state": public_task_state(state.current_state),
        "task_revision": state.revision,
        "state_etag": task_state_etag(state),
        "observed_facts": observed,
        "route": str(contract.get("route") or ""),
        "route_reason": "compiled from the immutable task contract",
        "performed": performed,
        "result": _result_summary(state),
        "not_performed": _not_performed(contract, state),
        "blocked_by": blocker,
        "risk": _risk_summary(contract, state, corrupt_tail=corrupt_tail),
        "next_action": "" if terminal else _next_action(state, contract),
        "resource_uri": resource_uri,
    }


def compact_task_status(contract: dict[str, Any], state: WorkflowState, *, resource_uri: str) -> dict[str, Any]:
    terminal = state.current_state in {"COMPLETED", "BLOCKED", "BLOCKED_CONFLICT", "FAILED"}
    return {
        "task_id": state.task_id,
        "state": public_task_state(state.current_state),
        "task_revision": state.revision,
        "state_etag": task_state_etag(state),
        "route": str(contract.get("route") or ""),
        "blocked_by": state.blocker or None,
        "next_action": "" if terminal else _next_action(state, contract),
        "resource_uri": resource_uri,
    }


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
