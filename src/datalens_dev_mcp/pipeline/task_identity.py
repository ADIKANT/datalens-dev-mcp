from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.build_identity import validate_build_identity
from datalens_dev_mcp.pipeline.target_binding import validate_target_binding
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


TASK_IDENTITY_SCHEMA_ID = "datalens_task_identity"


def build_task_identity(
    contract: dict[str, Any],
    *,
    build_identity: dict[str, Any],
    target_binding: dict[str, Any],
    style_binding_hash: str = "",
) -> dict[str, Any]:
    workspace = contract.get("workspace") or {}
    payload = {
        "schema_id": TASK_IDENTITY_SCHEMA_ID,
        "project_root": str(Path(str(workspace.get("project_root") or ".")).resolve()),
        "portfolio_subproject": str(workspace.get("portfolio_subproject") or ""),
        "contract_hash": str(contract.get("contract_hash") or ""),
        "build_identity_hash": str(build_identity.get("identity_hash") or ""),
        "target_binding_hash": str(target_binding.get("binding_hash") or ""),
        "style_binding_hash": str(style_binding_hash or ""),
    }
    payload["identity_hash"] = task_identity_hash(payload)
    return payload


def task_identity_hash(value: dict[str, Any]) -> str:
    material = dict(value)
    material.pop("identity_hash", None)
    return canonical_hash(material)


def validate_task_identity(
    value: dict[str, Any],
    *,
    build_identity: dict[str, Any] | None = None,
    target_binding: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != TASK_IDENTITY_SCHEMA_ID:
        issues.append("task identity schema_id is invalid")
    supplied = str(value.get("identity_hash") or "")
    if not supplied or supplied != task_identity_hash(value):
        issues.append("task identity hash mismatch")
    if build_identity is not None:
        issues.extend(validate_build_identity(build_identity))
        if value.get("build_identity_hash") != build_identity.get("identity_hash"):
            issues.append("task build identity hash mismatch")
    if target_binding is not None:
        issues.extend(validate_target_binding(target_binding))
        if value.get("target_binding_hash") != target_binding.get("binding_hash"):
            issues.append("task target binding hash mismatch")
    return tuple(issues)
