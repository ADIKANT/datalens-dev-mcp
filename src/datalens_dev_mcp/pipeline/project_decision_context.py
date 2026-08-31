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
VISUAL_PROFILE_CATEGORIES = (
    "layout",
    "tabs",
    "titles",
    "hints",
    "kpi",
    "tables",
    "series",
    "legend",
    "axes",
    "tooltip",
    "selectors",
    "formatting",
    "colors",
    "theme",
    "comparison",
    "data_states",
    "advanced_editor",
    "performance",
    "manual_overrides",
)
DECISION_SCOPES = frozenset({"portfolio", "project", "task"})
DECISION_STATUSES = frozenset({"active", "rejected", "superseded", "unresolved"})


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
    typed_profile = _normalized_typed_profile(profile)
    exemplar = _select_exemplar(descriptor, contract=contract, target_graph=target_graph)
    corrections = [
        dict(item)
        for item in descriptor.get("corrections") or []
        if isinstance(item, dict)
        and item.get("status") == "active"
        and _decision_applies(item, target_graph=target_graph)
    ]
    decisions = [
        dict(item)
        for item in descriptor.get("decisions") or []
        if isinstance(item, dict)
        and item.get("status") == "active"
        and _decision_applies(item, target_graph=target_graph)
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
        "typed_profile": typed_profile,
        "typed_decisions": [_typed_decision_projection(item) for item in decisions],
        "task_corrections": [
            _typed_decision_projection(item)
            for item in corrections
            if "typed_value" in item and str(item.get("category") or "") in VISUAL_PROFILE_CATEGORIES
        ],
        "accepted_exemplar_selection": "selected" if exemplar else "none",
        "accepted_exemplar_id": str((exemplar or {}).get("exemplar_id") or ""),
        "accepted_exemplar_hash": canonical_hash(exemplar) if exemplar else "",
        "accepted_exemplar_visual_contract": dict(
            (exemplar or {}).get("visual_contract")
            or (exemplar or {}).get("typed_profile")
            or {}
        ),
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
    version = value.get("context_version")
    if version not in {1, 2}:
        issues.append("context_version must equal 1 or 2")
    if not str(value.get("project_id") or "").strip():
        issues.append("project_id is required")
    profile = value.get("profile")
    if not isinstance(profile, dict) or not profile:
        issues.append("profile must be a non-empty object")
    elif version == 2:
        unsupported = sorted(set(profile) - set(VISUAL_PROFILE_CATEGORIES))
        if unsupported:
            issues.append("profile contains unsupported categories: " + ", ".join(unsupported))
        for category, section in profile.items():
            if not isinstance(section, dict):
                issues.append(f"profile.{category} must be an object")
        advanced = profile.get("advanced_editor") or {}
        if isinstance(advanced, dict):
            for key in ("protected_regions", "semantic_slots"):
                if key in advanced and not isinstance(advanced.get(key), list):
                    issues.append(f"profile.advanced_editor.{key} must be an array")
    match = value.get("match")
    if not isinstance(match, dict) or not any(match.get(key) for key in ("workbook_ids", "dashboard_ids")):
        issues.append("match must declare workbook_ids or dashboard_ids")
    for index, item in enumerate(value.get("accepted_exemplars") or []):
        if not isinstance(item, dict) or not str(item.get("exemplar_id") or ""):
            issues.append(f"accepted_exemplars[{index}] is invalid")
    for collection in ("decisions", "corrections"):
        for index, item in enumerate(value.get(collection) or []):
            if not isinstance(item, dict):
                issues.append(f"{collection}[{index}] must be an object")
                continue
            if collection == "decisions" or "typed_value" in item:
                issues.extend(_validate_decision_item(item, path=f"{collection}[{index}]"))
    hashes = [str(item) for item in value.get("source_hashes") or []]
    hashes.extend(
        str(item.get("source_sha256") or "")
        for item in value.get("corrections") or []
        if isinstance(item, dict) and item.get("source_sha256")
    )
    if any(not SHA256_RE.fullmatch(item) for item in hashes):
        issues.append("source hashes must be lowercase SHA-256 values")
    return tuple(dict.fromkeys(issues))


def _normalized_typed_profile(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        category: dict(profile.get(category) or {})
        for category in VISUAL_PROFILE_CATEGORIES
        if isinstance(profile.get(category), dict) and profile.get(category)
    }
    advanced = dict(normalized.get("advanced_editor") or {})
    if advanced:
        advanced.setdefault("protected_regions", [])
        advanced.setdefault("semantic_slots", [])
        normalized["advanced_editor"] = advanced
    return normalized


def _validate_decision_item(item: dict[str, Any], *, path: str) -> list[str]:
    issues: list[str] = []
    if not str(item.get("decision_id") or "").strip():
        issues.append(f"{path}.decision_id is required")
    category = str(item.get("category") or "")
    if category not in VISUAL_PROFILE_CATEGORIES:
        issues.append(f"{path}.category is unsupported")
    if str(item.get("scope") or "") not in DECISION_SCOPES:
        issues.append(f"{path}.scope is invalid")
    status = str(item.get("status") or "")
    if status not in DECISION_STATUSES:
        issues.append(f"{path}.status is invalid")
    applies_to = item.get("applies_to")
    if not isinstance(applies_to, dict):
        issues.append(f"{path}.applies_to must be an object")
    else:
        for key in ("object_types", "visualization_families", "object_ids"):
            if key in applies_to and not isinstance(applies_to.get(key), list):
                issues.append(f"{path}.applies_to.{key} must be an array")
    if not str(item.get("statement") or "").strip():
        issues.append(f"{path}.statement is required")
    if "typed_value" not in item:
        issues.append(f"{path}.typed_value is required")
    for key in ("source_refs", "final_state_refs", "supersedes"):
        if not isinstance(item.get(key), list):
            issues.append(f"{path}.{key} must be an array")
    if status == "active" and not list(item.get("final_state_refs") or []):
        issues.append(f"{path}.final_state_refs is required for an active decision")
    return issues


def _typed_decision_projection(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "decision_id",
            "category",
            "scope",
            "status",
            "applies_to",
            "statement",
            "typed_value",
            "source_refs",
            "final_state_refs",
            "supersedes",
        )
    }


def _decision_applies(item: dict[str, Any], *, target_graph: dict[str, Any]) -> bool:
    applies = item.get("applies_to") if isinstance(item.get("applies_to"), dict) else {}
    if not applies:
        return True
    nodes = [node for node in target_graph.get("nodes") or [] if isinstance(node, dict)]
    actual_ids = {str(node.get("object_id") or "") for node in nodes} - {""}
    actual_types = {str(node.get("object_type") or "") for node in nodes} - {""}
    actual_families = {
        str(node.get("visualization_family") or node.get("family") or "") for node in nodes
    } - {""}
    declared_ids = {str(value) for value in applies.get("object_ids") or []}
    declared_types = {str(value) for value in applies.get("object_types") or []}
    declared_families = {str(value) for value in applies.get("visualization_families") or []}
    checks = [
        bool(actual_ids & declared_ids) if declared_ids else True,
        bool(actual_types & declared_types) if declared_types else True,
        bool(actual_families & declared_families) if declared_families else True,
    ]
    return all(checks)


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
