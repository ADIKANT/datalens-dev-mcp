from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import monotonic
from types import SimpleNamespace
from typing import Any

from datalens_dev_mcp.api.scheduler import record_cache_hit
from datalens_dev_mcp.editor.authoring_profiles import (
    apply_authoring_profile_bundle,
    authoring_profile_route_decision,
    resolve_authoring_profile,
)
from datalens_dev_mcp.editor.bundle import generate_editor_bundle
from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload
from datalens_dev_mcp.html_pages import render_standalone_html_page, validate_standalone_html_page
from datalens_dev_mcp.knowledge.recipes import compact_recipe_for_payload, select_authoring_recipe
from datalens_dev_mcp.mcp.response_projection import (
    project_connection_response,
    project_dashboard_response,
    project_dataset_response,
    sanitize_response,
    serialized_metadata,
)
from datalens_dev_mcp.pipeline.artifacts import ensure_project_dirs, read_json, read_text, write_json, write_text
from datalens_dev_mcp.pipeline.baseline_preservation import (
    build_baseline_diff_contract,
    build_object_reuse_decision,
)
from datalens_dev_mcp.pipeline.dashboard_relations import (
    build_default_dashboard_relations,
    validate_dashboard_relations,
)
from datalens_dev_mcp.pipeline.deployment_report import build_deployment_report
from datalens_dev_mcp.pipeline.delivery_intent import resolve_delivery_intent_from_env
from datalens_dev_mcp.pipeline.evidence_mode import choose_evidence_mode
from datalens_dev_mcp.pipeline.governance import build_governance_brief
from datalens_dev_mcp.pipeline.governance_bundle import build_governance_bundle
from datalens_dev_mcp.pipeline.implemented_charts_catalog import update_implemented_charts_catalog
from datalens_dev_mcp.pipeline.live_maintenance import run_live_maintenance_update
from datalens_dev_mcp.pipeline.negative_requirements import (
    load_negative_requirement_ledger,
    validate_no_negative_requirement_drift,
)
from datalens_dev_mcp.pipeline.project_adapters import detect_project_adapter, list_project_adapter_registry
from datalens_dev_mcp.pipeline.project_live_workflows import (
    detect_project_live_workflows,
    plan_project_live_workflow,
    plan_project_manifest,
    read_project_live_summary,
    record_project_live_execution_context,
    run_project_live_apply,
    run_project_live_dry_run,
)
from datalens_dev_mcp.pipeline.proof_levels import proof_level_for_readback_branch
from datalens_dev_mcp.pipeline.readback import build_readback_summary, normalize_readback_mode
from datalens_dev_mcp.pipeline.reconciliation import (
    reconcile_partial_creates,
    validate_entries_reconciliation_evidence,
)
from datalens_dev_mcp.pipeline.requirements_workspace import (
    build_dashboard_blueprint_plan,
    initialize_requirements_workspace,
    ingest_requirements_markdown,
    populate_dashboard_map_canvas,
    read_persisted_requirements_text,
    select_dashboard_blueprint,
    summarize_implementation_plan,
    update_user_decision,
    validate_chart_plan_against_requirements,
)
from datalens_dev_mcp.pipeline.safe_apply import (
    create_publish_safe_apply_plan,
    create_safe_apply_plan,
    execute_safe_apply,
    load_safe_apply_stage_value,
    normalize_publish_object_type,
    readback_artifact_path,
    validate_safe_apply_plan_exhaustive,
)
from datalens_dev_mcp.pipeline.selector_maintenance import (
    DATE_RANGE_MAINTENANCE_KIND,
    compile_date_range_selector_merge,
)
from datalens_dev_mcp.pipeline.scenarios import normalize_scenario
from datalens_dev_mcp.pipeline.sql_performance import validate_project_sql_performance
from datalens_dev_mcp.pipeline.source_availability import (
    build_dashboard_source_availability_matrix,
    plan_source_availability_patch,
    validate_source_availability_consumers,
)
from datalens_dev_mcp.pipeline.target_lock import create_target_lock, validate_readback_target_lock
from datalens_dev_mcp.pipeline.user_request import normalize_user_request
from datalens_dev_mcp.pipeline.validation_evidence import build_validation_evidence_report
from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract
from datalens_dev_mcp.pipeline.visual_decisions import decide_chart
from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan, load_wizard_template_registry
from datalens_dev_mcp.pipeline.wizard_contracts import compact_wizard_dataset_readbacks
from datalens_dev_mcp.pipeline.route_registry import normalize_creation_route, visualization_for_family
from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from datalens_dev_mcp.validators.editor_sql_lint import lint_project_editor_sql
from datalens_dev_mcp.validators.route_validator import validate_route_payload
from datalens_dev_mcp.validators.security_validator import scan_path, scan_text

PLACEHOLDER_TARGETS = {
    "",
    "id",
    "target",
    "target_id",
    "workbook_id",
    "dashboard_id",
    "chart_id",
    "dataset_id",
    "connection_id",
    "dashboard",
    "<id>",
    "<target_id>",
    "<workbook_id>",
    "<dashboard_id>",
    "<chart_id>",
    "<dataset_id>",
    "<connection_id>",
}

_PROJECT_VALIDATION_CACHE_MAX_ENTRIES = 8
_PROJECT_VALIDATION_CACHE: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()
_PROJECT_VALIDATION_CACHE_LOCK = RLock()
_PROJECT_VALIDATION_CACHE_SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
}


def _looks_like_known_target(*values: Any) -> bool:
    for value in values:
        if isinstance(value, list):
            if _looks_like_known_target(*value):
                return True
            continue
        text = str(value or "").strip()
        if text and text.lower() not in PLACEHOLDER_TARGETS:
            return True
    return False


def _request_authorizes_standard_write(
    delivery_intent_text: str,
    *,
    legacy_approved: bool | None = None,
    default_text: str = "implement",
) -> bool:
    if legacy_approved is not None:
        return bool(legacy_approved)
    normalized = normalize_user_request(delivery_intent_text or default_text)
    return bool(
        normalized.task_intent in {"implement", "fix", "enhance", "redesign", "update"}
        and normalized.publish_override not in {"plan_only", "dry_run"}
        and not normalized.destructive_actions
    )


def _delivery_intent_decision(
    delivery_intent_text: str = "",
    *,
    default_text: str = "plan only",
    target_known: bool = False,
    approved: bool = False,
    approval_source: str = "",
    approval_sources: list[str] | None = None,
    fresh_readback_available: bool = False,
    revision_preservation_available: bool = False,
    saved_readback_available: bool = False,
    saved_readback_fresh: bool | None = None,
    destructive_operation: bool = False,
    proof_path: str = "",
    target_lock: dict[str, Any] | None = None,
    target_workbook_id: str = "",
    target_dashboard_id: str = "",
    target_chart_id: str = "",
) -> dict[str, Any]:
    return resolve_delivery_intent_from_env(
        delivery_intent_text,
        default_text=default_text,
        target_known=target_known,
        approved=approved,
        approval_source=approval_source,
        approval_sources=approval_sources,
        fresh_readback_available=fresh_readback_available,
        revision_preservation_available=revision_preservation_available,
        saved_readback_available=saved_readback_available,
        saved_readback_fresh=saved_readback_fresh,
        destructive_operation=destructive_operation,
        proof_path=proof_path,
        target_lock=target_lock,
        target_workbook_id=target_workbook_id,
        target_dashboard_id=target_dashboard_id,
        target_chart_id=target_chart_id,
    )


def dl_start_pipeline(
    project_root: str = ".",
    scenario: str = "new_dashboard",
    dashboard_name: str = "Synthetic Dashboard",
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    selected = normalize_scenario(scenario)
    initialize_requirements_workspace(root)
    registry = {
        "version": 1,
        "dashboard_name": dashboard_name,
        "scenario": selected,
        "stage_batch": {"current_stage": "intake", "current_batch": "none"},
        "chart_decisions": [],
        "build_outcomes": [],
    }
    registry_path = root / "datalens_mapping" / "governance_memory_registry.json"
    if not registry_path.exists():
        write_json(registry_path, registry)
    return {
        "project_root": str(root),
        "scenario": selected,
        "created": ["requirements/", "datalens_mapping/governance_memory_registry.json"],
        "memory_bank_owned_by": "project-memory-bank",
    }


def dl_load_project_context(
    project_root: str = ".",
    response_mode: str = "compact",
    max_preview_chars: int = 900,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    mode = (response_mode or "compact").strip().lower()
    if mode not in {"compact", "artifact"}:
        raise ValueError("response_mode must be compact or artifact")
    del max_preview_chars
    return {
        "project_root": str(root),
        "response_mode": mode,
        "deprecated": True,
        "internal_compatibility_only": True,
        "replacement": "Call project-memory-bank memory_context, then pass its project_context_ref.v1 to DataLens tools.",
    }


def dl_update_project_memory(
    project_root: str = ".",
    path: str = "memory-bank/progress.md",
    content: str = "",
    append: bool = True,
) -> dict[str, Any]:
    del project_root
    if not path.startswith("memory-bank/"):
        raise ValueError("compatibility suggestions must target memory-bank modules")
    return {
        "deprecated": True,
        "updated": False,
        "replacement": "Pass this bounded operation to project-memory-bank memory_record.",
        "suggested_records": [
            {
                "op": "upsert_entry" if append else "upsert_section",
                "path": path,
                "heading": "Current State",
                "entry_id": "datalens-compatibility-update",
                "content": content,
            }
        ],
    }


def _profile_csv(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = []
        for index, row in enumerate(reader):
            if index >= 100:
                break
            rows.append(row)
    return {"fields": fields, "sample_rows": len(rows)}


def _needs_source_route_decision(requirements_text: str, data_path: str) -> bool:
    if data_path:
        return True
    lowered = requirements_text.lower()
    return any(
        token in lowered
        for token in (
            "excel",
            "xlsx",
            "csv",
            "file upload",
            "upload file",
            "uploaded file",
            "file connection",
            "dataset-backed",
            "dataset backed",
            "datalens dataset",
            "existing dataset",
            "загруженный файл",
            "датасет",
        )
    )


def _write_source_route_artifacts(
    root: Path,
    requirements_text: str,
    data_path: str,
    data_profile: dict[str, Any],
) -> dict[str, Any]:
    from datalens_dev_mcp.pipeline.source_route_resolver import (
        render_manual_upload_handoff,
        validate_source_route_decision,
    )

    source_path = Path(data_path) if data_path else None
    fields = [{"name": field, "type": "unknown"} for field in (data_profile.get("fields") or [])]
    request = {
        "requirements_text": requirements_text,
        "source_file_name": source_path.name if source_path else "",
        "source_file_path": str(source_path) if source_path else "",
        "processed_file_path": str(source_path) if source_path else "",
        "expected_schema": fields,
        "source_mode": "dataset_backed",
    }
    decision = validate_source_route_decision(request)
    write_json(root / "artifacts" / "source_route_decision.json", decision)
    contract = (decision.get("decision") or {}).get("dataset_field_contract") or {}
    if contract:
        write_json(root / "requirements" / "dataset_field_contract.json", contract)
    handoff = render_manual_upload_handoff(decision.get("decision") or {})
    if handoff:
        write_text(root / "reports" / "manual_upload_handoff.md", handoff)
    return decision


def _case_from_requirements(requirements_text: str, data_profile: dict[str, Any]) -> dict[str, Any]:
    fields = data_profile.get("fields") or ["date_field", "dimension_1", "metric_1"]
    lowered = requirements_text.lower()
    explicit_kpi = any(
        marker in lowered
        for marker in ("chart visual: kpi", "visualization type: kpi", "kpi card", "kpi status", "metric card")
    )
    explicit_trend = any(
        marker in lowered
        for marker in ("chart visual: line", "chart visual: trend", "visualization type: line", "line chart")
    )
    if explicit_kpi:
        family = "kpi_value_delta" if "delta" in lowered else "kpi_value_only"
        task = "monitoring"
    elif explicit_trend:
        family = "line_chart"
        task = "time_trend"
    elif any(word in lowered for word in ("table", "registry", "lookup", "detail")):
        family = "table_node"
        task = "exact_lookup"
    elif any(word in lowered for word in ("selector", "filter", "control")):
        family = "single_select_dropdown"
        task = "filtering"
    elif any(word in lowered for word in ("markdown", "methodology", "owner", "note", "header")):
        family = "md_methodology_block"
        task = "metadata_methodology"
    elif any(word in lowered for word in ("map", "geo", "latitude", "longitude")):
        family = "native_map_geo_widget"
        task = "geo"
    elif any(word in lowered for word in ("trend", "time", "daily", "weekly", "month")):
        family = "line_chart"
        task = "time_trend"
    elif any(word in lowered for word in ("rank", "top", "compare", "bar")):
        family = "horizontal_bar"
        task = "comparison"
    else:
        family = "kpi_value_only"
        task = "monitoring"
    return {
        "schema_version": "2026-06-04.local_mcp_intake.case.v1",
        "case_id": "mcp_intake",
        "domain": "local_mcp_dashboard",
        "source_manifest": [{"source_id": "REQ-001", "role": "customer_requirements", "short_evidence": requirements_text[:240]}],
        "id_placeholder": {
            "dashboard_name": _first_title(requirements_text),
            "contact": "local_operator",
            "process": "DataLens dashboard delivery",
            "lifetime": "local_only",
            "update_frequency": "unknown",
            "objective": requirements_text[:500],
            "background": "Generated from MCP requirements intake.",
            "business_value": "Support governed DataLens dashboard delivery.",
            "audience": ["business owner", "analyst"],
            "decision_action": "Decide follow-up action from the requested dashboard evidence.",
            "data_sources": ["user_supplied_or_local_source"],
            "source_statuses": ["synthetic_or_user_supplied"],
            "metrics": [
                {
                    "metric_id": "MET-001",
                    "name": _first_title(requirements_text),
                    "requirement_phrase": requirements_text[:240],
                    "business_question": requirements_text[:240],
                    "analytical_task": task,
                    "required_fields": fields,
                    "source_contract_ids": ["DATA-001"],
                    "support_status": "supported_with_assumption",
                    "expected_family": family,
                    "metric_semantics": {
                        "unit": "declared_or_pending",
                        "grain": "declared_or_pending",
                        "aggregation": "declared_or_pending",
                        "numerator": fields[-1] if fields else "metric_1",
                        "denominator": "not_applicable_or_pending",
                        "additivity": "declared_or_pending",
                        "time_grain": "declared_or_pending",
                        "comparator": "declared_or_pending",
                        "baseline": "declared_or_pending",
                        "target": "declared_or_pending",
                    },
                    "assumptions": ["MCP intake used compact requirements text rather than full customer/S2T package."],
                    "rejected_alternatives": ["ungoverned_native_fallback", "blind_api_write"],
                }
            ],
            "open_questions": [],
            "out_of_scope": [],
        },
        "data_contracts": [
            {
                "contract_id": "DATA-001",
                "table_name": "table_1",
                "domain": "local_mcp_dashboard",
                "load_frequency": "unknown",
                "load_type": "unknown",
                "fields": [{"name": field, "type": "string", "flags": []} for field in fields],
                "source_mappings": [],
                "algorithms": [],
                "available_datetime_fields": [field for field in fields if field.lower().endswith(("dt", "dttm", "date"))],
                "supported_grains": [],
                "supported_filters": fields[:2],
                "dq_checks": [],
            }
        ],
    }


def dl_ingest_requirements(
    project_root: str = ".",
    requirements_text: str = "",
    data_path: str = "",
    source_name: str = "REQ-001",
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    persisted = ingest_requirements_markdown(
        root,
        markdown_text=requirements_text or "Synthetic dashboard requirements.",
        source_name=source_name,
        role="dashboard",
    )
    data_profile: dict[str, Any] = {}
    if data_path:
        data_file = Path(data_path)
        if data_file.suffix.lower() == ".csv" and data_file.is_file():
            data_profile = _profile_csv(data_file)
    source_route_decision: dict[str, Any] | None = None
    if _needs_source_route_decision(requirements_text, data_path):
        source_route_decision = _write_source_route_artifacts(root, requirements_text, data_path, data_profile)
    case = _case_from_requirements(requirements_text or "Synthetic dashboard requirements.", data_profile)
    bundle = build_governance_bundle(case)
    brief = _brief_from_governance_bundle(bundle)
    write_json(root / "artifacts" / "requirements_s2t_bundle.json", bundle)
    write_json(root / "artifacts" / "dashboard_brief.json", brief)
    write_json(root / "artifacts" / "data_contract.json", brief["data_contract"])
    result = {
        "dashboard_brief": brief,
        "data_profile": data_profile,
        "requirements_workspace": persisted,
        "suggested_records": [
            {
                "op": "upsert_entry",
                "path": "memory-bank/project.md",
                "heading": "Current State",
                "entry_id": "datalens-requirements",
                "content": f"DataLens requirements source `{source_name}` was ingested into the governed requirements workspace.",
            }
        ],
    }
    if source_route_decision is not None:
        result["source_route_decision"] = source_route_decision
    return result


def dl_build_governance_brief(project_root: str = ".", requirements_text: str = "") -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    existing = read_json(root / "artifacts" / "dashboard_brief.json", default=None)
    if existing:
        brief = existing
    else:
        # Route selection must use the controlling user/source input, not
        # generated requirement templates whose headings (for example
        # Methodology or Operational Lifecycle) can masquerade as chart intent.
        persisted_text = read_text(root / "requirements" / "source_inputs.md") or read_persisted_requirements_text(root)
        case = _case_from_requirements(requirements_text or persisted_text or "Synthetic dashboard requirements.", {})
        brief = _brief_from_governance_bundle(build_governance_bundle(case))
    write_json(root / "artifacts" / "dashboard_brief.json", brief)
    write_json(root / "datalens_mapping" / "governance_memory_registry.json", {
        "version": 1,
        "source_documents": [{"source_id": "REQ-001", "role": "customer_requirements", "status": "parsed"}],
        "dashboard_passport": {"dashboard_name": brief["dashboard_name"], "status": "parsed"},
        "metric_registry": [{"metric_id": "MET-001", "name": brief["dashboard_name"], "status": "active"}],
        "data_support_matrix": [{"metric_id": "MET-001", "data_support_status": "supported"}],
        "chart_decisions": brief["chart_decisions"],
        "assumptions": [],
        "customer_visible_caveats": [],
        "stage_batch": {"current_stage": "governance", "current_batch": "batch-001"},
        "build_outcomes": [],
    })
    return brief


def dl_init_requirements_workspace(project_root: str = ".") -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    return initialize_requirements_workspace(root)


def dl_ingest_requirements_markdown(
    project_root: str = ".",
    markdown_text: str = "",
    source_name: str = "user_input",
    role: str = "dashboard",
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    return ingest_requirements_markdown(root, markdown_text=markdown_text, source_name=source_name, role=role)


def dl_select_dashboard_blueprint(requirements_text: str = "", data_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    return select_dashboard_blueprint(requirements_text, data_profile=data_profile)


def dl_populate_dashboard_map_canvas(
    project_root: str = ".",
    source_text: str = "",
    source_name: str = "user_input",
    data_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    return populate_dashboard_map_canvas(root, source_text=source_text, source_name=source_name, data_profile=data_profile)


def dl_build_wizard_payload_template(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_wizard_payload_plan(config)


def dl_list_wizard_templates() -> dict[str, Any]:
    return load_wizard_template_registry()


def dl_build_dashboard_blueprint_plan(project_root: str = ".") -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    return build_dashboard_blueprint_plan(root)


def dl_update_user_decision(project_root: str = ".", decision_text: str = "", decision_id: str = "") -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    return update_user_decision(root, decision_text=decision_text, decision_id=decision_id)


def dl_summarize_implementation_plan(project_root: str = ".") -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    return summarize_implementation_plan(root)


def dl_validate_chart_plan_against_requirements(project_root: str = ".", chart_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    return validate_chart_plan_against_requirements(root, chart_plan=chart_plan or {})


def dl_generate_editor_bundle(
    project_root: str = ".",
    widget_id: str = "widget_001",
    route: str = "",
    authoring_profile: str = "",
    dataset_alias: str = "",
    columns: list[str] | None = None,
    selector_contract: dict[str, Any] | None = None,
    dataset_readbacks: list[dict[str, Any]] | None = None,
    html_page: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    if html_page is not None:
        incompatible = bool(
            str(route or "").strip()
            or str(authoring_profile or "").strip()
            or str(dataset_alias or "").strip()
            or columns is not None
            or selector_contract is not None
            or dataset_readbacks is not None
        )
        if incompatible:
            raise ValueError(
                "html_page is mutually exclusive with route, authoring_profile, dataset bindings, and selector inputs"
            )
        return _generate_standalone_html_artifact(root=root, page_id=widget_id, spec=html_page)
    profile = resolve_authoring_profile(
        project_root=root,
        requested_profile=authoring_profile,
    )
    if not profile.get("ok"):
        return profile
    brief = read_json(root / "artifacts" / "dashboard_brief.json", default={})
    if not brief:
        brief = dl_build_governance_brief(str(root))
    requirements_context = summarize_implementation_plan(root)
    intent_text = str(requirements_context.get("summary") or "")
    decision = (brief.get("chart_decisions") or [{}])[0]
    decision_record = decision.get("chart_decision_record") if isinstance(decision.get("chart_decision_record"), dict) else {}
    explicit_route_override = normalize_creation_route(route) if str(route or "").strip() else ""
    route_override = explicit_route_override or normalize_creation_route(decision.get("route") or "")
    selected_route = route_override
    requested_family = str(decision.get("family") or "")
    if decision_record:
        if requested_family and decision_record.get("selected_family") != requested_family:
            decision_record = {}
        elif selected_route and decision_record.get("selected_route") != selected_route:
            decision_record = {}
    if not decision_record:
        negative_requirements = load_negative_requirement_ledger(root)
        inferred = decide_chart(
            chart_id=str(decision.get("decision_id") or widget_id),
            business_question=intent_text or str((brief.get("requirements") or [{}])[0].get("text") or ""),
            audience=list(brief.get("audience") or []),
            dashboard_type=str(brief.get("dashboard_type") or "unknown"),
            data_shape={"fields": (brief.get("data_contract") or {}).get("fields") or []},
            negative_requirements=negative_requirements,
            requested_family=requested_family,
            source_evidence_refs=["dashboard_brief", "requirements_context"],
        )
        decision_record = inferred.to_dict()
        if route_override:
            decision_record["selected_route"] = route_override
        decision["chart_decision_record"] = decision_record
        decision["renderer_visual_spec"] = inferred.renderer_visual_spec.to_dict()
    if not route_override:
        selected_route = normalize_creation_route(
            str(decision_record.get("selected_route") or decision.get("route") or "wizard_native")
        )
    requested_family = str(decision_record.get("selected_family") or requested_family or "table_node")
    profile_route = authoring_profile_route_decision(
        profile=profile,
        family=requested_family,
        explicit_route=explicit_route_override,
    )
    if not profile_route.get("ok"):
        return {
            **profile_route,
            "authoring_profile": profile,
            "requested_route": explicit_route_override,
            "requested_family": requested_family,
        }
    if profile_route.get("active"):
        selected_route = str(profile_route["route"])
        requested_family = str(profile_route["family"])
        decision_record = {
            **decision_record,
            "selected_route": selected_route,
            "selected_family": requested_family,
            "selection_origin": "authoring_profile_registered_template",
            "authoring_profile_id": profile["id"],
        }
    widget_title = str(
        decision.get("title")
        or decision_record.get("title")
        or brief.get("dashboard_name")
        or "Untitled Widget"
    )
    if selected_route == "ql_explicit":
        return {
            "ok": False,
            "route": "ql_explicit",
            "selection_origin": "explicit_user_request",
            "status": "explicit_payload_required",
            "error": {
                "category": "explicit_payload_required",
                "message": (
                    "QL payloads are not generated from a general prompt; use generic lifecycle tools "
                    "with an explicit payload or fresh saved QL seed."
                ),
            },
        }
    if selected_route == "wizard_native":
        visualization_id = visualization_for_family(requested_family, semantic_text=intent_text) or "flatTable"
        registry_spec = (load_wizard_template_registry().get("templates") or {}).get(visualization_id) or {}
        data_contract = brief.get("data_contract") if isinstance(brief.get("data_contract"), dict) else {}
        # ``columns`` is an explicit caller-owned binding surface. Requirements
        # prose and inferred data-contract names are not DataLens field GUIDs
        # and must never be promoted to internal tokens automatically.
        raw_fields = list(columns) if columns is not None else [
            field
            for field in (data_contract.get("fields") or [])
            if isinstance(field, dict) and str(field.get("guid") or field.get("field_guid") or "").strip()
        ]
        field_values: list[dict[str, Any]] = []
        for index, field in enumerate(raw_fields):
            if isinstance(field, dict):
                guid = str(field.get("guid") or field.get("field_guid") or "").strip()
                if guid:
                    field_values.append({**field, "guid": guid})
            elif str(field or "").strip():
                # String values are accepted only from the explicit ``columns``
                # argument, where the caller is responsible for supplying the
                # saved dataset field GUIDs.
                field_values.append({"guid": str(field).strip(), "title": str(field).strip()})
        field_bindings: dict[str, Any] = {}
        for index, role_name in enumerate(registry_spec.get("required_roles") or []):
            if field_values:
                field_bindings[str(role_name)] = field_values[min(index, len(field_values) - 1)]
        if requested_family == "bubble" and field_values:
            field_bindings["size"] = field_values[-1]
        dataset_id = dataset_alias.strip() or str(data_contract.get("dataset_id") or "").strip()
        plan = build_wizard_payload_plan(
            {
                "schema_version": "2026-07-13.wizard_chart_compiler_input.v1",
                "widget_id": widget_id,
                "route": "wizard_native",
                "visualization_id": visualization_id,
                "semantic_family": requested_family,
                "dataset": dataset_id,
                **(
                    {"dataset_readbacks": list(dataset_readbacks)}
                    if dataset_readbacks is not None
                    else {}
                ),
                "field_bindings": field_bindings,
                "geo": {"evidence_kind": "validated_map_payload"} if visualization_id == "geolayer" else {},
                "options": {"title": widget_title},
            }
        )
        validation_errors = list((plan.get("validation") or {}).get("errors") or [])
        missing_source = any(
            error == "dataset is required" or error.startswith("field_bindings.")
            for error in validation_errors
        )
        plan["generation_status"] = (
            "ready" if plan.get("ok") else "blocked_missing_source" if missing_source else "blocked_invalid_template_config"
        )
        plan["chart_decision_record"] = decision_record
        plan["renderer_visual_spec"] = (
            decision_record.get("renderer_visual_spec") or decision.get("renderer_visual_spec") or {}
        )
        plan["source_template"] = f"templates/datalens/wizard/canonical_templates.json#{visualization_id}"
        plan["source_gallery"] = plan["source_template"]
        plan["requirements_context"] = {
            "implementation_plan": requirements_context["path"],
            "summary_preview": requirements_context["summary"][:1200],
        }
        write_json(root / "artifacts" / f"{widget_id}.wizard_payload_plan.json", plan)
        write_json(root / "artifacts" / f"{widget_id}.chart_decision.json", decision_record)
        relations = _write_dashboard_relations(
            root=root,
            brief=brief,
            widget_id=widget_id,
        )
        if plan.get("ok"):
            update_implemented_charts_catalog(root, bundle=plan, relations=relations, brief=brief)
        return plan
    visual_spec = decision_record.get("renderer_visual_spec") or decision.get("renderer_visual_spec") or {}
    data_contract = brief.get("data_contract") if isinstance(brief.get("data_contract"), dict) else {}
    contract_columns: list[str] = []
    for field in data_contract.get("fields") or []:
        if isinstance(field, dict):
            value = field.get("name") or field.get("field")
        else:
            value = field
        if str(value or "").strip():
            contract_columns.append(str(value).strip())
    resolved_dataset_alias = dataset_alias.strip() or str(data_contract.get("dataset_alias") or "").strip()
    resolved_columns = list(columns) if columns is not None else contract_columns
    bundle = generate_editor_bundle(
        widget_id=widget_id,
        route=selected_route,
        title=widget_title,
        dataset_alias=resolved_dataset_alias or None,
        columns=resolved_columns,
        markdown=intent_text or None,
        selector_contract=selector_contract,
        family=decision_record.get("selected_family") or decision.get("family"),
        visual_spec=visual_spec,
        chart_decision_record=decision_record,
    )
    if profile_route.get("active"):
        bundle = apply_authoring_profile_bundle(
            bundle=bundle,
            profile=profile,
            route_decision=profile_route,
        )
        if bundle.get("status") == "blocked_authoring_profile":
            return bundle
        provenance = bundle.get("template_provenance") if isinstance(bundle.get("template_provenance"), dict) else {}
        exact_match = bool(
            bundle.get("source_template") == profile_route.get("source_template")
            and bundle.get("route") == profile_route.get("route")
            and bundle.get("family") == profile_route.get("family")
            and provenance.get("policy") == "exact_registered_asset"
            and provenance.get("approximate_fallback_used") is False
            and provenance.get("profile_template_set_sha256") == profile.get("template_set_sha256")
            and provenance.get("profile_style_contract_sha256") == profile.get("style_contract_sha256")
        )
        if not exact_match:
            return {
                "ok": False,
                "status": "blocked_authoring_profile",
                "error": {
                    "category": "exact_template_identity_mismatch",
                    "message": (
                        f"profile {profile['id']} expected {profile_route.get('source_template')}; "
                        "approximate, changed, or unregistered output was refused"
                    ),
                },
                "authoring_profile": profile,
                "profile_route_decision": profile_route,
            }
        bundle["authoring_profile"] = {
            **profile,
            "enforced": True,
            "exact_template_reused": True,
        }
        bundle["profile_route_decision"] = profile_route
    selected_recipe = select_authoring_recipe(
        intent_text=intent_text,
        route=selected_route,
        source_type=str((brief.get("data_contract") or {}).get("source_type") or ""),
    )
    bundle["knowledge_recipe"] = compact_recipe_for_payload(selected_recipe["recipe"])
    if selected_recipe["blocked_advanced_exception_reason"]:
        bundle["advanced_exception_gate"] = {
            "status": "blocked_without_evidence",
            "reason": selected_recipe["blocked_advanced_exception_reason"],
        }
    bundle["requirements_context"] = {
        "implementation_plan": requirements_context["path"],
        "summary_preview": requirements_context["summary"][:1200],
    }
    bundle_dir = root / "dashboard" / widget_id
    for tab, content in bundle["tabs"].items():
        write_text(bundle_dir / tab, content)
    write_json(bundle_dir / "bundle.json", bundle)
    write_json(root / "artifacts" / f"{widget_id}.chart_decision.json", decision_record)
    relations = _write_dashboard_relations(
        root=root,
        brief=brief,
        widget_id=widget_id,
        selector_contract=(
            bundle.get("selector_contract")
            if isinstance(bundle.get("selector_contract"), dict)
            and bundle["selector_contract"].get("ok") is True
            else None
        ),
    )
    update_implemented_charts_catalog(root, bundle=bundle, relations=relations, brief=brief)
    return bundle


def _generate_standalone_html_artifact(
    *,
    root: Path,
    page_id: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    normalized_id = str(page_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?", normalized_id):
        raise ValueError("widget_id must be a safe 1..128 character artifact id")
    rendered = render_standalone_html_page(spec)
    privacy = scan_text(rendered["html"], source=f"html_pages/{normalized_id}.html")
    if not rendered["ok"] or not privacy.ok:
        return {
            "ok": False,
            "schema_version": rendered["schema_version"],
            "kind": "standalone_html_page",
            "generation_status": "blocked_validation",
            "page_id": normalized_id,
            "validation": rendered["validation"],
            "privacy": {"ok": privacy.ok, "issues": privacy.issues},
            "source_contract": rendered["source_contract"],
        }
    artifact_relative = Path("artifacts") / "html_pages" / f"{normalized_id}.html"
    manifest_relative = Path("artifacts") / "html_pages" / f"{normalized_id}.manifest.json"
    write_text(root / artifact_relative, rendered["html"])
    manifest = {
        "schema_version": rendered["schema_version"],
        "kind": "standalone_html_page",
        "page_id": normalized_id,
        "artifact": {
            "path": artifact_relative.as_posix(),
            "bytes": rendered["bytes"],
            "sha256": rendered["sha256"],
        },
        "validation": rendered["validation"],
        "source_contract": rendered["source_contract"],
    }
    write_json(root / manifest_relative, manifest)
    return {
        "ok": True,
        "schema_version": rendered["schema_version"],
        "kind": "standalone_html_page",
        "generation_status": "ready_local_artifact",
        "page_id": normalized_id,
        "artifact": manifest["artifact"],
        "manifest_path": manifest_relative.as_posix(),
        "validation": {
            "ok": True,
            "summary": rendered["validation"]["summary"],
        },
        "publication": rendered["source_contract"]["publication"],
        "source_contract": rendered["source_contract"],
    }


def dl_validate_project(project_root: str = ".") -> dict[str, Any]:
    root = Path(project_root)
    cache_key = str(root.expanduser().resolve())
    input_fingerprint = _project_validation_fingerprint(root)
    cached = _cached_project_validation(cache_key, input_fingerprint)
    if cached is not None:
        record_cache_hit("project_validation")
        cached["validation_cache"] = {
            "hit": True,
            "fingerprint": input_fingerprint,
            "strategy": "filesystem_metadata",
        }
        return cached

    issues: list[str] = []
    bundle_paths = list(root.glob("dashboard/*/bundle.json"))
    for bundle_path in bundle_paths:
        bundle = read_json(bundle_path, default={})
        generation_status = str(bundle.get("generation_status") or "")
        if generation_status and generation_status != "ready":
            blocking = bundle.get("blocking_issues") or (bundle.get("source_contract") or {}).get("issues") or []
            if blocking:
                for issue in blocking:
                    message = issue.get("message") if isinstance(issue, dict) else str(issue)
                    issues.append(f"{bundle_path}: generation blocked: {message}")
            else:
                issues.append(f"{bundle_path}: generation blocked: {generation_status}")
        result = validate_route_payload(bundle)
        issues.extend([f"{bundle_path}: {issue}" for issue in result.issues])
    wizard_plan_paths = list(root.glob("artifacts/*.wizard_payload_plan.json"))
    for wizard_plan_path in wizard_plan_paths:
        wizard_plan = read_json(wizard_plan_path, default={})
        generation_status = str(wizard_plan.get("generation_status") or "")
        if not wizard_plan.get("ok") or generation_status != "ready":
            validation_errors = list((wizard_plan.get("validation") or {}).get("errors") or [])
            if validation_errors:
                issues.extend(f"{wizard_plan_path}: generation blocked: {error}" for error in validation_errors)
            else:
                issues.append(f"{wizard_plan_path}: generation blocked: {generation_status or 'invalid Wizard plan'}")
    html_page_results = []
    for html_path in sorted(root.glob("artifacts/html_pages/*.html")):
        result = validate_standalone_html_page(
            html_path.read_bytes(),
            source=html_path.relative_to(root).as_posix(),
            strict=True,
        )
        html_page_results.append(
            {
                "path": html_path.relative_to(root).as_posix(),
                "ok": result["ok"],
                "summary": result["summary"],
                "sha256": result["sha256"],
            }
        )
        for finding in result["findings"]:
            if finding["severity"] in {"error", "warning"}:
                issues.append(
                    f"{html_path}: {finding['rule']}: {finding['message']}"
                )
    relations_path = root / "artifacts" / "dashboard_object_relations.json"
    if bundle_paths and not relations_path.is_file():
        issues.append("artifacts/dashboard_object_relations.json is required when dashboard bundles exist")
    elif relations_path.is_file():
        relation_result = validate_dashboard_relations(read_json(relations_path, default={}))
        issues.extend([f"{relations_path}: {issue}" for issue in relation_result.issues])
    standalone_html_only = bool(html_page_results) and not bundle_paths and not wizard_plan_paths
    if standalone_html_only:
        dashboard_preflight = {
            "ok": True,
            "applicability": "not_applicable_standalone_html",
            "checked_paths": [],
            "issues": [],
        }
        write_json(root / "artifacts" / "dashboard_payload_preflight.json", dashboard_preflight)
    else:
        dashboard_preflight = _run_dashboard_payload_preflight(root)
    for issue in dashboard_preflight["issues"]:
        if issue.get("severity") == "error":
            issues.append(f"{issue.get('path')}: {issue.get('rule')}: {issue.get('message')}")
    if standalone_html_only:
        visual_quality = {
            "ok": True,
            "applicability": "not_applicable_standalone_html",
            "checked_paths": [],
            "issues": [],
        }
        write_json(root / "artifacts" / "renderer_visual_quality.json", visual_quality)
    else:
        visual_quality = _run_renderer_visual_quality_preflight(root, bundle_paths)
    for issue in visual_quality["issues"]:
        if issue.get("severity") == "error":
            issues.append(f"{issue.get('path')}: {issue.get('rule')}: {issue.get('message')}")
    if standalone_html_only:
        sql_lint_report = {
            "ok": True,
            "applicability": "not_applicable_standalone_html",
            "checked_paths": [],
            "issues": [],
        }
    else:
        sql_lint_report = lint_project_editor_sql(root).to_dict()
    write_json(root / "artifacts" / "editor_sql_lint.json", sql_lint_report)
    for issue in sql_lint_report["issues"]:
        if issue.get("severity") == "error":
            issues.append(f"{issue.get('path')}: {issue.get('rule')}: {issue.get('message')}")
    if standalone_html_only:
        sql_performance = {
            "ok": True,
            "schema_version": "2026-06-25.sql_performance.v1",
            "applicability": "not_applicable_standalone_html",
            "checked_sql_count": 0,
            "sql_hashes": [],
            "issues": [],
            "reports": [],
        }
        write_json(root / "artifacts" / "sql_performance" / "project_semantic_validation.json", sql_performance)
    else:
        sql_performance = validate_project_sql_performance(root)
    for issue in sql_performance["issues"]:
        issues.append(f"sql_performance: {issue}")
    negative_drift = validate_no_negative_requirement_drift(root)
    for finding in negative_drift["findings"]:
        issues.append(
            "negative_requirement: "
            f"{finding.get('path')}:{finding.get('line')}: "
            f"{finding.get('requirement_id')} forbids {finding.get('token')}"
        )
    scan = scan_path(root)
    issues.extend(scan.issues)
    status = "pass" if not issues else "fail"
    report = {
        "status": status,
        "issues": issues,
        "checked": [
            "routes",
            "editor_bundles",
            "wizard_payload_plans",
            "standalone_html_pages",
            "dashboard_object_relations",
            "dashboard_payload_preflight",
            "renderer_visual_quality",
            "editor_sql_static_lint",
            "sql_performance_semantics",
            "negative_requirement_drift",
            "secrets",
        ],
        "dashboard_payload_preflight": dashboard_preflight,
        "renderer_visual_quality": visual_quality,
        "standalone_html_pages": html_page_results,
        "static_sql_lint": sql_lint_report,
        "sql_performance_semantics": {
            "ok": sql_performance["ok"],
            "checked_sql_count": sql_performance["checked_sql_count"],
            "issues": sql_performance["issues"],
            "artifact": str(root / "artifacts" / "sql_performance" / "project_semantic_validation.json"),
        },
        "negative_requirement_drift": negative_drift,
    }
    write_json(root / "artifacts" / "validation_report.json", report)
    output_fingerprint = _project_validation_fingerprint(root)
    _store_project_validation(cache_key, output_fingerprint, report)
    response = deepcopy(report)
    response["validation_cache"] = {
        "hit": False,
        "fingerprint": output_fingerprint,
        "strategy": "filesystem_metadata",
    }
    return response


def _project_validation_fingerprint(root: Path) -> str:
    rows: list[tuple[str, int, int, int]] = []
    if root.is_dir():
        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
                relative = path.relative_to(root)
                if any(part in _PROJECT_VALIDATION_CACHE_SKIP_DIRS for part in relative.parts):
                    continue
                stat = path.stat()
            except OSError:
                return ""
            rows.append((relative.as_posix(), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    encoded = json.dumps(sorted(rows), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cached_project_validation(cache_key: str, fingerprint: str) -> dict[str, Any] | None:
    if not fingerprint:
        return None
    with _PROJECT_VALIDATION_CACHE_LOCK:
        cached = _PROJECT_VALIDATION_CACHE.get(cache_key)
        if cached is None or cached[0] != fingerprint:
            return None
        _PROJECT_VALIDATION_CACHE.move_to_end(cache_key)
        return deepcopy(cached[1])


def _store_project_validation(cache_key: str, fingerprint: str, report: dict[str, Any]) -> None:
    if not fingerprint:
        return
    with _PROJECT_VALIDATION_CACHE_LOCK:
        _PROJECT_VALIDATION_CACHE[cache_key] = (fingerprint, deepcopy(report))
        _PROJECT_VALIDATION_CACHE.move_to_end(cache_key)
        while len(_PROJECT_VALIDATION_CACHE) > _PROJECT_VALIDATION_CACHE_MAX_ENTRIES:
            _PROJECT_VALIDATION_CACHE.popitem(last=False)


def dl_build_payload_plan(
    project_root: str = ".",
    workbook_id: str = "workbook_id",
    delivery_intent_text: str = "",
    target_known: bool = False,
    target_dashboard_id: str = "",
    target_chart_id: str = "",
    target_url: str = "",
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    payloads = []
    blocking_issues: list[dict[str, Any]] = []
    for bundle_path in root.glob("dashboard/*/bundle.json"):
        bundle = read_json(bundle_path, default={})
        generation_status = str(bundle.get("generation_status") or "")
        if generation_status and generation_status != "ready":
            blocking_issues.append(
                {
                    "widget_id": bundle.get("widget_id") or bundle_path.parent.name,
                    "status": generation_status,
                    "issues": bundle.get("blocking_issues")
                    or (bundle.get("source_contract") or {}).get("issues")
                    or [],
                    "action": "Supply dataset_alias and the required renderer output columns, then regenerate the bundle.",
                }
            )
            continue
        payload = compile_editor_payload(bundle, workbook_id=workbook_id)
        out = root / "artifacts" / "payloads" / f"{bundle.get('widget_id', bundle_path.parent.name)}.payload.json"
        write_json(out, payload)
        recipe = bundle.get("knowledge_recipe") if isinstance(bundle.get("knowledge_recipe"), dict) else {}
        payloads.append(
            {
                "widget_id": bundle.get("widget_id"),
                "method": "createEditorChart",
                "payload_path": str(out),
                "recipe_id": recipe.get("recipe_id") or "",
                "source_contract": recipe.get("source_contract") or "",
                "required_tabs": recipe.get("required_tabs") or [],
                "cardinality_limits": recipe.get("cardinality_limits") or {},
                "algorithmic_bound": recipe.get("algorithmic_bound") or "",
                "validation_checklist": recipe.get("validation_checklist") or [],
                "source_traces": recipe.get("source_traces") or [],
            }
        )
    for wizard_plan_path in root.glob("artifacts/*.wizard_payload_plan.json"):
        wizard_plan = read_json(wizard_plan_path, default={})
        generation_status = str(wizard_plan.get("generation_status") or "")
        if not wizard_plan.get("ok") or generation_status != "ready":
            blocking_issues.append(
                {
                    "widget_id": wizard_plan.get("widget_id") or wizard_plan_path.stem,
                    "status": generation_status or str(wizard_plan.get("status") or "blocked_invalid_template_config"),
                    "issues": list((wizard_plan.get("validation") or {}).get("errors") or []),
                    "action": "Supply an explicit dataset id and saved dataset field GUID bindings, then regenerate the Wizard plan.",
                }
            )
            continue
        dataset_readback_validation = (
            wizard_plan.get("dataset_readback_validation")
            if isinstance(wizard_plan.get("dataset_readback_validation"), dict)
            else {}
        )
        dataset_readbacks = [
            item
            for item in (wizard_plan.get("dataset_readbacks") or [])
            if isinstance(item, dict)
        ]
        if (
            wizard_plan.get("live_execution_ready") is not True
            or dataset_readback_validation.get("ok") is not True
            or not dataset_readbacks
        ):
            blocking_issues.append(
                {
                    "widget_id": wizard_plan.get("widget_id") or wizard_plan_path.stem,
                    "status": "blocked_missing_dataset_readback_evidence",
                    "issues": list(dataset_readback_validation.get("findings") or [])
                    or ["A validated saved dataset readback is required before Wizard create."],
                    "action": (
                        "Read the bound dataset, pass it as dataset_readbacks when compiling the Wizard plan, "
                        "then rebuild the payload plan."
                    ),
                }
            )
            continue
        compiled_payload = deepcopy(wizard_plan.get("compiled_payload") or {})
        if not any(compiled_payload.get(key) not in (None, "") for key in ("key", "workbookId")):
            compiled_payload["workbookId"] = workbook_id
            compiled_payload["name"] = str(wizard_plan.get("widget_id") or wizard_plan_path.stem)
        out = root / "artifacts" / "payloads" / f"{wizard_plan.get('widget_id') or wizard_plan_path.stem}.payload.json"
        write_json(out, compiled_payload)
        payloads.append(
            {
                "widget_id": wizard_plan.get("widget_id") or wizard_plan_path.stem,
                "method": "createWizardChart",
                "route": "wizard_native",
                "visualization_id": wizard_plan.get("visualization_id") or "",
                "source_kind": wizard_plan.get("source_kind") or "",
                "payload_path": str(out),
                "compiled_payload_sha256": wizard_plan.get("compiled_payload_sha256") or "",
                "validation": wizard_plan.get("validation") or {},
                "dataset_readbacks": dataset_readbacks,
                "dataset_readback_validation": dataset_readback_validation,
                "enforce_wizard_role_types": True,
            }
        )
    planned_object_key = (
        "planned_set:"
        + serialized_metadata(
            [
                {
                    "widget_id": str(item.get("widget_id") or ""),
                    "method": str(item.get("method") or ""),
                    "payload_path": str(item.get("payload_path") or ""),
                }
                for item in payloads
            ]
        )["sha256"]
        if payloads
        else ""
    )
    target_lock = create_target_lock(
        delivery_intent_text,
        target_source="user_url" if target_url else "manual",
        target_workbook_id=workbook_id,
        target_dashboard_id=target_dashboard_id,
        target_chart_id=target_chart_id,
        target_url=target_url,
        target_object_type="planned_object_set" if planned_object_key else "",
        target_object_key=planned_object_key,
    )
    delivery_decision = _delivery_intent_decision(
        delivery_intent_text,
        target_known=target_known or _looks_like_known_target(workbook_id, target_dashboard_id, target_chart_id),
        target_lock=target_lock.to_dict(),
        target_workbook_id=workbook_id,
        target_dashboard_id=target_dashboard_id,
        target_chart_id=target_chart_id,
        proof_path=str(root / "artifacts" / "payload_plan.json"),
    )
    plan = {
        "schema_version": "2026-05-25.payload_plan.v1",
        "status": "blocked" if blocking_issues else "ready",
        "workbook_id": workbook_id,
        "target_lock": target_lock.to_dict(),
        "payloads": payloads,
        "blocking_issues": blocking_issues,
        "delivery_intent_decision": delivery_decision,
    }
    write_json(root / "artifacts" / "payload_plan.json", plan)
    write_json(root / "artifacts" / "delivery" / "target_lock.json", target_lock.to_dict())
    _write_dashboard_preflight_candidate(root, workbook_id=workbook_id, payloads=payloads)
    return plan


def dl_detect_project_adapter(project_root: str = ".") -> dict[str, Any]:
    return detect_project_adapter(project_root)


def dl_detect_project_live_workflows(project_root: str = ".") -> dict[str, Any]:
    return detect_project_live_workflows(project_root)


def dl_list_project_live_workflows(project_root: str = ".") -> dict[str, Any]:
    detected = detect_project_live_workflows(project_root)
    if not detected.get("ok"):
        return detected
    return {
        **detected,
        "adapter_registry": list_project_adapter_registry()["adapters"],
        "workflow_names": detected.get("workflows") or [],
    }


def dl_plan_project_manifest(
    project_root: str = ".",
    write_manifest: bool = False,
    overwrite_existing: bool = False,
    target_workbook_id: str = "",
    dashboard_id: str = "",
    authoring_profile: str = "",
) -> dict[str, Any]:
    return plan_project_manifest(
        project_root,
        write_manifest=write_manifest,
        overwrite_existing=overwrite_existing,
        target_workbook_id=target_workbook_id,
        dashboard_id=dashboard_id,
        authoring_profile=authoring_profile,
    )


def dl_plan_project_live_workflow(
    project_root: str = ".",
    workflow_name: str = "",
    action: str = "dry_run",
    publish: bool = False,
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    result = plan_project_live_workflow(project_root, workflow_name=workflow_name, action=action, publish=publish)
    result["evidence_mode_decision"] = choose_evidence_mode(
        delivery_intent_text or action,
        changed_surfaces=[action, workflow_name],
        metadata_fetch_artifacts=result.get("expected_artifacts") or [],
    ).to_dict()
    result["delivery_intent_decision"] = _delivery_intent_decision(
        delivery_intent_text,
        default_text="implement" if publish else action,
        target_known=_looks_like_known_target(result.get("workbook_id"), result.get("dashboard_ids") or []),
        approved=False,
        fresh_readback_available=False,
        revision_preservation_available=False,
        saved_readback_available=False,
        proof_path=(result.get("summary_candidates") or [""])[0] if result.get("summary_candidates") else "",
        target_workbook_id=str(result.get("workbook_id") or ""),
        target_dashboard_id=(result.get("dashboard_ids") or [""])[0] if result.get("dashboard_ids") else "",
    )
    return result


def dl_run_project_live_dry_run(
    project_root: str = ".",
    workflow_name: str = "",
    execute_now: bool = False,
    timeout_sec: int = 120,
    execution_id: str = "",
) -> dict[str, Any]:
    result = run_project_live_dry_run(
        project_root,
        workflow_name=workflow_name,
        execute_now=execute_now,
        timeout_sec=timeout_sec,
        execution_id=execution_id,
    )
    result["evidence_mode_decision"] = choose_evidence_mode(
        "dry run",
        changed_surfaces=[workflow_name],
        metadata_fetch_artifacts=(result.get("expected_artifacts") or []),
    ).to_dict()
    result["delivery_intent_decision"] = _delivery_intent_decision(
        "dry run",
        default_text="dry run",
        target_known=_looks_like_known_target(result.get("workbook_id"), result.get("dashboard_ids") or []),
        proof_path=str((result.get("summary") or {}).get("summary_path") or ""),
        target_workbook_id=str(result.get("workbook_id") or ""),
        target_dashboard_id=(result.get("dashboard_ids") or [""])[0] if result.get("dashboard_ids") else "",
    )
    return result


def dl_run_project_live_apply(
    project_root: str = ".",
    workflow_name: str = "",
    execute_now: bool = False,
    publish: bool = False,
    action: str = "apply",
    timeout_sec: int = 120,
    delivery_intent_text: str = "",
    confirm_delete: bool = False,
    execution_id: str = "",
) -> dict[str, Any]:
    normalized_action = str(action or "apply").strip().lower().replace("-", "_")
    delete_confirmation: dict[str, Any] = {}
    preview: dict[str, Any] | None = None
    if execute_now and not execution_id and normalized_action == "retire_legacy_objects":
        preview = plan_project_live_workflow(
            project_root,
            workflow_name=workflow_name,
            action=normalized_action,
            publish=publish,
        )
        if not preview.get("ok"):
            return {**preview, "executed": False}
        delete_confirmation = _project_live_delete_confirmation(
            project_root=project_root,
            workflow_name=workflow_name,
            preview=preview,
            confirm_delete=confirm_delete,
        )
        if not delete_confirmation.get("confirmed"):
            return {
                **preview,
                "ok": False,
                "executed": False,
                "status": "delete_confirmation_required",
                "blocked_reasons": ["delete_confirmation_required"],
                "delete_confirmation_required": True,
                "delete_targets": delete_confirmation["delete_targets"],
                "delete_plan_hash": delete_confirmation["plan_hash"],
                "confirmation": delete_confirmation,
            }
    effective_authorized = _request_authorizes_standard_write(
        delivery_intent_text or action,
        default_text="implement",
    )
    if execute_now and not execution_id and normalized_action != "retire_legacy_objects":
        preview = preview or plan_project_live_workflow(
            project_root,
            workflow_name=workflow_name,
            action=normalized_action,
            publish=publish,
        )
        if not preview.get("ok"):
            return {**preview, "executed": False}
        pre_execution_decision = _project_live_delivery_decision(
            preview,
            delivery_intent_text,
            publish=publish,
            approved=effective_authorized,
            after_saved=False,
        )
        if pre_execution_decision.get("state") in {"read_only", "plan_only", "blocked"}:
            return {
                **preview,
                "executed": False,
                "status": str(pre_execution_decision.get("state") or "blocked"),
                "blocked_reasons": list(pre_execution_decision.get("blocked_reasons") or []),
                "delivery_intent_decision": pre_execution_decision,
            }
    result = run_project_live_apply(
        project_root,
        workflow_name=workflow_name,
        execute_now=execute_now,
        approved=effective_authorized,
        confirm_delete=bool(delete_confirmation.get("confirmed")),
        publish=publish,
        action=action,
        timeout_sec=timeout_sec,
        execution_id=execution_id,
    )
    result["evidence_mode_decision"] = choose_evidence_mode(
        delivery_intent_text or action,
        changed_surfaces=[action, workflow_name],
        metadata_fetch_artifacts=(result.get("expected_artifacts") or []),
    ).to_dict()
    delivery_decision = _project_live_delivery_decision(
        result,
        delivery_intent_text,
        publish=publish,
        approved=effective_authorized,
        after_saved=False,
    )
    result["delivery_intent_decision"] = delivery_decision
    resume_context = result.get("resume_context") if isinstance(result.get("resume_context"), dict) else {}
    if result.get("status") == "running" and result.get("execution_id"):
        resume_context = record_project_live_execution_context(
            project_root,
            str(result["execution_id"]),
            context={
                "auto_publish": delivery_decision.get("state") in {"save_then_publish", "publish_from_saved"}
                and not publish,
                "approved": effective_authorized,
                "delivery_intent_state": delivery_decision.get("state") or "",
                "publish_expected": delivery_decision.get("publish_expected"),
            },
        )
        result["resume_context"] = resume_context
    if delivery_intent_text:
        auto_publish_after_completion = delivery_decision.get("state") in {"save_then_publish", "publish_from_saved"}
    elif resume_context:
        auto_publish_after_completion = bool(resume_context.get("auto_publish"))
    else:
        auto_publish_after_completion = delivery_decision.get("state") in {"save_then_publish", "publish_from_saved"}
    if (
        result.get("status") not in {"running", "detached_running"}
        and str(result.get("action") or "") != "publish"
        and not result.get("publish_requested")
        and auto_publish_after_completion
        and not publish
        and (execute_now or bool(execution_id))
    ):
        result = _continue_project_live_publish(
            project_root=project_root,
            workflow_name=workflow_name,
            action=action,
            approved=bool(resume_context.get("approved", effective_authorized)),
            timeout_sec=timeout_sec,
            delivery_intent_text=delivery_intent_text or ("implement" if auto_publish_after_completion else "save only"),
            apply_result=result,
        )
    elif (
        execute_now
        and result.get("executed")
        and delivery_decision.get("state") == "save_only"
        and delivery_decision.get("publish_expected")
        and "publish_enabled" in (delivery_decision.get("blocked_reasons") or [])
    ):
        result["status"] = "saved_not_published"
        result["publish_blocked_reasons"] = ["publish_enabled"]
    if delete_confirmation.get("confirmed"):
        result["delete_confirmation"] = delete_confirmation
    return result


def _project_live_delete_confirmation(
    *,
    project_root: str,
    workflow_name: str,
    preview: dict[str, Any],
    confirm_delete: bool,
) -> dict[str, Any]:
    lifecycle = preview.get("retire_lifecycle") if isinstance(preview.get("retire_lifecycle"), dict) else {}
    targets = [
        {
            "id": str(item.get("id") or item.get("object_id") or item.get("entry_id") or ""),
            "type": str(item.get("type") or item.get("object_type") or ""),
        }
        for item in lifecycle.get("objects") or []
        if isinstance(item, dict)
    ]
    binding = {
        "action": "retire_legacy_objects",
        "workflow_name": workflow_name or str(preview.get("workflow_name") or ""),
        "manifest_path": str(preview.get("manifest_path") or ""),
        "workbook_id": str(lifecycle.get("workbook_id") or preview.get("workbook_id") or ""),
        "delete_targets": targets,
        "command": preview.get("command") or [],
        "required_proof_paths": lifecycle.get("required_proof_paths") or {},
    }
    plan_hash = serialized_metadata(binding)["sha256"]
    root = ensure_project_dirs(project_root)
    pending_path = root / "artifacts" / "delivery" / "delete_confirmation.json"
    pending = read_json(pending_path, default={})
    matched = bool(
        confirm_delete
        and str(pending.get("plan_hash") or "") == plan_hash
        and pending.get("delete_targets") == targets
    )
    confirmation = {
        "schema_version": "datalens.delete_confirmation.v1",
        "confirmed": matched,
        "confirm_delete": bool(confirm_delete),
        "plan_hash": plan_hash,
        "delete_targets": targets,
        "pending_path": str(pending_path),
        "same_plan": bool(str(pending.get("plan_hash") or "") == plan_hash),
    }
    write_json(pending_path, {**binding, **confirmation})
    return confirmation


def _project_live_delivery_decision(
    result: dict[str, Any],
    delivery_intent_text: str,
    *,
    publish: bool,
    approved: bool,
    after_saved: bool = False,
) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    saved_readback_available = bool(summary.get("saved") or result.get("saved_readback_path")) if after_saved else False
    result_action = str(result.get("action") or "").strip().lower()
    default_intent = "implement" if publish or result_action == "apply" else "save only"
    return _delivery_intent_decision(
        delivery_intent_text,
        default_text=default_intent,
        target_known=_looks_like_known_target(result.get("workbook_id"), result.get("dashboard_ids") or []),
        approved=approved,
        fresh_readback_available=False,
        revision_preservation_available=bool(result.get("safe_constraints") or summary),
        saved_readback_available=saved_readback_available,
        saved_readback_fresh=saved_readback_available or None,
        proof_path=str(summary.get("summary_path") or ""),
        target_workbook_id=str(result.get("workbook_id") or ""),
        target_dashboard_id=(result.get("dashboard_ids") or [""])[0] if result.get("dashboard_ids") else "",
    )


def _continue_project_live_publish(
    *,
    project_root: str,
    workflow_name: str,
    action: str,
    approved: bool,
    timeout_sec: int,
    delivery_intent_text: str,
    apply_result: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if not _project_live_stage_passed(apply_result):
        blockers.extend(
            apply_result.get("blocked_reasons")
            or ["apply summary did not pass validation; publish was not attempted"]
        )
    if "publish" not in (apply_result.get("workflow_modes") or []):
        blockers.append("missing_publish_path_for_save_then_publish")
    if blockers:
        return _project_live_delivery_result(apply_result, None, blockers)
    publish_result = run_project_live_apply(
        project_root,
        workflow_name=workflow_name,
        execute_now=True,
        approved=approved,
        publish=True,
        action=action,
        timeout_sec=timeout_sec,
    )
    publish_result["delivery_intent_decision"] = _project_live_delivery_decision(
        publish_result,
        delivery_intent_text,
        publish=True,
        approved=approved,
        after_saved=True,
    )
    if publish_result.get("status") != "running" and not _project_live_stage_passed(publish_result):
        blockers.extend(publish_result.get("blocked_reasons") or ["publish stage did not complete"])
    return _project_live_delivery_result(apply_result, publish_result, blockers)


def _project_live_delivery_result(
    apply_result: dict[str, Any],
    publish_result: dict[str, Any] | None,
    blockers: list[str],
) -> dict[str, Any]:
    summary = apply_result.get("summary") if isinstance(apply_result.get("summary"), dict) else {}
    publish_summary = (
        publish_result.get("summary")
        if isinstance(publish_result, dict) and isinstance(publish_result.get("summary"), dict)
        else {}
    )
    saved_paths = _project_live_readback_paths(summary, branch="saved")
    published_paths = _project_live_readback_paths(publish_summary, branch="published")
    apply_passed = _project_live_stage_passed(apply_result)
    publish_passed = bool(publish_result and _project_live_stage_passed(publish_result) and not blockers)
    publish_running = bool(publish_result and publish_result.get("status") == "running" and not blockers)
    if publish_passed:
        status = "completed"
    elif publish_running:
        status = "running"
    elif not apply_passed:
        status = str(apply_result.get("status") or "blocked")
    elif apply_result.get("executed"):
        status = "partial"
    else:
        status = "blocked"
    decision = _decision_with_stage_evidence(
        apply_result.get("delivery_intent_decision") if isinstance(apply_result.get("delivery_intent_decision"), dict) else {},
        save_status=str(apply_result.get("status") or ""),
        publish_status=str((publish_result or {}).get("status") or ("blocked" if blockers else "not_started")),
        saved_paths=saved_paths,
        published_paths=published_paths,
    )
    return {
        **apply_result,
        "ok": bool(apply_passed and (publish_passed or publish_running)),
        "status": status,
        "executed": bool(publish_result and publish_result.get("executed") and not blockers),
        "execution_id": str((publish_result or {}).get("execution_id") or apply_result.get("execution_id") or ""),
        "execution": (publish_result or {}).get("execution") or apply_result.get("execution") or {},
        "publish_blocked_reasons": blockers,
        "publish_result": publish_result,
        "approval_reuse_for_publish": bool((apply_result.get("delivery_intent_decision") or {}).get("approval_reuse_for_publish")),
        "delivery_intent_decision": decision,
        "project_live_delivery": {
            "state": "save_then_publish",
            "apply": _delivery_stage_snapshot(apply_result),
            "publish": _delivery_stage_snapshot(publish_result or {}),
            "saved": {
                "passed": apply_passed,
                "status": str(apply_result.get("status") or ""),
                "readback_paths": saved_paths,
            },
            "published": {
                "passed": publish_passed,
                "status": str((publish_result or {}).get("status") or ("blocked" if blockers else "not_started")),
                "readback_paths": published_paths,
            },
            "publish_blocked_reasons": blockers,
            "approval_reuse_for_publish": bool((apply_result.get("delivery_intent_decision") or {}).get("approval_reuse_for_publish")),
        },
    }


def _project_live_stage_passed(result: dict[str, Any]) -> bool:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    return bool(
        result.get("ok") is True
        and result.get("executed")
        and result.get("status") == "completed"
        and summary.get("ok") is True
    )


def _project_live_readback_paths(summary: dict[str, Any], *, branch: str) -> list[str]:
    keys = (
        [f"{branch}_readback_path", f"{branch}_readback_paths", "published_readback_path", "published_readback_paths"]
        if branch == "published"
        else [f"{branch}_readback_path", f"{branch}_readback_paths", "saved_readback_path", "saved_readback_paths"]
    )
    paths: list[str] = []
    for key in keys:
        value = summary.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
        elif isinstance(value, list):
            paths.extend(str(item) for item in value if str(item))
    return list(dict.fromkeys(paths))


def dl_read_project_live_summary(
    project_root: str = ".",
    workflow_name: str = "",
    action: str = "dry_run",
    publish: bool = False,
    summary_path: str = "",
) -> dict[str, Any]:
    result = read_project_live_summary(
        project_root,
        workflow_name=workflow_name,
        action=action,
        publish=publish,
        summary_path=summary_path,
    )
    result["evidence_mode_decision"] = choose_evidence_mode(
        "implement" if publish else action,
        changed_surfaces=[action, workflow_name],
        metadata_fetch_artifacts=(result.get("evidence_paths") or []),
    ).to_dict()
    result["delivery_intent_decision"] = _delivery_intent_decision(
        "implement" if publish else action,
        default_text="implement" if publish else action,
        target_known=_looks_like_known_target(result.get("workbook_id"), result.get("dashboard_ids") or []),
        approved=publish,
        fresh_readback_available=bool(result.get("summary_path")),
        revision_preservation_available=bool(result.get("saved")),
        saved_readback_available=bool(result.get("saved")),
        saved_readback_fresh=bool(result.get("saved")),
        proof_path=str(result.get("summary_path") or ""),
        target_workbook_id=str(result.get("workbook_id") or ""),
        target_dashboard_id=(result.get("dashboard_ids") or [""])[0] if result.get("dashboard_ids") else "",
    )
    return result


def dl_build_validation_evidence_report(project_root: str = ".") -> dict[str, Any]:
    return build_validation_evidence_report(project_root)


def dl_run_live_maintenance_update(
    project_root: str = ".",
    workbook_id: str = "",
    dashboard_id: str = "",
    target_tab_id: str = "",
    target_object_ids: list[str] | None = None,
    intent: str = "fix_existing",
    maintenance_mode: str = "quick_visible_patch",
    publish: bool = True,
    maintenance_evidence: dict[str, Any] | None = None,
    target_url: str = "",
    **legacy_evidence: Any,
) -> dict[str, Any]:
    evidence = _normalize_live_maintenance_evidence(maintenance_evidence, legacy_evidence)
    effective_authorized = _request_authorizes_standard_write(
        intent,
        default_text="fix existing dashboard",
    )
    return run_live_maintenance_update(
        project_root=project_root,
        workbook_id=workbook_id,
        dashboard_id=dashboard_id,
        target_tab_id=target_tab_id,
        target_object_ids=target_object_ids,
        intent=intent,
        maintenance_mode=maintenance_mode,
        approved=effective_authorized,
        publish=publish,
        browser_runtime_required=evidence["browser_runtime_required"],
        non_rendering_exemption=evidence["non_rendering_exemption"],
        baseline_snapshot_path=evidence["baseline_snapshot_path"],
        metadata_evidence_paths=evidence["metadata_evidence_paths"],
        source_availability_artifact=evidence["source_availability_artifact"],
        changed_objects=evidence["changed_objects"],
        allow_create=evidence["allow_create"],
        create_necessity_proof=evidence["create_necessity_proof"],
        cleanup_mode=evidence["cleanup_mode"],
        safe_apply_actions=evidence["safe_apply_actions"],
        guarded_requests=evidence["guarded_requests"],
        baseline_dashboard=evidence["baseline_dashboard"],
        proposed_dashboard=evidence["proposed_dashboard"],
        source_budget_evidence=evidence["source_budget_evidence"],
        runtime_gate_evidence=evidence["runtime_gate_evidence"],
        saved_runtime_gate_evidence=evidence["saved_runtime_gate_evidence"],
        published_runtime_gate_evidence=evidence["published_runtime_gate_evidence"],
        safe_apply_execution_evidence=evidence["safe_apply_execution_evidence"],
        saved_readback_evidence=evidence["saved_readback_evidence"],
        publish_from_saved_evidence=evidence["publish_from_saved_evidence"],
        published_readback_evidence=evidence["published_readback_evidence"],
        target_url=target_url,
    )


_LIVE_MAINTENANCE_EVIDENCE_DEFAULTS: dict[str, Any] = {
    "browser_runtime_required": True,
    "non_rendering_exemption": "",
    "baseline_snapshot_path": "",
    "metadata_evidence_paths": None,
    "source_availability_artifact": "",
    "changed_objects": None,
    "allow_create": False,
    "create_necessity_proof": None,
    "cleanup_mode": "plan_only",
    "safe_apply_actions": None,
    "guarded_requests": None,
    "source_budget_evidence": None,
    "runtime_gate_evidence": None,
    "saved_runtime_gate_evidence": None,
    "published_runtime_gate_evidence": None,
    "safe_apply_execution_evidence": None,
    "saved_readback_evidence": None,
    "publish_from_saved_evidence": None,
    "published_readback_evidence": None,
    "baseline_dashboard": None,
    "proposed_dashboard": None,
}
_LIVE_MAINTENANCE_OBJECT_FIELDS = {
    "create_necessity_proof",
    "runtime_gate_evidence",
    "saved_runtime_gate_evidence",
    "published_runtime_gate_evidence",
    "safe_apply_execution_evidence",
    "saved_readback_evidence",
    "publish_from_saved_evidence",
    "published_readback_evidence",
    "baseline_dashboard",
    "proposed_dashboard",
}
_LIVE_MAINTENANCE_OBJECT_LIST_FIELDS = {
    "changed_objects",
    "safe_apply_actions",
    "guarded_requests",
}
_LIVE_MAINTENANCE_STRING_FIELDS = {
    "non_rendering_exemption",
    "baseline_snapshot_path",
    "source_availability_artifact",
    "cleanup_mode",
}
_LIVE_MAINTENANCE_BOOL_FIELDS = {"browser_runtime_required", "allow_create"}


def _normalize_live_maintenance_evidence(
    maintenance_evidence: dict[str, Any] | None,
    legacy_evidence: dict[str, Any],
) -> dict[str, Any]:
    if maintenance_evidence is None:
        supplied: dict[str, Any] = {}
    elif isinstance(maintenance_evidence, dict):
        supplied = deepcopy(maintenance_evidence)
    else:
        raise ValueError("maintenance_evidence must be an object")

    known = set(_LIVE_MAINTENANCE_EVIDENCE_DEFAULTS)
    unknown_bundle = sorted(set(supplied) - known)
    unknown_legacy = sorted(set(legacy_evidence) - known)
    duplicate = sorted(set(supplied) & set(legacy_evidence))
    issues: list[str] = []
    if unknown_bundle:
        issues.append(f"maintenance_evidence has unknown fields: {', '.join(unknown_bundle)}")
    if unknown_legacy:
        issues.append(f"legacy maintenance evidence has unknown fields: {', '.join(unknown_legacy)}")
    if duplicate:
        issues.append(f"maintenance evidence fields were supplied twice: {', '.join(duplicate)}")
    if issues:
        raise ValueError("; ".join(issues))

    normalized = deepcopy(_LIVE_MAINTENANCE_EVIDENCE_DEFAULTS)
    normalized.update(supplied)
    normalized.update(deepcopy(legacy_evidence))
    for name in sorted(_LIVE_MAINTENANCE_BOOL_FIELDS):
        if type(normalized[name]) is not bool:
            issues.append(f"{name} must be boolean")
    for name in sorted(_LIVE_MAINTENANCE_STRING_FIELDS):
        if not isinstance(normalized[name], str):
            issues.append(f"{name} must be a string")
    metadata_paths = normalized["metadata_evidence_paths"]
    if metadata_paths is not None and (
        not isinstance(metadata_paths, list) or not all(isinstance(item, str) for item in metadata_paths)
    ):
        issues.append("metadata_evidence_paths must be an array of strings")
    for name in sorted(_LIVE_MAINTENANCE_OBJECT_FIELDS):
        value = normalized[name]
        if value is not None and not isinstance(value, dict):
            issues.append(f"{name} must be an object")
    for name in sorted(_LIVE_MAINTENANCE_OBJECT_LIST_FIELDS):
        value = normalized[name]
        if value is not None and (
            not isinstance(value, list) or not all(isinstance(item, dict) for item in value)
        ):
            issues.append(f"{name} must be an array of objects")
    source_budget = normalized["source_budget_evidence"]
    if source_budget is not None and not (
        isinstance(source_budget, dict)
        or (isinstance(source_budget, list) and all(isinstance(item, dict) for item in source_budget))
    ):
        issues.append("source_budget_evidence must be an object or an array of objects")
    if issues:
        raise ValueError("invalid maintenance evidence: " + "; ".join(issues))
    return normalized


def dl_build_dashboard_source_availability_matrix(
    dashboard_snapshot_path: str = "",
    metadata_fetch_inventory_path: str = "",
    data_health_readback_path: str = "",
    source_catalog_path: str = "",
    environments: list[str] | None = None,
    dashboard_object_ids: list[str] | None = None,
    strict_publish_gate: bool = True,
) -> dict[str, Any]:
    return build_dashboard_source_availability_matrix(
        dashboard_snapshot_path=dashboard_snapshot_path,
        metadata_fetch_inventory_path=metadata_fetch_inventory_path,
        data_health_readback_path=data_health_readback_path,
        source_catalog_path=source_catalog_path,
        environments=environments,
        dashboard_object_ids=dashboard_object_ids,
        strict_publish_gate=strict_publish_gate,
    )


def dl_validate_source_availability_consumers(
    matrix: dict[str, Any] | None = None,
    consumers: list[dict[str, Any]] | None = None,
    strict_publish_gate: bool = True,
) -> dict[str, Any]:
    return validate_source_availability_consumers(
        matrix=matrix,
        consumers=consumers,
        strict_publish_gate=strict_publish_gate,
    )


def dl_plan_source_availability_patch(
    matrix: dict[str, Any] | None = None,
    strict_publish_gate: bool = True,
) -> dict[str, Any]:
    return plan_source_availability_patch(matrix=matrix, strict_publish_gate=strict_publish_gate)


def dl_create_safe_apply_plan(
    project_root: str = ".",
    readback_mode: str = "minimal",
    entries_payload: dict[str, Any] | None = None,
    existing_update_actions: list[dict[str, Any]] | None = None,
    maintenance_contract: dict[str, Any] | None = None,
    delivery_intent_text: str = "",
    target_known: bool = False,
    target_workbook_id: str = "",
    target_dashboard_id: str = "",
    target_chart_id: str = "",
    target_url: str = "",
) -> dict[str, Any]:
    effective_authorized = _request_authorizes_standard_write(
        delivery_intent_text,
        default_text="implement",
    )
    root_path = Path(project_root)
    adapter = detect_project_adapter(root_path)
    if maintenance_contract is not None:
        if existing_update_actions:
            return {
                "ok": False,
                "status": "maintenance_contract_blocked",
                "actions": [],
                "blocked_reasons": ["maintenance_contract_conflicts_with_existing_update_actions"],
            }
        if str(maintenance_contract.get("kind") or "") != DATE_RANGE_MAINTENANCE_KIND:
            return {
                "ok": False,
                "status": "maintenance_contract_blocked",
                "actions": [],
                "blocked_reasons": ["maintenance_contract.kind_unsupported"],
            }
        if not str(target_workbook_id or "").strip():
            return {
                "ok": False,
                "status": "maintenance_contract_blocked",
                "actions": [],
                "blocked_reasons": ["maintenance_contract.target_workbook_id_missing"],
            }
        compiled_maintenance = compile_date_range_selector_merge(
            project_root=project_root,
            maintenance_contract=maintenance_contract,
        )
        if not compiled_maintenance.get("ok"):
            result = {
                "ok": False,
                "status": "maintenance_contract_blocked",
                "schema_version": compiled_maintenance.get("schema_version"),
                "project_root": str(root_path.resolve()),
                "maintenance_contract": compiled_maintenance,
                "actions": [],
                "blocked_reasons": list(compiled_maintenance.get("blocked_reasons") or []),
                "workflow_metrics": compiled_maintenance.get("workflow_metrics") or {},
            }
            root = ensure_project_dirs(project_root)
            write_json(root / "artifacts" / "safe_apply_plan.json", result)
            return result
        existing_update_actions = list(compiled_maintenance.get("actions") or [])
    early_target_lock = create_target_lock(
        delivery_intent_text,
        target_source="user_url" if target_url else "manual",
        target_workbook_id=target_workbook_id,
        target_dashboard_id=target_dashboard_id,
        target_chart_id=target_chart_id,
        target_url=target_url,
    )
    if existing_update_actions:
        result = _create_existing_object_update_safe_apply_plan(
            project_root=project_root,
            approved=effective_authorized,
            readback_mode="minimal" if maintenance_contract is not None else readback_mode,
            existing_update_actions=existing_update_actions,
            delivery_intent_text=delivery_intent_text,
            target_known=target_known,
            target_lock=early_target_lock.to_dict(),
            target_workbook_id=target_workbook_id,
        )
        if maintenance_contract is not None:
            result["maintenance_contract"] = compiled_maintenance
            result["workflow_metrics"] = compiled_maintenance.get("workflow_metrics") or {}
            result["runtime_smoke"] = compiled_maintenance.get("runtime_smoke") or {}
            root = ensure_project_dirs(project_root)
            write_json(root / "artifacts" / "safe_apply_plan.json", result)
        return result
    if adapter["adapter"] != "standard_bundle" and not (root_path / "artifacts" / "payload_plan.json").is_file():
        return {
            "ok": False,
            "status": "adapter_required",
            "error": {
                "category": "unsupported_custom_layout",
                "message": "Generic safe-apply cannot plan writes for this custom project layout.",
            },
            "adapter": adapter,
            "target_lock": early_target_lock.to_dict(),
            "actions": [],
            "delivery_intent_decision": _delivery_intent_decision(
                delivery_intent_text,
                target_known=target_known,
                approved=effective_authorized,
                target_lock=early_target_lock.to_dict(),
            ),
        }
    root = ensure_project_dirs(project_root)
    payload_plan = read_json(root / "artifacts" / "payload_plan.json", default={"payloads": []})
    if payload_plan.get("blocking_issues"):
        result = {
            "ok": False,
            "status": "payload_plan_blocked",
            "schema_version": "2026-05-25.safe_apply_plan.v1",
            "project_root": str(root),
            "actions": [],
            "blocked_reasons": ["payload_plan_has_blocking_issues"],
            "blocking_issues": deepcopy(payload_plan.get("blocking_issues") or []),
            "payload_plan_path": str(root / "artifacts" / "payload_plan.json"),
            "target_lock": (
                deepcopy(payload_plan.get("target_lock"))
                if isinstance(payload_plan.get("target_lock"), dict)
                else early_target_lock.to_dict()
            ),
            "delivery_intent_decision": _delivery_intent_decision(
                delivery_intent_text,
                target_known=target_known,
                approved=effective_authorized,
                target_lock=early_target_lock.to_dict(),
                proof_path=str(root / "artifacts" / "payload_plan.json"),
            ),
        }
        write_json(root / "artifacts" / "safe_apply_plan.json", result)
        return result
    existing_target_lock = payload_plan.get("target_lock") if isinstance(payload_plan.get("target_lock"), dict) else {}
    target_lock = create_target_lock(
        delivery_intent_text,
        target_source="user_url" if target_url else str(existing_target_lock.get("target_source") or "manual"),
        target_workbook_id=(
            target_workbook_id
            or str(payload_plan.get("workbook_id") or existing_target_lock.get("target_workbook_id") or "")
        ),
        target_dashboard_id=target_dashboard_id or str(existing_target_lock.get("target_dashboard_id") or ""),
        target_chart_id=target_chart_id or str(existing_target_lock.get("target_chart_id") or ""),
        target_url=target_url or str(existing_target_lock.get("target_url") or ""),
        target_object_type=str(existing_target_lock.get("target_object_type") or ""),
        target_object_key=str(existing_target_lock.get("target_object_key") or ""),
    )
    delivery_target_known = target_known or target_lock.known or _looks_like_known_target(payload_plan.get("workbook_id"))
    normalized_readback_mode = normalize_readback_mode(readback_mode)
    actions = []
    planned_objects = []
    for item in payload_plan.get("payloads", []):
        payload_path = str(item["payload_path"])
        payload = read_json(Path(payload_path), default={})
        entry = payload.get("entry") if isinstance(payload, dict) else {}
        data = entry.get("data") if isinstance(entry, dict) else {}
        internal_name = ""
        display_title = ""
        if isinstance(entry, dict):
            internal_name = str(entry.get("name") or "").strip()
        if isinstance(data, dict):
            internal_name = str(data.get("name") or internal_name).strip()
            display_title = str(data.get("title") or "").strip()
        if isinstance(payload, dict):
            internal_name = str(payload.get("name") or payload.get("key") or internal_name).strip()
            display_title = str(payload.get("title") or display_title or payload.get("name") or "").strip()
        method = str(item.get("method") or "")
        object_type = {
            "createEditorChart": "editor_chart",
            "createWizardChart": "wizard_chart",
        }.get(method, "unknown")
        planned_objects.append(
            {
                "display_title": display_title or internal_name or str(item.get("widget_id") or ""),
                "internal_name": internal_name or str(item.get("widget_id") or ""),
                "object_type": object_type,
            }
        )
        action_name = {
            "createEditorChart": "create_editor_chart",
            "createWizardChart": "create_wizard_chart",
        }.get(method, "create_object")
        readback_method = {
            "createEditorChart": "getEditorChart",
            "createWizardChart": "getWizardChart",
        }.get(method, "getWorkbookEntries")
        dataset_readbacks = [
            evidence
            for evidence in (item.get("dataset_readbacks") or [])
            if isinstance(evidence, dict)
        ]
        actions.append(
            {
                "action": action_name,
                "action_type": "create",
                "creation_necessity_proof": {
                    "schema_version": "datalens.object-creation-necessity.delta-v6",
                    "status": "required",
                    "update_insufficient_reason": (
                        "Payload plan describes a new chart object; pass workbook entries_payload to reconcile and reuse "
                        "existing matching objects before executing live create."
                    ),
                    "existing_readback_checked": entries_payload is not None,
                    "preserve_existing_ids_default": True,
                    "cleanup_report_required_if_created": True,
                },
                "object_type": object_type,
                "method": method,
                "mode": "save",
                "target_lock_hash": target_lock.lock_hash,
                "requires_fresh_read": True,
                "fresh_read_method": "getWorkbookEntries",
                "fresh_read_payload": {"workbookId": str(payload_plan.get("workbook_id") or "")},
                "readback_mode": normalized_readback_mode,
                "readback_required": normalized_readback_mode != "none",
                "readback_method": readback_method,
                "readback_payload": {"branch": "saved"},
                "readback_justification": "offline create plan; readback disabled explicitly" if normalized_readback_mode == "none" else "",
                "payload_path": payload_path,
                "payload_sha256": serialized_metadata(payload)["sha256"],
                "generator": "dl_build_payload_plan",
                "source_path": payload_path,
                **(
                    {
                        "dataset_readbacks": dataset_readbacks,
                        "enforce_wizard_role_types": True,
                    }
                    if method == "createWizardChart"
                    else {}
                ),
            }
        )
    if not actions:
        return {
            "ok": False,
            "status": "no_changed_actions",
            "error": {
                "category": "empty_changed_actions",
                "message": "Safe apply has no changed actions to execute.",
            },
            "adapter": adapter,
            "actions": [],
            "delivery_intent_decision": _delivery_intent_decision(
                delivery_intent_text,
                target_known=delivery_target_known,
                approved=effective_authorized,
                target_lock=target_lock.to_dict(),
                proof_path=str(root / "artifacts" / "safe_apply_plan.json"),
            ),
        }
    reconciliation = None
    reused_existing_objects: list[dict[str, Any]] = []
    if entries_payload is not None and planned_objects:
        workbook_id = str(payload_plan.get("workbook_id") or "")
        entries_evidence_validation = validate_entries_reconciliation_evidence(
            entries_payload,
            expected_workbook_id=workbook_id,
        )
        if not entries_evidence_validation["ok"]:
            result = {
                "ok": False,
                "status": "blocked_entries_reconciliation",
                "error": {
                    "category": "invalid_entries_reconciliation_evidence",
                    "message": "; ".join(entries_evidence_validation["issues"]),
                },
                "adapter": adapter,
                "entries_reconciliation_validation": entries_evidence_validation,
                "target_lock": target_lock.to_dict(),
                "actions": [],
                "delivery_intent_decision": _delivery_intent_decision(
                    delivery_intent_text,
                    target_known=delivery_target_known,
                    approved=effective_authorized,
                    target_lock=target_lock.to_dict(),
                    proof_path=str(root / "artifacts" / "safe_apply_plan.json"),
                ),
            }
            write_json(root / "artifacts" / "safe_apply_plan.json", result)
            return result
        reconciliation = reconcile_partial_creates(
            workbook_id=workbook_id,
            planned_objects=planned_objects,
            entries_payload=entries_payload,
        )
        reconciliation["evidence_validation"] = entries_evidence_validation
        reconciliation_path = root / "artifacts" / "entries_reconciliation.json"
        write_json(reconciliation_path, reconciliation)
        if reconciliation["duplicates_detected"]:
            return {
                "ok": False,
                "status": "manual_review",
                "error": {
                    "category": "duplicate_partial_create",
                    "message": "Duplicate existing objects were found; safe apply will not create more objects.",
                },
                "adapter": adapter,
                "reconciliation": reconciliation,
                "target_lock": target_lock.to_dict(),
                "actions": [],
                "delivery_intent_decision": _delivery_intent_decision(
                    delivery_intent_text,
                    target_known=delivery_target_known,
                    approved=effective_authorized,
                    target_lock=target_lock.to_dict(),
                    proof_path=str(root / "artifacts" / "safe_apply_plan.json"),
                ),
            }
        filtered_actions = []
        for action, item in zip(actions, reconciliation["objects"], strict=False):
            if item["recommended_action"] == "reuse":
                reused_existing_objects.append(item)
                continue
            creation_proof = {
                "schema_version": "datalens.object-creation-necessity.delta-v6",
                "status": "validated",
                "update_insufficient_reason": (
                    "Workbook entry reconciliation found no compatible existing object for the requested role."
                ),
                "existing_readback_checked": True,
                "preserve_existing_ids_default": True,
                "cleanup_report_required_if_created": True,
            }
            reuse_decision = build_object_reuse_decision(
                desired_role=str(action.get("action") or "create_object"),
                target_object_type=str(action.get("object_type") or "unknown"),
                existing_object_found=False,
                target_scope={"workbook_id": workbook_id},
                existing_candidates=list(item.get("matches") or []),
                selected_action="create",
                create_necessity_proof=creation_proof,
                cleanup_lifecycle={
                    "mode": "created_object_registry",
                    "owner_workflow": "dl_create_safe_apply_plan",
                    "active_graph_check": True,
                },
                baseline_proof_artifact=str(reconciliation_path),
            )
            action["creation_necessity_proof"] = creation_proof
            action["object_reuse_decision"] = reuse_decision
            action["cleanup_lifecycle"] = deepcopy(reuse_decision["cleanup_lifecycle"])
            action["entries_reconciliation"] = {
                "status": str(item.get("status") or ""),
                "recommended_action": str(item.get("recommended_action") or ""),
                "proof_artifact": str(reconciliation_path),
            }
            filtered_actions.append(action)
        actions = filtered_actions
        if not actions:
            return {
                "ok": False,
                "status": "no_changed_actions",
                "error": {
                    "category": "empty_changed_actions",
                    "message": "All planned creates already exist and can be reused; no live update action remains.",
                },
                "adapter": adapter,
                "reconciliation": reconciliation,
                "reused_existing_objects": reused_existing_objects,
                "target_lock": target_lock.to_dict(),
                "actions": [],
                "delivery_intent_decision": _delivery_intent_decision(
                    delivery_intent_text,
                    target_known=delivery_target_known,
                    approved=effective_authorized,
                    target_lock=target_lock.to_dict(),
                    proof_path=str(root / "artifacts" / "safe_apply_plan.json"),
                ),
            }
    plan = create_safe_apply_plan(
        project_root=str(root),
        actions=actions,
        approved=effective_authorized,
        user_request_text=delivery_intent_text,
    )
    plan["adapter"] = adapter
    plan["target_lock"] = target_lock.to_dict()
    plan["delivery_intent_decision"] = _delivery_intent_decision(
        delivery_intent_text,
        target_known=delivery_target_known,
        approved=effective_authorized,
        fresh_readback_available=False,
        revision_preservation_available=any(action.get("requires_fresh_read") for action in actions),
        saved_readback_available=False,
        target_lock=target_lock.to_dict(),
        proof_path=str(root / "artifacts" / "safe_apply_plan.json"),
    )
    if reconciliation is not None:
        plan["reconciliation"] = reconciliation
        plan["reused_existing_objects"] = reused_existing_objects
    plan["suggested_records"] = [
        {
            "op": "upsert_entry",
            "path": "memory-bank/project.md",
            "heading": "Current State",
            "entry_id": "datalens-safe-apply-plan",
            "content": (
                "A DataLens safe-apply plan exists; execution follows the user request and remains gated by "
                "runtime switches, target lock, fresh read, save-first semantics, and readback."
            ),
        }
    ]
    preflight = validate_safe_apply_plan_exhaustive(plan)
    plan["preflight"] = preflight
    plan["ok"] = preflight.get("ok") is True
    plan["status"] = "safe_apply_plan_ready" if plan["ok"] else "safe_apply_plan_blocked"
    if not plan["ok"]:
        plan["blocked_reasons"] = list(preflight.get("issues") or ["safe_apply_preflight_failed"])
    write_json(root / "artifacts" / "safe_apply_plan.json", plan)
    write_json(root / "artifacts" / "delivery" / "target_lock.json", target_lock.to_dict())
    return plan


def _create_existing_object_update_safe_apply_plan(
    *,
    project_root: str,
    approved: bool,
    readback_mode: str,
    existing_update_actions: list[dict[str, Any]],
    delivery_intent_text: str,
    target_known: bool,
    target_lock: dict[str, Any],
    target_workbook_id: str = "",
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    normalized_readback_mode = normalize_readback_mode(readback_mode)
    actions: list[dict[str, Any]] = []
    plan_actions: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []
    for index, item in enumerate(existing_update_actions):
        built = _existing_update_action(
            item,
            index=index,
            readback_mode=normalized_readback_mode,
            target_lock=target_lock,
            project_root=root,
        )
        if built.get("blocked_reasons"):
            blocked_reasons.extend(str(reason) for reason in built["blocked_reasons"])
        if built.get("action"):
            actions.append(built["action"])
            plan_actions.append(built["plan_action"])
    if actions:
        target_objects = _existing_update_target_objects(actions)
        if target_workbook_id:
            dashboard_ids = [
                item["object_id"]
                for item in target_objects
                if item["method"] == "updateDashboard"
            ]
            chart_ids = [
                item["object_id"]
                for item in target_objects
                if item["method"] != "updateDashboard"
            ]
            action_set_lock = create_target_lock(
                delivery_intent_text,
                target_source=str(target_lock.get("target_source") or "manual"),
                target_workbook_id=target_workbook_id,
                target_dashboard_id=dashboard_ids[0] if len(dashboard_ids) == 1 else "",
                target_chart_id=chart_ids[0] if len(chart_ids) == 1 else "",
                target_url=str(target_lock.get("target_url") or ""),
                target_object_type="safe_apply_action_set",
                target_object_key="|".join(
                    f"{item['method']}:{item['object_id']}" for item in target_objects
                ),
                target_objects=target_objects,
            ).to_dict()
        else:
            action_set_lock = _local_action_set_target_lock(target_objects)
        target_lock = action_set_lock
        for action in actions:
            action["target_lock_hash"] = str(target_lock.get("lock_hash") or "")
    update_plan = {
        "schema_version": "datalens.existing-object-update-plan.v1",
        "project_root": str(root),
        "actions": plan_actions,
        "blocked_reasons": blocked_reasons,
        "target_lock": target_lock,
    }
    write_json(root / "artifacts" / "existing_object_update_plan.json", update_plan)
    if blocked_reasons or not actions:
        result = {
            "ok": False,
            "status": "blocked",
            "schema_version": "datalens.existing-object-update-plan.v1",
            "project_root": str(root),
            "existing_object_update_plan": update_plan,
            "actions": actions,
            "blocked_reasons": blocked_reasons or ["existing_update_actions_empty"],
            "delivery_intent_decision": _delivery_intent_decision(
                delivery_intent_text,
                target_known=target_known or bool(actions),
                approved=approved,
                target_lock=target_lock,
                proof_path=str(root / "artifacts" / "existing_object_update_plan.json"),
            ),
        }
        write_json(root / "artifacts" / "safe_apply_plan.json", result)
        return result
    safe_plan = create_safe_apply_plan(
        project_root=str(root),
        actions=actions,
        approved=approved,
        user_request_text=delivery_intent_text,
    )
    safe_plan["existing_object_update_plan"] = update_plan
    safe_plan["target_lock"] = target_lock
    safe_plan["delivery_intent_decision"] = _delivery_intent_decision(
        delivery_intent_text,
        target_known=True,
        approved=approved,
        fresh_readback_available=True,
        revision_preservation_available=True,
        saved_readback_available=False,
        target_lock=target_lock,
        proof_path=str(root / "artifacts" / "safe_apply_plan.json"),
    )
    preflight = validate_safe_apply_plan_exhaustive(safe_plan)
    safe_plan["preflight"] = preflight
    safe_plan["ok"] = preflight.get("ok") is True
    safe_plan["status"] = (
        "existing_object_update_plan_created"
        if safe_plan["ok"]
        else "existing_object_update_plan_blocked"
    )
    if not safe_plan["ok"]:
        safe_plan["blocked_reasons"] = list(preflight.get("issues") or ["safe_apply_preflight_failed"])
    write_json(root / "artifacts" / "safe_apply_plan.json", safe_plan)
    write_json(root / "artifacts" / "delivery" / "target_lock.json", target_lock)
    return safe_plan


def _existing_update_action(
    item: dict[str, Any],
    *,
    index: int,
    readback_mode: str,
    target_lock: dict[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    object_type = str(item.get("object_type") or item.get("type") or "").strip().lower()
    method_spec = _existing_update_method_spec(object_type)
    payload = dict(item.get("payload") or item.get("updated_payload") or item.get("readback_payload") or {})
    envelope = item.get("readback") if isinstance(item.get("readback"), dict) else {}
    readback_path = str(item.get("readback_path") or "").strip()
    blocked: list[str] = []
    if readback_path:
        loaded = _load_existing_update_readback(project_root, readback_path)
        if not loaded["ok"]:
            blocked.append(f"existing_update[{index}].{loaded['reason']}")
        else:
            envelope = loaded["readback"]
            artifact_payload = _payload_from_readback_envelope(envelope)
            if payload and payload != artifact_payload:
                blocked.append(f"existing_update[{index}].payload_conflicts_with_readback_path")
            payload = artifact_payload
    elif not payload and envelope:
        payload = _payload_from_readback_envelope(envelope)
    if not method_spec:
        return {"blocked_reasons": [f"existing_update[{index}].unsupported_object_type:{object_type}"]}
    artifact_object_id = _object_id_from_update_payload(payload, method_spec["id_key"])
    artifact_revision = _revision_from_update_payload(payload)
    requested_object_id = str(item.get("object_id") or "").strip()
    requested_revision = str(item.get("base_revision") or item.get("rev_id") or "").strip()
    object_id = requested_object_id or artifact_object_id
    base_revision = requested_revision or artifact_revision
    if requested_object_id and artifact_object_id and requested_object_id != artifact_object_id:
        blocked.append(f"existing_update[{index}].readback_object_id_mismatch")
    if requested_revision and artifact_revision and requested_revision != artifact_revision:
        blocked.append(f"existing_update[{index}].readback_revision_mismatch")
    if not object_id:
        blocked.append(f"existing_update[{index}].missing_object_id")
    if not base_revision:
        blocked.append(f"existing_update[{index}].missing_base_revision")
    payload.setdefault("mode", "save")
    if not isinstance(payload.get("entry"), dict):
        payload.setdefault(method_spec["id_key"], object_id)
    _inject_revision(payload, base_revision)
    desired_overlay = item.get("desired_overlay")
    if desired_overlay is not None and not isinstance(desired_overlay, dict):
        blocked.append(f"existing_update[{index}].desired_overlay_invalid")
        desired_overlay = None
    if desired_overlay is None:
        desired_overlay = deepcopy(payload)
    preview = _merge_existing_update_overlay(payload, desired_overlay)
    if method_spec["method"] == "updateEditorChart":
        validation = validate_editor_runtime_contract(preview, source=f"existing_update[{index}]")
        errors = [finding for finding in validation.get("findings") or [] if finding.get("severity") == "error"]
        if errors and not item.get("validator_required_cleanup"):
            blocked.append(f"existing_update[{index}].full_object_editor_validation_failed")
    wizard_dataset_readbacks: list[dict[str, Any]] | None = None
    enforce_wizard_role_types: bool | None = None
    if method_spec["method"] == "updateWizardChart":
        raw_dataset_readbacks = item.get("dataset_readbacks")
        if raw_dataset_readbacks is not None:
            if not isinstance(raw_dataset_readbacks, list) or not all(
                isinstance(evidence, dict) for evidence in raw_dataset_readbacks
            ):
                blocked.append(f"existing_update[{index}].dataset_readbacks_invalid")
            else:
                wizard_dataset_readbacks = compact_wizard_dataset_readbacks(
                    payload,
                    raw_dataset_readbacks,
                )
        raw_enforce_role_types = item.get("enforce_wizard_role_types")
        if raw_enforce_role_types is not None and type(raw_enforce_role_types) is not bool:
            blocked.append(f"existing_update[{index}].enforce_wizard_role_types_invalid")
        elif raw_enforce_role_types is not None:
            enforce_wizard_role_types = raw_enforce_role_types
        if enforce_wizard_role_types is True and not wizard_dataset_readbacks:
            blocked.append(f"existing_update[{index}].dataset_readbacks_required_for_role_type_enforcement")
    plan_action = {
        "object_id": object_id,
        "object_type": object_type,
        "method": method_spec["method"],
        "mode": "save",
        "base_revision": base_revision,
        "changed_sections": [str(section) for section in item.get("changed_sections") or []],
        "validator_required_cleanup": [str(section) for section in item.get("validator_required_cleanup") or []],
        "requires_saved_readback": True,
        "requires_publish_readback": True,
    }
    action = {
        "action": f"update_{object_type or 'object'}",
        "action_type": "update",
        "method": method_spec["method"],
        "mode": "save",
        "target_lock_hash": str(target_lock.get("lock_hash") or ""),
        "requires_fresh_read": True,
        "fresh_read_method": method_spec["read_method"],
        "fresh_read_payload": {method_spec["id_key"]: object_id, "branch": "saved"},
        "preserve_unknown_fields": True,
        "readback_mode": readback_mode,
        "readback_required": readback_mode != "none",
        "readback_method": method_spec["read_method"],
        "readback_payload": {method_spec["id_key"]: object_id, "branch": "saved"},
        "payload": preview,
        "desired_overlay": desired_overlay,
        "changed_sections": plan_action["changed_sections"],
        "base_revision": base_revision,
        "validator_required_cleanup": plan_action["validator_required_cleanup"],
    }
    if method_spec["method"] == "updateDashboard":
        baseline_source = {
            "kind": "saved_readback",
            "path": readback_path,
        }
        action["current_dashboard"] = deepcopy(payload)
        action["baseline_dashboard"] = deepcopy(payload)
        action["baseline_diff_contract"] = build_baseline_diff_contract(
            dashboard_id=object_id,
            baseline_source=baseline_source,
            baseline_dashboard=payload,
            proposed_dashboard=preview,
            changed_objects=[],
        )
    if wizard_dataset_readbacks is not None:
        action["dataset_readbacks"] = wizard_dataset_readbacks
        plan_action["dataset_readbacks"] = wizard_dataset_readbacks
    if enforce_wizard_role_types is not None:
        action["enforce_wizard_role_types"] = enforce_wizard_role_types
        plan_action["enforce_wizard_role_types"] = enforce_wizard_role_types
    return {"action": action if not blocked else None, "plan_action": plan_action, "blocked_reasons": blocked}


def _existing_update_method_spec(object_type: str) -> dict[str, str]:
    normalized = normalize_publish_object_type(object_type)
    if normalized == "dashboard":
        return {"method": "updateDashboard", "read_method": "getDashboard", "id_key": "dashboardId"}
    if normalized == "editor_chart":
        return {"method": "updateEditorChart", "read_method": "getEditorChart", "id_key": "chartId"}
    if normalized == "wizard_chart":
        return {"method": "updateWizardChart", "read_method": "getWizardChart", "id_key": "chartId"}
    return {}


def _existing_update_target_objects(actions: list[dict[str, Any]]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for action in actions:
        fresh = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
        object_id = str(
            fresh.get("dashboardId")
            or fresh.get("chartId")
            or fresh.get("datasetId")
            or fresh.get("connectionId")
            or ""
        ).strip()
        targets.append(
            {
                "method": str(action.get("method") or "").strip(),
                "object_id": object_id,
            }
        )
    targets.sort(key=lambda item: (item["method"], item["object_id"]))
    return targets


def _local_action_set_target_lock(target_objects: list[dict[str, str]]) -> dict[str, Any]:
    lock_hash = serialized_metadata({"targets": target_objects})["sha256"]
    target_ids = [item["object_id"] for item in target_objects if item.get("object_id")]
    all_targets_known = bool(target_objects) and len(target_ids) == len(target_objects)
    dashboard_ids = [
        item["object_id"]
        for item in target_objects
        if item["method"] == "updateDashboard" and item.get("object_id")
    ]
    chart_ids = [
        item["object_id"]
        for item in target_objects
        if item["method"] != "updateDashboard" and item.get("object_id")
    ]
    return {
        "target_source": "manual",
        "target_workbook_id": "",
        "target_dashboard_id": dashboard_ids[0] if len(target_objects) == 1 and len(dashboard_ids) == 1 else "",
        "target_chart_id": chart_ids[0] if len(target_objects) == 1 and len(chart_ids) == 1 else "",
        "target_object_type": "safe_apply_action_set",
        "target_object_key": "|".join(
            f"{item['method']}:{item['object_id']}" for item in target_objects
        ),
        "target_objects": target_objects,
        "target_url": "",
        "lock_hash": lock_hash,
        "status": "locked" if all_targets_known else "missing",
        "evidence": [
            f"action_target:{item['method']}:{item['object_id']}"
            for item in target_objects
            if item.get("object_id")
        ],
    }


def _load_existing_update_readback(project_root: Path, readback_path: str) -> dict[str, Any]:
    path = Path(readback_path)
    if not path.is_absolute():
        path = project_root / path
    try:
        resolved = path.resolve()
        resolved.relative_to(project_root.resolve())
    except (OSError, ValueError):
        return {"ok": False, "reason": "readback_path_outside_project"}
    if not resolved.is_file():
        return {"ok": False, "reason": "readback_path_missing"}
    loaded = read_json(resolved, default=None)
    if not isinstance(loaded, dict):
        return {"ok": False, "reason": "readback_path_invalid"}
    return {"ok": True, "readback": loaded}


def _merge_existing_update_overlay(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = deepcopy(base)
        for key, value in overlay.items():
            merged[key] = (
                _merge_existing_update_overlay(base.get(key), value)
                if key in base
                else deepcopy(value)
            )
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        return deepcopy(overlay)
    return deepcopy(overlay)


def _payload_from_readback_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    for key in ("entry", "dashboard", "chart", "object"):
        value = envelope.get(key)
        if isinstance(value, dict):
            nested = value.get("entry")
            if isinstance(nested, dict):
                return {"entry": nested}
            return dict(value)
    response = envelope.get("response")
    if isinstance(response, dict):
        nested = response.get("entry")
        if isinstance(nested, dict):
            return {"entry": nested}
        for key in ("dashboard", "chart", "object"):
            value = response.get(key)
            if isinstance(value, dict):
                nested = value.get("entry")
                return {"entry": nested} if isinstance(nested, dict) else dict(value)
    for key in ("entries", "charts", "objects"):
        values = envelope.get(key)
        if isinstance(values, list) and len(values) == 1 and isinstance(values[0], dict):
            nested = values[0].get("entry")
            return {"entry": nested} if isinstance(nested, dict) else dict(values[0])
    return dict(envelope)


def _object_id_from_update_payload(payload: dict[str, Any], id_key: str) -> str:
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    return str(payload.get(id_key) or payload.get("entryId") or payload.get("id") or entry.get("entryId") or entry.get("id") or "")


def _revision_from_update_payload(payload: dict[str, Any]) -> str:
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    return str(payload.get("revId") or payload.get("revision") or entry.get("revId") or entry.get("revision") or "")


def _inject_revision(payload: dict[str, Any], revision: str) -> None:
    if not revision:
        return
    if isinstance(payload.get("entry"), dict):
        payload["entry"].setdefault("revId", revision)
    else:
        payload.setdefault("revId", revision)


def dl_execute_safe_apply(
    project_root: str = ".",
    plan_path: str = "",
    delivery_intent_text: str = "",
) -> dict[str, Any]:
    from datalens_dev_mcp.config import DataLensConfig

    started_at = monotonic()
    root = ensure_project_dirs(project_root)
    resolved_plan_path = Path(plan_path) if plan_path else root / "artifacts" / "safe_apply_plan.json"
    plan = read_json(resolved_plan_path, default={})
    stored_intent_text = _stored_plan_intent_text(plan)
    effective_intent_text = delivery_intent_text or stored_intent_text or "plan only"
    if delivery_intent_text:
        request_authorized = _request_authorizes_standard_write(
            delivery_intent_text,
            default_text="plan only",
        )
    elif isinstance(plan.get("request_intent"), dict):
        request_authorized = _stored_plan_request_authorized(plan)
    else:
        request_authorized = bool(plan.get("approved"))
    if request_authorized and not plan.get("approved"):
        plan = _authorize_safe_apply_plan_from_request(plan, effective_intent_text)
    config = DataLensConfig.from_env()
    target_lock = plan.get("target_lock") if isinstance(plan.get("target_lock"), dict) else {}
    target_known = (
        str(target_lock.get("status") or "") == "locked"
        if isinstance(plan.get("request_intent"), dict)
        else bool(plan.get("actions"))
    )
    delivery_decision = _delivery_intent_decision(
        effective_intent_text,
        target_known=target_known,
        approved=request_authorized,
        fresh_readback_available=False,
        revision_preservation_available=any(action.get("requires_fresh_read") for action in plan.get("actions", [])),
        saved_readback_available=False,
        proof_path=str(root / "artifacts" / "safe_apply_result.json"),
        target_lock=target_lock,
    )
    if delivery_decision.get("state") in {"read_only", "plan_only", "blocked"}:
        result = _nonexecuted_safe_apply_result(plan, delivery_decision)
        _attach_fast_path_execution_metrics(
            result=result,
            plan=plan,
            elapsed_seconds=monotonic() - started_at,
        )
        write_json(root / "artifacts" / "safe_apply_result.json", result)
        return result
    result = execute_safe_apply(plan, config=config)
    result["delivery_intent_decision"] = delivery_decision
    if delivery_decision.get("state") == "save_then_publish":
        result = _execute_publish_after_save(
            root=root,
            plan=plan,
            save_result=result,
            config=config,
            delivery_intent_text=effective_intent_text,
            plan_path=resolved_plan_path,
        )
    else:
        saved_readbacks = _persist_result_readbacks(
            root=root,
            plan=plan,
            result=result,
            branch="saved",
        ) if result.get("executed") else {"items": [], "errors": []}
        saved_items = list(saved_readbacks.get("items") or [])
        saved_paths = [str(item["path"]) for item in saved_items]
        saved_errors = [str(error) for error in (saved_readbacks.get("errors") or [])]
        publish_disabled = bool(
            result.get("executed")
            and delivery_decision.get("state") == "save_only"
            and delivery_decision.get("publish_expected")
            and "publish_enabled" in (delivery_decision.get("blocked_reasons") or [])
        )
        publish_blockers = ["publish_enabled"] if publish_disabled else []
        result["delivery_result"] = _delivery_result_summary(
            state=delivery_decision.get("state", ""),
            save_result=dict(result),
            publish_results=[],
            saved_readbacks=saved_items,
            published_readbacks=[],
            publish_blockers=publish_blockers,
            approval_reuse=False,
        )
        result["saved_readback_paths"] = saved_paths
        result["saved_readback_errors"] = saved_errors
        result["delivery_intent_decision"] = _decision_with_stage_evidence(
            result.get("delivery_intent_decision") if isinstance(result.get("delivery_intent_decision"), dict) else {},
            save_status=result.get("status", ""),
            publish_status="blocked" if publish_disabled else "not_requested",
            saved_paths=saved_paths,
            published_paths=[],
        )
        if publish_disabled:
            result["status"] = "saved_not_published"
            result["publish_blocked_reasons"] = ["publish_enabled"]
    _attach_fast_path_execution_metrics(
        result=result,
        plan=plan,
        elapsed_seconds=monotonic() - started_at,
    )
    write_json(root / "artifacts" / "safe_apply_result.json", result)
    return result


def _attach_fast_path_execution_metrics(
    *,
    result: dict[str, Any],
    plan: dict[str, Any],
    elapsed_seconds: float,
) -> None:
    configured = plan.get("workflow_metrics")
    if not isinstance(configured, dict) or configured.get("mode") != "date_range_selector_fast_path":
        return
    save_actions = result.get("actions") if isinstance(result.get("actions"), list) else []
    publish_actions = [
        action
        for item in result.get("publish_results") or []
        if isinstance(item, dict) and isinstance(item.get("result"), dict)
        for action in item["result"].get("actions") or []
        if isinstance(action, dict)
    ]
    executor_rpc_count = _safe_apply_result_rpc_count(save_actions) + _safe_apply_result_rpc_count(
        publish_actions
    )
    initial_read_count = int(configured.get("initial_exact_read_count") or 0)
    total_rpc_count = initial_read_count + executor_rpc_count
    max_rpc_count = int(configured.get("max_datalens_rpc_count") or 0)
    metrics = deepcopy(configured)
    metrics.update(
        {
            "executor_elapsed_seconds": round(max(0.0, elapsed_seconds), 3),
            "executor_rpc_count": executor_rpc_count,
            "observed_total_rpc_count": total_rpc_count,
            "budget_met": bool(max_rpc_count and total_rpc_count <= max_rpc_count),
            "snapshot_call_count": 0,
            "workbook_inventory_call_count": 0,
            "publish_group_count": len(result.get("publish_results") or []),
        }
    )
    result["workflow_metrics"] = metrics
    runtime_smoke = plan.get("runtime_smoke")
    if isinstance(runtime_smoke, dict) and runtime_smoke.get("required"):
        smoke = deepcopy(runtime_smoke)
        smoke["status"] = (
            "required"
            if result.get("status") == "completed" and result.get("executed")
            else "blocked_until_safe_apply_completes"
        )
        result["runtime_smoke"] = smoke
        result["maintenance_completion"] = {
            "complete": False,
            "status": (
                "runtime_smoke_required"
                if smoke["status"] == "required"
                else "safe_apply_incomplete"
            ),
        }


def _safe_apply_result_rpc_count(actions: list[dict[str, Any]]) -> int:
    count = 0
    for action in actions:
        artifacts = action.get("artifacts") if isinstance(action.get("artifacts"), dict) else {}
        if artifacts.get("pre_write"):
            count += 1
        if action.get("write_attempted"):
            count += 1
        if artifacts.get("readback"):
            count += 1
    return count


def _authorize_safe_apply_plan_from_request(plan: dict[str, Any], delivery_intent_text: str) -> dict[str, Any]:
    authorized = deepcopy(plan)
    raw_text = str(delivery_intent_text or "")
    normalized = normalize_user_request(raw_text or "implement")
    request_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    created_at = str(authorized.get("created_at") or "request_authorized")
    provenance = {
        "approved": True,
        "approval_source": "current_user_request",
        "approval_note": "",
        "approved_at": created_at,
        "request_digest": request_digest,
    }
    authorized["approved"] = True
    authorized["approval_provenance"] = provenance
    authorized["request_intent"] = {
        "normalized_intent": normalized.task_intent,
        "publish_override": normalized.publish_override,
        "request_sha256": request_digest,
        "request_text_present": bool(raw_text),
        "authorization_source": "current_user_request" if raw_text else "tool_call_intent",
        "authorizes_standard_mutation": True,
    }
    for action in authorized.get("actions") or []:
        if isinstance(action, dict):
            action["approval_provenance"] = dict(provenance)
    return authorized


def _stored_plan_request_authorized(plan: dict[str, Any]) -> bool:
    intent = plan.get("request_intent") if isinstance(plan.get("request_intent"), dict) else {}
    return bool(
        intent.get("authorizes_standard_mutation")
        and str(intent.get("normalized_intent") or "") in {"implement", "fix", "enhance", "redesign", "update"}
        and str(intent.get("publish_override") or "none") not in {"plan_only", "dry_run"}
    )


def _stored_plan_intent_text(plan: dict[str, Any]) -> str:
    intent = plan.get("request_intent") if isinstance(plan.get("request_intent"), dict) else {}
    normalized = str(intent.get("normalized_intent") or "").strip()
    if not normalized:
        return ""
    publish_override = str(intent.get("publish_override") or "none").strip()
    suffix = {
        "plan_only": " plan only",
        "dry_run": " dry run",
        "draft": " draft",
        "save_only": " save only",
        "no_publish": " no publish",
    }.get(publish_override, "")
    return normalized + suffix


def _nonexecuted_safe_apply_result(plan: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    state = str(decision.get("state") or "blocked")
    return {
        "executed": False,
        "status": state,
        "proof_level": "source_static",
        "proof_levels": ["source_static"],
        "completed_action_count": 0,
        "completed_action_indices": [],
        "failed_action_index": None,
        "failed_action_indices": [],
        "skipped_action_indices": list(range(len(plan.get("actions") or []))),
        "blocked_reasons": list(decision.get("blocked_reasons") or []),
        "actions": [],
        "publish_allowed": False,
        "delivery_intent_decision": decision,
        "delivery_result": {
            "state": state,
            "save": {"executed": False, "status": "not_started"},
            "publish": {"executed": False, "status": "not_started"},
        },
    }


def _execute_publish_after_save(
    *,
    root: Path,
    plan: dict[str, Any],
    save_result: dict[str, Any],
    config: Any,
    delivery_intent_text: str,
    plan_path: Path,
) -> dict[str, Any]:
    saved_readbacks = _persist_result_readbacks(
        root=root,
        plan=plan,
        result=save_result,
        branch="saved",
    )
    publish_blockers = list(saved_readbacks.get("errors") or [])
    publish_results: list[dict[str, Any]] = []
    published_readbacks: list[dict[str, Any]] = []
    approval_reuse = bool(plan.get("approved"))
    if save_result.get("status") != "completed" or not save_result.get("executed"):
        publish_blockers.append("save execution did not complete; publish was not attempted")
    if not saved_readbacks.get("items"):
        publish_blockers.append("saved readback artifact is required before publish")

    prepared_plans: list[dict[str, Any]] = []
    for item in saved_readbacks.get("items") or []:
        if publish_blockers:
            break
        candidate = create_publish_safe_apply_plan(
            project_root=str(root),
            target=item["target"],
            object_type=item["object_type"],
            object_id=item.get("object_id", ""),
            saved_readback_path=item["path"],
            approved=bool(plan.get("approved")),
            readback_mode=item.get("readback_mode", "minimal"),
            user_request_text=delivery_intent_text,
        )
        _inherit_publish_plan_context(
            publish_plan=candidate,
            source_plan=plan,
            source_plan_path=plan_path,
            approval_reuse=approval_reuse,
        )
        if not candidate.get("ok"):
            publish_blockers.append(
                f"publish plan blocked for {item.get('object_id') or item['path']}: "
                f"{(candidate.get('error') or {}).get('message') or candidate.get('status')}"
            )
            publish_results.append({"plan": candidate, "result": None})
            break
        prepared_plans.append(candidate)

    grouped_publish_plan: dict[str, Any] | None = None
    if prepared_plans and not publish_blockers:
        grouped_actions = [
            deepcopy(action)
            for prepared in prepared_plans
            for action in prepared.get("actions") or []
            if isinstance(action, dict)
        ]
        grouped_publish_plan = create_safe_apply_plan(
            project_root=str(root),
            actions=grouped_actions,
            approved=bool(plan.get("approved")),
            user_request_text=delivery_intent_text,
        )
        grouped_publish_plan["ok"] = True
        grouped_publish_plan["status"] = "grouped_publish_plan_created"
        grouped_publish_plan["publish_sources"] = [
            deepcopy(source)
            for prepared in prepared_plans
            for source in prepared.get("publish_sources") or []
            if isinstance(source, dict)
        ]
        grouped_publish_plan["object_count"] = len(grouped_actions)
        grouped_publish_plan["transaction_policy"]["publish_preflight_scope"] = "all_saved_objects"
        _inherit_publish_plan_context(
            publish_plan=grouped_publish_plan,
            source_plan=plan,
            source_plan_path=plan_path,
            approval_reuse=approval_reuse,
        )
        grouped_preflight = validate_safe_apply_plan_exhaustive(grouped_publish_plan)
        grouped_publish_plan["grouped_preflight"] = grouped_preflight
        write_json(root / "artifacts" / "publish_safe_apply_plan.json", grouped_publish_plan)
        publish_results.append({"plan": grouped_publish_plan, "result": None})
        if not grouped_preflight.get("ok"):
            publish_blockers.extend(
                f"grouped publish preflight: {issue}"
                for issue in grouped_preflight.get("issues") or ["validation failed"]
            )

    if grouped_publish_plan is not None and not publish_blockers:
        publish_result = execute_safe_apply(grouped_publish_plan, config=config)
        publish_result["delivery_intent_decision"] = _delivery_intent_decision(
            delivery_intent_text,
            default_text="implement",
            target_known=True,
            approved=bool(plan.get("approved")),
            fresh_readback_available=True,
            revision_preservation_available=True,
            saved_readback_available=True,
            saved_readback_fresh=bool(publish_result.get("executed")),
            proof_path=str(root / "artifacts" / "safe_apply_result.json"),
            target_lock=plan.get("target_lock") if isinstance(plan.get("target_lock"), dict) else None,
        )
        publish_result["approval_reuse_for_publish"] = approval_reuse
        publish_results[0]["result"] = publish_result
        published = _persist_result_readbacks(
            root=root,
            plan=grouped_publish_plan,
            result=publish_result,
            branch="published",
        )
        published_readbacks.extend(published.get("items") or [])
        publish_blockers.extend(published.get("errors") or [])
        if publish_result.get("status") != "completed" or not publish_result.get("executed"):
            publish_blockers.append("publish execution did not complete")

    aggregate = dict(save_result)
    aggregate["delivery_result"] = _delivery_result_summary(
        state="save_then_publish",
        save_result=save_result,
        publish_results=publish_results,
        saved_readbacks=saved_readbacks.get("items") or [],
        published_readbacks=published_readbacks,
        publish_blockers=publish_blockers,
        approval_reuse=approval_reuse,
    )
    aggregate["approval_reuse_for_publish"] = approval_reuse
    aggregate["publish_results"] = publish_results
    aggregate["saved_readback_paths"] = [item["path"] for item in saved_readbacks.get("items") or []]
    aggregate["published_readback_paths"] = [item["path"] for item in published_readbacks]
    aggregate["publish_blocked_reasons"] = publish_blockers
    aggregate["proof_levels"] = _merge_proof_levels(save_result, *[item["result"] for item in publish_results if item.get("result")])
    publish_status = _publish_stage_status(publish_results, publish_blockers)
    aggregate["save_stage_status"] = str(save_result.get("status") or "")
    aggregate["publish_stage_status"] = publish_status
    aggregate["delivery_intent_decision"] = _decision_with_stage_evidence(
        aggregate.get("delivery_intent_decision") if isinstance(aggregate.get("delivery_intent_decision"), dict) else {},
        save_status=aggregate["save_stage_status"],
        publish_status=publish_status,
        saved_paths=aggregate["saved_readback_paths"],
        published_paths=aggregate["published_readback_paths"],
    )
    if publish_blockers:
        aggregate["executed"] = False
        aggregate["status"] = "partial" if save_result.get("executed") else save_result.get("status", "blocked")
    elif publish_results:
        aggregate["executed"] = all(bool(item.get("result", {}).get("executed")) for item in publish_results)
        aggregate["status"] = "completed" if aggregate["executed"] else "partial"
    return aggregate


def _inherit_publish_plan_context(
    *,
    publish_plan: dict[str, Any],
    source_plan: dict[str, Any],
    source_plan_path: Path,
    approval_reuse: bool,
) -> None:
    inherited_target_lock = (
        source_plan.get("target_lock")
        if isinstance(source_plan.get("target_lock"), dict)
        else {}
    )
    inherited_target_lock_hash = str(inherited_target_lock.get("lock_hash") or "").strip()
    if inherited_target_lock_hash:
        publish_plan["target_lock"] = deepcopy(inherited_target_lock)
        for publish_action in publish_plan.get("actions") or []:
            if isinstance(publish_action, dict):
                publish_action["target_lock_hash"] = inherited_target_lock_hash
    if isinstance(source_plan.get("request_intent"), dict):
        inherited_intent = deepcopy(source_plan["request_intent"])
        publish_plan["request_intent"] = inherited_intent
        request_digest = str(inherited_intent.get("request_sha256") or "")
        if isinstance(publish_plan.get("approval_provenance"), dict):
            publish_plan["approval_provenance"]["request_digest"] = request_digest
        for publish_action in publish_plan.get("actions") or []:
            if isinstance(publish_action, dict) and isinstance(
                publish_action.get("approval_provenance"),
                dict,
            ):
                publish_action["approval_provenance"]["request_digest"] = request_digest
    publish_plan["approval_reuse_for_publish"] = approval_reuse
    publish_plan["approval_reuse"] = {
        "reused_from_plan_path": str(source_plan_path),
        "source_approval": (source_plan.get("approval_provenance") or {}),
    }
    for action in publish_plan.get("actions") or []:
        if isinstance(action, dict):
            action["approval_reuse_for_publish"] = approval_reuse
            if isinstance(action.get("approval_provenance"), dict):
                action["approval_provenance"]["reused_for_publish"] = approval_reuse
                action["approval_provenance"]["source_plan_path"] = str(source_plan_path)


def _persist_result_readbacks(
    *,
    root: Path,
    plan: dict[str, Any],
    result: dict[str, Any],
    branch: str,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    result_actions = result.get("actions") if isinstance(result.get("actions"), list) else []
    multiple = len(result_actions) > 1
    for action_result in result_actions:
        if not isinstance(action_result, dict) or not action_result.get("executed"):
            continue
        index = int(action_result.get("index") or 0)
        verification = (
            action_result.get("readback_verification")
            if isinstance(action_result.get("readback_verification"), dict)
            else {}
        )
        if verification.get("verified") is not True:
            errors.append(f"action {index} readback lacks successful post-write verification")
            continue
        plan_action = actions[index] if 0 <= index < len(actions) and isinstance(actions[index], dict) else {}
        stage = load_safe_apply_stage_value(action_result, "readback", project_root=root)
        if not stage.get("ok"):
            errors.append(str((stage.get("error") or {}).get("message") or "readback stage is missing"))
            continue
        value = stage.get("value") if isinstance(stage.get("value"), dict) else {}
        if not value:
            errors.append(f"action {index} readback is empty")
            continue
        payload = dict(value)
        payload["branch"] = branch
        object_type = _publish_object_type_for_action(plan_action, action_result)
        target = _publish_target_for_object_type(object_type)
        object_id = _object_id_from_readback(payload) or str(action_result.get("object_id") or "")
        artifact_target = _artifact_target_name(target, object_id=object_id, index=index, multiple=multiple)
        path = readback_artifact_path(root, artifact_target, branch)
        write_json(path, payload)
        items.append(
            {
                "action_index": index,
                "path": str(path),
                "target": artifact_target,
                "object_type": object_type,
                "object_id": object_id,
                "branch": branch,
                "readback_mode": action_result.get("readback_mode") or plan_action.get("readback_mode") or "minimal",
            }
        )
    return {"items": items, "errors": errors}


def _publish_object_type_for_action(plan_action: dict[str, Any], action_result: dict[str, Any]) -> str:
    method = str(plan_action.get("method") or action_result.get("method") or "")
    if "Dashboard" in method:
        return "dashboard"
    if "WizardChart" in method:
        return "wizard_chart"
    return "editor_chart"


def _publish_target_for_object_type(object_type: str) -> str:
    return "dashboard" if object_type == "dashboard" else "chart"


def _artifact_target_name(target: str, *, object_id: str, index: int, multiple: bool) -> str:
    if not multiple:
        return target
    safe_id = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(object_id or "")).strip("_")
    return f"{target}_{safe_id or index}"


def _object_id_from_readback(value: dict[str, Any]) -> str:
    for key in ("entry", "dashboard", "chart", "object"):
        candidate = value.get(key)
        if isinstance(candidate, dict):
            nested = candidate.get("entry")
            if isinstance(nested, dict):
                candidate = nested
            object_id = _object_id_from_candidate(candidate)
            if object_id:
                return object_id
    for key in ("entries", "charts"):
        entries = value.get(key)
        if isinstance(entries, list) and len(entries) == 1 and isinstance(entries[0], dict):
            object_id = _object_id_from_candidate(entries[0])
            if object_id:
                return object_id
    return _object_id_from_candidate(value)


def _object_id_from_candidate(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("entryId")
        or candidate.get("id")
        or candidate.get("dashboardId")
        or candidate.get("chartId")
        or ""
    ).strip()


def _merge_proof_levels(*results: dict[str, Any]) -> list[str]:
    levels: list[str] = ["source_static"]
    for result in results:
        for level in result.get("proof_levels") or []:
            if level not in levels:
                levels.append(str(level))
    return levels


def _delivery_result_summary(
    *,
    state: str,
    save_result: dict[str, Any],
    publish_results: list[dict[str, Any]],
    saved_readbacks: list[dict[str, Any]],
    published_readbacks: list[dict[str, Any]],
    publish_blockers: list[str],
    approval_reuse: bool,
) -> dict[str, Any]:
    return {
        "state": state,
        "save": _delivery_stage_snapshot(save_result),
        "publish": [_delivery_stage_snapshot(item.get("result") or {}) for item in publish_results],
        "publish_plans": [_delivery_plan_snapshot(item.get("plan") or {}) for item in publish_results],
        "saved": {
            "passed": bool(save_result.get("executed") and saved_readbacks),
            "status": str(save_result.get("status") or ""),
            "readback_paths": [item["path"] for item in saved_readbacks],
        },
        "published": {
            "passed": bool(publish_results and not publish_blockers and published_readbacks),
            "status": _publish_stage_status(publish_results, publish_blockers),
            "readback_paths": [item["path"] for item in published_readbacks],
        },
        "saved_readbacks": saved_readbacks,
        "published_readbacks": published_readbacks,
        "publish_blocked_reasons": publish_blockers,
        "approval_reuse_for_publish": approval_reuse,
    }


def _delivery_stage_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ok",
        "executed",
        "status",
        "returncode",
        "proof_level",
        "proof_levels",
        "completed_action_count",
        "completed_action_indices",
        "failed_action_index",
        "failed_action_indices",
        "skipped_action_indices",
        "blocked_reasons",
        "publish_blocked_reasons",
        "saved_readback_paths",
        "published_readback_paths",
        "saved_readback_errors",
        "published_readback_errors",
        "save_stage_status",
        "publish_stage_status",
        "summary",
    )
    return {key: deepcopy(result[key]) for key in keys if key in result}


def _delivery_plan_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
    snapshot = {
        key: deepcopy(plan[key])
        for key in ("ok", "status", "safe_apply_id", "project_root", "target_lock", "error")
        if key in plan
    }
    snapshot["action_count"] = len(actions)
    snapshot["methods"] = [str(action.get("method") or "") for action in actions if isinstance(action, dict)]
    return snapshot


def _publish_stage_status(publish_results: list[dict[str, Any]], publish_blockers: list[str]) -> str:
    if publish_blockers:
        return "blocked"
    if not publish_results:
        return "not_started"
    if all(bool(item.get("result", {}).get("executed")) for item in publish_results):
        return "completed"
    return "partial"


def _decision_with_stage_evidence(
    decision: dict[str, Any],
    *,
    save_status: str,
    publish_status: str,
    saved_paths: list[str],
    published_paths: list[str],
) -> dict[str, Any]:
    updated = dict(decision)
    updated["save_stage_status"] = save_status
    updated["publish_stage_status"] = publish_status
    updated["saved_readback_path"] = saved_paths[0] if saved_paths else ""
    updated["published_readback_path"] = published_paths[0] if published_paths else ""
    return updated


def dl_create_publish_from_saved_plan(
    project_root: str = ".",
    target: str = "dashboard",
    object_type: str = "dashboard",
    object_id: str = "",
    object_ids: list[str] | None = None,
    saved_readback_path: str = "",
    readback_mode: str = "minimal",
    delivery_intent_text: str = "",
    target_workbook_id: str = "",
    target_dashboard_id: str = "",
    target_chart_id: str = "",
    target_url: str = "",
) -> dict[str, Any]:
    effective_authorized = _request_authorizes_standard_write(
        delivery_intent_text,
        default_text="implement",
    )
    plan = create_publish_safe_apply_plan(
        project_root=project_root,
        target=target,
        object_type=object_type,
        object_id=object_id,
        object_ids=object_ids,
        saved_readback_path=saved_readback_path,
        approved=effective_authorized,
        readback_mode=readback_mode,
        user_request_text=delivery_intent_text,
    )
    plan["delivery_intent_decision"] = _delivery_intent_decision(
        delivery_intent_text,
        default_text="implement",
        target_known=_looks_like_known_target(object_id, object_ids or [], saved_readback_path),
        approved=effective_authorized,
        fresh_readback_available=True,
        revision_preservation_available=True,
        saved_readback_available=bool(saved_readback_path),
        saved_readback_fresh=bool(plan.get("ok")),
        proof_path=str(Path(project_root) / "artifacts" / "publish_safe_apply_plan.json"),
    )
    if plan.get("ok"):
        root = ensure_project_dirs(project_root)
        existing_target_lock = read_json(root / "artifacts" / "delivery" / "target_lock.json", default={})
        plan_target_lock = plan.get("target_lock") if isinstance(plan.get("target_lock"), dict) else {}
        target_objects = (
            plan_target_lock.get("target_objects")
            if isinstance(plan_target_lock.get("target_objects"), list)
            else []
        )
        normalized_object_type = normalize_publish_object_type(object_type)
        resolved_object_id = str(object_id or "").strip()
        target_lock = create_target_lock(
            delivery_intent_text,
            target_source="user_url" if target_url else str(existing_target_lock.get("target_source") or "manual"),
            target_workbook_id=target_workbook_id or str(existing_target_lock.get("target_workbook_id") or ""),
            target_dashboard_id=(
                target_dashboard_id
                or str(existing_target_lock.get("target_dashboard_id") or "")
                or (resolved_object_id if normalized_object_type == "dashboard" else "")
            ),
            target_chart_id=(
                target_chart_id
                or str(existing_target_lock.get("target_chart_id") or "")
                or (resolved_object_id if normalized_object_type != "dashboard" else "")
            ),
            target_url=target_url or str(existing_target_lock.get("target_url") or ""),
            target_object_type="safe_apply_action_set",
            target_object_key="|".join(
                f"{item.get('method', '')}:{item.get('object_id', '')}"
                for item in target_objects
                if isinstance(item, dict)
            ),
            target_objects=target_objects,
        )
        plan["target_lock"] = target_lock.to_dict()
        for action in plan.get("actions") or []:
            if isinstance(action, dict):
                action["target_lock_hash"] = target_lock.lock_hash
        plan["delivery_intent_decision"] = _delivery_intent_decision(
            delivery_intent_text,
            default_text="implement",
            target_known=True,
            approved=effective_authorized,
            fresh_readback_available=True,
            revision_preservation_available=True,
            saved_readback_available=True,
            saved_readback_fresh=True,
            proof_path=str(root / "artifacts" / "publish_safe_apply_plan.json"),
            target_lock=target_lock.to_dict(),
        )
        write_json(root / "artifacts" / "publish_safe_apply_plan.json", plan)
        write_json(root / "artifacts" / "delivery" / "target_lock.json", target_lock.to_dict())
    return plan


def dl_readback_and_report(
    project_root: str = ".",
    target: str = "dashboard",
    dashboard_id: str = "",
    chart_ids: list[str] | None = None,
    dataset_id: str = "",
    connection_id: str = "",
    branch: str = "saved",
    readback_mode: str = "minimal",
    delivery_intent_text: str = "",
    target_workbook_id: str = "",
    target_url: str = "",
    client: Any | None = None,
) -> dict[str, Any]:
    root = ensure_project_dirs(project_root)
    normalized_readback_mode = normalize_readback_mode(readback_mode)
    normalized_branch = str(branch or "").strip().lower()
    if normalized_branch not in {"saved", "published"}:
        return {"ok": False, "error": {"category": "invalid_branch", "message": "branch must be saved or published"}}
    validation = read_json(root / "artifacts" / "validation_report.json", default={"status": "not_run"})
    safe_result = read_json(root / "artifacts" / "safe_apply_result.json", default={"executed": False, "blocked_reasons": []})
    existing_target_lock = read_json(root / "artifacts" / "delivery" / "target_lock.json", default={})
    target_lock = create_target_lock(
        delivery_intent_text,
        target_source="user_url" if target_url else str(existing_target_lock.get("target_source") or "manual"),
        target_workbook_id=target_workbook_id or str(existing_target_lock.get("target_workbook_id") or ""),
        target_dashboard_id=dashboard_id or str(existing_target_lock.get("target_dashboard_id") or ""),
        target_chart_id=(chart_ids or [""])[0] if chart_ids else str(existing_target_lock.get("target_chart_id") or ""),
        target_url=target_url or str(existing_target_lock.get("target_url") or ""),
    )
    snapshot: dict[str, Any] | None = None
    if dashboard_id and normalized_readback_mode in {"full", "debug"}:
        from datalens_dev_mcp.mcp.tools.snapshot import dl_snapshot_dashboard

        snapshot_client = _exclusive_snapshot_client(client)
        snapshot = dl_snapshot_dashboard(
            project_root=project_root,
            dashboard_id=dashboard_id,
            workbook_id=target_workbook_id,
            snapshot_branch=normalized_branch,
            include_dormant_summary=True,
            artifact_retention="latest_only",
            client=snapshot_client,
        )
        readback = _readback_from_snapshot(
            snapshot=snapshot,
            target=target,
            dashboard_id=dashboard_id,
            chart_ids=chart_ids or [],
            dataset_id=dataset_id,
            connection_id=connection_id,
            branch=normalized_branch,
            readback_mode=normalized_readback_mode,
            client=snapshot_client,
        )
    else:
        readback = _live_readback(
            target=target,
            dashboard_id=dashboard_id,
            chart_ids=chart_ids or [],
            dataset_id=dataset_id,
            connection_id=connection_id,
            branch=normalized_branch,
            readback_mode=normalized_readback_mode,
            client=client,
        )
    artifact_path = readback_artifact_path(root, target, normalized_branch)
    readback["artifact_path"] = str(artifact_path)
    readback.setdefault(
        "proof_level",
        proof_level_for_readback_branch(normalized_branch, live_readback=bool(readback.get("live_readback"))),
    )
    report = build_deployment_report(
        safe_apply_result=safe_result,
        validation=validation,
        readback_mode=normalized_readback_mode,
        readback_branch=normalized_branch,
    )
    relation_summary = _relation_report_summary(read_json(root / "artifacts" / "dashboard_object_relations.json", default={}))
    readback["object_relations"] = relation_summary
    readback["target_lock"] = target_lock.to_dict()
    readback["target_lock_validation"] = validate_readback_target_lock(target_lock, readback)
    report["object_relations"] = relation_summary
    report["target_lock"] = target_lock.to_dict()
    report["target_lock_validation"] = readback["target_lock_validation"]
    report["readback_branch"] = normalized_branch
    report["saved_readback_path"] = str(readback_artifact_path(root, target, "saved"))
    report["published_readback_path"] = str(readback_artifact_path(root, target, "published"))
    report["branch_artifact_path"] = str(artifact_path)
    delivery_decision = _delivery_intent_decision(
        delivery_intent_text,
        default_text="implement" if normalized_branch == "published" else "save only",
        target_known=_looks_like_known_target(dashboard_id, chart_ids or [], dataset_id, connection_id),
        approved=True,
        fresh_readback_available=normalized_readback_mode != "none",
        revision_preservation_available=True,
        saved_readback_available=normalized_branch == "saved"
        or readback_artifact_path(root, target, "saved").is_file(),
        saved_readback_fresh=normalized_branch == "saved"
        or readback_artifact_path(root, target, "saved").is_file(),
        proof_path=str(artifact_path),
        target_lock=target_lock.to_dict(),
    )
    readback["delivery_intent_decision"] = delivery_decision
    report["delivery_intent_decision"] = delivery_decision
    canonical_readback = sanitize_response(readback)
    deployment_report_path = root / "artifacts" / "deployment_report.json"
    write_json(artifact_path, canonical_readback)
    write_json(deployment_report_path, report)
    inline_readback = _project_readback_inline(
        canonical_readback,
        project_root=project_root,
        artifact_path=artifact_path,
    )
    inline_report = dict(report)
    inline_report.pop("target_lock", None)
    inline_report.pop("target_lock_validation", None)
    inline_report.pop("delivery_intent_decision", None)
    inline_report["canonical_artifact"] = {
        "path": str(deployment_report_path),
        **serialized_metadata(report),
    }
    return {"readback": inline_readback, "deployment_report": inline_report}


def _write_dashboard_relations(
    *,
    root: Path,
    brief: dict[str, Any],
    widget_id: str,
    selector_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    relations = build_default_dashboard_relations(
        brief=brief,
        widget_id=widget_id,
        selector_contract=selector_contract,
    )
    write_json(root / "artifacts" / "dashboard_object_relations.json", relations)
    return relations


def _relation_report_summary(relations: dict[str, Any]) -> dict[str, Any]:
    if not relations:
        return {"available": False, "selector_count": 0, "chart_count": 0, "relation_targets": []}
    targets: list[str] = []
    for selector in relations.get("selectors") or []:
        for target in selector.get("targets") or []:
            target_id = target.get("target_id")
            if target_id:
                targets.append(str(target_id))
    return {
        "available": True,
        "selector_count": len(relations.get("selectors") or []),
        "chart_count": len(relations.get("charts") or []),
        "relation_targets": sorted(set(targets)),
    }


def _brief_from_governance_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    passport = bundle["dashboard_requirements_passport"]
    contracts = bundle.get("data_contracts") or []
    fields = []
    for contract in contracts:
        for field in contract.get("fields") or []:
            name = field.get("name")
            if name and name not in fields:
                fields.append(name)
    decisions = []
    for decision in bundle.get("chart_decisions") or []:
        family = decision.get("selected_family") or decision.get("family")
        record = decide_chart(
            chart_id=str(decision.get("decision_id") or decision.get("metric_id") or "CD-001"),
            business_question=str(passport.get("objective", "")),
            audience=list(passport.get("audience") or []),
            data_shape={"fields": fields},
            requested_family=str(family or ""),
            source_evidence_refs=["governance_bundle"],
        )
        decisions.append(
            {
                "decision_id": decision.get("decision_id"),
                "metric_id": decision.get("metric_id"),
                "widget_id": decision.get("metric_id") or "widget_001",
                "family": record.selected_family,
                "route": record.selected_route,
                "entry_type": decision.get("editor_entry_type"),
                "status": decision.get("status"),
                "governance_decision": {
                    "chart_family_decided_by": "datalens-dataviz-governance",
                    "approved": decision.get("status") in {"ready", "draft_with_assumptions"},
                    "decision_id": decision.get("decision_id"),
                    "selected_family": record.selected_family,
                    "approved_route": record.selected_route,
                },
                "chart_decision_record": record.to_dict(),
                "renderer_visual_spec": record.renderer_visual_spec.to_dict(),
            }
        )
    return {
        "schema_version": "2026-06-04.dashboard_brief.local.v1",
        "dashboard_name": passport.get("dashboard_name", "Local Dashboard"),
        "audience": passport.get("audience") or [],
        "decision_action": passport.get("decision_action", "missing"),
        "requirements": [{"requirement_id": "REQ-001", "text": passport.get("objective", "")}],
        "data_contract": {"contract_id": "DATA-001", "fields": fields, "source_status": "local_mcp_intake"},
        "chart_decisions": decisions or build_governance_brief(requirements_text=passport.get("objective", "")).get("chart_decisions", []),
    }


def _live_readback(
    *,
    target: str,
    dashboard_id: str,
    chart_ids: list[str],
    dataset_id: str,
    connection_id: str,
    branch: str,
    readback_mode: str,
    client: Any | None,
) -> dict[str, Any]:
    normalized_mode = normalize_readback_mode(readback_mode)
    if normalized_mode == "none":
        readback = build_readback_summary(target=target, mode="none", skipped_reason="readback_mode none")
        readback["live_readback"] = False
        readback["proof_level"] = "source_static"
        return readback
    normalized_target = str(target or "").strip().lower().replace("-", "_")
    if not dashboard_id and not chart_ids and not dataset_id and not connection_id:
        readback = build_readback_summary(target=target, mode=normalized_mode)
        readback["live_readback"] = False
        readback["proof_level"] = "source_static"
        return readback
    if client is None:
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        client = DataLensApiClient(DataLensConfig.from_env())
    dashboard = (
        _readback_rpc(client, "getDashboard", {"dashboardId": dashboard_id, "branch": branch})
        if dashboard_id
        else None
    )
    selected_chart_ids = chart_ids if normalized_mode in {"full", "debug"} else chart_ids[:1]
    charts = [
        _readback_rpc(client, "getEditorChart", {"chartId": chart_id, "branch": branch})
        for chart_id in selected_chart_ids
    ]
    dataset = None
    connection = None
    if normalized_target == "dataset" and dataset_id:
        dataset = _readback_rpc(client, "getDataset", {"datasetId": dataset_id})
    if normalized_target in {"connection", "connector"} and connection_id:
        connection = _readback_rpc(client, "getConnection", {"connectionId": connection_id})
    identity_rows = [
        _readback_identity_row(value, fallback_id=fallback_id)
        for value, fallback_id in [
            (dashboard, dashboard_id),
            *[(chart, chart_id) for chart, chart_id in zip(charts, selected_chart_ids)],
            (dataset, dataset_id),
            (connection, connection_id),
        ]
        if isinstance(value, dict) and value
    ]
    return {
        "target": target,
        "read_at": build_readback_summary(target=target, mode=normalized_mode)["read_at"],
        "live_readback": True,
        "mode": normalized_mode,
        "branch": branch,
        "proof_level": proof_level_for_readback_branch(branch),
        "dashboard": dashboard,
        "charts": charts,
        "dataset": dataset,
        "connection": connection,
        "object_ids": [row["object_id"] for row in identity_rows if row["object_id"]],
        "object_revisions": {
            row["object_id"]: row["revision_id"]
            for row in identity_rows
            if row["object_id"] and row["revision_id"]
        },
        "counts_by_object_type": {
            "dashboard": 1 if dashboard else 0,
            "chart": len(charts),
            "dataset": 1 if dataset else 0,
            "connection": 1 if connection else 0,
        },
        "omitted_chart_ids": chart_ids[len(selected_chart_ids):],
    }


def _readback_rpc(client: Any, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    reader = getattr(client, "rpc_exclusive_read", None)
    if callable(reader):
        return reader(method, payload)
    readonly_reader = getattr(client, "rpc_readonly", None)
    if callable(readonly_reader):
        return readonly_reader(method, payload)
    return client.rpc(method, payload)


def _exclusive_snapshot_client(client: Any | None) -> Any:
    active_client = client
    if active_client is None:
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.config import DataLensConfig

        active_client = DataLensApiClient(DataLensConfig.from_env())
    reader = getattr(active_client, "rpc_exclusive_read", None)
    if not callable(reader):
        return active_client

    class ExclusiveSnapshotClient:
        config = SimpleNamespace(max_read_concurrency=1)

        def rpc_readonly(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
            return reader(method, payload)

    return ExclusiveSnapshotClient()


def _readback_from_snapshot(
    *,
    snapshot: dict[str, Any],
    target: str,
    dashboard_id: str,
    chart_ids: list[str],
    dataset_id: str,
    connection_id: str,
    branch: str,
    readback_mode: str,
    client: Any,
) -> dict[str, Any]:
    manifest_metadata = snapshot.get("manifest") if isinstance(snapshot.get("manifest"), dict) else {}
    manifest_path = Path(str(manifest_metadata.get("path") or ""))
    manifest = read_json(manifest_path, default={}) if manifest_path.is_file() else {}
    refs = manifest.get("object_refs") if isinstance(manifest.get("object_refs"), list) else []

    def payload_for(object_type: str, object_id: str, *, expected_branch: str = "") -> dict[str, Any] | None:
        if not object_id:
            return None
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("object_id") or "") != object_id:
                continue
            ref_type = str(ref.get("object_type") or "")
            if object_type == "chart":
                if not str(ref.get("method") or "").startswith("get") or "Chart" not in str(ref.get("method") or ""):
                    continue
            elif ref_type != object_type:
                continue
            if expected_branch and str(ref.get("branch") or "") != expected_branch:
                continue
            path = Path(str(ref.get("path") or ""))
            value = read_json(path, default={}) if path.is_file() else {}
            if isinstance(value, dict) and value:
                return value
        return None

    dashboard = payload_for("dashboard", dashboard_id, expected_branch=branch)
    chart_pairs = [
        (chart_id, payload)
        for chart_id in chart_ids
        if (payload := payload_for("chart", chart_id, expected_branch=branch)) is not None
    ]
    found_chart_ids = {chart_id for chart_id, _ in chart_pairs}
    chart_pairs.extend(
        (
            chart_id,
            _readback_rpc(
                client,
                "getEditorChart",
                {"chartId": chart_id, "branch": branch},
            ),
        )
        for chart_id in chart_ids
        if chart_id not in found_chart_ids
    )
    charts = [payload for _, payload in chart_pairs]
    dataset = payload_for("dataset", dataset_id) if dataset_id else None
    connection = payload_for("connection", connection_id) if connection_id else None
    if dataset_id and dataset is None:
        dataset = _readback_rpc(client, "getDataset", {"datasetId": dataset_id})
    if connection_id and connection is None:
        connection = _readback_rpc(client, "getConnection", {"connectionId": connection_id})
    identity_rows = [
        _readback_identity_row(value, fallback_id=fallback_id)
        for value, fallback_id in [
            (dashboard, dashboard_id),
            *[(chart, chart_id) for chart_id, chart in chart_pairs],
            (dataset, dataset_id),
            (connection, connection_id),
        ]
        if isinstance(value, dict) and value
    ]
    requested_chart_ids = set(chart_ids)
    found_chart_ids = {row["object_id"] for row in identity_rows if row["object_id"] in requested_chart_ids}
    errors = list(snapshot.get("errors") or [])
    for missing_chart_id in [item for item in chart_ids if item not in found_chart_ids]:
        errors.append(
            {
                "method": "snapshot_artifact_read",
                "object_id": missing_chart_id,
                "message": "requested chart is absent from the verified dashboard snapshot",
            }
        )
    return {
        "target": target,
        "read_at": build_readback_summary(target=target, mode=readback_mode)["read_at"],
        "live_readback": bool(dashboard),
        "mode": readback_mode,
        "branch": branch,
        "proof_level": proof_level_for_readback_branch(branch, live_readback=bool(dashboard)),
        "dashboard": dashboard,
        "charts": charts,
        "dataset": dataset,
        "connection": connection,
        "object_ids": [row["object_id"] for row in identity_rows if row["object_id"]],
        "object_revisions": {
            row["object_id"]: row["revision_id"]
            for row in identity_rows
            if row["object_id"] and row["revision_id"]
        },
        "counts_by_object_type": snapshot.get("counts_by_object_type") or {},
        "omitted_chart_ids": [item for item in chart_ids if item not in found_chart_ids],
        "snapshot_manifest": manifest_metadata,
        "compact_graph": snapshot.get("compact_graph"),
        "active_graph_edges": snapshot.get("active_graph_edges", []),
        "branch_summary": snapshot.get("branch_summary", {}),
        "branch_comparison": snapshot.get("branch_comparison", {}),
        "errors": errors,
        "omissions": snapshot.get("omissions", []),
        "object_artifact_count": snapshot.get("object_artifact_count", 0),
        "snapshot_reused": bool(snapshot.get("snapshot_reused")),
        "snapshot_rpc": {
            "source_probe_rpc_count": int(snapshot.get("source_probe_rpc_count") or 0),
            "hydration_rpc_count": int(snapshot.get("hydration_rpc_count") or 0),
        },
    }


def _project_readback_inline(
    readback: dict[str, Any],
    *,
    project_root: str,
    artifact_path: Path,
) -> dict[str, Any]:
    """Keep full sanitized entries in the canonical artifact and return compact MCP summaries."""

    projected = dict(readback)
    dashboard = readback.get("dashboard")
    if isinstance(dashboard, dict):
        projected["dashboard"] = project_dashboard_response(
            dashboard,
            response_mode="summary",
            project_root=project_root,
        )
    charts = readback.get("charts")
    if isinstance(charts, list):
        projected["charts"] = [
            _project_chart_readback(chart, "summary")
            for chart in charts
            if isinstance(chart, dict)
        ]
    dataset = readback.get("dataset")
    if isinstance(dataset, dict):
        projected["dataset"] = project_dataset_response(
            dataset,
            response_mode="summary",
            project_root=project_root,
        )
    connection = readback.get("connection")
    if isinstance(connection, dict):
        projected["connection"] = project_connection_response(
            connection,
            response_mode="summary",
            project_root=project_root,
        )
    metadata = serialized_metadata(readback)
    projected["canonical_artifact"] = {
        "path": str(artifact_path),
        **metadata,
    }
    return projected


def _project_chart_readback(response: dict[str, Any], response_mode: str) -> dict[str, Any]:
    from datalens_dev_mcp.mcp.response_projection import project_editor_chart_response, project_wizard_chart_response

    entry = response.get("entry") if isinstance(response.get("entry"), dict) else response
    scope = str(entry.get("scope") or entry.get("type") or "").lower()
    if "wizard" in scope:
        return project_wizard_chart_response(response, response_mode=response_mode)
    return project_editor_chart_response(response, response_mode=response_mode)


def _readback_identity_row(value: dict[str, Any], *, fallback_id: str = "") -> dict[str, str]:
    candidates: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
            entry = item.get("entry") if isinstance(item.get("entry"), dict) else item
            if identity:
                candidates.append(identity)
            if any(key in entry for key in ("entryId", "revId", "rev_id", "revisionId")):
                candidates.append(entry)
            for nested in item.values():
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)
    chosen = next(
        (
            item
            for item in candidates
            if str(
                item.get("rev_id")
                or item.get("revId")
                or item.get("revision_id")
                or item.get("revisionId")
                or ""
            ).strip()
        ),
        candidates[0] if candidates else {},
    )
    return {
        "object_id": str(
            chosen.get("id") or chosen.get("object_id") or chosen.get("entryId") or fallback_id or ""
        ).strip(),
        "revision_id": str(
            chosen.get("rev_id") or chosen.get("revId") or chosen.get("revision_id") or chosen.get("revisionId") or ""
        ).strip(),
    }


def _first_title(text: str) -> str:
    ignored = {
        "source inputs",
        "s2t",
        "data architecture",
        "datasets",
        "connectors",
        "fields",
        "metrics",
        "dashboard requirements",
        "dashboard pages",
        "charts",
        "selectors",
        "object relations",
        "user decisions",
        "implementation plan",
        "change log",
        "source of truth",
    }
    for line in text.splitlines():
        if not line.startswith("# ") or line.startswith("## "):
            continue
        compact = line.strip("# -:\t ")
        if compact and compact.lower() not in ignored:
            return compact[:80]
    for line in text.splitlines():
        compact = line.strip("# -:\t ")
        if compact and compact.lower() not in ignored and not compact.startswith("`requirements/"):
            return compact[:80]
    return "Local DataLens Dashboard"


def _run_dashboard_payload_preflight(root: Path) -> dict[str, Any]:
    checked_paths: list[str] = []
    issues: list[dict[str, str]] = []
    candidate_paths = sorted(root.glob("artifacts/**/*dashboard*payload*.json"))
    payload_plan = root / "artifacts" / "payload_plan.json"
    if payload_plan.is_file():
        candidate_paths.append(payload_plan)
    seen: set[Path] = set()
    for path in candidate_paths:
        if path in seen or not path.is_file():
            continue
        if path.name == "dashboard_payload_preflight.json":
            continue
        seen.add(path)
        payload = read_json(path, default={})
        if not _looks_like_dashboard_payload(payload, path):
            continue
        checked_paths.append(str(path))
        result = validate_dashboard_payload(payload)
        for issue in result.issues:
            item = issue.to_dict()
            item["path"] = f"{path}:{item['path']}"
            issues.append(item)
        issues.extend(_visual_payload_contract_issues(payload, path=path))
    if not checked_paths:
        issues.append(
            {
                "severity": "error",
                "rule": "zero_dashboard_payload_preflight_coverage",
                "path": str(root / "artifacts"),
                "message": "Dashboard payload preflight checked zero paths; an empty fixture cannot produce a pass.",
                "suggested_fix": (
                    "Generate or provide at least one dashboard payload artifact before claiming "
                    "dashboard preflight coverage."
                ),
            }
        )
    report = {
        "ok": not any(issue["severity"] == "error" for issue in issues),
        "checked_paths": checked_paths,
        "issues": issues,
    }
    write_json(root / "artifacts" / "dashboard_payload_preflight.json", report)
    return report


def _run_renderer_visual_quality_preflight(root: Path, bundle_paths: list[Path]) -> dict[str, Any]:
    checked_paths: list[str] = []
    issues: list[dict[str, str]] = []
    for path in bundle_paths + sorted(root.glob("artifacts/**/*chart_decision*.json")):
        payload = read_json(path, default={})
        for spec_path, spec in _iter_renderer_visual_specs(payload):
            checked_paths.append(f"{path}:{spec_path}")
            result = validate_visual_quality_contract(spec)
            for finding in result.findings:
                issues.append(
                    {
                        "severity": finding.severity,
                        "rule": finding.rule,
                        "path": f"{path}:{spec_path}{finding.path.removeprefix('$')}",
                        "message": finding.message,
                        "suggested_fix": "Add labels/axes/native metadata alternatives in renderer_visual_spec.",
                    }
                )
    report = {
        "ok": not any(issue["severity"] == "error" for issue in issues),
        "checked_paths": checked_paths,
        "issues": issues,
    }
    write_json(root / "artifacts" / "renderer_visual_quality.json", report)
    return report


def _visual_payload_contract_issues(payload: dict[str, Any], *, path: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if _has_object_granularity_manifest(payload):
        from datalens_dev_mcp.pipeline.dashboard_object_granularity import validate_dashboard_object_granularity

        result = validate_dashboard_object_granularity(payload)
        issues.extend(_finding_issue_dicts(result.findings, path=path, source="dashboard_object_granularity"))
    if _has_selector_contract(payload):
        from datalens_dev_mcp.pipeline.selector_layout_contract import validate_selector_layout_contract

        result = validate_selector_layout_contract(payload)
        issues.extend(_finding_issue_dicts(result.findings, path=path, source="selector_layout_contract"))
    body = _joined_strings(payload).lower()
    if _has_kpi_contract(payload) or "kpi-card" in body or "metric-card" in body or "card-grid" in body:
        from datalens_dev_mcp.pipeline.kpi_indicator_contract import validate_kpi_indicator_contract

        result = validate_kpi_indicator_contract(payload)
        issues.extend(_finding_issue_dicts(result.findings, path=path, source="kpi_indicator_contract"))
    for index, table_payload in enumerate(_table_contract_payloads(payload)):
        from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract

        result = validate_native_table_contract(table_payload)
        issues.extend(
            _finding_issue_dicts(
                result.findings,
                path=path,
                source="native_table_contract",
                prefix=f"$.table_contracts[{index}]",
            )
        )
    for spec_path, spec in _iter_renderer_visual_specs(payload):
        result = validate_visual_quality_contract(spec)
        issues.extend(
            _finding_issue_dicts(
                result.findings,
                path=path,
                source="renderer_visual_quality",
                prefix=spec_path,
            )
        )
    return issues


def _finding_issue_dicts(
    findings: Any,
    *,
    path: Path,
    source: str,
    prefix: str = "",
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for finding in findings:
        finding_path = str(getattr(finding, "path", "$"))
        if prefix:
            finding_path = prefix + finding_path.removeprefix("$")
        issues.append(
            {
                "severity": str(getattr(finding, "severity", "error")),
                "rule": str(getattr(finding, "rule", source)),
                "path": f"{path}:{finding_path}",
                "message": str(getattr(finding, "message", "")),
                "suggested_fix": source,
            }
        )
    return issues


def _has_object_granularity_manifest(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("objects", "object_manifest", "expected_visual_count", "dashboard_like_advanced_editor"))


def _has_selector_contract(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("selectors", "selector_rows", "controls", "selectorRows"))


def _has_kpi_contract(payload: dict[str, Any]) -> bool:
    return any(key in payload for key in ("kpis", "indicators", "expected_kpi_count"))


def _table_contract_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if _looks_like_table_contract(payload):
        candidates.append(payload)
    for key in ("tables", "table_payloads"):
        raw = payload.get(key)
        if isinstance(raw, list):
            candidates.extend(item for item in raw if isinstance(item, dict) and _looks_like_table_contract(item))
    objects = payload.get("objects") or payload.get("object_manifest") or []
    if isinstance(objects, list):
        for item in objects:
            if isinstance(item, dict) and _looks_like_table_contract(item):
                candidates.append(item)
    return candidates


def _looks_like_table_contract(value: dict[str, Any]) -> bool:
    route = str(
        value.get("route")
        or value.get("selected_route")
        or value.get("object_type")
        or value.get("entry_type")
        or value.get("type")
        or ""
    ).strip().lower()
    if route not in {"table_node", "editor_table", "native_table"}:
        return False
    return bool(value.get("columns") or value.get("rows") or value.get("table_payload") or value.get("source") or value.get("row_count"))


def _iter_renderer_visual_specs(value: Any, path: str = "$"):
    if isinstance(value, dict):
        spec = value.get("renderer_visual_spec")
        if isinstance(spec, dict) and spec:
            yield f"{path}.renderer_visual_spec", spec
        elif _looks_like_renderer_visual_spec(value):
            yield path, value
        for key, item in value.items():
            if key == "renderer_visual_spec":
                continue
            yield from _iter_renderer_visual_specs(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_renderer_visual_specs(item, f"{path}[{index}]")


def _looks_like_renderer_visual_spec(value: dict[str, Any]) -> bool:
    return bool(
        (value.get("family") or value.get("selected_family"))
        and any(key in value for key in ("labels", "label_spec", "axes", "axis_spec", "encoding", "analytical_task"))
    )


def _joined_strings(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            parts.append(_joined_strings(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(_joined_strings(item))
    elif isinstance(value, str):
        parts.append(value)
    return "\n".join(parts)


def _write_dashboard_preflight_candidate(root: Path, *, workbook_id: str, payloads: list[dict[str, Any]]) -> None:
    if not payloads:
        return
    items = []
    for index, payload in enumerate(payloads, start=1):
        widget_id = str(payload.get("widget_id") or f"widget_{index:03d}")
        items.append(
            {
                "id": f"{widget_id}_item",
                "type": "chart",
                "chartId": widget_id,
                "title": widget_id.replace("_", " ").title(),
            }
        )
    dashboard_payload = {
        "schema_version": "2026-06-25.dashboard_preflight_candidate.v1",
        "dashboardId": "local_dashboard_preflight",
        "workbookId": workbook_id,
        "tabs": [{"id": "main", "title": "Main", "items": [item["id"] for item in items]}],
        "items": items,
        "selector_rows": [],
    }
    write_json(root / "artifacts" / "dashboard_payloads" / "generated.dashboard.payload.json", dashboard_payload)


def _looks_like_dashboard_payload(payload: Any, path: Path) -> bool:
    if not isinstance(payload, dict):
        return False
    lowered_path = str(path).lower()
    if "dashboard" in lowered_path and "payload" in lowered_path:
        return True
    keys = {str(key) for key in payload}
    return bool(keys & {"dashboardId", "dashboard_id", "dash", "blocks", "items", "widgets", "selector_rows"})
