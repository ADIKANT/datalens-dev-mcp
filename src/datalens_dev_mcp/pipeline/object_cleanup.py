from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_object_cleanup_report(
    *,
    dashboard_id: str,
    workbook_id: str = "",
    created_objects: list[dict[str, Any]] | None = None,
    saved_graph: dict[str, Any] | None = None,
    published_graph: dict[str, Any] | None = None,
    cleanup_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    saved_ids = _active_ids(saved_graph or {})
    published_ids = _active_ids(published_graph or {})
    active_graph_checked = bool(saved_graph or published_graph)
    cleanup_by_id = {str(item.get("object_id") or ""): item for item in cleanup_results or [] if isinstance(item, dict)}
    rows: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for item in created_objects or []:
        object_id = str(item.get("object_id") or item.get("entryId") or item.get("chartId") or "").strip()
        if not object_id:
            continue
        active_in_saved = object_id in saved_ids
        active_in_published = object_id in published_ids
        rows.append(
            {
                "object_id": object_id,
                "object_type": str(item.get("object_type") or item.get("type") or ""),
                "name": str(item.get("name") or item.get("title") or ""),
                "reason": str(item.get("reason") or item.get("creation_reason") or ""),
                "active_in_saved": active_in_saved,
                "active_in_published": active_in_published,
            }
        )
        actions.append(
            _cleanup_action(
                object_id=object_id,
                active_in_saved=active_in_saved,
                active_in_published=active_in_published,
                active_graph_checked=active_graph_checked,
                result=cleanup_by_id.get(object_id, {}),
            )
        )
    return {
        "schema_version": "datalens.object-cleanup-report.delta-v6",
        "dashboard_id": dashboard_id,
        "workbook_id": workbook_id,
        "generated_at": _now(),
        "created_objects": rows,
        "active_graph_checked": active_graph_checked,
        "cleanup_actions": actions,
        "proof_artifacts": _proof_paths(saved_graph or {}) + _proof_paths(published_graph or {}),
    }


def build_final_handoff_contract(
    *,
    status: str,
    dashboard_id: str,
    workbook_id: str = "",
    changed_objects: list[dict[str, Any]] | None = None,
    saved_readback: str = "",
    published_readback: str = "",
    runtime_gate: dict[str, Any] | str | None = None,
    source_availability_matrix: str = "",
    cleanup_report: str = "",
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    gate_status, gate_ref = _runtime_gate_status_and_ref(runtime_gate)
    normalized_status = _normalize_handoff_status(status)
    active_limitations = [str(item) for item in limitations or [] if str(item)]
    if normalized_status == "done" and gate_status != "passed":
        normalized_status = "runtime_not_verified" if gate_status in {"blocked", "not_run", ""} else "blocked"
        active_limitations.append("browser/runtime verification did not pass for changed runtime objects")
    verification = {
        "saved_readback": saved_readback,
        "published_readback": published_readback,
        "runtime_gate": gate_ref,
    }
    if source_availability_matrix:
        verification["source_availability_matrix"] = source_availability_matrix
    if cleanup_report:
        verification["cleanup_report"] = cleanup_report
    return {
        "schema_version": "datalens.final-handoff.delta-v6",
        "status": normalized_status,
        "dashboard_id": dashboard_id,
        "workbook_id": workbook_id,
        "changed_objects": [_changed_object_row(item) for item in changed_objects or []],
        "verification": verification,
        "limitations": active_limitations,
    }


def _cleanup_action(
    *,
    object_id: str,
    active_in_saved: bool,
    active_in_published: bool,
    active_graph_checked: bool,
    result: dict[str, Any],
) -> dict[str, Any]:
    if not active_graph_checked:
        return {
            "object_id": object_id,
            "action": "blocked",
            "verified_absent": False,
            "error": "active graph was not checked",
        }
    if active_in_saved or active_in_published:
        return {
            "object_id": object_id,
            "action": "blocked",
            "verified_absent": False,
            "error": "object is active in saved or published graph",
        }
    action = str(result.get("action") or "none").strip().lower()
    if action not in {"none", "delete", "retire", "blocked"}:
        action = "blocked"
    followup_absent = bool(
        result.get("verified_absent") or result.get("followup_absent") or result.get("readback_not_found")
    )
    empty_body = bool(result.get("empty_body") or result.get("response_body") == "")
    verified_absent = followup_absent if action in {"delete", "retire"} else False
    error = ""
    if action in {"delete", "retire"} and not followup_absent:
        error = (
            "empty-body delete may have succeeded but follow-up readback did not verify absence"
            if empty_body
            else "follow-up readback did not verify absence"
        )
    return {"object_id": object_id, "action": action, "verified_absent": verified_absent, "error": error}


def _active_ids(graph: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    entries = graph.get("entries") if isinstance(graph.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("entry_id") or entry.get("object_id") or entry.get("entryId") or "").strip()
        role = str(entry.get("role") or "").strip()
        if entry_id and role not in {"dormant", "unused", "retired"}:
            result.add(entry_id)
    for key in ("active_object_ids", "active_entry_ids", "chart_ids", "object_ids"):
        values = graph.get(key)
        if isinstance(values, list):
            result.update(str(item) for item in values if str(item))
    return result


def _proof_paths(graph: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("artifact_path", "path", "proof_path"):
        value = str(graph.get(key) or "")
        if value:
            paths.append(value)
    raw = graph.get("proof_artifacts")
    if isinstance(raw, list):
        paths.extend(str(item) for item in raw if str(item))
    return paths


def _runtime_gate_status_and_ref(runtime_gate: dict[str, Any] | str | None) -> tuple[str, str]:
    if isinstance(runtime_gate, str):
        return ("", runtime_gate)
    if not isinstance(runtime_gate, dict):
        return ("", "")
    status = str(runtime_gate.get("status") or "").strip()
    path = str(runtime_gate.get("artifact_path") or runtime_gate.get("path") or "")
    return status, path or "inline:runtime_publish_gate"


def _normalize_handoff_status(status: str) -> str:
    normalized = str(status or "blocked").strip().lower()
    if normalized in {"done", "runtime_not_verified", "blocked", "rolled_back"}:
        return normalized
    return "blocked"


def _changed_object_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "object_id": str(item.get("object_id") or item.get("entryId") or item.get("chartId") or ""),
        "object_type": str(item.get("object_type") or item.get("type") or ""),
        "saved_rev": str(item.get("saved_rev") or item.get("saved_rev_id") or ""),
        "published_rev": str(item.get("published_rev") or item.get("published_rev_id") or ""),
    }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
