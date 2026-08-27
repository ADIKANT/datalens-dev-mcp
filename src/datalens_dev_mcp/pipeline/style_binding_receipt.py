from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


STYLE_BINDING_SCHEMA_ID = "datalens_style_binding_receipt"


def build_style_binding_receipt(
    *,
    source_kind: str,
    reference_binding_hash: str,
    technology: str,
    tab_order: list[str],
    tab_hashes: dict[str, str],
    protected_regions: list[dict[str, Any]],
    semantic_slots: list[dict[str, Any]],
    source_hash: str,
) -> dict[str, Any]:
    payload = {
        "schema_id": STYLE_BINDING_SCHEMA_ID,
        "source_kind": source_kind,
        "reference_binding_hash": reference_binding_hash,
        "technology": technology,
        "tab_order": list(tab_order),
        "tab_hashes": dict(tab_hashes),
        "protected_runtime_hash": canonical_hash(protected_regions),
        "protected_region_count": len(protected_regions),
        "semantic_slot_hash": canonical_hash(semantic_slots),
        "semantic_slot_count": len(semantic_slots),
        "source_hash": source_hash,
    }
    payload["binding_hash"] = style_binding_hash(payload)
    return payload


def style_binding_hash(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("binding_hash", None)
    return canonical_hash(material)


def validate_style_binding_receipt(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != STYLE_BINDING_SCHEMA_ID:
        issues.append("style binding schema_id is invalid")
    supplied = str(value.get("binding_hash") or "")
    if not supplied or supplied != style_binding_hash(value):
        issues.append("style binding hash mismatch")
    return tuple(issues)
