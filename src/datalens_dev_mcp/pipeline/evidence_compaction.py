from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import write_json
from datalens_dev_mcp.pipeline.result_dedup import ACTIVE_CONTEXT_RESULTS
from datalens_dev_mcp.serialization import serialized_metadata, stable_sha256
from datalens_dev_mcp.validators.redaction import sanitize_value


VOLATILE_KEYS = frozenset({"timestamp", "updated_at", "polled_at", "elapsed_ms", "request_id", "trace_id"})


def compact_task_evidence(
    *,
    policy_version: str,
    task_contract: dict[str, Any],
    target_binding: dict[str, Any] | None,
    style_binding: dict[str, Any] | None,
    checkpoint: dict[str, Any],
    build_identity: dict[str, Any] | None = None,
    task_identity: dict[str, Any] | None = None,
    last_state_change: Any = None,
    active_blocker: Any = None,
    active_hypothesis: str = "",
    next_transition: str = "",
    results: list[dict[str, Any]] | None = None,
    artifact_root: str | Path | None = None,
    inline_char_budget: int = 6000,
) -> dict[str, Any]:
    stable = sanitize_value(
        {
            "server_policy_version": policy_version,
            "task_contract": task_contract,
            "build_identity": build_identity or {},
            "task_identity": task_identity or {},
            "target_binding": target_binding or {},
            "style_binding": style_binding or {},
            "current_checkpoint": _stable_value(checkpoint),
        }
    )
    active_results = [
        record for record in (results or []) if record.get("classification", "material") in ACTIVE_CONTEXT_RESULTS
    ]
    volatile_tail = sanitize_value(
        {
            "last_state_change": last_state_change,
            "active_blocker": active_blocker,
            "active_hypothesis": active_hypothesis,
            "next_transition": next_transition,
            "active_results": active_results[-5:],
        }
    )
    payload = {
        "schema_id": "datalens_compact_evidence",
        "stable_context": stable,
        "stable_context_sha256": stable_sha256(stable),
        "volatile_tail": volatile_tail,
    }
    metadata = serialized_metadata(payload)
    if metadata["serialized_chars"] <= max(1000, inline_char_budget) or artifact_root is None:
        return {**payload, "full_evidence": metadata}
    root = Path(artifact_root)
    digest = metadata["sha256"]
    path = root / "evidence" / f"compact-evidence-{digest[:16]}.json"
    write_json(path, payload)
    synopsis = {
        "state": checkpoint.get("current_state", ""),
        "next_transition": next_transition,
        "active_blocker": bool(active_blocker),
    }
    return {
        "schema_id": payload["schema_id"],
        "stable_context_sha256": payload["stable_context_sha256"],
        "volatile_tail": volatile_tail,
        "full_evidence": {
            **metadata,
            "uri": f"artifact://{path.as_posix()}",
            "synopsis": synopsis,
        },
    }


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable_value(item) for key, item in sorted(value.items()) if key not in VOLATILE_KEYS}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    return value
