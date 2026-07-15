from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from datalens_dev_mcp.pipeline.proof_levels import proof_level_for_readback_branch


def build_deployment_report(
    *,
    safe_apply_result: dict[str, Any],
    validation: dict[str, Any],
    readback_mode: str = "minimal",
    readback_branch: str = "saved",
) -> dict[str, Any]:
    write_executed = bool(safe_apply_result.get("executed"))
    readback_required = readback_mode != "none"
    readback_proof_level = proof_level_for_readback_branch(readback_branch, live_readback=readback_required)
    proof_levels = ["source_static"]
    if readback_required:
        proof_levels.append(readback_proof_level)
    if write_executed:
        proof_levels.append("controlled_live_write")
    return {
        "schema_version": "2026-05-25.deployment_report.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "proof_level": "controlled_live_write" if write_executed else readback_proof_level,
        "proof_levels": sorted(dict.fromkeys(proof_levels)),
        "write_proof_level": "controlled_live_write" if write_executed else "source_static",
        "readback_proof_level": readback_proof_level,
        "validation_proof_level": "source_static",
        "write_executed": write_executed,
        "blocked_reasons": safe_apply_result.get("blocked_reasons", []),
        "validation_status": validation.get("status", "unknown"),
        "readback_mode": readback_mode,
        "readback_required": readback_required,
        "publish_included": False,
    }
