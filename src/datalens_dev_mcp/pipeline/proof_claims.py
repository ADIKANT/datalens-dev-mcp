from __future__ import annotations

import hashlib
import json
from typing import Any

from datalens_dev_mcp.pipeline.proof_levels import PROOF_LEVELS


def build_proof_claim(
    *,
    claim: str,
    proof_level: str,
    evidence: dict[str, Any] | None = None,
    revision: str = "",
) -> dict[str, Any]:
    normalized_level = proof_level if proof_level in PROOF_LEVELS else "source_static"
    value = evidence if isinstance(evidence, dict) else {}
    issues: list[str] = []
    if normalized_level == "browser_rendered" and value.get("schema_id") != "qa_attestation":
        issues.append("browser_rendered claim requires qa_attestation evidence")
    if normalized_level == "contract_runtime" and value.get("schema_id") != "render_contract_result":
        issues.append("contract_runtime claim requires render_contract_result evidence")
    if revision and str(value.get("revision") or value.get("saved_revision") or "") != revision:
        issues.append("proof evidence revision does not match the claimed revision")
    result = {
        "schema_id": "proof_claim",
        "claim": claim,
        "proof_level": normalized_level,
        "revision": revision,
        "evidence_schema_id": str(value.get("schema_id") or ""),
        "evidence_sha256": _sha256(value),
        "ok": not issues,
        "issues": issues,
    }
    result["sha256"] = _sha256(result)
    return result


def highest_honest_proof_level(claims: list[dict[str, Any]]) -> str:
    valid = [item.get("proof_level") for item in claims if item.get("ok") is True]
    return max(valid, key=PROOF_LEVELS.index) if valid else "source_static"


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
