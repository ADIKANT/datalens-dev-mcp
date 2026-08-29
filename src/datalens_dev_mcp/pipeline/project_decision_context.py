from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

DECISION_CONTEXT_SCHEMA_ID = "datalens_project_decision_context"
PROJECT_MANIFEST_NAMES = (".datalens-mcp.json", "datalens-mcp.project.json")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def resolve_project_decision_context(
    contract: dict[str, Any],
    *,
    target_graph: dict[str, Any],
) -> dict[str, Any]:
    """Resolve one project-local, hash-locked decision descriptor.

    This extends the existing reference/style binding owner. The descriptor is
    data, not executable policy, and must stay inside the declared project.
    """

    root = Path(str((contract.get("workspace") or {}).get("project_root") or ".")).resolve()
    manifest = _project_manifest(root)
    declaration = manifest.get("decision_context") if isinstance(manifest, dict) else None
    if not isinstance(declaration, dict):
        return {"status": "inactive", "active": False, "accepted_exemplar_selection": "none"}
    locator = str(declaration.get("descriptor_path") or "").strip()
    expected_sha256 = str(declaration.get("sha256") or "").strip().lower()
    if not locator or not SHA256_RE.fullmatch(expected_sha256):
        return _error("decision_context requires descriptor_path and a lowercase SHA-256 lock")
    candidate = Path(locator)
    if candidate.is_absolute():
        return _error("decision_context descriptor_path must be project-relative")
    descriptor_path = (root / candidate).resolve()
    if descriptor_path != root and root not in descriptor_path.parents:
        return _error("decision_context descriptor_path escapes project_root")
    if not descriptor_path.is_file():
        return _error("decision_context descriptor is missing")
    actual_sha256 = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        return _error("decision_context descriptor SHA-256 lock mismatch")
    descriptor = read_json(descriptor_path, {}) or {}
    issues = validate_project_decision_context(descriptor)
    if issues:
        return _error("invalid decision_context descriptor: " + "; ".join(issues))
    if not _target_matches(descriptor, contract=contract, target_graph=target_graph):
        return _error("decision_context target does not match the current project target")
    profile = dict(descriptor["profile"])
    exemplar = _select_exemplar(descriptor, contract=contract, target_graph=target_graph)
    corrections = [
        dict(item)
        for item in descriptor.get("corrections") or []
        if isinstance(item, dict) and item.get("status") == "active"
    ]
    bounded_decisions = {
        key: profile[key]
        for key in (
            "accepted_layout",
            "selector_semantics",
            "title_hint_policy",
            "date_policy",
            "empty_state_policy",
            "superseded_decisions",
        )
        if key in profile
    }
    bounded_decisions["active_corrections"] = [
        str(item.get("statement") or "") for item in corrections if str(item.get("statement") or "")
    ]
    # Keep stable order for public projection and hashing.
    bounded_decisions = {
        key: bounded_decisions[key]
        for key in (
            "accepted_layout",
            "selector_semantics",
            "title_hint_policy",
            "date_policy",
            "empty_state_policy",
            "active_corrections",
            "superseded_decisions",
        )
        if key in bounded_decisions
    }
    source_hashes = sorted(
        {
            *[str(value) for value in descriptor.get("source_hashes") or []],
            *[str(item.get("source_sha256") or "") for item in corrections],
            *([str((exemplar.get("source") or {}).get("sha256") or "")] if exemplar else []),
        }
        - {""}
    )
    payload: dict[str, Any] = {
        "schema_id": "datalens_project_decision_context_binding",
        "active": True,
        "project_id": str(descriptor.get("project_id") or ""),
        "descriptor_sha256": actual_sha256,
        "project_profile_hash": canonical_hash(profile),
        "accepted_exemplar_selection": "selected" if exemplar else "none",
        "accepted_exemplar_id": str((exemplar or {}).get("exemplar_id") or ""),
        "accepted_exemplar_hash": canonical_hash(exemplar) if exemplar else "",
        "correction_set_hash": canonical_hash(corrections),
        "bounded_decisions": bounded_decisions,
        "source_hashes": source_hashes,
    }
    payload["context_hash"] = canonical_hash(payload)
    return {"status": "success", **payload}


def validate_project_decision_context(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != DECISION_CONTEXT_SCHEMA_ID:
        issues.append(f"schema_id must be {DECISION_CONTEXT_SCHEMA_ID}")
    if value.get("context_version") != 1:
        issues.append("context_version must equal 1")
    if not str(value.get("project_id") or "").strip():
        issues.append("project_id is required")
    if not isinstance(value.get("profile"), dict) or not value.get("profile"):
        issues.append("profile must be a non-empty object")
    match = value.get("match")
    if not isinstance(match, dict) or not any(match.get(key) for key in ("workbook_ids", "dashboard_ids")):
        issues.append("match must declare workbook_ids or dashboard_ids")
    for index, item in enumerate(value.get("accepted_exemplars") or []):
        if not isinstance(item, dict) or not str(item.get("exemplar_id") or ""):
            issues.append(f"accepted_exemplars[{index}] is invalid")
    hashes = [str(item) for item in value.get("source_hashes") or []]
    hashes.extend(
        str(item.get("source_sha256") or "")
        for item in value.get("corrections") or []
        if isinstance(item, dict) and item.get("source_sha256")
    )
    if any(not SHA256_RE.fullmatch(item) for item in hashes):
        issues.append("source hashes must be lowercase SHA-256 values")
    return tuple(dict.fromkeys(issues))


def _project_manifest(root: Path) -> dict[str, Any]:
    for name in PROJECT_MANIFEST_NAMES:
        path = root / name
        if path.is_file():
            value = read_json(path, {}) or {}
            return value if isinstance(value, dict) else {}
    return {}


def _target_matches(
    descriptor: dict[str, Any],
    *,
    contract: dict[str, Any],
    target_graph: dict[str, Any],
) -> bool:
    declared = descriptor.get("match") or {}
    target = contract.get("target") or {}
    actual_workbooks = {
        str(target.get("workbook_id") or ""),
        *[
            str(item.get("workbook_id") or "")
            for item in target_graph.get("nodes") or []
            if isinstance(item, dict)
        ],
    } - {""}
    actual_dashboards = {
        str(target.get("dashboard_id") or ""),
        *[
            str(item.get("object_id") or "")
            for item in target_graph.get("nodes") or []
            if isinstance(item, dict) and str(item.get("object_type") or "") == "dashboard"
        ],
    } - {""}
    declared_workbooks = {str(item) for item in declared.get("workbook_ids") or []}
    declared_dashboards = {str(item) for item in declared.get("dashboard_ids") or []}
    return bool(
        (declared_workbooks and actual_workbooks & declared_workbooks)
        or (declared_dashboards and actual_dashboards & declared_dashboards)
    )


def _select_exemplar(
    descriptor: dict[str, Any],
    *,
    contract: dict[str, Any],
    target_graph: dict[str, Any],
) -> dict[str, Any]:
    exemplars = [dict(item) for item in descriptor.get("accepted_exemplars") or [] if isinstance(item, dict)]
    if not exemplars:
        return {}
    target = contract.get("target") or {}
    target_ids = {
        str(target.get("dashboard_id") or ""),
        str(target.get("chart_id") or ""),
        *[str(item) for item in target.get("object_ids") or []],
        *[
            str(item.get("object_id") or "")
            for item in target_graph.get("nodes") or []
            if isinstance(item, dict)
        ],
    } - {""}
    matched = [item for item in exemplars if str(item.get("object_id") or "") in target_ids]
    if len(matched) == 1:
        return matched[0]
    return exemplars[0] if len(exemplars) == 1 else {}


def _error(reason: str) -> dict[str, Any]:
    return {"status": "blocked", "active": False, "reason": reason}
