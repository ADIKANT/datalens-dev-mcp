from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


def build_dataset_context_binding(profile: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_id": "dataset_context_binding",
        "dataset_context_profile_hash": str(profile.get("profile_hash") or ""),
        "query_set_hash": str(profile.get("query_set_hash") or ""),
        "dataset_schema_hash": str(profile.get("schema_hash") or ""),
        "context_observed_at": str(profile.get("observed_at") or ""),
        "context_limitations": sorted(set((profile.get("sample_scope") or {}).get("limitations") or [])),
    }
    payload["binding_hash"] = _binding_hash(payload)
    return payload


def build_plan_binding(**hashes: str) -> dict[str, Any]:
    payload = {
        "schema_id": "datalens_public_plan_binding",
        **{key: str(value or "") for key, value in sorted(hashes.items())},
    }
    payload["binding_hash"] = _binding_hash(payload)
    return payload


def validate_binding(value: dict[str, Any], *, schema_id: str) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != schema_id:
        issues.append("binding schema_id is invalid")
    if value.get("binding_hash") != _binding_hash(value):
        issues.append("binding hash mismatch")
    for key, item in value.items():
        if key.endswith("_hash") and key != "binding_hash" and (not isinstance(item, str) or len(item) != 64):
            issues.append(f"{key} must be a sha256 value")
    return tuple(issues)


def _binding_hash(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("binding_hash", None)
    return canonical_hash(material)
