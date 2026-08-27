from __future__ import annotations

from typing import Any

from datalens_dev_mcp import __version__
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


STAGE_RECEIPT_SCHEMA_ID = "datalens_task_stage_receipt"
STAGE_STATUSES = frozenset({"success", "blocked", "conflict", "ambiguous", "failed"})


def build_stage_receipt(
    *,
    task_id: str,
    contract_hash: str,
    transition: str,
    status: str,
    proof_level: str = "source_static",
    target_binding_hash: str = "",
    input_hashes: dict[str, str] | None = None,
    output_hashes: dict[str, str] | None = None,
    provider_calls: list[dict[str, Any]] | None = None,
    hard_requirements: list[str] | None = None,
    missing_requirements: list[str] | None = None,
    reason: str = "",
    observed_facts: list[str] | None = None,
) -> dict[str, Any]:
    normalized = status if status in STAGE_STATUSES else "failed"
    missing = list(missing_requirements or [])
    payload = {
        "schema_id": STAGE_RECEIPT_SCHEMA_ID,
        "receipt_version": 1,
        "task_id": task_id,
        "contract_hash": contract_hash,
        "transition": transition,
        "status": normalized,
        "build_identity_hash": canonical_hash({"package": "datalens-dev-mcp", "version": __version__}),
        "target_binding_hash": target_binding_hash,
        "input_hashes": dict(input_hashes or {}),
        "output_hashes": dict(output_hashes or {}),
        "proof_level": proof_level,
        "provider_calls": list(provider_calls or []),
        "freshness": {"observed_at": "", "saved_revision": "", "published_revision": ""},
        "hard_requirements": list(hard_requirements or []),
        "missing_requirements": missing,
        "artifact_uri": "",
        "artifact_sha256": "",
        "ok": normalized == "success" and not missing,
        "reason": reason,
        "observed_facts": list(observed_facts or []),
    }
    return payload


def validate_stage_receipt(receipt: dict[str, Any], *, task_id: str, contract_hash: str, transition: str) -> tuple[str, ...]:
    issues: list[str] = []
    if receipt.get("schema_id") != STAGE_RECEIPT_SCHEMA_ID:
        issues.append("handler did not return a typed stage receipt")
    if receipt.get("receipt_version") != 1:
        issues.append("stage receipt version is unsupported")
    if receipt.get("task_id") != task_id:
        issues.append("stage receipt task_id mismatch")
    if receipt.get("contract_hash") != contract_hash:
        issues.append("stage receipt contract_hash mismatch")
    if receipt.get("transition") != transition:
        issues.append("stage receipt transition mismatch")
    if receipt.get("status") == "success" and receipt.get("ok") is not True:
        issues.append("successful stage receipt must set ok=true")
    if receipt.get("status") == "success" and receipt.get("missing_requirements"):
        issues.append("successful stage receipt has missing requirements")
    return tuple(issues)
