from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TERMINAL_STATES = frozenset(
    {"COMPLETED", "BLOCKED", "BLOCKED_CONFLICT", "FAILED", "FAILED_ARCHITECTURE_REVIEW_REQUIRED"}
)
WRITE_TRANSITIONS = frozenset({"VALIDATED -> SAVED", "SAVED_READBACK -> PUBLISHED"})


@dataclass(frozen=True)
class WorkflowState:
    schema_id: str = "datalens_workflow_state"
    task_id: str = ""
    contract_hash: str = ""
    current_state: str = "RESOLVED"
    next_transition: str = "RESOLVED -> BASELINE_READ"
    completed_transitions: tuple[str, ...] = ()
    successful_idempotency_keys: tuple[str, ...] = ()
    receipt_uris: tuple[str, ...] = ()
    blocker: dict[str, Any] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    last_event_id: int = 0
    last_event_hash: str = ""
    revision: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> WorkflowState:
        fields = cls.__dataclass_fields__
        payload = {key: value[key] for key in fields if key in value}
        for key in ("completed_transitions", "successful_idempotency_keys", "receipt_uris"):
            if key in payload:
                payload[key] = tuple(payload[key] or ())
        return cls(**payload)


def initial_workflow_state(task_id: str, contract_hash: str) -> WorkflowState:
    return WorkflowState(task_id=task_id, contract_hash=contract_hash)


def transition_name(source: str, target: str) -> str:
    return f"{source} -> {target}"


def transition_target(transition: str) -> str:
    parts = transition.split(" -> ", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"invalid workflow transition: {transition!r}")
    return parts[1]


def is_terminal(state: WorkflowState) -> bool:
    return state.current_state in TERMINAL_STATES
