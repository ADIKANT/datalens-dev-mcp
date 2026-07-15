#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.request_compiler import compile_method_request
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.response_projection import (
    sanitize_response,
    serialized_metadata,
    stable_json_text,
)
from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, execute_safe_apply

ARTIFACT_DIR = REPO_ROOT / "artifacts" / "controlled_live"
CONTROLLED_TRANSIENT_FLAGS = {
    "DATALENS_MCP_ALLOW_CONTROLLED_TEST_WRITES": "1",
    "DATALENS_MCP_ENABLE_WRITES": "1",
    "DATALENS_MCP_LIVE_ALLOW_SAVE": "1",
    "DATALENS_MCP_LIVE_ALLOW_PUBLISH": "1",
    "DATALENS_MCP_ENABLE_EXPERT_RPC": "0",
}
SCHEMA_VERSION = "2026-06-25.controlled_live_lifecycle.v1"
CONTROLLED_LIVE_REQUIRED_ROUTES = {
    "editor_chart",
    "table_node",
    "control_node",
    "markdown_node",
    "wizard_native",
    "dashboard",
    "dataset",
}
NON_BLOCKING_DOCUMENTED_STATES = {
    "documented_but_not_live_write_verified",
    "documented_but_plan_only",
    "blocked_by_explicit_policy",
}


ROUTES = [
    {
        "route": "editor_chart",
        "entry_type": "advanced-chart_node",
        "read_method": "getEditorChart",
        "create_method": "createEditorChart",
        "update_method": "updateEditorChart",
        "id_key": "chartId",
        "publishable": True,
    },
    {
        "route": "table_node",
        "entry_type": "table_node",
        "read_method": "getEditorChart",
        "create_method": "createEditorChart",
        "update_method": "updateEditorChart",
        "id_key": "chartId",
        "publishable": True,
    },
    {
        "route": "control_node",
        "entry_type": "control_node",
        "read_method": "getEditorChart",
        "create_method": "createEditorChart",
        "update_method": "updateEditorChart",
        "id_key": "chartId",
        "publishable": True,
    },
    {
        "route": "markdown_node",
        "entry_type": "markdown_node",
        "read_method": "getEditorChart",
        "create_method": "createEditorChart",
        "update_method": "updateEditorChart",
        "id_key": "chartId",
        "publishable": True,
    },
    {
        "route": "wizard_native",
        "entry_type": "ymap_wizard_node",
        "read_method": "getWizardChart",
        "create_method": "createWizardChart",
        "update_method": "updateWizardChart",
        "id_key": "chartId",
        "publishable": True,
    },
    {
        "route": "dashboard",
        "entry_type": "",
        "scope": "dash",
        "read_method": "getDashboard",
        "create_method": "createDashboard",
        "update_method": "updateDashboard",
        "id_key": "dashboardId",
        "publishable": True,
    },
    {
        "route": "dataset",
        "scope": "dataset",
        "read_method": "getDataset",
        "create_method": "createDataset",
        "update_method": "updateDataset",
        "id_key": "datasetId",
        "publishable": False,
    },
    {
        "route": "connection",
        "scope": "connection",
        "read_method": "getConnection",
        "create_method": "createConnection",
        "update_method": "updateConnection",
        "id_key": "connectionId",
        "publishable": False,
    },
]


class ControlledLiveBlocked(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ARTIFACT_DIR / "controlled_lifecycle_raw.json"))
    parser.add_argument("--test-workbook-id", default="")
    parser.add_argument("--approved-live-writes", action="store_true")
    parser.add_argument("--confirm-disposable-workbook", action="store_true")
    parser.add_argument("--approval-note", default="")
    args = parser.parse_args()
    out = Path(args.out)
    try:
        result = run_controlled_lifecycle(
            out=out,
            approved_live_writes=args.approved_live_writes,
            approval_note=args.approval_note,
            test_workbook_id=args.test_workbook_id,
            confirm_disposable_workbook=args.confirm_disposable_workbook,
        )
    except ControlledLiveBlocked as exc:
        result = {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "error": {"category": "controlled_live_blocked", "message": str(exc)},
            "test_object_inventory": [],
        }
        write_json(out, result)
    print(
        json.dumps(
            {
                "ok": result.get("ok"),
                "status": result.get("status"),
                "artifact": str(out),
                "runtime_preflight": result.get("runtime_preflight", {}),
                "route_evidence_summary": result.get("route_evidence_summary", {}),
            }
        )
    )
    return 0 if result.get("ok") else 1


def run_controlled_lifecycle(
    *,
    out: Path,
    approved_live_writes: bool,
    approval_note: str,
    test_workbook_id: str = "",
    confirm_disposable_workbook: bool = False,
    client: Any | None = None,
    config: DataLensConfig | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    base_env = dict(os.environ if env is None else env)
    workbook_id = (test_workbook_id or base_env.get("DATALENS_MCP_TEST_WORKBOOK_ID", "")).strip()
    transient_env = build_transient_controlled_env(base_env, workbook_id)
    cfg = build_transient_controlled_config(config or DataLensConfig.from_env())
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = f"mcp_controlled_test_{run_id}_"
    ensure_live_guards(
        env=transient_env,
        cfg=cfg,
        workbook_id=workbook_id,
        approved_live_writes=approved_live_writes,
        approval_note=approval_note,
        confirm_disposable_workbook=confirm_disposable_workbook,
    )
    active_client = client or DataLensApiClient(cfg)
    root = out.parent
    root.mkdir(parents=True, exist_ok=True)
    initial_inventory = active_client.rpc("getWorkbookEntries", {"workbookId": workbook_id})
    initial_fingerprint = workbook_fingerprint(initial_inventory)
    runtime_preflight = runtime_preflight_summary(
        cfg=cfg,
        env=transient_env,
        workbook_id=workbook_id,
        auth_probe_ok=True,
    )
    route_preflights = preflight_routes(
        client=active_client,
        root=root,
        run_id=run_id,
        workbook_id=workbook_id,
        prefix=prefix,
        inventory=initial_inventory,
    )
    target_check = planned_target_check(route_preflights, workbook_id)
    if not target_check["ok"]:
        raise ControlledLiveBlocked("planned target outside approved workbook")
    runtime_preflight["planned_targets_inside_approved_workbook"] = True
    runtime_preflight["planned_target_check"] = target_check
    preflight_by_route = {item["route"]: item for item in route_preflights}
    route_results: list[dict[str, Any]] = []
    test_inventory: list[dict[str, Any]] = []
    for route in ROUTES:
        try:
            route_result = run_route(
                client=active_client,
                root=root,
                run_id=run_id,
                workbook_id=workbook_id,
                prefix=prefix,
                route=route,
                inventory=initial_inventory,
                config=cfg,
                route_preflight=preflight_by_route.get(route["route"], {}),
            )
        except Exception as exc:  # noqa: BLE001
            route_result = route_exception_error(route, exc)
        route_results.append(route_result)
        if route_result.get("object_id"):
            test_inventory.append(
                {
                    "route": route_result["route"],
                    "object_type": route_result["object_type"],
                    "object_id": route_result["object_id"],
                    "name": route_result["name"],
                    "cleanup_required": True,
                }
            )
    final_inventory = active_client.rpc("getWorkbookEntries", {"workbookId": workbook_id})
    evidence_summary = summarize_route_evidence(route_results)
    result = {
        "ok": evidence_summary["ok"],
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "run_id": run_id,
        "approval_record": {
            "approved_live_writes": approved_live_writes,
            "approval_note": approval_note,
            "workbook_id": workbook_id,
            "cleanup_approved": False,
            "manual_env_exports_required": False,
        },
        "runtime_preflight": runtime_preflight,
        "test_workbook_id": workbook_id,
        "prefix": prefix,
        "preflight_before_first_write": {
            "completed": True,
            "route_count": len(route_preflights),
            "ok_route_count": sum(1 for item in route_preflights if item.get("status") == "preflight_ok"),
            "skipped_route_count": sum(1 for item in route_preflights if item.get("status") == "skipped"),
            "failed_route_count": sum(1 for item in route_preflights if item.get("status") == "failed"),
        },
        "initial_workbook_fingerprint": initial_fingerprint,
        "final_workbook_fingerprint": workbook_fingerprint(final_inventory),
        "route_evidence_summary": evidence_summary,
        "routes": route_results,
        "test_object_inventory": test_inventory,
        "rollback_manual_cleanup_plan": build_manual_cleanup_plan(
            workbook_id=workbook_id,
            prefix=prefix,
            test_inventory=test_inventory,
        ),
    }
    write_json(out, result)
    write_json(root / "test_object_inventory.json", test_inventory)
    write_sidecar_reports(root, result)
    return result


def build_transient_controlled_env(base_env: dict[str, str], workbook_id: str) -> dict[str, str]:
    transient = dict(base_env)
    transient["DATALENS_MCP_TEST_WORKBOOK_ID"] = workbook_id
    transient.update(CONTROLLED_TRANSIENT_FLAGS)
    return transient


def build_transient_controlled_config(cfg: DataLensConfig) -> DataLensConfig:
    return replace(
        cfg,
        write_enabled=True,
        expert_rpc_enabled=False,
        token_refresh_enabled=False,
        env_file_path="",
        env_file_reload_state="transient_no_canonical_reload",
    )


def ensure_live_guards(
    *,
    env: dict[str, str],
    cfg: DataLensConfig,
    workbook_id: str,
    approved_live_writes: bool,
    approval_note: str,
    confirm_disposable_workbook: bool,
) -> None:
    if not approved_live_writes or not approval_note.strip():
        raise ControlledLiveBlocked("explicit --approved-live-writes and --approval-note are required")
    if not workbook_id:
        raise ControlledLiveBlocked("explicit --test-workbook-id is required")
    if not confirm_disposable_workbook:
        raise ControlledLiveBlocked("explicit --confirm-disposable-workbook is required")
    if env.get("DATALENS_MCP_ALLOW_CONTROLLED_TEST_WRITES") != "1":
        raise ControlledLiveBlocked("DATALENS_MCP_ALLOW_CONTROLLED_TEST_WRITES=1 is required")
    if not cfg.write_enabled:
        raise ControlledLiveBlocked("DATALENS_MCP_ENABLE_WRITES=1 is required")
    if env.get("DATALENS_MCP_LIVE_ALLOW_SAVE") != "1":
        raise ControlledLiveBlocked("DATALENS_MCP_LIVE_ALLOW_SAVE=1 is required")
    if env.get("DATALENS_MCP_LIVE_ALLOW_PUBLISH") != "1":
        raise ControlledLiveBlocked("DATALENS_MCP_LIVE_ALLOW_PUBLISH=1 is required")
    if cfg.expert_rpc_enabled:
        raise ControlledLiveBlocked("DATALENS_MCP_ENABLE_EXPERT_RPC must remain disabled")


def runtime_preflight_summary(*, cfg: DataLensConfig, env: dict[str, str], workbook_id: str, auth_probe_ok: bool) -> dict[str, Any]:
    return {
        "env_file_loaded": bool(cfg.env_file_loaded),
        "auth_probe_ok": bool(auth_probe_ok),
        "workbook_confirmed_disposable": True,
        "writes_enabled": bool(cfg.write_enabled),
        "save_enabled": env.get("DATALENS_MCP_LIVE_ALLOW_SAVE") == "1",
        "publish_enabled": env.get("DATALENS_MCP_LIVE_ALLOW_PUBLISH") == "1",
        "controlled_test_writes_enabled": env.get("DATALENS_MCP_ALLOW_CONTROLLED_TEST_WRITES") == "1",
        "expert_rpc_disabled": not cfg.expert_rpc_enabled,
        "manual_env_exports_required": False,
        "transient_guarded_env": True,
        "transient_env_persisted": False,
        "canonical_env_file_mutated": False,
        "token_refresh_on_401_enabled": bool(cfg.token_refresh_enabled),
        "unconditional_token_mint_at_startup": False,
    }


def preflight_routes(
    *,
    client: Any,
    root: Path,
    run_id: str,
    workbook_id: str,
    prefix: str,
    inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for route in ROUTES:
        source = select_source_entry(inventory, route)
        if not source:
            if route["route"] == "connection":
                results.append(
                    {
                        "route": route["route"],
                        "status": "skipped",
                        "state": "documented_but_not_live_write_verified",
                        "reason": "no safe non-secret reusable connection source fixture in approved test workbook",
                    }
                )
                continue
            results.append(
                {
                    "route": route["route"],
                    "status": "setup_blocker",
                    "state": "live_write_not_verified_missing_safe_fixture",
                    "reason": "no source object found in approved test workbook",
                }
            )
            continue
        object_id = source["entryId"]
        source_read = client.rpc(route["read_method"], read_payload_for(route, object_id))
        source_artifact = write_envelope(root, run_id, route["route"], "preflight_source_read", source_read)
        if route["route"] == "connection":
            results.append(
                {
                    "route": route["route"],
                    "status": "skipped",
                    "state": "documented_but_not_live_write_verified",
                    "reason": "connection readback omits canonical create type/secret material required for safe clone",
                    "source_object_id": object_id,
                    "source_artifact": source_artifact,
                }
            )
            continue
        create_payload = build_create_payload(route, source_read, workbook_id, prefix)
        create_compiled = compile_method_request(
            route["create_method"],
            create_payload,
            object_type=route["route"],
            operation="create",
            workbook_id=workbook_id,
        )
        compiled_artifact = write_envelope(root, run_id, route["route"], "preflight_create_compiled", create_compiled)
        if not create_compiled["ok"]:
            results.append(
                {
                    "route": route["route"],
                    "status": "failed",
                    "state": "failed",
                    "source_object_id": object_id,
                    "source_read": source_read,
                    "source_artifact": source_artifact,
                    "compiled_artifact": compiled_artifact,
                    "error": create_compiled["error"],
                }
            )
            continue
        results.append(
            {
                "route": route["route"],
                "status": "preflight_ok",
                "source_object_id": object_id,
                "source_read": source_read,
                "source_artifact": source_artifact,
                "create_payload": create_payload,
                "create_compiled": create_compiled,
                "compiled_artifact": compiled_artifact,
            }
        )
    return results


def planned_target_check(route_preflights: list[dict[str, Any]], workbook_id: str) -> dict[str, Any]:
    outside: list[dict[str, str]] = []
    checked: list[str] = []
    for item in route_preflights:
        payload = item.get("create_payload")
        if not isinstance(payload, dict):
            continue
        checked.append(str(item.get("route") or ""))
        for path, value in workbook_fields(payload):
            if value and value != workbook_id:
                outside.append({"route": str(item.get("route") or ""), "path": path, "workbook_id": value})
    return {
        "ok": not outside,
        "approved_workbook_id": workbook_id,
        "checked_routes": checked,
        "outside_targets": outside,
    }


def workbook_fields(value: Any, path: str = "$") -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}"
            if key in {"workbookId", "workbook_id", "workbookIdOrFolderId"}:
                fields.append((next_path, str(item or "")))
            fields.extend(workbook_fields(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            fields.extend(workbook_fields(item, f"{path}[{index}]"))
    return fields


def run_route(
    *,
    client: Any,
    root: Path,
    run_id: str,
    workbook_id: str,
    prefix: str,
    route: dict[str, Any],
    inventory: dict[str, Any],
    config: DataLensConfig,
    route_preflight: dict[str, Any],
) -> dict[str, Any]:
    if route_preflight.get("status") == "failed":
        return {
            "route": route["route"],
            "object_type": route.get("entry_type") or route.get("scope") or route["route"],
            "state": "failed",
            "status": "failed_preflight",
            "preflight": {
                "source_artifact": route_preflight.get("source_artifact"),
                "compiled_artifact": route_preflight.get("compiled_artifact"),
                "error": route_preflight.get("error"),
            },
        }
    source = select_source_entry(inventory, route)
    if not source:
        if route["route"] == "connection":
            return {
                "route": route["route"],
                "object_type": route.get("entry_type") or route.get("scope") or route["route"],
                "state": "documented_but_not_live_write_verified",
                "status": "skipped",
                "reason": "no safe non-secret reusable connection source fixture in approved test workbook",
            }
        return {
            "route": route["route"],
            "object_type": route.get("entry_type") or route.get("scope") or route["route"],
            "state": "live_write_not_verified_missing_safe_fixture",
            "status": "setup_blocker",
            "reason": "no source object found in approved test workbook",
        }
    if route_preflight.get("status") == "skipped":
        return {
            "route": route["route"],
            "object_type": route.get("entry_type") or route.get("scope") or route["route"],
            "state": route_preflight.get("state") or "documented_but_not_live_write_verified",
            "status": "skipped",
            "reason": route_preflight.get("reason") or "route skipped by preflight",
            "preflight": {
                "source_object_id": route_preflight.get("source_object_id"),
                "source_artifact": route_preflight.get("source_artifact"),
            },
        }
    object_id = source["entryId"]
    source_read = route_preflight.get("source_read") or client.rpc(route["read_method"], read_payload_for(route, object_id))
    source_artifact = route_preflight.get("source_artifact") or write_envelope(
        root, run_id, route["route"], "source_read", source_read
    )
    create_payload = route_preflight.get("create_payload") or build_create_payload(
        route, source_read, workbook_id, prefix
    )
    create_compiled = route_preflight.get("create_compiled") or compile_method_request(
        route["create_method"], create_payload, object_type=route["route"], operation="create", workbook_id=workbook_id
    )
    if not create_compiled["ok"]:
        return route_error(route, "create_compile_failed", create_compiled)
    created = client.rpc(route["create_method"], create_compiled["payload"])
    created_artifact = write_envelope(root, run_id, route["route"], "create", created)
    created_id = extract_created_id(created, route["id_key"])
    if not created_id:
        return route_error(route, "missing_created_object_id", created)
    saved_read = client.rpc(route["read_method"], read_payload_for(route, created_id))
    saved_artifact = write_envelope(root, run_id, route["route"], "saved_read", saved_read)
    update_payload = build_update_payload(route, saved_read, created_id, meaningful=False)
    update_compiled = compile_method_request(
        route["update_method"],
        update_payload,
        object_type=route["route"],
        operation="update",
        object_id=created_id,
        mode="save",
    )
    if not update_compiled["ok"]:
        return route_error(route, "noop_update_compile_failed", update_compiled)
    noop_write = client.rpc(route["update_method"], update_compiled["payload"])
    noop_artifact = write_envelope(root, run_id, route["route"], "noop_update", noop_write)
    post_noop_read = client.rpc(route["read_method"], read_payload_for(route, created_id))
    post_noop_artifact = write_envelope(root, run_id, route["route"], "post_noop_read", post_noop_read)
    meaningful_payload = build_update_payload(route, post_noop_read, created_id, meaningful=True)
    meaningful_compiled = compile_method_request(
        route["update_method"],
        meaningful_payload,
        object_type=route["route"],
        operation="update",
        object_id=created_id,
        mode="save",
    )
    if not meaningful_compiled["ok"]:
        return route_error(route, "meaningful_update_compile_failed", meaningful_compiled)
    meaningful_write = client.rpc(route["update_method"], meaningful_compiled["payload"])
    meaningful_artifact = write_envelope(root, run_id, route["route"], "meaningful_update", meaningful_write)
    updated_read = client.rpc(route["read_method"], read_payload_for(route, created_id))
    updated_artifact = write_envelope(root, run_id, route["route"], "updated_read", updated_read)
    stale_result = run_stale_negative(
        client=client,
        root=root,
        run_id=run_id,
        route=route,
        payload=meaningful_compiled["payload"],
        object_id=created_id,
        config=config,
    )
    publish_artifacts: list[dict[str, Any]] = []
    if route.get("publishable"):
        publish_payload = build_update_payload(route, updated_read, created_id, meaningful=False)
        publish_compiled = compile_method_request(
            route["update_method"],
            publish_payload,
            object_type=route["route"],
            operation="update",
            object_id=created_id,
            mode="publish",
        )
        if not publish_compiled["ok"]:
            return route_error(route, "publish_compile_failed", publish_compiled)
        published = client.rpc(route["update_method"], publish_compiled["payload"])
        publish_artifacts.append(write_envelope(root, run_id, route["route"], "publish", published))
        published_read = client.rpc(route["read_method"], read_payload_for(route, created_id, branch="published"))
        publish_artifacts.append(write_envelope(root, run_id, route["route"], "published_read", published_read))
    return {
        "route": route["route"],
        "object_type": route.get("entry_type") or route.get("scope") or route["route"],
        "state": "controlled_live_write_verified",
        "status": "completed",
        "publishable": bool(route.get("publishable")),
        "source_object_id": object_id,
        "object_id": created_id,
        "name": create_payload.get("name") or create_payload.get("entry", {}).get("name") or "",
        "artifacts": {
            "source_read": source_artifact,
            "create": created_artifact,
            "saved_read": saved_artifact,
            "noop_update": noop_artifact,
            "post_noop_read": post_noop_artifact,
            "meaningful_update": meaningful_artifact,
            "updated_read": updated_artifact,
            "publish": publish_artifacts,
        },
        "revision_evidence": revision_evidence(
            saved_read=saved_read,
            post_noop_read=post_noop_read,
            updated_read=updated_read,
        ),
        "stale_revision_negative": stale_result,
    }


def select_source_entry(inventory: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    entries = inventory.get("entries") if isinstance(inventory.get("entries"), list) else []
    entry_type = route.get("entry_type")
    scope = route.get("scope")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry_type and entry.get("type") == entry_type:
            return entry
        if scope and entry.get("scope") == scope:
            return entry
    return {}


def read_payload_for(route: dict[str, Any], object_id: str, *, branch: str = "saved") -> dict[str, Any]:
    payload = {route["id_key"]: object_id}
    if route["id_key"] in {"chartId", "dashboardId"}:
        payload["branch"] = branch
    return payload


def build_create_payload(
    route: dict[str, Any],
    source_read: dict[str, Any],
    workbook_id: str,
    prefix: str,
) -> dict[str, Any]:
    name = prefix + route["route"]
    if route["route"] == "dataset":
        dataset = dict(source_read.get("dataset") or {})
        dataset["description"] = f"{name} controlled lifecycle canary"
        return {"dataset": dataset, "name": name, "workbook_id": workbook_id}
    if route["route"] == "connection":
        payload = {
            key: value
            for key, value in source_read.items()
            if key not in {"id", "connectionId", "revId", "savedId", "permissions", "full_permissions"}
        }
        payload["name"] = name
        return payload
    if route["route"] == "wizard_native":
        payload = dict(source_read)
        for key in create_entry_strip_keys():
            payload.pop(key, None)
        payload["name"] = name
        payload["workbookId"] = workbook_id
        payload["template"] = payload.get("template") or "datalens"
        return payload
    entry = source_entry(source_read)
    normalize_create_entry(entry)
    if route["create_method"] == "createEditorChart":
        normalize_editor_entry_data(entry)
    entry["name"] = name
    entry["workbookId"] = workbook_id
    return {"entry": entry}


def build_update_payload(
    route: dict[str, Any],
    readback: dict[str, Any],
    object_id: str,
    *,
    meaningful: bool,
) -> dict[str, Any]:
    if route["route"] == "dataset":
        dataset = dict(readback.get("dataset") or {})
        if meaningful:
            dataset["description"] = (dataset.get("description") or "") + " updated"
        return {"datasetId": object_id, "data": {"dataset": dataset}}
    if route["route"] == "connection":
        data = {
            key: value
            for key, value in readback.items()
            if key not in {"id", "connectionId", "revId", "savedId", "permissions", "full_permissions"}
        }
        if meaningful:
            data["name"] = str(data.get("name") or "connection") + "_updated"
        return {"connectionId": object_id, "data": data}
    if route["route"] == "wizard_native":
        payload = dict(readback)
        payload["entryId"] = object_id
        payload["template"] = payload.get("template") or "datalens"
        if meaningful and isinstance(payload.get("annotation"), dict):
            payload["annotation"]["description"] = "controlled lifecycle update"
        return payload
    entry = source_entry(readback)
    entry["entryId"] = object_id
    if route["route"] == "dashboard":
        normalize_dashboard_update_entry(entry)
    elif route["update_method"] == "updateEditorChart":
        normalize_editor_entry_data(entry)
    if meaningful:
        annotation = entry.setdefault("annotation", {})
        if isinstance(annotation, dict):
            annotation["description"] = "controlled lifecycle update"
    return {"entry": entry}


def run_stale_negative(
    *,
    client: Any,
    root: Path,
    run_id: str,
    route: dict[str, Any],
    payload: dict[str, Any],
    object_id: str,
    config: DataLensConfig,
) -> dict[str, Any]:
    stale_payload = json.loads(json.dumps(payload))
    if "entry" in stale_payload and isinstance(stale_payload["entry"], dict):
        stale_payload["entry"]["revId"] = "stale_revision_fixture"
    elif "revId" in stale_payload:
        stale_payload["revId"] = "stale_revision_fixture"
    else:
        return {"executed": False, "status": "not_applicable", "reason": "no revision field"}
    plan = create_safe_apply_plan(
        project_root=str(root),
        approved=True,
        approval_note="controlled live stale revision guard negative",
        actions=[
            {
                "action": "controlled_live_stale_revision_negative",
                "method": route["update_method"],
                "payload": stale_payload,
                "object_id": object_id,
                "expected_rev_id": "stale_revision_fixture",
                "requires_fresh_read": True,
                "fresh_read_method": route["read_method"],
                "fresh_read_payload": read_payload_for(route, object_id),
                "readback_method": route["read_method"],
                "readback_payload": read_payload_for(route, object_id),
                "readback_mode": "minimal",
                "readback_required": True,
                "changed": True,
            }
        ],
    )
    result = execute_safe_apply(plan, config=config, client=client)
    artifact = write_envelope(root, run_id, route["route"], "stale_safe_apply_result", result)
    action = result.get("actions", [{}])[0] if result.get("actions") else {}
    error = action.get("error") if isinstance(action.get("error"), dict) else {}
    if error.get("category") == "stale_revision" and not action.get("write_attempted"):
        return {
            "executed": True,
            "status": "blocked_expected",
            "write_attempted": False,
            "safe_apply_status": result.get("status"),
            "artifact": artifact,
        }
    return {
        "executed": True,
        "status": "unexpected_success",
        "write_attempted": bool(action.get("write_attempted")),
        "object_id": object_id,
        "safe_apply_status": result.get("status"),
        "artifact": artifact,
    }


def source_entry(value: dict[str, Any]) -> dict[str, Any]:
    for key in ("entry", "dashboard", "chart", "object"):
        item = value.get(key)
        if isinstance(item, dict):
            nested = item.get("entry")
            return dict(nested if isinstance(nested, dict) else item)
    return dict(value)


def normalize_create_entry(entry: dict[str, Any]) -> None:
    for key in create_entry_strip_keys():
        entry.pop(key, None)
    if entry.get("meta") is None:
        entry["meta"] = {}
    if entry.get("annotation") is None:
        entry["annotation"] = {}


def normalize_dashboard_update_entry(entry: dict[str, Any]) -> None:
    allowed = {"entryId", "data", "meta", "revId"}
    for key in list(entry):
        if key not in allowed:
            entry.pop(key, None)
    if entry.get("meta") is None:
        entry["meta"] = {}


def normalize_editor_entry_data(entry: dict[str, Any]) -> None:
    data = entry.setdefault("data", {})
    if not isinstance(data, dict):
        entry["data"] = {}
        data = entry["data"]
    for key in ("controls", "meta", "params", "prepare", "sources"):
        if data.get(key) is None:
            data[key] = ""


def create_entry_strip_keys() -> tuple[str, ...]:
    return (
        "entryId",
        "id",
        "chartId",
        "dashboardId",
        "revId",
        "rev_id",
        "savedId",
        "saved_id",
        "publishedId",
        "published_id",
        "key",
        "tenantId",
        "createdAt",
        "createdBy",
        "updatedAt",
        "updatedBy",
        "version",
    )


def extract_created_id(value: dict[str, Any], id_key: str) -> str:
    for candidate in (value, value.get("entry"), value.get("result"), value.get("object")):
        if not isinstance(candidate, dict):
            continue
        for key in (id_key, "entryId", "id", "chartId", "dashboardId", "datasetId", "connectionId"):
            item = candidate.get(key)
            if item:
                return str(item)
    return ""


def workbook_fingerprint(value: dict[str, Any]) -> dict[str, Any]:
    entries = value.get("entries") if isinstance(value.get("entries"), list) else []
    by_scope: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        by_scope[str(entry.get("scope") or "")] = by_scope.get(str(entry.get("scope") or ""), 0) + 1
        by_type[str(entry.get("type") or "")] = by_type.get(str(entry.get("type") or ""), 0) + 1
    return {
        "entry_count": len(entries),
        "by_scope": dict(sorted(by_scope.items())),
        "by_type": dict(sorted(by_type.items())),
        "sha256": serialized_metadata(sanitize_response(value))["sha256"],
    }


def summarize_route_evidence(route_results: list[dict[str, Any]]) -> dict[str, Any]:
    malformed_verified_routes = [
        {
            "route": route.get("route"),
            "missing": missing_verified_route_evidence(route),
        }
        for route in route_results
        if route.get("state") == "controlled_live_write_verified" and missing_verified_route_evidence(route)
    ]
    verified_required_routes = sorted(
        {
            str(route.get("route"))
            for route in route_results
            if route.get("state") == "controlled_live_write_verified"
            and str(route.get("route")) in CONTROLLED_LIVE_REQUIRED_ROUTES
            and not missing_verified_route_evidence(route)
        }
    )
    documented_routes = sorted(
        {
            str(route.get("route"))
            for route in route_results
            if route.get("state") in NON_BLOCKING_DOCUMENTED_STATES
            and str(route.get("route")) not in CONTROLLED_LIVE_REQUIRED_ROUTES
        }
    )
    missing_required_routes = sorted(CONTROLLED_LIVE_REQUIRED_ROUTES - set(verified_required_routes))
    failed_routes = [
        {
            "route": route.get("route"),
            "state": route.get("state"),
            "status": route.get("status"),
            "reason": route.get("reason") or route.get("error", {}).get("category"),
        }
        for route in route_results
        if route.get("state") == "failed" or str(route.get("status") or "").startswith("failed")
    ]
    setup_blockers = [
        {
            "route": route.get("route"),
            "state": route.get("state"),
            "status": route.get("status"),
            "reason": route.get("reason"),
        }
        for route in route_results
        if route.get("state") == "live_write_not_verified_missing_safe_fixture"
    ]
    blocking_routes = failed_routes + malformed_verified_routes + [
        item for item in setup_blockers if item.get("route") in CONTROLLED_LIVE_REQUIRED_ROUTES
    ]
    return {
        "ok": not missing_required_routes and not blocking_routes,
        "required_routes": sorted(CONTROLLED_LIVE_REQUIRED_ROUTES),
        "verified_required_routes": verified_required_routes,
        "documented_non_blocking_routes": documented_routes,
        "missing_required_routes": missing_required_routes,
        "failed_routes": failed_routes,
        "setup_blockers": setup_blockers,
        "malformed_verified_routes": malformed_verified_routes,
        "route_state_counts": route_state_counts(route_results),
    }


def missing_verified_route_evidence(route: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not route.get("object_id"):
        missing.append("object_id")
    artifacts = route.get("artifacts") if isinstance(route.get("artifacts"), dict) else {}
    for key in ("create", "saved_read", "noop_update", "post_noop_read", "meaningful_update", "updated_read"):
        if not artifacts.get(key):
            missing.append(f"artifacts.{key}")
    if route.get("publishable") and not artifacts.get("publish"):
        missing.append("artifacts.publish")
    return missing


def route_state_counts(route_results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for route in route_results:
        state = str(route.get("state") or "unknown_due_to_missing_evidence")
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def revision_evidence(
    *,
    saved_read: dict[str, Any],
    post_noop_read: dict[str, Any],
    updated_read: dict[str, Any],
) -> dict[str, Any]:
    return {
        "saved_rev_id": extract_revision_id(saved_read),
        "post_noop_rev_id": extract_revision_id(post_noop_read),
        "updated_rev_id": extract_revision_id(updated_read),
    }


def extract_revision_id(value: dict[str, Any]) -> str:
    for candidate in (value, value.get("entry"), value.get("result"), value.get("object"), value.get("dataset")):
        if not isinstance(candidate, dict):
            continue
        for key in ("revId", "rev_id", "savedId", "saved_id"):
            item = candidate.get(key)
            if item:
                return str(item)
    return ""


def build_manual_cleanup_plan(
    *,
    workbook_id: str,
    prefix: str,
    test_inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "cleanup_approved": False,
        "delete_or_cleanup_executed": False,
        "workbook_id": workbook_id,
        "prefix": prefix,
        "object_count": len(test_inventory),
        "objects": test_inventory,
        "operator_note": (
            "No delete or cleanup is approved in this release run. Objects listed here are disposable "
            "controlled lifecycle canaries and require separate cleanup approval before deletion."
        ),
    }


def route_error(route: dict[str, Any], category: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": route["route"],
        "object_type": route.get("entry_type") or route.get("scope") or route["route"],
        "state": "failed",
        "status": "failed",
        "error": {"category": category, "message": stable_json_text(sanitize_response(payload))[:800]},
    }


def route_exception_error(route: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "route": route["route"],
        "object_type": route.get("entry_type") or route.get("scope") or route["route"],
        "state": "failed",
        "status": "failed",
        "error": {
            "category": exc.__class__.__name__,
            "message": sanitize_response({"message": str(exc)[:1200]})["message"],
        },
    }


def write_envelope(root: Path, run_id: str, route: str, label: str, value: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_response(value)
    metadata = serialized_metadata(sanitized)
    path = root / "controlled_live" / run_id / route / f"{label}.{metadata['sha256'][:12]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json_text(sanitized) + "\n", encoding="utf-8")
    return {
        "path": str(path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path),
        **metadata,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_response(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_sidecar_reports(root: Path, result: dict[str, Any]) -> None:
    write_controlled_report(root / "controlled_lifecycle_report.md", result)
    write_manual_cleanup_plan(root / "manual_cleanup_plan.md", result)
    write_call_matrix(root / "controlled_lifecycle_call_matrix.csv", result)


def write_controlled_report(path: Path, result: dict[str, Any]) -> None:
    summary = result.get("route_evidence_summary") or {}
    lines = [
        "# Controlled Lifecycle Report",
        "",
        f"- Status: `{result.get('status')}`",
        f"- Overall ok: `{result.get('ok')}`",
        f"- Test workbook: `{result.get('test_workbook_id')}`",
        f"- Run ID: `{result.get('run_id')}`",
        f"- Required routes verified: `{len(summary.get('verified_required_routes') or [])}/{len(summary.get('required_routes') or [])}`",
        f"- Documented non-blocking routes: `{', '.join(summary.get('documented_non_blocking_routes') or []) or 'none'}`",
        f"- Test objects recorded: `{len(result.get('test_object_inventory') or [])}`",
        f"- Cleanup approved: `{(result.get('rollback_manual_cleanup_plan') or {}).get('cleanup_approved')}`",
        "",
        "## Runtime Preflight",
        "",
    ]
    runtime = result.get("runtime_preflight") if isinstance(result.get("runtime_preflight"), dict) else {}
    for key in sorted(runtime):
        if key == "planned_target_check":
            continue
        lines.append(f"- {key}: `{runtime[key]}`")
    lines.extend(["", "## Route States", ""])
    for route in result.get("routes") or []:
        lines.append(
            f"- `{route.get('route')}`: `{route.get('state')}` / `{route.get('status')}`"
            + (f" / `{route.get('object_id')}`" if route.get("object_id") else "")
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manual_cleanup_plan(path: Path, result: dict[str, Any]) -> None:
    plan = result.get("rollback_manual_cleanup_plan") if isinstance(result.get("rollback_manual_cleanup_plan"), dict) else {}
    lines = [
        "# Manual Cleanup Plan",
        "",
        f"- Cleanup approved: `{plan.get('cleanup_approved')}`",
        f"- Delete or cleanup executed: `{plan.get('delete_or_cleanup_executed')}`",
        f"- Workbook ID: `{plan.get('workbook_id')}`",
        f"- Prefix: `{plan.get('prefix')}`",
        f"- Object count: `{plan.get('object_count')}`",
        "",
        "No delete or cleanup is approved in this release run. Do not delete these canary objects without separate approval.",
        "",
        "## Objects",
        "",
    ]
    for item in plan.get("objects") or []:
        lines.append(
            f"- `{item.get('route')}` `{item.get('object_type')}` `{item.get('object_id')}` `{item.get('name')}`"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_call_matrix(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "route",
                "object_type",
                "state",
                "status",
                "object_id",
                "source_read",
                "create",
                "saved_read",
                "noop_update",
                "post_noop_read",
                "meaningful_update",
                "updated_read",
                "publish_count",
                "stale_negative_status",
            ],
        )
        writer.writeheader()
        for route in result.get("routes") or []:
            artifacts = route.get("artifacts") if isinstance(route.get("artifacts"), dict) else {}
            stale = route.get("stale_revision_negative") if isinstance(route.get("stale_revision_negative"), dict) else {}
            writer.writerow(
                {
                    "route": route.get("route", ""),
                    "object_type": route.get("object_type", ""),
                    "state": route.get("state", ""),
                    "status": route.get("status", ""),
                    "object_id": route.get("object_id", ""),
                    "source_read": artifact_path(artifacts.get("source_read")),
                    "create": artifact_path(artifacts.get("create")),
                    "saved_read": artifact_path(artifacts.get("saved_read")),
                    "noop_update": artifact_path(artifacts.get("noop_update")),
                    "post_noop_read": artifact_path(artifacts.get("post_noop_read")),
                    "meaningful_update": artifact_path(artifacts.get("meaningful_update")),
                    "updated_read": artifact_path(artifacts.get("updated_read")),
                    "publish_count": len(artifacts.get("publish") or []),
                    "stale_negative_status": stale.get("status", ""),
                }
            )


def artifact_path(value: Any) -> str:
    return str(value.get("path") or "") if isinstance(value, dict) else ""


if __name__ == "__main__":
    raise SystemExit(main())
