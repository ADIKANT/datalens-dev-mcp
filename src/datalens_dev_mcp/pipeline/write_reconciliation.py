from __future__ import annotations

from collections.abc import Callable
from typing import Any


def reconcile_objects(
    expected_objects: list[dict[str, Any]],
    *,
    read_object: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Classify every target by read only; an uncertain write is never replayed."""

    statuses: list[dict[str, Any]] = []
    for expected in expected_objects:
        evidence = read_object(expected)
        statuses.append(
            {
                "object_id": str(expected.get("object_id") or ""),
                "status": "matched" if evidence.get("content_equivalent") else "mismatch",
                "revision": str(evidence.get("revision") or ""),
                "payload_hash": str(evidence.get("payload_hash") or ""),
                "diff_paths": list(evidence.get("diff_paths") or []),
            }
        )
    matched = bool(statuses) and all(item["status"] == "matched" for item in statuses)
    return {
        "ok": matched,
        "status": "matched" if matched else "blocked",
        "object_statuses": statuses,
        "write_replayed": False,
        "reason": "provider state matches the expected materialization" if matched else "provider state is incomplete or differs",
    }
