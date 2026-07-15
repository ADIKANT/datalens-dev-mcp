from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.pipeline.route_registry import decide_registered_route


ENVIRONMENT_TOKENS = {
    "prod": {"prod", "production", "prd"},
    "stage": {"stage", "stg", "preprod", "uat"},
    "dev": {"dev", "development"},
    "test": {"test", "qa", "sandbox"},
}
ENVIRONMENT_ALIAS_NAMES = {
    "prod": "prodConnection",
    "stage": "stageConnection",
    "dev": "devConnection",
    "test": "testConnection",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _compact_run_id() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _extract_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("entries"), list):
        return payload["entries"]
    if isinstance(payload.get("pages"), list):
        entries: list[dict[str, Any]] = []
        for page in payload["pages"]:
            if isinstance(page, dict) and isinstance(page.get("entries"), list):
                entries.extend(page["entries"])
        return entries
    return []


def _tokens(*values: str) -> set[str]:
    text = " ".join(value for value in values if value)
    return {token for token in re.split(r"[^A-Za-z0-9]+", text.lower()) if token}


def _infer_environment(*values: str) -> str:
    tokens = _tokens(*values)
    matches = [
        environment
        for environment, environment_tokens in ENVIRONMENT_TOKENS.items()
        if tokens & environment_tokens
    ]
    return matches[0] if len(matches) == 1 else "unknown"


def _entry_label(entry: dict[str, Any]) -> str:
    return str(entry.get("displayKey") or entry.get("key") or entry.get("entryId") or "").strip()


def _connection_body(connection_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(connection_payload, dict):
        return {}
    for key in ("entry", "connection"):
        nested = connection_payload.get(key)
        if isinstance(nested, dict):
            return nested
    data = connection_payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("connection"), dict):
        return data["connection"]
    return connection_payload


def _connection_name(connection_payload: dict[str, Any] | None) -> str:
    payload = _connection_body(connection_payload)
    return str(payload.get("name") or payload.get("displayName") or "").strip()


def _connection_type(entry: dict[str, Any], connection_payload: dict[str, Any] | None) -> str:
    payload = _connection_body(connection_payload)
    for key in ("db_type", "type"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return str(entry.get("type") or "").strip()


def _normalize_ids(value: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value or []:
        item = str(item).strip()
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def _selected_ids(available_ids: list[str], explicit_ids: list[str] | None) -> tuple[list[str], list[str]]:
    explicit = _normalize_ids(explicit_ids)
    if not explicit:
        return list(available_ids), []
    missing = sorted(set(explicit) - set(available_ids))
    return explicit, missing


def _build_environment_aliases(
    connections: list[dict[str, Any]],
    selected_connection_ids: list[str],
) -> tuple[dict[str, str], list[str]]:
    selected = [connection for connection in connections if connection["entry_id"] in set(selected_connection_ids)]
    blockers: list[str] = []
    aliases: dict[str, str] = {}

    if not selected:
        return aliases, ["No selected connections were found for workbook source resolution."]

    if len(selected) == 1:
        connection = selected[0]
        aliases["defaultConnection"] = connection["entry_id"]
        environment = connection["inferred_environment"]
        if environment != "unknown":
            aliases[ENVIRONMENT_ALIAS_NAMES[environment]] = connection["entry_id"]
        connection["inferred_environment"] = environment if environment != "unknown" else "default"
        return aliases, blockers

    by_environment: dict[str, list[str]] = {}
    unknown_ids: list[str] = []
    for connection in selected:
        environment = connection["inferred_environment"]
        if environment == "unknown":
            unknown_ids.append(connection["entry_id"])
            continue
        by_environment.setdefault(environment, []).append(connection["entry_id"])

    for environment, ids in sorted(by_environment.items()):
        if len(ids) > 1:
            blockers.append(f"Ambiguous {environment} connections: {', '.join(sorted(ids))}.")
        else:
            aliases[ENVIRONMENT_ALIAS_NAMES[environment]] = ids[0]

    if unknown_ids:
        blockers.append(f"Unknown environment for connections: {', '.join(sorted(unknown_ids))}.")
    if "prodConnection" in aliases:
        aliases["defaultConnection"] = aliases["prodConnection"]
    elif len(aliases) == 1 and not blockers:
        aliases["defaultConnection"] = next(iter(aliases.values()))
    elif "defaultConnection" not in aliases:
        blockers.append("Unable to infer defaultConnection from multiple workbook connections.")
    return aliases, blockers


def dl_build_workbook_source_resolution(
    workbook_id: str,
    entries_payload: dict[str, Any],
    connection_payloads: dict[str, dict[str, Any] | None] | None = None,
    explicit_connection_ids: list[str] | None = None,
    explicit_dataset_ids: list[str] | None = None,
) -> dict[str, Any]:
    workbook_id = str(workbook_id).strip()
    if not workbook_id:
        raise DataLensApiError("workbook_id is required for workbook source resolution.")

    entries = _extract_entries(entries_payload)
    connection_payloads = connection_payloads or {}
    connection_entries = [entry for entry in entries if entry.get("scope") == "connection" and entry.get("entryId")]
    dataset_entries = [entry for entry in entries if entry.get("scope") == "dataset" and entry.get("entryId")]

    connections: list[dict[str, Any]] = []
    for entry in connection_entries:
        entry_id = str(entry["entryId"])
        payload = connection_payloads.get(entry_id)
        name = _connection_name(payload)
        label = _entry_label(entry)
        connections.append(
            {
                "entry_id": entry_id,
                "scope": "connection",
                "inventory_type": str(entry.get("type") or ""),
                "connection_type": _connection_type(entry, payload),
                "display_key": label,
                "name": name,
                "inferred_environment": _infer_environment(name, label),
                "workbook_id": str(entry.get("workbookId") or workbook_id),
            }
        )

    datasets = [
        {
            "entry_id": str(entry["entryId"]),
            "scope": "dataset",
            "display_key": _entry_label(entry),
            "name": str(entry.get("name") or ""),
            "workbook_id": str(entry.get("workbookId") or workbook_id),
        }
        for entry in dataset_entries
    ]

    selected_connection_ids, missing_connections = _selected_ids(
        [connection["entry_id"] for connection in connections],
        explicit_connection_ids,
    )
    selected_dataset_ids, missing_datasets = _selected_ids(
        [dataset["entry_id"] for dataset in datasets],
        explicit_dataset_ids,
    )

    blockers: list[str] = []
    if missing_connections:
        blockers.append(
            f"Explicit connection ids are not present in workbook {workbook_id}: {', '.join(missing_connections)}."
        )
    if missing_datasets:
        blockers.append(f"Explicit dataset ids are not present in workbook {workbook_id}: {', '.join(missing_datasets)}.")
    if not connections:
        blockers.append(f"Workbook {workbook_id} has no connection entries in getWorkbookEntries.")

    environment_aliases, alias_blockers = _build_environment_aliases(connections, selected_connection_ids)
    blockers.extend(alias_blockers)

    return {
        "version": 1,
        "generated_at": _now_utc(),
        "source": {"method": "getWorkbookEntries + getConnection", "workbook_id": workbook_id},
        "workbook_id": workbook_id,
        "connections": connections,
        "datasets": datasets,
        "selected_connection_ids": selected_connection_ids,
        "selected_dataset_ids": selected_dataset_ids,
        "api_connection_ids": [],
        "environment_aliases": environment_aliases,
        "blockers": blockers,
    }


def _dashboard_item_ids(entry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for tab in ((entry.get("data") or {}).get("tabs") or []):
        if not isinstance(tab, dict):
            continue
        for item in tab.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    return ids


def _require_dashboard_entry_shape(entry: dict[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} must be a dashboard entry object with data.tabs list.")
    data = entry.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("tabs"), list):
        raise ValueError(
            f"{label} must be a dashboard entry object with minimum shape "
            "{entryId?: string, data: {tabs: [...]}} including data.tabs; compact summaries are not accepted."
        )
    return entry


def _selector_wiring_status(entry: dict[str, Any], widget_plan: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    item_ids = _dashboard_item_ids(entry)
    for widget in widget_plan:
        widget_id = str(widget.get("widget_id") or "")
        if widget_id and item_ids and widget_id not in item_ids:
            errors.append(f"Widget {widget_id!r} is missing from dashboard items.")
        selector = widget.get("selector_definition")
        if not isinstance(selector, dict):
            continue
        affected = selector.get("affected_components")
        if not isinstance(affected, list) or not affected:
            errors.append(f"Selector {widget_id!r} must declare affected_components.")
            continue
        for component in affected:
            target_id = str((component or {}).get("widget_id") or "")
            if not target_id:
                errors.append(f"Selector {widget_id!r} has an affected component without widget_id.")
            elif item_ids and target_id not in item_ids:
                errors.append(f"Selector {widget_id!r} references missing widget {target_id!r}.")
    return {"status": "fail" if errors else "pass", "errors": errors}


def dl_build_selector_wiring_summary(
    remote_entry: dict[str, Any],
    proposed_entry: dict[str, Any],
    widget_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate selector wiring for dashboard entry objects.

    Minimum accepted shape is a hydrated dashboard entry object containing
    `data.tabs`; compact read summaries must be expanded before calling.
    """
    remote_entry = _require_dashboard_entry_shape(remote_entry, "remote_entry")
    proposed_entry = _require_dashboard_entry_shape(proposed_entry, "proposed_entry")
    summary = {
        "remote": _selector_wiring_status(remote_entry, widget_plan),
        "proposed": _selector_wiring_status(proposed_entry, widget_plan),
    }
    if summary["proposed"]["status"] != "pass":
        raise DataLensApiError(
            "Proposed dashboard selector wiring failed: " + "; ".join(summary["proposed"]["errors"])
        )
    return summary


def dl_build_runtime_verification_plan(workbook_id: str, run_id: str | None = None, execute: bool = False) -> dict[str, Any]:
    run_id = run_id or _compact_run_id()
    return {
        "version": 1,
        "execute": execute,
        "mode": "save",
        "workbook_id": workbook_id,
        "run_id": run_id,
        "objects": {
            "editor": {
                "key": f"runtime_verify_{run_id}_markdown",
                "name": f"js - verify markdown {run_id}",
                "type": "markdown_node",
            },
            "dashboard": {
                "key": f"runtime_verify_{run_id}_dashboard",
                "name": f"js - verify dashboard {run_id}",
            },
        },
        "steps": [
            {"method": "createEditorChart", "purpose": "create saved disposable markdown_node"},
            {"method": "getEditorChart", "purpose": "read back created editor object"},
            {"method": "createDashboard", "purpose": "create saved disposable dashboard mounting the editor object"},
            {"method": "getDashboard", "purpose": "read back created dashboard"},
            {"method": "updateEditorChart", "purpose": "update disposable editor object using fresh entryId/revId"},
            {"method": "getEditorChart", "purpose": "read back updated editor object"},
            {"method": "updateDashboard", "purpose": "update disposable dashboard using fresh entryId/revId"},
            {"method": "getDashboard", "purpose": "read back updated dashboard"},
        ],
    }


def _widget_decision(widget: dict[str, Any]) -> str:
    explicit = str(widget.get("decision") or widget.get("approved_route") or widget.get("route") or "").strip()
    if explicit:
        return explicit
    family = str(widget.get("approved_target_family") or widget.get("family") or "").lower()
    return decide_registered_route(family or "table_node").route


def _classification_workbooks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("workbooks"), list):
        return payload["workbooks"]
    if isinstance(payload.get("widgets"), list):
        return [{"workbook_id": "local", "title": "Local classification", "widgets": payload["widgets"]}]
    raise DataLensApiError("classification file must contain a workbooks or widgets list.")


def _render_wizard_summary(plan: dict[str, Any]) -> str:
    lines = [
        "# Wizard-To-JS Conversion Plan",
        "",
        f"- Workbooks: {plan['plan_summary']['workbook_count']}",
        f"- Widgets: {plan['plan_summary']['widget_count']}",
        "",
        "## Decisions",
    ]
    for decision, count in plan["plan_summary"]["decision_counts"].items():
        lines.append(f"- `{decision}`: {count}")
    lines.append("")
    return "\n".join(lines)


def dl_run_wizard_to_js_plan(
    project_root: str = ".",
    classification_path: str = "",
    plan_output_path: str = "",
    summary_output_path: str = "",
    workbook_ids: list[str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    classification = (
        Path(classification_path)
        if classification_path
        else root / "datalens_mapping" / "wizard_widget_classification.json"
    )
    if not classification.is_file():
        raise FileNotFoundError(str(classification))

    payload = _load_json(classification)
    requested = set(workbook_ids or [])
    workbooks: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    widget_count = 0

    for workbook in _classification_workbooks(payload):
        workbook_id = str(workbook.get("workbook_id") or workbook.get("id") or "local")
        if requested and workbook_id not in requested:
            continue
        widgets = workbook.get("widgets") or workbook.get("classified_widgets") or []
        planned_widgets = []
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            decision = _widget_decision(widget)
            decision_counts.update([decision])
            widget_count += 1
            planned_widgets.append(
                {
                    "entry_id": widget.get("entry_id") or widget.get("entryId") or widget.get("id"),
                    "name": widget.get("name") or widget.get("title") or "Untitled widget",
                    "decision": decision,
                    "source_family": widget.get("source_family") or widget.get("family") or "unknown",
                    "notes": widget.get("notes") or "",
                }
            )
        workbooks.append(
            {
                "workbook_id": workbook_id,
                "title": workbook.get("title") or workbook.get("name") or workbook_id,
                "widgets": planned_widgets,
            }
        )

    missing = requested - {workbook["workbook_id"] for workbook in workbooks}
    if missing:
        raise DataLensApiError("Requested workbook IDs are missing from the classification file: " + ", ".join(sorted(missing)))

    plan = {
        "version": 1,
        "scenario": "wizard_to_js",
        "generated_at": _now_utc(),
        "classification_path": str(classification),
        "plan_summary": {
            "workbook_count": len(workbooks),
            "widget_count": widget_count,
            "decision_counts": dict(sorted(decision_counts.items())),
        },
        "workbooks": workbooks,
    }

    plan_path = Path(plan_output_path) if plan_output_path else root / "datalens_mapping" / "wizard_to_js_plan.json"
    summary_path = Path(summary_output_path) if summary_output_path else root / "summaries" / "wizard_to_js_plan.md"
    _write_json(plan_path, plan)
    _write_text(summary_path, _render_wizard_summary(plan))

    return {
        "scenario": "wizard_to_js",
        "classification_path": str(classification),
        "plan_output_path": str(plan_path),
        "summary_output_path": str(summary_path),
        "workbook_count": len(workbooks),
        "widget_count": widget_count,
        "decision_counts": dict(sorted(decision_counts.items())),
    }
