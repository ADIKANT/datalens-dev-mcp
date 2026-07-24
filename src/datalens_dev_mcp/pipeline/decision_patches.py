from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json


DECISION_LEDGER_PATH = Path("requirements/user_decisions.v2.json")
DECISION_LEDGER_SCHEMA_VERSION = "2026-07-23.user_decision_ledger.v2"
DECISION_PATCH_SCHEMA_VERSION = "2026-07-23.user_decision_patch.v1"
DECISION_SCOPE_KINDS = {"project", "family", "object"}
SEMANTIC_ROLES = {
    "success",
    "failure",
    "warning",
    "neutral",
    "focus",
    "comparison",
    "track",
}
VISUAL_SPEC_OVERLAY_SECTIONS = {
    "colors",
    "labels",
    "tooltip",
    "kpi_context",
    "comparison_context",
    "responsive_layout",
    "layout_contract",
}
_PATCH_FIELDS = {
    "schema_version",
    "scope",
    "metric_semantics",
    "visual_spec_overlay",
    "required_semantic_roles",
    "forbidden_semantic_roles",
    "supersedes",
}


def load_user_decision_ledger(project_root: str | Path) -> dict[str, Any]:
    path = Path(project_root) / DECISION_LEDGER_PATH
    payload = read_json(path, default=None)
    if payload is None:
        return {
            "schema_version": DECISION_LEDGER_SCHEMA_VERSION,
            "revisions": [],
        }
    if not isinstance(payload, dict):
        raise ValueError("user decision ledger must be an object")
    if payload.get("schema_version") != DECISION_LEDGER_SCHEMA_VERSION:
        raise ValueError("user decision ledger schema_version is unsupported")
    revisions = payload.get("revisions")
    if not isinstance(revisions, list) or not all(isinstance(item, dict) for item in revisions):
        raise ValueError("user decision ledger revisions must be an array of objects")
    return payload


def record_user_decision_patch(
    project_root: str | Path,
    *,
    decision_id: str,
    decision_text: str,
    decision_patch: dict[str, Any],
) -> dict[str, Any]:
    root = Path(project_root)
    ledger = load_user_decision_ledger(root)
    normalized, issues = normalize_decision_patch(decision_patch, ledger=ledger)
    if issues:
        return {
            "ok": False,
            "error": {
                "category": "invalid_decision_patch",
                "message": "; ".join(issues),
            },
            "issues": issues,
        }
    recorded_at = _now_utc()
    ordinal = len(ledger["revisions"]) + 1
    revision_seed = {
        "decision_id": decision_id,
        "decision_text": decision_text,
        "patch": normalized,
        "recorded_at": recorded_at,
        "ordinal": ordinal,
    }
    revision_id = (
        f"{decision_id}@"
        f"{hashlib.sha256(_canonical_bytes(revision_seed)).hexdigest()[:16]}"
    )
    revision = {
        "revision_id": revision_id,
        "decision_id": decision_id,
        "recorded_at": recorded_at,
        "ordinal": ordinal,
        "decision_text": decision_text,
        "patch": normalized,
    }
    ledger["revisions"].append(revision)
    write_json(root / DECISION_LEDGER_PATH, ledger)
    return {
        "ok": True,
        "path": DECISION_LEDGER_PATH.as_posix(),
        "decision_id": decision_id,
        "revision_id": revision_id,
        "decision_ledger_sha256": _ledger_sha256(ledger),
        "patch": normalized,
    }


def normalize_decision_patch(
    value: Any,
    *,
    ledger: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(value, dict):
        return {}, ["decision_patch must be an object"]
    issues: list[str] = []
    unknown = sorted(set(value) - _PATCH_FIELDS)
    if unknown:
        issues.append(f"decision_patch has unsupported fields: {', '.join(unknown)}")
    schema_version = str(value.get("schema_version") or DECISION_PATCH_SCHEMA_VERSION)
    if schema_version != DECISION_PATCH_SCHEMA_VERSION:
        issues.append("decision_patch.schema_version is unsupported")

    scope = value.get("scope")
    normalized_scope: dict[str, Any] = {}
    if not isinstance(scope, dict):
        issues.append("decision_patch.scope is required and must be an object")
    else:
        scope_unknown = sorted(set(scope) - {"kind", "id", "ids"})
        if scope_unknown:
            issues.append(f"decision_patch.scope has unsupported fields: {', '.join(scope_unknown)}")
        kind = str(scope.get("kind") or "").strip().lower()
        if kind not in DECISION_SCOPE_KINDS:
            issues.append("decision_patch.scope.kind must be project, family, or object")
        raw_ids = scope.get("ids")
        if raw_ids is None and scope.get("id") not in (None, ""):
            raw_ids = [scope.get("id")]
        if raw_ids is None:
            raw_ids = []
        if not isinstance(raw_ids, list):
            issues.append("decision_patch.scope.ids must be an array")
            raw_ids = []
        ids = list(dict.fromkeys(str(item).strip() for item in raw_ids if str(item).strip()))
        if kind in {"family", "object"} and not ids:
            issues.append(f"decision_patch.scope.ids is required for {kind} scope")
        if kind == "project" and ids:
            issues.append("project-scoped decision_patch must not declare scope ids")
        normalized_scope = {"kind": kind, "ids": ids}

    metric_semantics = value.get("metric_semantics") or {}
    if not isinstance(metric_semantics, dict):
        issues.append("decision_patch.metric_semantics must be an object")
        metric_semantics = {}
    visual_overlay = value.get("visual_spec_overlay") or {}
    if not isinstance(visual_overlay, dict):
        issues.append("decision_patch.visual_spec_overlay must be an object")
        visual_overlay = {}
    else:
        unknown_sections = sorted(set(visual_overlay) - VISUAL_SPEC_OVERLAY_SECTIONS)
        if unknown_sections:
            issues.append(
                "decision_patch.visual_spec_overlay has unsupported sections: "
                + ", ".join(unknown_sections)
            )
        if any(not isinstance(section, dict) for section in visual_overlay.values()):
            issues.append("decision_patch.visual_spec_overlay sections must be objects")

    required_roles = _normalize_roles(
        value.get("required_semantic_roles"),
        field="required_semantic_roles",
        issues=issues,
    )
    forbidden_roles = _normalize_roles(
        value.get("forbidden_semantic_roles"),
        field="forbidden_semantic_roles",
        issues=issues,
    )
    conflicts = sorted(set(required_roles) & set(forbidden_roles))
    if conflicts:
        issues.append(
            "decision_patch semantic roles cannot be both required and forbidden: "
            + ", ".join(conflicts)
        )

    raw_supersedes = value.get("supersedes") or []
    if isinstance(raw_supersedes, str):
        raw_supersedes = [raw_supersedes]
    if not isinstance(raw_supersedes, list):
        issues.append("decision_patch.supersedes must be a string or an array")
        raw_supersedes = []
    supersedes = list(dict.fromkeys(str(item).strip() for item in raw_supersedes if str(item).strip()))
    if ledger is not None and supersedes:
        known = {
            token
            for revision in ledger.get("revisions") or []
            for token in (
                str(revision.get("decision_id") or ""),
                str(revision.get("revision_id") or ""),
            )
            if token
        }
        missing = sorted(set(supersedes) - known)
        if missing:
            issues.append("decision_patch.supersedes references unknown decisions: " + ", ".join(missing))

    normalized = {
        "schema_version": DECISION_PATCH_SCHEMA_VERSION,
        "scope": normalized_scope,
        "metric_semantics": deepcopy(metric_semantics),
        "visual_spec_overlay": {
            key: deepcopy(value)
            for key, value in visual_overlay.items()
            if key in VISUAL_SPEC_OVERLAY_SECTIONS
        },
        "required_semantic_roles": required_roles,
        "forbidden_semantic_roles": forbidden_roles,
        "supersedes": supersedes,
    }
    if not any(
        (
            normalized["metric_semantics"],
            normalized["visual_spec_overlay"],
            normalized["required_semantic_roles"],
            normalized["forbidden_semantic_roles"],
            normalized["supersedes"],
        )
    ):
        issues.append("decision_patch must contain a semantic change or supersedes reference")
    return normalized, issues


def decision_ledger_sha256(project_root: str | Path) -> str:
    path = Path(project_root) / DECISION_LEDGER_PATH
    if not path.is_file():
        return ""
    return _ledger_sha256(load_user_decision_ledger(project_root))


def resolve_active_decision_contract(
    project_root: str | Path,
    chart_plan: dict[str, Any],
) -> dict[str, Any]:
    ledger = load_user_decision_ledger(project_root)
    revisions = ledger.get("revisions") or []
    superseded = _superseded_revision_ids(revisions)
    matching: list[tuple[int, int, dict[str, Any]]] = []
    for index, revision in enumerate(revisions):
        if _revision_is_superseded(revision, superseded):
            continue
        patch = revision.get("patch") if isinstance(revision.get("patch"), dict) else {}
        scope = patch.get("scope") if isinstance(patch.get("scope"), dict) else {}
        match, precedence = _scope_match(scope, chart_plan)
        if match:
            matching.append((precedence, index, revision))
    matching.sort(key=lambda item: (item[0], item[1]))

    metric_semantics: dict[str, Any] = {}
    visual_spec_overlay: dict[str, Any] = {}
    required_roles: set[str] = set()
    forbidden_roles: set[str] = set()
    for _precedence, _index, revision in matching:
        patch = revision["patch"]
        metric_semantics = _deep_merge(metric_semantics, patch.get("metric_semantics") or {})
        visual_spec_overlay = _deep_merge(
            visual_spec_overlay,
            patch.get("visual_spec_overlay") or {},
        )
        for role in patch.get("required_semantic_roles") or []:
            required_roles.add(role)
            forbidden_roles.discard(role)
        for role in patch.get("forbidden_semantic_roles") or []:
            forbidden_roles.add(role)
            required_roles.discard(role)
    return {
        "schema_version": "2026-07-23.active_user_decision_contract.v1",
        "decision_ledger_sha256": _ledger_sha256(ledger) if revisions else "",
        "matched_revision_ids": [
            str(revision.get("revision_id") or "")
            for _precedence, _index, revision in matching
        ],
        "metric_semantics": metric_semantics,
        "visual_spec_overlay": visual_spec_overlay,
        "required_semantic_roles": sorted(required_roles),
        "forbidden_semantic_roles": sorted(forbidden_roles),
    }


def apply_decision_contract_to_chart_plan(
    project_root: str | Path,
    chart_plan: dict[str, Any],
) -> dict[str, Any]:
    patched = deepcopy(chart_plan)
    contract = resolve_active_decision_contract(project_root, patched)
    if not contract["matched_revision_ids"]:
        return {
            "chart_plan": patched,
            "decision_contract": contract,
        }
    record = (
        patched.get("chart_decision_record")
        if isinstance(patched.get("chart_decision_record"), dict)
        else patched
    )
    record["metric_semantics"] = _deep_merge(
        record.get("metric_semantics") or {},
        contract["metric_semantics"],
    )
    visual_spec = _deep_merge(
        record.get("renderer_visual_spec") or {},
        contract["visual_spec_overlay"],
    )
    visual_spec["semantic_roles_contract"] = {
        "required": contract["required_semantic_roles"],
        "forbidden": contract["forbidden_semantic_roles"],
    }
    colors = visual_spec.get("colors") if isinstance(visual_spec.get("colors"), dict) else {}
    semantic_roles = (
        colors.get("semantic_roles")
        if isinstance(colors.get("semantic_roles"), dict)
        else {}
    )
    for role in contract["forbidden_semantic_roles"]:
        semantic_roles[role] = ""
    if semantic_roles:
        colors["semantic_roles"] = semantic_roles
        visual_spec["colors"] = colors
    visual_spec["decision_ledger_sha256"] = contract["decision_ledger_sha256"]
    record["renderer_visual_spec"] = visual_spec
    record["decision_ledger_sha256"] = contract["decision_ledger_sha256"]
    record["active_decision_revision_ids"] = contract["matched_revision_ids"]
    if record is not patched:
        patched["chart_decision_record"] = record
    patched["decision_ledger_sha256"] = contract["decision_ledger_sha256"]
    return {
        "chart_plan": patched,
        "decision_contract": contract,
    }


def decision_contract_drift_issues(
    project_root: str | Path,
    chart_plan: dict[str, Any],
) -> list[str]:
    contract = resolve_active_decision_contract(project_root, chart_plan)
    if not contract["matched_revision_ids"]:
        return []
    record = (
        chart_plan.get("chart_decision_record")
        if isinstance(chart_plan.get("chart_decision_record"), dict)
        else chart_plan
    )
    actual_sha = str(
        record.get("decision_ledger_sha256")
        or chart_plan.get("decision_ledger_sha256")
        or ""
    )
    issues: list[str] = []
    if actual_sha != contract["decision_ledger_sha256"]:
        issues.append("chart plan decision_ledger_sha256 does not match the active user decision ledger")
    if not _is_deep_subset(contract["metric_semantics"], record.get("metric_semantics") or {}):
        issues.append("chart plan metric_semantics drift from active user decision patches")
    if not _is_deep_subset(
        contract["visual_spec_overlay"],
        record.get("renderer_visual_spec") or {},
    ):
        issues.append("chart plan renderer_visual_spec drift from active user decision patches")
    role_contract = (record.get("renderer_visual_spec") or {}).get("semantic_roles_contract") or {}
    if sorted(role_contract.get("required") or []) != contract["required_semantic_roles"]:
        issues.append("chart plan required semantic roles drift from active user decision patches")
    if sorted(role_contract.get("forbidden") or []) != contract["forbidden_semantic_roles"]:
        issues.append("chart plan forbidden semantic roles drift from active user decision patches")
    return issues


def _scope_match(scope: dict[str, Any], chart_plan: dict[str, Any]) -> tuple[bool, int]:
    kind = str(scope.get("kind") or "")
    ids = set(str(item) for item in scope.get("ids") or [])
    if kind == "project":
        return True, 0
    record = (
        chart_plan.get("chart_decision_record")
        if isinstance(chart_plan.get("chart_decision_record"), dict)
        else {}
    )
    if kind == "family":
        candidates = {
            str(chart_plan.get("family") or ""),
            str(chart_plan.get("selected_family") or ""),
            str(record.get("selected_family") or ""),
            str((chart_plan.get("renderer_visual_spec") or {}).get("family") or ""),
            str((record.get("renderer_visual_spec") or {}).get("family") or ""),
        }
        return bool(ids & candidates), 1
    if kind == "object":
        candidates = {
            str(chart_plan.get(key) or "")
            for key in ("chart_id", "widget_id", "object_id", "decision_id")
        }
        candidates.update(
            str(record.get(key) or "")
            for key in ("chart_id", "widget_id", "object_id", "decision_id")
        )
        return bool(ids & candidates), 2
    return False, 99


def _superseded_revision_ids(revisions: list[dict[str, Any]]) -> set[str]:
    superseded: set[str] = set()
    latest_by_decision: dict[str, str] = {}
    for revision in revisions:
        decision_id = str(revision.get("decision_id") or "")
        revision_id = str(revision.get("revision_id") or "")
        previous = latest_by_decision.get(decision_id)
        if previous:
            superseded.add(previous)
        if decision_id and revision_id:
            latest_by_decision[decision_id] = revision_id
        patch = revision.get("patch") if isinstance(revision.get("patch"), dict) else {}
        for token in patch.get("supersedes") or []:
            for candidate in revisions:
                if token in {
                    str(candidate.get("decision_id") or ""),
                    str(candidate.get("revision_id") or ""),
                }:
                    superseded.add(str(candidate.get("revision_id") or ""))
    return superseded


def _revision_is_superseded(revision: dict[str, Any], superseded: set[str]) -> bool:
    return str(revision.get("revision_id") or "") in superseded


def _normalize_roles(value: Any, *, field: str, issues: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(f"decision_patch.{field} must be an array")
        return []
    normalized = list(dict.fromkeys(str(item).strip().lower() for item in value if str(item).strip()))
    unknown = sorted(set(normalized) - SEMANTIC_ROLES)
    if unknown:
        issues.append(f"decision_patch.{field} has unsupported roles: {', '.join(unknown)}")
    return [item for item in normalized if item in SEMANTIC_ROLES]


def _deep_merge(base: Any, overlay: Any) -> Any:
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return deepcopy(overlay)
    merged = deepcopy(base)
    for key, value in overlay.items():
        merged[key] = _deep_merge(merged.get(key), value) if key in merged else deepcopy(value)
    return merged


def _is_deep_subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _is_deep_subset(value, actual[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return expected == actual
    return expected == actual


def _ledger_sha256(ledger: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(ledger)).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
