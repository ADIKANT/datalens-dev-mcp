from __future__ import annotations

from typing import Any

from datalens_dev_mcp.validators.redaction import redact_text, sanitize_value


MAX_CHECKPOINT_BYTES = 8_192


def render_checkpoint(
    *,
    contract: dict[str, Any],
    state: dict[str, Any],
    plan_uris: list[str] | tuple[str, ...] = (),
    completion_criteria: list[str] | tuple[str, ...] = (),
) -> str:
    safe_contract = sanitize_value(contract)
    safe_state = sanitize_value(state)
    target = safe_contract.get("target") or {}
    scope = safe_contract.get("scope") or {}
    lines = [
        "# DataLens task checkpoint",
        "",
        f"- Task: `{safe_contract.get('task_id', '')}`",
        f"- Contract hash: `{safe_contract.get('contract_hash', '')}`",
        f"- Current state: `{safe_state.get('current_state', '')}`",
        f"- Next transition: `{safe_state.get('next_transition', '')}`",
        f"- Workbook: `{target.get('workbook_id', '')}`",
        f"- Dashboard: `{target.get('dashboard_id', '')}`",
        f"- Objects: `{', '.join(target.get('object_ids') or [])}`",
        f"- Forbidden changes: `{', '.join(scope.get('forbidden_changes') or [])}`",
    ]
    completed = safe_state.get("completed_transitions") or []
    if completed:
        lines.extend(("", "## Completed transitions", "", *[f"- {item}" for item in completed]))
    blocker = safe_state.get("blocker") or {}
    if blocker:
        lines.extend(("", "## Current blocker", "", f"- {blocker}"))
    receipts = safe_state.get("receipt_uris") or []
    if plan_uris or receipts:
        lines.extend(("", "## Exact artifacts", "", *[f"- {item}" for item in [*plan_uris, *receipts]]))
    if completion_criteria:
        lines.extend(("", "## Completion criteria", "", *[f"- {item}" for item in completion_criteria]))
    content = redact_text("\n".join(lines) + "\n")
    encoded = content.encode("utf-8")
    if len(encoded) <= MAX_CHECKPOINT_BYTES:
        return content
    marker = "\n- Checkpoint truncated to bounded operator context.\n"
    budget = MAX_CHECKPOINT_BYTES - len(marker.encode("utf-8"))
    return encoded[:budget].decode("utf-8", errors="ignore") + marker
