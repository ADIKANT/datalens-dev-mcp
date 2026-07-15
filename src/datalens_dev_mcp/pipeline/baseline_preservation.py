from __future__ import annotations

from pathlib import Path
from typing import Any


BACKUP_CORPUS_ROOT = Path("backup")


def find_backup_baseline_path(
    *,
    dashboard_id: str = "",
    workbook_id: str = "",
    backup_root: str | Path = BACKUP_CORPUS_ROOT,
) -> str:
    """Find a likely read-only backup path for a dashboard/workbook id."""

    root = Path(backup_root)
    if not root.exists():
        return ""
    candidates: list[Path] = []
    if dashboard_id:
        candidates.extend(
            [
                root / f"dashboard__{dashboard_id}",
                root / f"dashboard__{dashboard_id}.json",
                root / dashboard_id,
                root / f"{dashboard_id}.json",
            ]
        )
    if workbook_id:
        workbook_root = root / f"workbook__{workbook_id}"
        candidates.extend(
            [
                workbook_root,
                root / f"workbook__{workbook_id}.json",
                root / workbook_id,
                root / f"{workbook_id}.json",
            ]
        )
        if dashboard_id:
            candidates.extend(
                [
                    workbook_root / f"dashboard__{dashboard_id}",
                    workbook_root / f"dashboard__{dashboard_id}.json",
                    workbook_root / dashboard_id,
                    workbook_root / f"{dashboard_id}.json",
                ]
            )
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def build_baseline_diff_contract(
    *,
    dashboard_id: str,
    workbook_id: str = "",
    baseline_source: dict[str, Any] | None = None,
    baseline_dashboard: dict[str, Any] | None = None,
    proposed_dashboard: dict[str, Any] | None = None,
    changed_objects: list[dict[str, Any]] | None = None,
    allowed_removed_object_ids: list[str] | None = None,
    allow_broad_rebuild: bool = False,
) -> dict[str, Any]:
    baseline = baseline_dashboard or {}
    proposed = proposed_dashboard or {}
    allowed_removed = {str(item) for item in allowed_removed_object_ids or [] if str(item)}
    baseline_refs = _dashboard_references(baseline)
    proposed_refs = _dashboard_references(proposed)
    removed_ids = sorted(set(baseline_refs) - set(proposed_refs) - allowed_removed)
    added_ids = sorted(set(proposed_refs) - set(baseline_refs))
    unexpected_layout_diff = [
        {"object_id": object_id, "diff_type": "removed_active_object", "baseline": baseline_refs[object_id]}
        for object_id in removed_ids
    ]
    feature_losses = _table_pivot_feature_losses(baseline_refs, proposed_refs)
    unexpected_layout_diff.extend(feature_losses)

    blocked_reasons: list[str] = []
    if removed_ids and not allow_broad_rebuild:
        blocked_reasons.append("broad_rebuild_or_object_drop_requires_explicit_authorization")
    if feature_losses:
        blocked_reasons.append("table_or_pivot_actionability_regressed")

    object_rows = _changed_object_rows(changed_objects, baseline_refs, proposed_refs, removed_ids, added_ids)
    source = dict(baseline_source or {})
    if not source:
        source = {"kind": "snapshot", "path": ""}
    source.setdefault("kind", "snapshot")
    source.setdefault("path", "")
    return {
        "schema_version": "datalens.baseline-diff-contract.delta-v6",
        "dashboard_id": dashboard_id,
        "workbook_id": workbook_id,
        "baseline_source": source,
        "tabs": _tab_rows(baseline, proposed),
        "changed_objects": object_rows,
        "unexpected_layout_diff": unexpected_layout_diff,
        "blocked_reasons": blocked_reasons,
        "preservation_policy": {
            "default_change_type": "preserve",
            "existing_object_update_first": True,
            "creation_requires_necessity_proof": True,
            "backup_root_read_only": str(BACKUP_CORPUS_ROOT),
        },
    }


def create_necessity_proof(
    *,
    action: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    existing = action.get("creation_necessity_proof") if isinstance(
        action.get("creation_necessity_proof"), dict
    ) else {}
    reason = str(
        existing.get("update_insufficient_reason")
        or action.get("update_insufficient_reason")
        or payload.get("update_insufficient_reason")
        or (
            "No existing object id/base revision was supplied for this create action; "
            "caller must reconcile workbook entries before live execution."
        )
    ).strip()
    return {
        "schema_version": "datalens.object-creation-necessity.delta-v6",
        "status": str(existing.get("status") or "required"),
        "update_insufficient_reason": reason,
        "existing_readback_checked": bool(
            existing.get("existing_readback_checked")
            or action.get("existing_readback_checked")
            or action.get("entries_reconciliation")
            or action.get("reconciliation")
        ),
        "preserve_existing_ids_default": True,
        "cleanup_report_required_if_created": True,
    }


def build_object_reuse_decision(
    *,
    desired_role: str,
    target_object_id: str = "",
    target_object_type: str = "unknown",
    existing_object_found: bool | None = None,
    target_scope: dict[str, Any] | None = None,
    existing_candidates: list[dict[str, Any]] | None = None,
    selected_action: str = "",
    create_necessity_proof: dict[str, Any] | None = None,
    cleanup_lifecycle: dict[str, Any] | None = None,
    temporary_lifecycle: dict[str, Any] | None = None,
    stale_revision_retry_count: int = 0,
    baseline_proof_artifact: str = "",
) -> dict[str, Any]:
    candidates = [dict(item) for item in existing_candidates or [] if isinstance(item, dict)]
    action = str(selected_action or "").strip().lower()
    if not action:
        action = "reuse" if candidates else "block"
    if action not in {"update", "reuse", "create", "replace", "remove", "block"}:
        action = "block"
    change_type = {
        "reuse": "update",
        "update": "update",
        "create": "create",
        "replace": "replace",
        "remove": "remove",
        "block": "block",
    }[action]
    blocked_reasons: list[str] = []
    proof = create_necessity_proof or {}
    if action == "create":
        if not str((proof or {}).get("update_insufficient_reason") or "").strip():
            blocked_reasons.append("create_requires_update_insufficient_reason")
        if not bool((proof or {}).get("existing_readback_checked") or (proof or {}).get("object_reuse_checked")):
            blocked_reasons.append("create_requires_existing_object_reuse_check")
        if not baseline_proof_artifact:
            blocked_reasons.append("create_requires_baseline_proof_artifact")
        lifecycle = cleanup_lifecycle or temporary_lifecycle or {}
        if not isinstance(lifecycle, dict) or not (
            lifecycle.get("owner_workflow")
            or lifecycle.get("mode")
            or lifecycle.get("active_graph_check")
            or lifecycle.get("rollback_path")
        ):
            blocked_reasons.append("create_requires_cleanup_lifecycle")
    if action == "block" and not blocked_reasons:
        blocked_reasons.append("no_reuse_or_update_candidate_selected")
    existing_found = bool(candidates) if existing_object_found is None else bool(existing_object_found)
    create_allowed = action == "create" and not blocked_reasons
    return {
        "schema_version": "datalens.delta_v7.object_reuse_decision.v1",
        "v8_schema_version": "datalens.delta_v8.object_reuse_decision.v1",
        "desired_role": desired_role,
        "target_object_id": target_object_id,
        "target_object_type": _normalize_target_object_type(target_object_type),
        "existing_object_found": existing_found,
        "target_scope": target_scope or {},
        "existing_candidates": candidates,
        "decision": "block" if blocked_reasons and action == "create" else action,
        "change_type": change_type,
        "create_allowed": create_allowed,
        "create_necessity_proof": proof,
        "cleanup_lifecycle": cleanup_lifecycle or {},
        "temporary_lifecycle": temporary_lifecycle or cleanup_lifecycle or {},
        "stale_revision_retry_count": max(int(stale_revision_retry_count or 0), 0),
        "baseline_proof_artifact": baseline_proof_artifact,
        "blocked_reasons": blocked_reasons,
    }


def _changed_object_rows(
    changed_objects: list[dict[str, Any]] | None,
    baseline_refs: dict[str, dict[str, Any]],
    proposed_refs: dict[str, dict[str, Any]],
    removed_ids: list[str],
    added_ids: list[str],
) -> list[dict[str, Any]]:
    if changed_objects:
        return [dict(item) for item in changed_objects]
    rows: list[dict[str, Any]] = []
    for object_id in sorted(set(baseline_refs) & set(proposed_refs)):
        rows.append({"object_id": object_id, "object_type": baseline_refs[object_id].get("object_type", ""), "change_type": "preserve"})
    for object_id in added_ids:
        rows.append(
            {
                "object_id": object_id,
                "object_type": proposed_refs[object_id].get("object_type", ""),
                "change_type": "append",
                "reason": "new object appears in proposed graph",
            }
        )
    for object_id in removed_ids:
        rows.append(
            {
                "object_id": object_id,
                "object_type": baseline_refs[object_id].get("object_type", ""),
                "change_type": "blocked",
                "reason": "active baseline object is missing from proposed graph",
            }
        )
    return rows


def _dashboard_references(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    _collect_references(value, refs, path="$")
    return refs


def _collect_references(value: Any, refs: dict[str, dict[str, Any]], *, path: str) -> None:
    if isinstance(value, dict):
        object_id = _object_id(value)
        if object_id:
            refs.setdefault(object_id, _reference_contract(value, path=path))
        for key, item in value.items():
            _collect_references(item, refs, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_references(item, refs, path=f"{path}[{index}]")


def _object_id(value: dict[str, Any]) -> str:
    for key in ("entryId", "entry_id", "chartId", "chart_id", "targetEntryId", "target_entry_id", "object_id"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def _reference_contract(value: dict[str, Any], *, path: str) -> dict[str, Any]:
    object_type = str(value.get("type") or value.get("object_type") or value.get("entry_type") or "object")
    return {
        "path": path,
        "object_type": object_type,
        "is_table_or_pivot": _is_table_or_pivot_or_list(value),
        "features": {
            "links": _has_any_key(value, {"link", "links", "url", "href", "issue_url", "ticket_url"}),
            "actions": _has_any_key(value, {"action", "actions", "button", "buttons", "command"}),
            "alerts": _has_any_key(value, {"alert", "alerts", "warning", "status"}),
            "conditional_formatting": _has_any_key(
                value,
                {"conditional_formatting", "formatting", "format", "style_rules", "styles"},
            ),
            "sort": _has_any_key(value, {"sort", "sorting", "order_by", "orderBy"}),
            "dimensions": _has_any_key(value, {"dimensions", "dimension", "rows", "columns"}),
            "measures": _has_any_key(value, {"measures", "measure", "metrics"}),
            "pivot_layout": _has_any_key(value, {"pivot", "pivot_layout", "pivotConfig", "pivot_config"}),
        },
    }


def _is_table_or_pivot_or_list(value: dict[str, Any]) -> bool:
    text = " ".join(str(value.get(key) or "") for key in ("type", "object_type", "entry_type", "name", "title")).lower()
    return "table" in text or "pivot" in text or "list" in text


def _has_any_key(value: Any, keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in keys:
                return True
            if _has_any_key(item, keys):
                return True
    elif isinstance(value, list):
        return any(_has_any_key(item, keys) for item in value)
    return False


def _table_pivot_feature_losses(
    baseline_refs: dict[str, dict[str, Any]],
    proposed_refs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    losses: list[dict[str, Any]] = []
    for object_id, baseline in baseline_refs.items():
        if not baseline.get("is_table_or_pivot") or object_id not in proposed_refs:
            continue
        proposed = proposed_refs[object_id]
        missing = [
            feature
            for feature, required in (baseline.get("features") or {}).items()
            if required and not (proposed.get("features") or {}).get(feature)
        ]
        if missing:
            losses.append({"object_id": object_id, "diff_type": "lost_table_or_pivot_features", "missing_features": missing})
    return losses


def _tab_rows(baseline: dict[str, Any], proposed: dict[str, Any]) -> list[dict[str, Any]]:
    baseline_tabs = _tabs_by_id(baseline)
    proposed_tabs = _tabs_by_id(proposed)
    rows: list[dict[str, Any]] = []
    for tab_id in sorted(set(baseline_tabs) | set(proposed_tabs)):
        rows.append(
            {
                "tab_id": tab_id,
                "baseline_present": tab_id in baseline_tabs,
                "proposed_present": tab_id in proposed_tabs,
            }
        )
    return rows


def _tabs_by_id(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = value.get("tabs") or value.get("dashboardTabs") or []
    result: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for index, tab in enumerate(raw):
            if isinstance(tab, dict):
                tab_id = str(tab.get("id") or tab.get("tabId") or tab.get("title") or f"tab_{index}")
                result[tab_id] = tab
    return result


def _normalize_target_object_type(value: str) -> str:
    normalized = str(value or "unknown").strip().lower()
    if normalized in {"dashboard", "wizard_chart", "editor_chart", "dataset", "control", "unknown"}:
        return normalized
    if normalized in {"chart", "advanced_editor_chart", "editor"}:
        return "editor_chart"
    if normalized in {"wizard", "wizardchart"}:
        return "wizard_chart"
    return "unknown"
