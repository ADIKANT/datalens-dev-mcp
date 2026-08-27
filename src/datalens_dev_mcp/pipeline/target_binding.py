from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


TARGET_BINDING_SCHEMA_ID = "datalens_target_binding"


def resolve_contract_target_binding(contract: dict[str, Any]) -> dict[str, Any]:
    target = contract.get("target") or {}
    payload = {
        "schema_id": TARGET_BINDING_SCHEMA_ID,
        "source": "task_contract",
        "workbook_id": str(target.get("workbook_id") or ""),
        "dashboard_id": str(target.get("dashboard_id") or ""),
        "object_ids": sorted(str(item) for item in target.get("object_ids") or []),
        "object_types": sorted(str(item) for item in target.get("object_types") or []),
        "saved_revision": str(target.get("saved_revision") or ""),
        "published_revision": str(target.get("published_revision") or ""),
        "payload_hash": str(target.get("payload_hash") or ""),
        "layout_hash": str(target.get("layout_hash") or ""),
        "tabs_hash": str(target.get("tabs_hash") or ""),
        "technology": str(target.get("technology") or ""),
        "target_graph_hash": str(target.get("target_graph_hash") or ""),
    }
    payload["binding_hash"] = target_binding_hash(payload)
    return payload


def create_live_target_binding(
    *,
    workbook_id: str,
    dashboard_id: str,
    object_ids: list[str],
    object_types: list[str],
    saved_revision: str,
    published_revision: str,
    payload_hash: str,
    layout_hash: str,
    tabs_hash: str,
    technology: str,
    target_graph_hash: str,
) -> dict[str, Any]:
    payload = {
        "schema_id": TARGET_BINDING_SCHEMA_ID,
        "source": "live_discovery",
        "workbook_id": str(workbook_id or ""),
        "dashboard_id": str(dashboard_id or ""),
        "object_ids": sorted(set(str(item) for item in object_ids if item)),
        "object_types": sorted(set(str(item) for item in object_types if item)),
        "saved_revision": str(saved_revision or ""),
        "published_revision": str(published_revision or ""),
        "payload_hash": str(payload_hash or ""),
        "layout_hash": str(layout_hash or ""),
        "tabs_hash": str(tabs_hash or ""),
        "technology": str(technology or ""),
        "target_graph_hash": str(target_graph_hash or ""),
    }
    payload["binding_hash"] = target_binding_hash(payload)
    return payload


def target_binding_hash(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("binding_hash", None)
    return canonical_hash(material)


def validate_target_binding(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != TARGET_BINDING_SCHEMA_ID:
        issues.append("target binding schema_id is invalid")
    supplied = str(value.get("binding_hash") or "")
    if not supplied or supplied != target_binding_hash(value):
        issues.append("target binding hash mismatch")
    return tuple(issues)
