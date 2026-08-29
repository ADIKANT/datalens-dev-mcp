from __future__ import annotations

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.pipeline.workflow_state import WorkflowState


PUBLIC_STATE_ALIASES = {"VALIDATED": "PLAN_VALIDATED"}


def public_task_state(state: str) -> str:
    return PUBLIC_STATE_ALIASES.get(state, state)


def task_state_etag(state: WorkflowState) -> str:
    return canonical_hash(state.to_dict())
