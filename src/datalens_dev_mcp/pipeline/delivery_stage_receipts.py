from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

DELIVERY_SCHEMA_IDS = frozenset(
    {
        "datalens_save_stage_receipt",
        "datalens_saved_readback_receipt",
        "datalens_publish_stage_receipt",
        "datalens_published_readback_receipt",
    }
)


def build_delivery_receipt(schema_id: str, **values: Any) -> dict[str, Any]:
    if schema_id not in DELIVERY_SCHEMA_IDS:
        raise ValueError(f"unsupported delivery receipt schema: {schema_id}")
    payload = {
        "schema_id": schema_id,
        "receipt_version": 1,
        "observed_at": str(values.pop("observed_at", "") or _utc_now()),
        **values,
    }
    payload["receipt_hash"] = delivery_receipt_hash(payload)
    return payload


def delivery_receipt_hash(receipt: dict[str, Any]) -> str:
    material = dict(receipt)
    material.pop("receipt_hash", None)
    return canonical_hash(material)


def validate_delivery_receipt(
    receipt: dict[str, Any],
    *,
    schema_id: str,
    task_id: str,
    contract_hash: str,
) -> tuple[str, ...]:
    issues: list[str] = []
    if receipt.get("schema_id") != schema_id:
        issues.append("delivery receipt schema mismatch")
    if receipt.get("receipt_version") != 1:
        issues.append("delivery receipt version is unsupported")
    if receipt.get("task_id") != task_id:
        issues.append("delivery receipt task_id mismatch")
    if receipt.get("contract_hash") != contract_hash:
        issues.append("delivery receipt contract_hash mismatch")
    if receipt.get("receipt_hash") != delivery_receipt_hash(receipt):
        issues.append("delivery receipt hash mismatch")
    return tuple(issues)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
