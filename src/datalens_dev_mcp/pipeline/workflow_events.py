from __future__ import annotations

import hashlib
import json
from typing import Any

from datalens_dev_mcp.validators.redaction import sanitize_value


EVENT_STATUSES = frozenset({"success", "blocked", "retryable", "failed"})


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def event_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    return canonical_hash(payload)


def create_workflow_event(
    *,
    event_id: int,
    previous_hash: str,
    task_id: str,
    transition: str,
    input_value: Any,
    result_receipt: str,
    status: str,
    timestamp: str,
    idempotency_key: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in EVENT_STATUSES:
        raise ValueError(f"unsupported workflow event status: {status}")
    event = {
        "schema_id": "datalens_workflow_event",
        "event_id": event_id,
        "previous_hash": previous_hash,
        "task_id": task_id,
        "transition": transition,
        "input_hash": canonical_hash(sanitize_value(input_value)),
        "result_receipt": str(result_receipt or ""),
        "status": status,
        "timestamp": timestamp,
        "idempotency_key": idempotency_key,
        "details": sanitize_value(details or {}),
    }
    event["event_hash"] = event_hash(event)
    return event


def validate_event(event: dict[str, Any], *, previous: dict[str, Any] | None = None) -> tuple[str, ...]:
    issues: list[str] = []
    if event.get("schema_id") != "datalens_workflow_event":
        issues.append("schema_id is invalid")
    if event.get("status") not in EVENT_STATUSES:
        issues.append("status is invalid")
    if event.get("event_hash") != event_hash(event):
        issues.append("event_hash does not match event content")
    if previous is None:
        if event.get("event_id") != 1 or event.get("previous_hash") not in {"", None}:
            issues.append("first event must start the hash chain")
    else:
        if event.get("event_id") != int(previous.get("event_id") or 0) + 1:
            issues.append("event_id is not monotonic")
        if event.get("previous_hash") != previous.get("event_hash"):
            issues.append("previous_hash does not match")
        if event.get("task_id") != previous.get("task_id"):
            issues.append("task_id changed inside the event chain")
    return tuple(issues)
