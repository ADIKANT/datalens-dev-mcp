from __future__ import annotations

from typing import Any

PROOF_LEVELS = (
    "source_static",
    "installed_static",
    "live_read_only_api",
    "save_readback",
    "publish_readback",
    "browser_rendered",
    "controlled_live_write",
)


def proof_level_for_readback_branch(branch: str, *, live_readback: bool = True) -> str:
    if not live_readback:
        return "source_static"
    normalized = str(branch or "").strip().lower()
    if normalized == "published":
        return "publish_readback"
    if normalized == "saved":
        return "save_readback"
    return "live_read_only_api"


def with_proof_level(payload: dict[str, Any], proof_level: str) -> dict[str, Any]:
    result = dict(payload)
    result["proof_level"] = proof_level if proof_level in PROOF_LEVELS else "source_static"
    return result

