from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.concurrency import bounded_read_map, configured_read_workers
from datalens_dev_mcp.api.methods import openapi_lock_summary
from datalens_dev_mcp.api.scheduler import record_cache_hit
from datalens_dev_mcp.mcp.response_projection import sanitize_response, serialized_metadata, stable_json_text
from datalens_dev_mcp.pipeline.artifacts import ensure_project_dirs, read_json, write_json


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
ACTIVE_GRAPH_EDGE_PREVIEW_LIMIT = 24
DORMANT_ENTRY_PREVIEW_LIMIT = 12
INLINE_FAILURE_PREVIEW_LIMIT = 8
ENTRY_REVISION_KEYS = (
    "revId",
    "rev_id",
    "savedId",
    "saved_id",
    "publishedId",
    "published_id",
    "updatedAt",
    "updated_at",
    "modifiedAt",
    "modified_at",
)


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
    manifest_path = run_dir / "manifest.json"
    try:
        previous_manifest = read_json(manifest_path, default={})
    except (OSError, ValueError):
        previous_manifest = {}

    errors: list[dict[str, str]] = []
    omissions: list[dict[str, str]] = []
    object_refs: list[dict[str, Any]] = []
    object_artifacts: dict[str, dict[str, Any]] = {}
    dashboard_payloads: dict[str, dict[str, Any]] = {}
    branch_summaries: dict[str, dict[str, Any]] = {}
    active_candidates: set[str] = set()
    active_candidates_by_branch: dict[str, set[str]] = {}
    tab_count = 0
    resolved_workbook_id = str(workbook_id or "").strip()

    dashboard_reads = _read_many(
        active_client,
        [
            ("getDashboard", {"dashboardId": dashboard_id, "branch": branch})
            for branch in branches
        ],
    )
    for branch, dashboard in zip(branches, dashboard_reads):
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
            branch_candidates = _dashboard_active_candidates(data, dashboard_id=dashboard_id)
            active_candidates_by_branch[branch] = branch_candidates
            active_candidates.update(branch_candidates)
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
    active_chart_ids_by_branch = {
        branch: sorted(
            candidate
            for candidate in active_candidates_by_branch.get(branch, set())
            if candidate != dashboard_id and _is_chart_type(inventory_types.get(candidate, "chart"))
        )
        for branch in branches
    }
    source_state = _snapshot_source_state(
        dashboard_id=dashboard_id,
        workbook_id=resolved_workbook_id,
        snapshot_branch=branch_mode,
        branch_summaries=branch_summaries,
        inventory_entries=inventory_entries,
    )
    if _snapshot_manifest_is_reusable(
        previous_manifest,
        manifest_path=manifest_path,
        dashboard_id=dashboard_id,
        workbook_id=resolved_workbook_id,
        snapshot_branch=branch_mode,
        include_dormant_summary=include_dormant_summary,
        artifact_retention=retention,
        source_state=source_state,
    ):
        record_cache_hit("dashboard_snapshot")
        return _reused_snapshot_response(
            previous_manifest,
            manifest_path=manifest_path,
            dashboard_id=dashboard_id,
            workbook_id=resolved_workbook_id,
            snapshot_branch=branch_mode,
            branch_summaries=branch_summaries,
            source_probe_rpc_count=len(branches) + (1 if resolved_workbook_id else 0),
        )

    hydration_rpc_count = 0
    relation_ids = [dashboard_id, *active_chart_ids]
    relations_response: dict[str, Any] = {}
    relation_edges: list[dict[str, Any]] = []
    if relation_ids:
        hydration_rpc_count += 1
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

    required_object_branch_pairs: set[tuple[str, str, str]] = {
        ("dashboard", dashboard_id, branch)
        for branch in branches
    }
    captured_object_branch_pairs: set[tuple[str, str, str]] = {
        ("dashboard", dashboard_id, branch)
        for branch in branch_summaries
    }
    hydrated_chart_ids_by_type: dict[str, set[str]] = {}
    chart_specs: list[tuple[str, str, str, str, dict[str, Any]]] = []
    for branch in branches:
        for chart_id in active_chart_ids_by_branch.get(branch, []):
            object_type = _normalize_chart_type(inventory_types.get(chart_id, "chart"))
            required_object_branch_pairs.add((object_type, chart_id, branch))
            method = _read_method_for_chart_type(object_type)
            if not method:
                omissions.append(
                    {
                        "object_type": object_type,
                        "object_id": chart_id,
                        "branch": branch,
                        "reason": "no_curated_read_method",
                    }
                )
                continue
            chart_specs.append(
                (
                    chart_id,
                    object_type,
                    method,
                    branch,
                    {"chartId": chart_id, "branch": branch},
                )
            )
    hydration_rpc_count += len(chart_specs)
    chart_reads = _read_many(
        active_client,
        [(method, payload) for _, _, method, _, payload in chart_specs],
    )
    for (chart_id, object_type, method, branch, _), response in zip(chart_specs, chart_reads):
        if response["ok"]:
            hydrated_chart_ids_by_type.setdefault(object_type, set()).add(chart_id)
            captured_object_branch_pairs.add((object_type, chart_id, branch))
            _record_object(
                object_refs=object_refs,
                object_artifacts=object_artifacts,
                object_dir=object_dir,
                method=method,
                object_type=object_type,
                object_id=chart_id,
                branch=branch,
                response=response["response"],
            )
            graph_edges.extend(_chart_dependency_edges(chart_id, response["response"], inventory_types))
        else:
            errors.append(
                {
                    "method": method,
                    "object_id": chart_id,
                    "branch": branch,
                    "message": response["message"],
                }
            )

    dataset_ids = sorted(
        {
            str(edge["target"])
            for edge in graph_edges
            if edge.get("source") in active_chart_ids
            and _is_dataset_type(edge.get("target_type") or inventory_types.get(str(edge.get("target")), ""))
        }
    )

    dataset_specs: list[tuple[str, dict[str, Any]]] = []
    for dataset_id in dataset_ids:
        payload: dict[str, Any] = {"datasetId": dataset_id}
        if resolved_workbook_id:
            payload["workbookId"] = resolved_workbook_id
        dataset_specs.append((dataset_id, payload))
    hydration_rpc_count += len(dataset_specs)
    dataset_reads = _read_many(
        active_client,
        [("getDataset", payload) for _, payload in dataset_specs],
    )
    for (dataset_id, _), response in zip(dataset_specs, dataset_reads):
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

    connection_specs: list[tuple[str, dict[str, Any]]] = []
    for connection_id in connection_ids:
        payload = {"connectionId": connection_id}
        if resolved_workbook_id:
            payload["workbookId"] = resolved_workbook_id
        connection_specs.append((connection_id, payload))
    hydration_rpc_count += len(connection_specs)
    connection_reads = _read_many(
        active_client,
        [("getConnection", payload) for _, payload in connection_specs],
    )
    for (connection_id, _), response in zip(connection_specs, connection_reads):
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
    counts_by_object_type.update(
        {
            key: len(chart_ids)
            for key, chart_ids in sorted(hydrated_chart_ids_by_type.items())
        }
    )
    if include_dormant_summary:
        counts_by_object_type["dormant"] = int(dormant.get("count", 0))

    missing_object_branch_pairs = required_object_branch_pairs - captured_object_branch_pairs
    object_branch_coverage = _object_branch_coverage(
        requested_branches=branches,
        required_pairs=required_object_branch_pairs,
        captured_pairs=captured_object_branch_pairs,
    )
    coverage = {
        "schema_version": "2026-07-19.dashboard_snapshot_coverage.v1",
        "scope": "dashboard_dependency_graph",
        "org_wide": False,
        "requested_branches": branches,
        "captured_branches": [branch for branch in branches if branch in branch_summaries],
        "object_branch_coverage": object_branch_coverage,
    }
    completion = _snapshot_completion(
        errors=errors,
        omissions=omissions,
        requested_branches=branches,
        captured_branches=set(branch_summaries),
        missing_dependency_pairs=missing_object_branch_pairs,
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
        "source_fingerprint": source_state["fingerprint"],
        "inventory_revision_complete": source_state["inventory_revision_complete"],
        "inventory_entry_count": source_state["inventory_entry_count"],
    }
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

    active_graph_edge_preview = compact_graph["edges"][:ACTIVE_GRAPH_EDGE_PREVIEW_LIMIT]
    inline_errors, inline_errors_metadata = _bounded_inline_preview(
        errors,
        limit=INLINE_FAILURE_PREVIEW_LIMIT,
    )
    inline_omissions, inline_omissions_metadata = _bounded_inline_preview(
        omissions,
        limit=INLINE_FAILURE_PREVIEW_LIMIT,
    )
    inline_coverage = _compact_inline_coverage(coverage)
    response = {
        "ok": not errors,
        "model_facing_tool_calls": 1,
        "target_identity": {"dashboard_id": dashboard_id, "workbook_id": resolved_workbook_id},
        "snapshot_branch": branch_mode,
        "counts_by_object_type": counts_by_object_type,
        "tab_count": tab_count,
        "active_chart_count": len(active_chart_ids),
        "active_graph_edges": active_graph_edge_preview,
        "active_graph_edge_preview": {
            "total_count": len(compact_graph["edges"]),
            "preview_count": len(active_graph_edge_preview),
            "limit": ACTIVE_GRAPH_EDGE_PREVIEW_LIMIT,
            "truncated": len(active_graph_edge_preview) < len(compact_graph["edges"]),
        },
        "branch_summary": branch_summaries,
        "branch_comparison": manifest["branch_comparison"],
        "errors": inline_errors,
        "errors_preview": inline_errors_metadata,
        "omissions": inline_omissions,
        "omissions_preview": inline_omissions_metadata,
        "completion": completion,
        "coverage": inline_coverage,
        "api_contract": api_contract,
        "manifest": manifest_metadata,
        "compact_graph": graph_metadata,
        "object_artifact_count": len(object_artifacts),
        "dormant_summary": _compact_dormant_preview(dormant),
        "retained_manifest_paths": retained_manifest_paths,
        "snapshot_reused": False,
        "snapshot_reuse_eligible": source_state["inventory_revision_complete"],
        "source_probe_rpc_count": len(branches) + (1 if resolved_workbook_id else 0),
        "hydration_rpc_count": hydration_rpc_count,
    }
    response_metadata = serialized_metadata(response)
    response["inline_serialized_chars"] = response_metadata["serialized_chars"]
    response["inline_serialized_bytes"] = response_metadata["serialized_bytes"]
    return response


def _snapshot_source_state(
    *,
    dashboard_id: str,
    workbook_id: str,
    snapshot_branch: str,
    branch_summaries: dict[str, dict[str, Any]],
    inventory_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_branch_count = 2 if snapshot_branch == "both" else 1
    revision_complete = bool(inventory_entries) and all(
        any(entry.get(key) not in (None, "") for key in ENTRY_REVISION_KEYS) for entry in inventory_entries
    )
    fingerprint = ""
    if revision_complete and len(branch_summaries) == expected_branch_count:
        inventory_rows = []
        for entry in inventory_entries:
            inventory_rows.append(
                {
                    "entry_id": _entry_id(entry),
                    "scope": entry.get("scope"),
                    "type": entry.get("type"),
                    "entry_type": entry.get("entryType"),
                    "object_type": entry.get("objectType"),
                    "kind": entry.get("kind"),
                    "display_key": entry.get("displayKey"),
                    "hidden": entry.get("hidden"),
                    "deleted": entry.get("isDeleted"),
                    "revisions": {key: entry.get(key) for key in ENTRY_REVISION_KEYS if entry.get(key) not in (None, "")},
                }
            )
        payload = {
            "dashboard_id": dashboard_id,
            "workbook_id": workbook_id,
            "snapshot_branch": snapshot_branch,
            "branches": branch_summaries,
            "inventory": sorted(inventory_rows, key=stable_json_text),
        }
        fingerprint = hashlib.sha256(stable_json_text(payload).encode("utf-8")).hexdigest()
    return {
        "fingerprint": fingerprint,
        "inventory_revision_complete": revision_complete,
        "inventory_entry_count": len(inventory_entries),
    }


def _snapshot_manifest_is_reusable(
    manifest: Any,
    *,
    manifest_path: Path,
    dashboard_id: str,
    workbook_id: str,
    snapshot_branch: str,
    include_dormant_summary: bool,
    artifact_retention: str,
    source_state: dict[str, Any],
) -> bool:
    if not isinstance(manifest, dict) or not source_state.get("fingerprint"):
        return False
    target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}
    if target != {
        "dashboard_id": dashboard_id,
        "workbook_id": workbook_id,
        "snapshot_branch": snapshot_branch,
    }:
        return False
    if manifest.get("source_fingerprint") != source_state["fingerprint"]:
        return False
    if not manifest.get("inventory_revision_complete") or manifest.get("errors"):
        return False
    dormant = manifest.get("dormant") if isinstance(manifest.get("dormant"), dict) else {}
    if bool(dormant.get("included")) != bool(include_dormant_summary):
        return False
    if manifest.get("artifact_retention") != artifact_retention:
        return False
    graph = manifest.get("graph")
    graph_artifact = manifest.get("compact_graph_artifact")
    object_artifacts = manifest.get("object_artifacts")
    if not isinstance(graph, dict) or not isinstance(graph_artifact, dict) or not isinstance(object_artifacts, list):
        return False
    if not _artifact_metadata_matches(graph_artifact):
        return False
    if not object_artifacts or not all(
        isinstance(artifact, dict) and _artifact_metadata_matches(artifact) for artifact in object_artifacts
    ):
        return False
    if artifact_retention in {"hash_partitioned", "both"}:
        latest_metadata = _file_metadata(manifest_path)
        retained_path = (
            manifest_path.parent.parent / "by_hash" / latest_metadata["sha256"] / "manifest.json"
        )
        if not retained_path.is_file() or _file_metadata(retained_path)["sha256"] != latest_metadata["sha256"]:
            return False
    return True


def _artifact_metadata_matches(metadata: dict[str, Any]) -> bool:
    path_value = metadata.get("path")
    expected_sha256 = str(metadata.get("sha256") or "")
    if not path_value or not expected_sha256:
        return False
    path = Path(str(path_value))
    try:
        return path.is_file() and _file_metadata(path)["sha256"] == expected_sha256
    except OSError:
        return False


def _reused_snapshot_response(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    dashboard_id: str,
    workbook_id: str,
    snapshot_branch: str,
    branch_summaries: dict[str, dict[str, Any]],
    source_probe_rpc_count: int,
) -> dict[str, Any]:
    graph = manifest["graph"]
    manifest_metadata = _file_metadata(manifest_path)
    retained_manifest_paths = [str(manifest_path)]
    if manifest.get("artifact_retention") in {"hash_partitioned", "both"}:
        retained_manifest_paths.append(
            str(manifest_path.parent.parent / "by_hash" / manifest_metadata["sha256"] / "manifest.json")
        )
    active_chart_ids = graph.get("active_chart_ids") if isinstance(graph.get("active_chart_ids"), list) else []
    object_artifacts = manifest.get("object_artifacts") if isinstance(manifest.get("object_artifacts"), list) else []
    graph_edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    active_graph_edge_preview = graph_edges[:ACTIVE_GRAPH_EDGE_PREVIEW_LIMIT]
    errors = manifest.get("errors") if isinstance(manifest.get("errors"), list) else []
    omissions = manifest.get("omissions") if isinstance(manifest.get("omissions"), list) else []
    inline_errors, inline_errors_metadata = _bounded_inline_preview(
        errors,
        limit=INLINE_FAILURE_PREVIEW_LIMIT,
    )
    inline_omissions, inline_omissions_metadata = _bounded_inline_preview(
        omissions,
        limit=INLINE_FAILURE_PREVIEW_LIMIT,
    )
    coverage = manifest.get("coverage") if isinstance(manifest.get("coverage"), dict) else {}
    response = {
        "ok": True,
        "model_facing_tool_calls": 1,
        "target_identity": {"dashboard_id": dashboard_id, "workbook_id": workbook_id},
        "snapshot_branch": snapshot_branch,
        "counts_by_object_type": manifest.get("counts_by_object_type") or {},
        "tab_count": int(manifest.get("tabs") or 0),
        "active_chart_count": len(active_chart_ids),
        "active_graph_edges": active_graph_edge_preview,
        "active_graph_edge_preview": {
            "total_count": len(graph_edges),
            "preview_count": len(active_graph_edge_preview),
            "limit": ACTIVE_GRAPH_EDGE_PREVIEW_LIMIT,
            "truncated": len(active_graph_edge_preview) < len(graph_edges),
        },
        "branch_summary": branch_summaries,
        "branch_comparison": manifest.get("branch_comparison") or {"available": False},
        "errors": inline_errors,
        "errors_preview": inline_errors_metadata,
        "omissions": inline_omissions,
        "omissions_preview": inline_omissions_metadata,
        "completion": manifest.get("completion") or {},
        "coverage": _compact_inline_coverage(coverage),
        "api_contract": manifest.get("api_contract") or {},
        "manifest": manifest_metadata,
        "compact_graph": manifest["compact_graph_artifact"],
        "object_artifact_count": len(object_artifacts),
        "dormant_summary": manifest.get("dormant") or {"included": False},
        "retained_manifest_paths": retained_manifest_paths,
        "snapshot_reused": True,
        "snapshot_reuse_eligible": True,
        "source_probe_rpc_count": source_probe_rpc_count,
        "hydration_rpc_count": 0,
        "reuse_basis": "fresh_dashboard_and_revision_complete_workbook_inventory",
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
    missing_dependency_pairs: set[tuple[str, str, str]],
) -> dict[str, Any]:
    missing_root_branches = [branch for branch in requested_branches if branch not in captured_branches]
    unsafe_reasons = ["dashboard_root_not_captured"] if missing_root_branches else []
    if unsafe_reasons:
        status = "unsafe"
    elif errors or omissions or missing_dependency_pairs:
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
        "missing_dependency_pair_count": len(missing_dependency_pairs),
        "missing_dependency_pairs_sha256": serialized_metadata(
            _object_branch_pair_items(missing_dependency_pairs)
        )["sha256"],
        "missing_dependency_pairs_ref": "coverage.object_branch_coverage.missing_pairs",
        "unsafe_reasons": unsafe_reasons,
    }


def _object_branch_coverage(
    *,
    requested_branches: list[str],
    required_pairs: set[tuple[str, str, str]],
    captured_pairs: set[tuple[str, str, str]],
) -> dict[str, Any]:
    missing_pairs = required_pairs - captured_pairs
    captured_required_pairs = required_pairs & captured_pairs
    required_rows = [list(item) for item in sorted(required_pairs)]
    captured_rows = [list(item) for item in sorted(captured_required_pairs)]
    missing_pair_items = _object_branch_pair_items(missing_pairs)
    _missing_preview, missing_pairs_metadata = _bounded_inline_preview(
        missing_pair_items,
        limit=INLINE_FAILURE_PREVIEW_LIMIT,
    )
    return {
        "required_pair_count": len(required_pairs),
        "captured_pair_count": len(captured_required_pairs),
        "missing_pair_count": len(missing_pairs),
        "required_pairs_sha256": hashlib.sha256(stable_json_text(required_rows).encode("utf-8")).hexdigest(),
        "captured_pairs_sha256": hashlib.sha256(stable_json_text(captured_rows).encode("utf-8")).hexdigest(),
        "missing_pairs_preview": missing_pairs_metadata,
        "by_branch": {
            branch: {
                "required_pair_count": sum(
                    1 for _object_type, _object_id, pair_branch in required_pairs if pair_branch == branch
                ),
                "captured_pair_count": sum(
                    1
                    for _object_type, _object_id, pair_branch in captured_required_pairs
                    if pair_branch == branch
                ),
                "missing_pair_count": sum(
                    1 for _object_type, _object_id, pair_branch in missing_pairs if pair_branch == branch
                ),
            }
            for branch in requested_branches
        },
        "missing_pairs": missing_pair_items,
    }


def _object_branch_pair_items(pairs: set[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [
        {"object_type": object_type, "object_id": object_id, "branch": branch}
        for object_type, object_id, branch in sorted(pairs)
    ]


def _bounded_inline_preview(
    items: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    preview = items[:limit]
    return preview, {
        "total_count": len(items),
        "preview_count": len(preview),
        "limit": limit,
        "truncated": len(preview) < len(items),
        "sha256": serialized_metadata(items)["sha256"],
    }


def _compact_inline_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    inline = dict(coverage)
    full_object_branch = coverage.get("object_branch_coverage")
    if not isinstance(full_object_branch, dict):
        return inline
    object_branch = dict(full_object_branch)
    missing_pairs = full_object_branch.get("missing_pairs")
    if not isinstance(missing_pairs, list):
        missing_pairs = []
    preview, metadata = _bounded_inline_preview(
        [item for item in missing_pairs if isinstance(item, dict)],
        limit=INLINE_FAILURE_PREVIEW_LIMIT,
    )
    object_branch["missing_pairs"] = preview
    object_branch["missing_pairs_preview"] = metadata
    inline["object_branch_coverage"] = object_branch
    return inline


def _read_rpc(client: Any, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if hasattr(client, "rpc_readonly"):
            return {"ok": True, "response": client.rpc_readonly(method, payload)}
        return {"ok": True, "response": client.rpc(method, payload)}
    except Exception as exc:  # pragma: no cover - exact client errors vary by transport.
        return {"ok": False, "message": _safe_error_text(exc)}


def _read_many(
    client: Any,
    specs: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    return bounded_read_map(
        specs,
        lambda spec: _read_rpc(client, spec[0], spec[1]),
        max_workers=configured_read_workers(client),
    )


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
        _write_text_if_changed(path, text + "\n")
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
        "total_count": len(dormant_entries),
        "counts_by_object_type": dict(sorted(counts.items())),
        "entries": dormant_entries,
        "preview_count": len(dormant_entries),
        "truncated": False,
        "hydrated": False,
    }


def _compact_dormant_preview(dormant: dict[str, Any]) -> dict[str, Any]:
    compact = dict(dormant)
    entries = dormant.get("entries") if isinstance(dormant.get("entries"), list) else []
    preview = entries[:DORMANT_ENTRY_PREVIEW_LIMIT]
    total_count = int(dormant.get("total_count") or dormant.get("count") or len(entries))
    compact["entries"] = preview
    compact["total_count"] = total_count
    compact["preview_count"] = len(preview)
    compact["preview_limit"] = DORMANT_ENTRY_PREVIEW_LIMIT
    compact["truncated"] = len(preview) < total_count
    return compact


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
    _write_text_if_changed(path, stable_json_text(payload) + "\n")


def _write_text_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == content:
                return
        except (OSError, UnicodeDecodeError):
            pass
    path.write_text(content, encoding="utf-8")


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned[:80] or "dashboard"
