from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import validate_event
from datalens_dev_mcp.pipeline.workflow_state import WorkflowState, initial_workflow_state


class WorkflowReplayError(RuntimeError):
    pass


def read_event_chain(path: str | Path) -> tuple[list[dict[str, Any]], bool]:
    source = Path(path)
    if not source.is_file():
        return [], False
    lines = source.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    corrupt_tail = False
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        last = index == len(lines) - 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            if last:
                corrupt_tail = True
                break
            raise WorkflowReplayError(f"event line {index + 1} is not valid JSON") from exc
        issues = validate_event(event, previous=events[-1] if events else None)
        if issues:
            if last:
                corrupt_tail = True
                break
            raise WorkflowReplayError(f"event line {index + 1} failed validation: {'; '.join(issues)}")
        events.append(event)
    return events, corrupt_tail


def replay_workflow(
    *,
    events_path: str | Path,
    task_id: str,
    contract_hash: str,
) -> tuple[WorkflowState, bool]:
    events, corrupt_tail = read_event_chain(events_path)
    state = initial_workflow_state(task_id, contract_hash)
    completed: list[str] = []
    keys: list[str] = []
    receipts: list[str] = []
    blocker: dict[str, Any] = {}
    reconciliation: dict[str, Any] = {}
    current = state.current_state
    next_transition = state.next_transition
    revision = state.revision
    for event in events:
        details = event.get("details") or {}
        current = str(details.get("next_state") or current)
        next_transition = str(details.get("next_transition") or "")
        if event.get("status") == "success":
            completed.append(str(event.get("transition") or ""))
            key = str(event.get("idempotency_key") or "")
            if key:
                keys.append(key)
        receipt = str(event.get("result_receipt") or "")
        if receipt:
            receipts.append(receipt)
        blocker = dict(details.get("blocker") or {})
        reconciliation = dict(details.get("reconciliation") or {})
        revision += 1
    if events:
        last_id = int(events[-1]["event_id"])
        last_hash = str(events[-1]["event_hash"])
    else:
        last_id = 0
        last_hash = ""
    return (
        WorkflowState(
            task_id=task_id,
            contract_hash=contract_hash,
            current_state=current,
            next_transition=next_transition,
            completed_transitions=tuple(completed),
            successful_idempotency_keys=tuple(keys),
            receipt_uris=tuple(dict.fromkeys(receipts)),
            blocker=blocker,
            reconciliation=reconciliation,
            last_event_id=last_id,
            last_event_hash=last_hash,
            revision=revision,
        ),
        corrupt_tail,
    )


def repair_corrupt_event_tail(path: str | Path) -> int:
    events, corrupt_tail = read_event_chain(path)
    if not corrupt_tail:
        return 0
    content = "".join(
        json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for event in events
    )
    source = Path(path)
    temporary = source.with_name(f".{source.name}.repair.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(source)
    return 1
