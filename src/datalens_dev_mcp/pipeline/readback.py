from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
        "schema_version": "2026-05-25.readback.v1",
        "target": target,
        "mode": normalized_mode,
        "proof_level": normalized_proof_level if normalized_mode != "none" else "source_static",
        "read_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "skipped" if normalized_mode == "none" else ("read" if response is not None else "not_executed"),
        "skipped_reason": skipped_reason if normalized_mode == "none" else "",
        "response_keys": sorted(response.keys()) if isinstance(response, dict) else [],
    }
