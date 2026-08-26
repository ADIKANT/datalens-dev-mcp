from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import hashlib
import json

from datalens_dev_mcp.pipeline.proof_levels import PROOF_LEVELS

READBACK_MODES = ("none", "minimal", "full", "debug")


def normalize_readback_mode(mode: str | None) -> str:
    normalized = (mode or "minimal").strip().lower()
    if normalized not in READBACK_MODES:
        raise ValueError(f"readback_mode must be one of {READBACK_MODES}")
    return normalized


def build_readback_summary(
    *,
    target: str,
    response: dict[str, Any] | None = None,
    mode: str = "minimal",
    skipped_reason: str = "",
    proof_level: str = "live_read_only_api",
) -> dict[str, Any]:
    normalized_mode = normalize_readback_mode(mode)
    normalized_proof_level = proof_level if proof_level in PROOF_LEVELS else "source_static"
    return {
        "schema_id": "readback",
        "target": target,
        "mode": normalized_mode,
        "proof_level": normalized_proof_level if normalized_mode != "none" else "source_static",
        "read_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "skipped" if normalized_mode == "none" else ("read" if response is not None else "not_executed"),
        "skipped_reason": skipped_reason if normalized_mode == "none" else "",
        "response_keys": sorted(response.keys()) if isinstance(response, dict) else [],
    }


def workflow_readback_result(
    response: dict[str, Any],
    *,
    expected_revision: str = "",
    expected_hash: str = "",
) -> dict[str, Any]:
    """Return a deterministic reconciliation result for saved/published readback."""

    revision = str(response.get("revision") or response.get("revId") or response.get("updatedAt") or "")
    payload = response.get("data") if isinstance(response.get("data"), dict) else response
    actual_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    revision_conflict = bool(expected_revision and revision and revision != expected_revision)
    hash_conflict = bool(expected_hash and actual_hash != expected_hash)
    return {
        "status": "conflict" if revision_conflict or hash_conflict else "matched",
        "expected_revision": expected_revision,
        "actual_revision": revision,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "semantic_diff": {
            "revision_changed": revision_conflict,
            "content_hash_changed": hash_conflict,
        } if revision_conflict or hash_conflict else {},
    }
