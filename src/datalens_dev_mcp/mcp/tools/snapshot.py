from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.methods import openapi_lock_summary
from datalens_dev_mcp.mcp.response_projection import sanitize_response, serialized_metadata, stable_json_text
from datalens_dev_mcp.pipeline.artifacts import ensure_project_dirs, write_json


DASHBOARD_ID_KEYS = (
    "chartId",
    "chart_id",
    "entryId",
    "entry_id",
    "targetEntryId",
    "target_entry_id",
)
RELATION_SOURCE_KEYS = ("fromEntryId", "from_entry_id", "sourceEntryId", "source", "from")
RELATION_TARGET_KEYS = ("toEntryId", "to_entry_id", "targetEntryId", "target", "to")
VOLATILE_KEYS = {
    "createdAt",
    "updatedAt",
    "created_at",
    "updated_at",
    "revId",
    "rev_id",
    "savedId",
    "saved_id",
    "permissions",
    "favorite",
}
EDITOR_NODE_TYPES = ("table_node", "control_node", "markdown_node", "d3_node")


def dl_snapshot_dashboard(
    project_root: str = ".",
    dashboard_id: str = "",
    workbook_id: str = "",
    snapshot_branch: str = "saved",
    include_dormant_summary: bool = True,
    artifact_retention: str = "latest_only",
    client: Any | None = None,
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    if not dashboard_id:
        return {"ok": False, "error": {"category": "missing_dashboard_id", "message": "dashboard_id is required"}}
    branch_mode = str(snapshot_branch or "saved").strip().lower()
    if branch_mode not in {"saved", "published", "both"}:
        return {
            "ok": False,
            "error": {"category": "invalid_branch", "message": "snapshot_branch must be saved, published, or both"},
        }
    retention = str(artifact_retention or "latest_only").strip().lower()
    if retention not in {"latest_only", "hash_partitioned", "both"}:
        return {
            "ok": False,
            "error": {
                "category": "invalid_retention",
                "message": "artifact_retention must be latest_only, hash_partitioned, or both",
            },
        }

    active_client = client or _default_client()
    branches = ["saved", "published"] if branch_mode == "both" else [branch_mode]
    safe_dashboard_id = _safe_segment(dashboard_id)
    run_dir = root / "artifacts" / "authoritative_hardening" / "snapshots" / safe_dashboard_id / "latest"
    object_dir = run_dir / "objects"
    object_dir.mkdir(parents=True, exist_ok=True)

    errors: list[dict[str, str]] = []
    omissions: list[dict[str, str]] = []
    object_refs: list[dict[str, Any]] = []
    object_artifacts: dict[str, dict[str, Any]] = {}
    dashboard_payloads: dict[str, dict[str, Any]] = {}
    branch_summaries: dict[str, dict[str, Any]] = {}
    active_candidates: set[str] = set()
    tab_count = 0
    resolved_workbook_id = str(workbook_id or "").strip()

    for branch in branches:
        payload = {"dashboardId": dashboard_id, "branch": branch}
        dashboard = _read_rpc(active_client, "getDashboard", payload)
        if dashboard["ok"]:
            response = dashboard["response"]
            dashboard_payloads[branch] = response
            _record_object(
                object_refs=object_refs,
                object_artifacts=object_artifacts,
                object_dir=object_dir,
                method="getDashboard",
                object_type="dashboard",
                object_id=dashboard_id,
                branch=branch,
                response=response,
            )
            data = _object_data(response, "dashboard")
            entry = _object_entry(response, "dashboard")
            resolved_workbook_id = resolved_workbook_id or str(_first_value(entry, response, keys=("workbookId", "workbook_id")))
            tabs = _as_list(data.get("tabs"))
            tab_count = max(tab_count, len(tabs))
            active_candidates.update(_dashboard_active_candidates(data, dashboard_id=dashboard_id))
            normalized_structure = _strip_volatile(data)
            branch_summaries[branch] = {
                "rev_id": _first_value(entry, response, keys=("revId", "rev_id")),
                "saved_id": _first_value(entry, response, keys=("savedId", "saved_id")),
                "data_sha256": hashlib.sha256(stable_json_text(sanitize_response(data)).encode("utf-8")).hexdigest(),
                "normalized_structure_sha256": hashlib.sha256(
                    stable_json_text(sanitize_response(normalized_structure)).encode("utf-8")
                ).hexdigest(),
            }
        else:
            errors.append({"method": "getDashboard", "branch": branch, "message": dashboard["message"]})

    inventory_response: dict[str, Any] = {}
    inventory_entries: list[dict[str, Any]] = []
    inventory_types: dict[str, str] = {}
    if resolved_workbook_id:
        inventory = _read_rpc(active_client, "getWorkbookEntries", {"workbookId": resolved_workbook_id})
        if inventory["ok"]:
            inventory_response = inventory["response"]
            inventory_entries = _extract_entries(inventory_response)
            inventory_types = {_entry_id(entry): _classify_entry_type(entry) for entry in inventory_entries if _entry_id(entry)}
            _record_object(
                object_refs=object_refs,
                object_artifacts=object_artifacts,
                object_dir=object_dir,
                method="getWorkbookEntries",
                object_type="workbook_inventory",
                object_id=resolved_workbook_id,
                branch="",
                response=inventory_response,
            )
        else:
            errors.append({"method": "getWorkbookEntries", "message": inventory["message"]})
    else:
        omissions.append({"object_type": "workbook_inventory", "reason": "workbook_id_not_available"})

    active_chart_ids = sorted(
        candidate
        for candidate in active_candidates
        if candidate != dashboard_id and _is_chart_type(inventory_types.get(candidate, "chart"))
    )
    relation_ids = [dashboard_id, *active_chart_ids]
    relations_response: dict[str, Any] = {}
    relation_edges: list[dict[str, Any]] = []
    if relation_ids:
        relations = _read_rpc(active_client, "getEntriesRelations", {"entryIds": relation_ids})
        if relations["ok"]:
            relations_response = relations["response"]
            relation_edges = _extract_relation_edges(relations_response, inventory_types)
            _record_object(
                object_refs=object_refs,
                object_artifacts=object_artifacts,
                object_dir=object_dir,
                method="getEntriesRelations",
                object_type="entry_relations",
                object_id=dashboard_id,
                branch="",
                response=relations_response,
            )
        else:
            errors.append({"method": "getEntriesRelations", "message": relations["message"]})

    graph_edges = _dashboard_edges(dashboard_id, active_chart_ids, inventory_types) + relation_edges

    hydrated_chart_types: Counter[str] = Counter()
    for chart_id in active_chart_ids:
        object_type = _normalize_chart_type(inventory_types.get(chart_id, "chart"))
        method = _read_method_for_chart_type(object_type)
        if not method:
            omissions.append({"object_type": object_type, "object_id": chart_id, "reason": "no_curated_read_method"})
            continue
        response = _read_rpc(active_client, method, {"chartId": chart_id, "branch": branches[0]})
        if response["ok"]:
            hydrated_chart_types[object_type] += 1
            _record_object(
                object_refs=object_refs,
                object_artifacts=object_artifacts,
                object_dir=object_dir,
                method=method,
                object_type=object_type,
                object_id=chart_id,
                branch=branches[0],
                response=response["response"],
            )
            graph_edges.extend(_chart_dependency_edges(chart_id, response["response"], inventory_types))
        else:
            errors.append({"method": method, "object_id": chart_id, "message": response["message"]})

    dataset_ids = sorted(
        {
            str(edge["target"])
            for edge in graph_edges
            if edge.get("source") in active_chart_ids
            and _is_dataset_type(edge.get("target_type") or inventory_types.get(str(edge.get("target")), ""))
        }
    )

    for dataset_id in dataset_ids:
        payload: dict[str, Any] = {"datasetId": dataset_id}
        if resolved_workbook_id:
            payload["workbookId"] = resolved_workbook_id
        response = _read_rpc(active_client, "getDataset", payload)
        if response["ok"]:
            _record_object(
                object_refs=object_refs,
                object_artifacts=object_artifacts,
                object_dir=object_dir,
                method="getDataset",
                object_type="dataset",
                object_id=dataset_id,
                branch="",
                response=response["response"],
            )
            graph_edges.extend(_dataset_dependency_edges(dataset_id, response["response"], inventory_types))
        else:
            errors.append({"method": "getDataset", "object_id": dataset_id, "message": response["message"]})

    connection_ids = sorted(
        {
            str(edge["target"])
            for edge in graph_edges
            if edge.get("source") in dataset_ids
            and _is_connection_type(edge.get("target_type") or inventory_types.get(str(edge.get("target")), ""))
        }
    )

    for connection_id in connection_ids:
        payload = {"connectionId": connection_id}
        if resolved_workbook_id:
            payload["workbookId"] = resolved_workbook_id
        response = _read_rpc(active_client, "getConnection", payload)
        if response["ok"]:
            _record_object(
                object_refs=object_refs,
                object_artifacts=object_artifacts,
                object_dir=object_dir,
                method="getConnection",
                object_type="connection",
                object_id=connection_id,
                branch="",
                response=response["response"],
            )
        else:
            errors.append({"method": "getConnection", "object_id": connection_id, "message": response["message"]})

    active_ids = {dashboard_id, *active_chart_ids, *dataset_ids, *connection_ids}
    dormant = _dormant_summary(inventory_entries, active_ids) if include_dormant_summary else {"included": False}
    counts_by_object_type: dict[str, int] = {
        "dashboard": len(branch_summaries),
        "chart": len(active_chart_ids),
        "dataset": len(dataset_ids),
        "connection": len(connection_ids),
    }
    counts_by_object_type.update({key: int(value) for key, value in sorted(hydrated_chart_types.items())})
    if include_dormant_summary:
        counts_by_object_type["dormant"] = int(dormant.get("count", 0))

    coverage = {
        "schema_version": "2026-07-19.dashboard_snapshot_coverage.v1",
        "scope": "dashboard_dependency_graph",
        "org_wide": False,
        "requested_branches": branches,
        "captured_branches": [branch for branch in branches if branch in branch_summaries],
    }
    completion = _snapshot_completion(
        errors=errors,
        omissions=omissions,
        requested_branches=branches,
        captured_branches=set(branch_summaries),
    )
    api_contract = {
        "source": "compiled_openapi_lock",
        "header_name": "x-dl-api-version",
        **openapi_lock_summary(),
    }

    compact_graph = {
        "schema_version": "2026-06-25.dashboard_object_graph.v1",
        "dashboard_id": dashboard_id,
        "workbook_id": resolved_workbook_id,
        "snapshot_branch": branch_mode,
        "active_objects": _active_objects(
            dashboard_id=dashboard_id,
            chart_ids=active_chart_ids,
            dataset_ids=dataset_ids,
            connection_ids=connection_ids,
            inventory_types=inventory_types,
        ),
        "active_chart_ids": active_chart_ids,
        "dataset_ids": dataset_ids,
        "connection_ids": connection_ids,
        "edges": _dedupe_edges(graph_edges),
        "unresolved_edges": [],
    }
    graph_path = run_dir / "compact_graph.json"
    write_json(graph_path, compact_graph)
    graph_metadata = _file_metadata(graph_path)

    manifest = {
        "schema_version": "2026-06-25.dashboard_snapshot.v1",
        "target": {
            "dashboard_id": dashboard_id,
            "workbook_id": resolved_workbook_id,
            "snapshot_branch": branch_mode,
        },
        "tabs": tab_count,
        "counts_by_object_type": counts_by_object_type,
        "branches": branch_summaries,
        "branch_comparison": _branch_comparison(branch_summaries),
        "graph": compact_graph,
        "compact_graph_artifact": graph_metadata,
        "dormant": dormant,
        "object_refs": object_refs,
        "object_artifacts": sorted(object_artifacts.values(), key=lambda item: item["sha256"]),
        "errors": errors,
        "omissions": omissions,
        "completion": completion,
        "coverage": coverage,
        "api_contract": api_contract,
        "artifact_retention": retention,
    }
    manifest_path = run_dir / "manifest.json"
    _write_stable_json(manifest_path, manifest)
    manifest_metadata = _file_metadata(manifest_path)
    retained_manifest_paths = [str(manifest_path)]
    if retention in {"hash_partitioned", "both"}:
        retained = (
            root
            / "artifacts"
            / "authoritative_hardening"
            / "snapshots"
            / safe_dashboard_id
            / "by_hash"
            / manifest_metadata["sha256"]
        )
        retained.mkdir(parents=True, exist_ok=True)
        retained_manifest = retained / "manifest.json"
        _write_stable_json(retained_manifest, manifest)
        retained_manifest_paths.append(str(retained_manifest))

    response = {
        "ok": not errors,
        "model_facing_tool_calls": 1,
        "target_identity": {"dashboard_id": dashboard_id, "workbook_id": resolved_workbook_id},
        "snapshot_branch": branch_mode,
        "counts_by_object_type": counts_by_object_type,
        "tab_count": tab_count,
        "active_chart_count": len(active_chart_ids),
        "active_graph_edges": compact_graph["edges"][:200],
        "branch_summary": branch_summaries,
        "branch_comparison": manifest["branch_comparison"],
        "errors": errors,
        "omissions": omissions,
        "completion": completion,
        "coverage": coverage,
        "api_contract": api_contract,
        "manifest": manifest_metadata,
        "compact_graph": graph_metadata,
        "object_artifact_count": len(object_artifacts),
        "dormant_summary": dormant,
        "retained_manifest_paths": retained_manifest_paths,
    }
    response_metadata = serialized_metadata(response)
    response["inline_serialized_chars"] = response_metadata["serialized_chars"]
    response["inline_serialized_bytes"] = response_metadata["serialized_bytes"]
    return response


def _default_client() -> Any:
    from datalens_dev_mcp.api.client import DataLensApiClient
    from datalens_dev_mcp.config import DataLensConfig

    return DataLensApiClient(DataLensConfig.from_env())


def _snapshot_completion(
    *,
    errors: list[dict[str, str]],
    omissions: list[dict[str, str]],
    requested_branches: list[str],
    captured_branches: set[str],
) -> dict[str, Any]:
    missing_root_branches = [branch for branch in requested_branches if branch not in captured_branches]
    unsafe_reasons = ["dashboard_root_not_captured"] if missing_root_branches else []
    if unsafe_reasons:
        status = "unsafe"
    elif errors or omissions:
        status = "partial"
    else:
        status = "complete"
    return {
        "schema_version": "2026-07-19.dashboard_snapshot_completion.v1",
        "status": status,
        "complete": status == "complete",
        "authoritative_backup_complete": status == "complete",
        "error_count": len(errors),
        "omission_count": len(omissions),
        "missing_root_branches": missing_root_branches,
        "unsafe_reasons": unsafe_reasons,
    }


def _read_rpc(client: Any, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if hasattr(client, "rpc_readonly"):
            return {"ok": True, "response": client.rpc_readonly(method, payload)}
        return {"ok": True, "response": client.rpc(method, payload)}
    except Exception as exc:  # pragma: no cover - exact client errors vary by transport.
        return {"ok": False, "message": _safe_error_text(exc)}


def _safe_error_text(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    for marker in ("Authorization", "DATALENS_IAM_TOKEN", "YC_IAM_TOKEN", "Bearer ", "token", "iam"):
        text = text.replace(marker, "<redacted>")
    return text[:400]


def _record_object(
    *,
    object_refs: list[dict[str, Any]],
    object_artifacts: dict[str, dict[str, Any]],
    object_dir: Path,
    method: str,
    object_type: str,
    object_id: str,
    branch: str,
    response: dict[str, Any],
) -> None:
    sanitized = sanitize_response(response)
    text = stable_json_text(sanitized)
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = object_dir / f"{sha256}.json"
    if sha256 not in object_artifacts:
        path.write_text(text + "\n", encoding="utf-8")
        object_artifacts[sha256] = {
            "path": str(path),
            "sha256": sha256,
            "serialized_chars": len(text),
            "serialized_bytes": len(text.encode("utf-8")),
        }
    object_refs.append(
        {
            "object_type": object_type,
            "object_id": object_id,
            "branch": branch,
            "method": method,
            "sha256": sha256,
            "path": str(path),
        }
    )


def _dashboard_active_candidates(data: dict[str, Any], *, dashboard_id: str) -> set[str]:
    candidates: set[str] = set()
    for item in _iter_dicts(data):
        for key in DASHBOARD_ID_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value and value != dashboard_id:
                candidates.add(value)
    return candidates


def _extract_entries(response: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("entries", "items", "result"):
        value = response.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("entries") or value.get("items")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _extract_relation_edges(response: dict[str, Any], inventory_types: dict[str, str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for item in _iter_dicts(response):
        source = _first_value(item, keys=RELATION_SOURCE_KEYS)
        target = _first_value(item, keys=RELATION_TARGET_KEYS)
        if not source or not target or source == target:
            continue
        relation_type = str(item.get("relationType") or item.get("type") or item.get("scope") or "relation")
        edges.append(
            {
                "source": str(source),
                "source_type": _normalize_object_type(inventory_types.get(str(source), "")),
                "target": str(target),
                "target_type": _normalize_object_type(inventory_types.get(str(target), "")),
                "relation": relation_type,
            }
        )
    return _dedupe_edges(edges)


def _dashboard_edges(dashboard_id: str, chart_ids: list[str], inventory_types: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "source": dashboard_id,
            "source_type": "dashboard",
            "target": chart_id,
            "target_type": _normalize_object_type(inventory_types.get(chart_id, "chart")),
            "relation": "dashboard_item",
        }
        for chart_id in chart_ids
    ]


def _chart_dependency_edges(chart_id: str, response: dict[str, Any], inventory_types: dict[str, str]) -> list[dict[str, Any]]:
    edges = []
    for dataset_id in sorted(_object_ids_by_kind(response, id_kind="dataset")):
        edges.append(
            {
                "source": chart_id,
                "source_type": _normalize_object_type(inventory_types.get(chart_id, "chart")),
                "target": dataset_id,
                "target_type": "dataset",
                "relation": "chart_payload_dataset",
            }
        )
    for target_id in sorted(_object_ids_by_kind(response, id_kind="connection")):
        edges.append(
            {
                "source": chart_id,
                "source_type": _normalize_object_type(inventory_types.get(chart_id, "chart")),
                "target": target_id,
                "target_type": "connection",
                "relation": "chart_payload_connection",
            }
        )
    return _dedupe_edges(edges)


def _dataset_dependency_edges(dataset_id: str, response: dict[str, Any], inventory_types: dict[str, str]) -> list[dict[str, Any]]:
    return _dedupe_edges(
        [
            {
                "source": dataset_id,
                "source_type": "dataset",
                "target": connection_id,
                "target_type": "connection",
                "relation": "dataset_payload_connection",
            }
            for connection_id in sorted(_object_ids_by_kind(response, id_kind="connection"))
        ]
    )


def _object_ids_by_kind(value: Any, *, id_kind: str) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if id_kind == "dataset" and lowered in {"datasetid", "dataset_id", "datasetentryid"}:
                if isinstance(item, str) and item:
                    ids.add(item)
            elif id_kind == "connection" and lowered in {"connectionid", "connection_id", "connid", "conn_id"}:
                if isinstance(item, str) and item:
                    ids.add(item)
            ids.update(_object_ids_by_kind(item, id_kind=id_kind))
    elif isinstance(value, list):
        for item in value:
            ids.update(_object_ids_by_kind(item, id_kind=id_kind))
    return ids


def _active_objects(
    *,
    dashboard_id: str,
    chart_ids: list[str],
    dataset_ids: list[str],
    connection_ids: list[str],
    inventory_types: dict[str, str],
) -> list[dict[str, str]]:
    rows = [{"object_id": dashboard_id, "object_type": "dashboard", "scope": "dashboard"}]
    rows.extend(
        {
            "object_id": chart_id,
            "object_type": _normalize_object_type(inventory_types.get(chart_id, "chart")),
            "scope": inventory_types.get(chart_id, "chart"),
        }
        for chart_id in chart_ids
    )
    rows.extend({"object_id": dataset_id, "object_type": "dataset", "scope": "dataset"} for dataset_id in dataset_ids)
    rows.extend(
        {"object_id": connection_id, "object_type": "connection", "scope": "connection"}
        for connection_id in connection_ids
    )
    return rows


def _dormant_summary(entries: list[dict[str, Any]], active_ids: set[str]) -> dict[str, Any]:
    dormant_entries: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    for entry in entries:
        entry_id = _entry_id(entry)
        if not entry_id or entry_id in active_ids:
            continue
        object_type = _normalize_object_type(_classify_entry_type(entry))
        counts[object_type] += 1
        dormant_entries.append({"entry_id": entry_id, "object_type": object_type})
    return {
        "included": True,
        "count": len(dormant_entries),
        "counts_by_object_type": dict(sorted(counts.items())),
        "entries": dormant_entries[:100],
        "hydrated": False,
    }


def _classify_entry_type(entry: dict[str, Any]) -> str:
    raw = " ".join(str(entry.get(key) or "") for key in ("scope", "type", "entryType", "objectType", "kind")).lower()
    if "dashboard" in raw or raw in {"dash"}:
        return "dashboard"
    if "dataset" in raw:
        return "dataset"
    if "connection" in raw or "connector" in raw:
        return "connection"
    for node_type in EDITOR_NODE_TYPES:
        if node_type in raw:
            return node_type
    if "wizard" in raw:
        return "wizard_chart"
    if "editor" in raw or "advanced" in raw:
        return "editor_chart"
    if "ql" in raw:
        return "ql_chart"
    if "chart" in raw:
        return "chart"
    return raw.strip() or "unknown"


def _normalize_object_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if _is_dataset_type(normalized):
        return "dataset"
    if _is_connection_type(normalized):
        return "connection"
    if _is_chart_type(normalized):
        return _normalize_chart_type(normalized)
    if "dashboard" in normalized or normalized == "dash":
        return "dashboard"
    return normalized or "unknown"


def _normalize_chart_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    for node_type in EDITOR_NODE_TYPES:
        if node_type in normalized:
            return node_type
    if "wizard" in normalized:
        return "wizard_chart"
    if "editor" in normalized or "advanced" in normalized:
        return "editor_chart"
    if "ql" in normalized:
        return "ql_chart"
    return "chart"


def _read_method_for_chart_type(object_type: str) -> str:
    if object_type == "editor_chart" or object_type in EDITOR_NODE_TYPES:
        return "getEditorChart"
    if object_type == "wizard_chart":
        return "getWizardChart"
    if object_type == "ql_chart":
        return "getQLChart"
    return ""


def _is_chart_type(value: str) -> bool:
    normalized = str(value or "").lower()
    return (
        normalized in {"chart", "editor_chart", "wizard_chart", "ql_chart"}
        or normalized in EDITOR_NODE_TYPES
        or "chart" in normalized
    )


def _is_dataset_type(value: str) -> bool:
    return "dataset" in str(value or "").lower()


def _is_connection_type(value: str) -> bool:
    normalized = str(value or "").lower()
    return "connection" in normalized or "connector" in normalized


def _entry_id(entry: dict[str, Any]) -> str:
    return str(_first_value(entry, keys=("entryId", "entry_id", "id", "chartId", "datasetId", "connectionId")) or "")


def _object_entry(response: dict[str, Any], object_key: str) -> dict[str, Any]:
    result = response.get("result")
    if isinstance(result, dict):
        nested_entry = _object_entry(result, object_key)
        if nested_entry:
            return nested_entry
    if isinstance(response.get("entry"), dict):
        return response["entry"]
    nested = response.get(object_key)
    if isinstance(nested, dict) and isinstance(nested.get("entry"), dict):
        return nested["entry"]
    if isinstance(nested, dict):
        return nested
    return response if isinstance(response, dict) else {}


def _object_data(response: dict[str, Any], object_key: str) -> dict[str, Any]:
    entry = _object_entry(response, object_key)
    if isinstance(entry.get("data"), dict):
        return entry["data"]
    nested = response.get(object_key)
    if isinstance(nested, dict) and isinstance(nested.get("data"), dict):
        return nested["data"]
    if isinstance(response.get("data"), dict):
        return response["data"]
    return {}


def _branch_comparison(branch_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    saved = branch_summaries.get("saved") or {}
    published = branch_summaries.get("published") or {}
    if not saved or not published:
        return {"available": False}
    return {
        "available": True,
        "same_rev_id": saved.get("rev_id") == published.get("rev_id"),
        "same_saved_id": saved.get("saved_id") == published.get("saved_id"),
        "same_normalized_structure": saved.get("normalized_structure_sha256")
        == published.get("normalized_structure_sha256"),
    }


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_volatile(item) for key, item in sorted(value.items()) if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for item in value.values():
            found.extend(_iter_dicts(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_iter_dicts(item))
    return found


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        key = (str(edge.get("source")), str(edge.get("target")), str(edge.get("relation")))
        deduped[key] = edge
    return [deduped[key] for key in sorted(deduped)]


def _first_value(*sources: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return value
    return ""


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _file_metadata(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": str(path),
        "serialized_bytes": len(content.rstrip(b"\n")),
        "sha256": hashlib.sha256(content.rstrip(b"\n")).hexdigest(),
    }


def _write_stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json_text(payload) + "\n", encoding="utf-8")


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned[:80] or "dashboard"
