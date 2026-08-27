from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


REFERENCE_BINDING_SCHEMA_ID = "datalens_reference_binding"


def build_reference_binding(
    *,
    source_kind: str,
    locator_hash: str,
    object_id: str = "",
    revision: str = "",
    source_hash: str = "",
    technology: str = "",
    exact_required: bool = False,
) -> dict[str, Any]:
    payload = {
        "schema_id": REFERENCE_BINDING_SCHEMA_ID,
        "source_kind": source_kind,
        "locator_hash": locator_hash,
        "object_id": object_id,
        "revision": revision,
        "source_hash": source_hash,
        "technology": technology,
        "exact_required": bool(exact_required),
    }
    payload["binding_hash"] = reference_binding_hash(payload)
    return payload


def reference_binding_hash(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("binding_hash", None)
    return canonical_hash(material)


def validate_reference_binding(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != REFERENCE_BINDING_SCHEMA_ID:
        issues.append("reference binding schema_id is invalid")
    supplied = str(value.get("binding_hash") or "")
    if not supplied or supplied != reference_binding_hash(value):
        issues.append("reference binding hash mismatch")
    if value.get("exact_required") and not value.get("source_hash"):
        issues.append("exact reference binding requires a source hash")
    return tuple(issues)
