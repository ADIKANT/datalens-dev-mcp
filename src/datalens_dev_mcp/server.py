from __future__ import annotations

import argparse
from copy import deepcopy
import inspect
import json
import os
import sys
import traceback
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from datalens_dev_mcp import __version__
from datalens_dev_mcp.api.errors import DataLensApiError, DataLensSafetyError
from datalens_dev_mcp.config import EXECUTION_SWITCH_ENV_NAMES, load_env_file, use_api_defaults
from datalens_dev_mcp.local_config import apply_tool_defaults, load_local_config
from datalens_dev_mcp.mcp.heavy_response import (
    DEFAULT_HEAVY_INLINE_CHAR_BUDGET,
    HEAVY_TOOL_NAMES,
    project_heavy_tool_response,
)
from datalens_dev_mcp.mcp.prompts import get_prompt, list_prompts
from datalens_dev_mcp.mcp.response_projection import (
    project_public_resource_text,
    project_public_response,
    sanitize_response,
)
from datalens_dev_mcp.mcp.resources import list_resources, read_resource
from datalens_dev_mcp.mcp.tool_registry_policy import hidden_tool_calls_enabled
from datalens_dev_mcp.pipeline.context_contracts import (
    PROJECT_CONTEXT_AWARE_TOOLS,
    finalize_project_contract_result,
    validate_project_contract_inputs,
)
from datalens_dev_mcp.runtime_resources import RuntimeResourceError
from datalens_dev_mcp.validators.redaction import redact_text
from datalens_dev_mcp.mcp.tools import (
    config_tools,
    data_evidence,
    diagnostics,
    discovery,
    dq_reconciliation,
    local_planning,
    object_lifecycle,
    pipeline,
    reconciliation,
    reference,
    rpc,
    runtime,
    snapshot,
)


MCP_PROTOCOL_VERSION = "2025-06-18"
DEFAULT_TOOL_SURFACE = "standard"


def _tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": _input_schema_for_tool(name, properties=properties, required=required),
    }


TOOLS: dict[str, Callable[..., Any]] = {
    "dl_get_local_config": config_tools.dl_get_local_config,
    "dl_runtime_status": runtime.dl_runtime_status,
    "dl_auth_probe": runtime.dl_auth_probe,
    "dl_validate_editor_runtime_contract": runtime.dl_validate_editor_runtime_contract,
    "dl_classify_source_error": runtime.dl_classify_source_error,
    "dl_diagnose": diagnostics.dl_diagnose,
    "dl_reference": reference.dl_reference,
    "dl_start_pipeline": pipeline.dl_start_pipeline,
    "dl_ingest_requirements": pipeline.dl_ingest_requirements,
    "dl_build_governance_brief": pipeline.dl_build_governance_brief,
    "dl_init_requirements_workspace": pipeline.dl_init_requirements_workspace,
    "dl_ingest_requirements_markdown": pipeline.dl_ingest_requirements_markdown,
    "dl_select_dashboard_blueprint": pipeline.dl_select_dashboard_blueprint,
    "dl_populate_dashboard_map_canvas": pipeline.dl_populate_dashboard_map_canvas,
    "dl_list_wizard_templates": pipeline.dl_list_wizard_templates,
    "dl_build_wizard_payload_template": pipeline.dl_build_wizard_payload_template,
    "dl_build_dashboard_blueprint_plan": pipeline.dl_build_dashboard_blueprint_plan,
    "dl_update_user_decision": pipeline.dl_update_user_decision,
    "dl_summarize_implementation_plan": pipeline.dl_summarize_implementation_plan,
    "dl_validate_chart_plan_against_requirements": pipeline.dl_validate_chart_plan_against_requirements,
    "dl_generate_editor_bundle": pipeline.dl_generate_editor_bundle,
    "dl_validate_project": pipeline.dl_validate_project,
    "dl_build_payload_plan": pipeline.dl_build_payload_plan,
    "dl_detect_project_adapter": pipeline.dl_detect_project_adapter,
    "dl_detect_project_live_workflows": pipeline.dl_detect_project_live_workflows,
    "dl_list_project_live_workflows": pipeline.dl_list_project_live_workflows,
    "dl_plan_project_manifest": pipeline.dl_plan_project_manifest,
    "dl_plan_project_live_workflow": pipeline.dl_plan_project_live_workflow,
    "dl_run_project_live_dry_run": pipeline.dl_run_project_live_dry_run,
    "dl_run_project_live_apply": pipeline.dl_run_project_live_apply,
    "dl_read_project_live_summary": pipeline.dl_read_project_live_summary,
    "dl_run_live_maintenance_update": pipeline.dl_run_live_maintenance_update,
    "dl_build_dashboard_source_availability_matrix": pipeline.dl_build_dashboard_source_availability_matrix,
    "dl_validate_source_availability_consumers": pipeline.dl_validate_source_availability_consumers,
    "dl_plan_source_availability_patch": pipeline.dl_plan_source_availability_patch,
    "dl_create_safe_apply_plan": pipeline.dl_create_safe_apply_plan,
    "dl_execute_safe_apply": pipeline.dl_execute_safe_apply,
    "dl_create_publish_from_saved_plan": pipeline.dl_create_publish_from_saved_plan,
    "dl_readback_and_report": pipeline.dl_readback_and_report,
    "dl_snapshot_dashboard": snapshot.dl_snapshot_dashboard,
    "dl_build_validation_evidence_report": pipeline.dl_build_validation_evidence_report,
    "dl_build_data_evidence_probe_plan": data_evidence.dl_build_data_evidence_probe_plan,
    "dl_record_data_evidence": data_evidence.dl_record_data_evidence,
    "dl_evaluate_data_evidence": data_evidence.dl_evaluate_data_evidence,
    "dl_ingest_dq_control_summary": dq_reconciliation.dl_ingest_dq_control_summary,
    "dl_build_dq_layer_reconciliation_plan": dq_reconciliation.dl_build_dq_layer_reconciliation_plan,
    "dl_classify_dq_reconciliation": dq_reconciliation.dl_classify_dq_reconciliation,
    "dl_build_dq_before_after_report": dq_reconciliation.dl_build_dq_before_after_report,
    "dl_list_workbooks": discovery.dl_list_workbooks,
    "dl_get_workbook_entries": discovery.dl_get_workbook_entries,
    "dl_get_dashboard": discovery.dl_get_dashboard,
    "dl_get_editor_chart": discovery.dl_get_editor_chart,
    "dl_get_wizard_chart": discovery.dl_get_wizard_chart,
    "dl_get_dataset": discovery.dl_get_dataset,
    "dl_get_connection": discovery.dl_get_connection,
    "dl_get_entries_relations": discovery.dl_get_entries_relations,
    "dl_probe_auth": object_lifecycle.dl_probe_auth,
    "dl_read_object": object_lifecycle.dl_read_object,
    "dl_validate_object_payload": object_lifecycle.dl_validate_object_payload,
    "dl_list_related_objects": object_lifecycle.dl_list_related_objects,
    "dl_get_dataset_schema": object_lifecycle.dl_get_dataset_schema,
    "dl_plan_object_create": object_lifecycle.dl_plan_object_create,
    "dl_plan_object_update": object_lifecycle.dl_plan_object_update,
    "dl_validate_object": object_lifecycle.dl_validate_object,
    "dl_compile_guarded_rpc_request": object_lifecycle.dl_compile_guarded_rpc_request,
    "dl_plan_publish_from_saved": object_lifecycle.dl_plan_publish_from_saved,
    "dl_create_editor_chart_plan": object_lifecycle.dl_create_editor_chart_plan,
    "dl_update_editor_chart_plan": object_lifecycle.dl_update_editor_chart_plan,
    "dl_create_wizard_chart_plan": object_lifecycle.dl_create_wizard_chart_plan,
    "dl_update_wizard_chart_plan": object_lifecycle.dl_update_wizard_chart_plan,
    "dl_create_dashboard_plan": object_lifecycle.dl_create_dashboard_plan,
    "dl_update_dashboard_plan": object_lifecycle.dl_update_dashboard_plan,
    "dl_create_connector_plan": object_lifecycle.dl_create_connector_plan,
    "dl_update_connector_plan": object_lifecycle.dl_update_connector_plan,
    "dl_create_dataset_plan": object_lifecycle.dl_create_dataset_plan,
    "dl_update_dataset_plan": object_lifecycle.dl_update_dataset_plan,
    "dl_plan_guarded_dataset_update": object_lifecycle.dl_plan_guarded_dataset_update,
    "dl_plan_dashboard_tab_update": object_lifecycle.dl_plan_dashboard_tab_update,
    "dl_create_dataset_field_plan": object_lifecycle.dl_create_dataset_field_plan,
    "dl_update_dataset_field_plan": object_lifecycle.dl_update_dataset_field_plan,
    "dl_create_calculated_field_plan": object_lifecycle.dl_create_calculated_field_plan,
    "dl_update_calculated_field_plan": object_lifecycle.dl_update_calculated_field_plan,
    "dl_save_object_plan": object_lifecycle.dl_save_object_plan,
    "dl_publish_object_plan": object_lifecycle.dl_publish_object_plan,
    "dl_reconcile_partial_creates": reconciliation.dl_reconcile_partial_creates,
    "dl_list_api_methods": rpc.dl_list_api_methods,
    "dl_get_api_method_schema": rpc.dl_get_api_method_schema,
    "dl_rpc_readonly": rpc.dl_rpc_readonly,
    "dl_rpc_expert": rpc.dl_rpc_expert,
    "dl_build_workbook_source_resolution": local_planning.dl_build_workbook_source_resolution,
    "dl_build_selector_wiring_summary": local_planning.dl_build_selector_wiring_summary,
    "dl_build_runtime_verification_plan": local_planning.dl_build_runtime_verification_plan,
    "dl_run_wizard_to_js_plan": local_planning.dl_run_wizard_to_js_plan,
}

STANDARD_TOOL_NAMES = {
    "dl_get_local_config",
    "dl_runtime_status",
    "dl_auth_probe",
    "dl_validate_editor_runtime_contract",
    "dl_classify_source_error",
    "dl_diagnose",
    "dl_reference",
    "dl_generate_editor_bundle",
    "dl_validate_project",
    "dl_build_payload_plan",
    "dl_create_safe_apply_plan",
    "dl_execute_safe_apply",
    "dl_create_publish_from_saved_plan",
    "dl_readback_and_report",
    "dl_snapshot_dashboard",
    "dl_build_validation_evidence_report",
    "dl_list_workbooks",
    "dl_get_workbook_entries",
    "dl_read_object",
    "dl_get_entries_relations",
    "dl_plan_object_create",
    "dl_plan_object_update",
    "dl_validate_object",
    "dl_plan_guarded_dataset_update",
    "dl_plan_dashboard_tab_update",
    "dl_reconcile_partial_creates",
    "dl_list_api_methods",
    "dl_get_api_method_schema",
    "dl_detect_project_live_workflows",
    "dl_plan_project_manifest",
    "dl_plan_project_live_workflow",
    "dl_run_project_live_dry_run",
    "dl_run_project_live_apply",
    "dl_read_project_live_summary",
    "dl_run_live_maintenance_update",
    "dl_build_dashboard_source_availability_matrix",
    "dl_validate_source_availability_consumers",
    "dl_plan_source_availability_patch",
}

CORE_PROFILE_TOOLS = {
    "dl_get_local_config",
    "dl_runtime_status",
    "dl_auth_probe",
    "dl_validate_editor_runtime_contract",
    "dl_classify_source_error",
    "dl_build_dashboard_blueprint_plan",
    "dl_validate_chart_plan_against_requirements",
    "dl_generate_editor_bundle",
    "dl_validate_project",
    "dl_build_payload_plan",
    "dl_create_safe_apply_plan",
    "dl_execute_safe_apply",
    "dl_create_publish_from_saved_plan",
    "dl_readback_and_report",
    "dl_snapshot_dashboard",
    "dl_build_validation_evidence_report",
    "dl_list_workbooks",
    "dl_get_workbook_entries",
    "dl_get_dashboard",
    "dl_get_editor_chart",
    "dl_get_wizard_chart",
    "dl_get_dataset",
    "dl_get_connection",
    "dl_validate_object_payload",
}

TEST_ONLY_TOOL_PROFILE_MEMBERS: dict[str, set[str]] = {
    DEFAULT_TOOL_SURFACE: STANDARD_TOOL_NAMES,
    "core": CORE_PROFILE_TOOLS,
    "dashboard": CORE_PROFILE_TOOLS
    | {
        "dl_init_requirements_workspace",
        "dl_select_dashboard_blueprint",
        "dl_populate_dashboard_map_canvas",
        "dl_list_wizard_templates",
        "dl_build_wizard_payload_template",
        "dl_update_user_decision",
        "dl_summarize_implementation_plan",
        "dl_get_entries_relations",
        "dl_read_object",
        "dl_list_related_objects",
        "dl_create_editor_chart_plan",
        "dl_update_editor_chart_plan",
        "dl_create_wizard_chart_plan",
        "dl_update_wizard_chart_plan",
        "dl_create_dashboard_plan",
        "dl_update_dashboard_plan",
        "dl_plan_dashboard_tab_update",
        "dl_reconcile_partial_creates",
        "dl_build_workbook_source_resolution",
        "dl_build_selector_wiring_summary",
    },
    "dq": CORE_PROFILE_TOOLS
    | {
        "dl_build_data_evidence_probe_plan",
        "dl_record_data_evidence",
        "dl_evaluate_data_evidence",
        "dl_ingest_dq_control_summary",
        "dl_build_dq_layer_reconciliation_plan",
        "dl_classify_dq_reconciliation",
        "dl_build_dq_before_after_report",
    },
    "dataset": CORE_PROFILE_TOOLS
    | {
        "dl_get_dataset",
        "dl_get_connection",
        "dl_get_dataset_schema",
        "dl_create_connector_plan",
        "dl_update_connector_plan",
        "dl_create_dataset_plan",
        "dl_update_dataset_plan",
        "dl_plan_guarded_dataset_update",
        "dl_create_dataset_field_plan",
        "dl_update_dataset_field_plan",
        "dl_create_calculated_field_plan",
        "dl_update_calculated_field_plan",
    },
    "expert": CORE_PROFILE_TOOLS
    | {
        "dl_start_pipeline",
        "dl_detect_project_adapter",
        "dl_detect_project_live_workflows",
        "dl_list_project_live_workflows",
        "dl_plan_project_live_workflow",
        "dl_run_project_live_dry_run",
        "dl_run_project_live_apply",
        "dl_read_project_live_summary",
        "dl_list_api_methods",
        "dl_get_api_method_schema",
        "dl_rpc_readonly",
        "dl_rpc_expert",
        "dl_build_workbook_source_resolution",
        "dl_build_runtime_verification_plan",
        "dl_run_wizard_to_js_plan",
    },
    "all": set(TOOLS),
}

# Compatibility surfaces are test-only. Normal MCP runtime ignores profile
# selection and returns only STANDARD_TOOL_NAMES from tools/list.
TOOL_PROFILE_MEMBERS = TEST_ONLY_TOOL_PROFILE_MEMBERS

PARAM_DESCRIPTIONS: dict[str, str] = {
    "project_root": "Local project root.",
    "config_path": "Optional local MCP config path.",
    "local_config_path": "Resolved local MCP config JSON file used by the current server process.",
    "workbook_id": "DataLens workbook id.",
    "project_id": "Local or external project id placeholder.",
    "dashboard_id": "DataLens dashboard id.",
    "chart_id": "DataLens chart id.",
    "dataset_id": "DataLens dataset id.",
    "dataset_alias": "Caller-owned dataset link alias for generated Editor sources.",
    "connection_id": "DataLens connection id.",
    "entry_ids": "DataLens entry ids for relation lookup.",
    "object_type": "Supported object type.",
    "object_id": "DataLens object id.",
    "object_ids": "DataLens object ids.",
    "source_adapter": "Named lifecycle source adapter.",
    "payload": "Payload. Must not contain secrets.",
    "entry": "DataLens entry payload or plan payload. Must not contain secrets.",
    "sections": "Generated or hydrated Editor sections to validate before save or publish.",
    "allow_unknown_warnings": "Audited override for unknown runtime warnings only; known forbidden errors still block.",
    "artifact_paths": "Editor JSON artifact paths inside project_root; mutually exclusive with entry and sections.",
    "include_references": "Include full corpus reference rows instead of only the stable reference-set id and URLs.",
    "error_payload": "Structured DataLens source error payload to classify without secrets.",
    "config": "Route or object config payload. Must not contain secrets.",
    "mode": "Save or publish mode. Save is the safe default.",
    "branch": "DataLens branch to read.",
    "method": "Curated DataLens API method name.",
    "readback_mode": "Readback depth for saved/published verification.",
    "plan_path": "Path to the guarded safe-apply plan artifact to execute.",
    "write_manifest": "Write generated manifest.",
    "confirm_delete": "Confirm retire_legacy_objects IDs and unchanged plan hash.",
    "saved_readback_path": "Saved-branch readback artifact.",
    "workflow_name": "Manifest workflow name.",
    "overwrite_existing": "Allow the generated project manifest to replace an existing manifest.",
    "target_workbook_id": "Target workbook id to include in a generated project manifest.",
    "action": "Project-live action.",
    "execute_now": "Execute command.",
    "timeout_sec": "Command timeout seconds.",
    "execution_id": "Poll a running project-live command by id; never relaunches it.",
    "publish": "Request publish.",
    "summary_path": "Summary JSON path inside project.",
    "requirements_text": "Dashboard requirements text.",
    "markdown_text": "Requirement Markdown to persist.",
    "source_text": "Source requirement or S2T text.",
    "source_name": "Human-readable source label.",
    "role": "Requirement source role.",
    "data_path": "Optional local data sample path.",
    "data_profile": "Optional compact data profile.",
    "chart_plan": "Chart plan payload to validate.",
    "widget_id": "Local widget id.",
    "route": "Editor route override.",
    "authoring_profile": (
        "Versioned registered-template profile; standard_editor_v1 reuses exact Editor assets "
        "and blocks fallback generation."
    ),
    "target": "Readback target kind.",
    "chart_ids": "Chart ids to read back.",
    "page": "Result page number.",
    "page_size": "Result page size.",
    "scope": "Optional API object-type filter; use all/* for every entry, never a chart or dashboard title.",
    "operation": "Object operation to validate.",
    "required_fields": "Dataset fields that must exist.",
    "dataset": "Inline dataset payload for offline field validation.",
    "current_dataset": "Fresh getDataset payload.",
    "proposed_dataset": "Proposed dataset payload.",
    "affected_chart_payloads": "Saved chart payloads that depend on dataset field GUIDs.",
    "validate_only": "Plan validateDataset only without updateDataset.",
    "allow_guid_changes": "Allow reviewed dataset field GUID changes; disabled by default.",
    "current_dashboard": "Fresh getDashboard payload before a guarded dashboard tab update.",
    "tab": "Dashboard tab payload to append or replace.",
    "tab_operation": "Dashboard tab operation.",
    "tab_id": "Existing tab id, tabId, or title for replace operations.",
    "entries_payload": "getWorkbookEntries response payload.",
    "planned_objects": "Planned objects with display_title, internal_name, and object_type.",
    "provider_config": "Read-only metadata/data evidence provider configuration.",
    "probe_operation": "Read-only evidence probe operation.",
    "table_ref": "Physical table reference as schema.table or catalog.schema.table.",
    "columns": "Explicit column list for source binding or bounded probes; SELECT * is not allowed.",
    "selector_contract": (
        "Explicit selector parameter, option-source, default, and reset contract. "
        "Required for production editor_js_control generation."
    ),
    "dataset_readbacks": "Fresh dataset readbacks used to validate Wizard field GUID and role bindings.",
    "where_clause": "Optional bounded WHERE predicate for read-only data probes.",
    "cte_sql": "CTE SQL used only for stage-count probe planning.",
    "graph_config": "Graph/link/freshness probe options such as source_key, target_key, or timestamp_column.",
    "sample_limit": "Maximum bounded sample row count.",
    "query": "Reference search query or formula expression.",
    "name": "Optional exact recipe, formula, visualization, error, capability, or source-trace name.",
    "limit": "Maximum compact reference rows to return.",
    "max_chars": "Maximum serialized reference response characters before artifact spill.",
    "max_items": "Maximum diagnostic rows returned inline; full details spill to artifacts/sql_performance.",
    "environment": "Target environment label such as dev, stage, or prod.",
    "artifact_name": "Safe project-local data evidence artifact name.",
    "evidence": "Sanitized read-only data evidence payload to record under the project.",
    "control_summary": "Aggregated DQ control-file summary; raw rows are omitted.",
    "identity_keys": "DQ identity mapping: strict_business_key, stable_rk_key, and resolved_key.",
    "layers": "DQ layer reconciliation plan items from control/raw/history/current/mart/dashboard.",
    "control_records": "Small sanitized control evidence records for classification; do not pass full raw files.",
    "evidence_records": "Sanitized layer/dashboard evidence records for DQ classification.",
    "strict_business_key": "Mutable business key such as order number.",
    "stable_key": "Stable RK/resolved identity key.",
    "amount_field": "Amount field name used for DQ bridge totals.",
    "before": "Before-fix DQ classification result.",
    "after": "After-fix DQ classification result.",
    "fix_scope": "DQ fix scope such as dashboard or upstream.",
    "approved_upstream_override": "Explicit approval to proceed despite upstream contradictions.",
    "inventory": "Aggregate inventory evidence. Truncated inventories cannot prove absence.",
    "targeted_evidence": "Targeted table_discovery evidence that can prove availability or absence.",
    "connection_payloads": "Mapping from connection entry id to getConnection payload.",
    "explicit_connection_ids": "Optional selected connection ids.",
    "explicit_dataset_ids": "Optional selected dataset ids.",
    "remote_entry": "Current dashboard entry read from DataLens.",
    "proposed_entry": "Proposed dashboard entry after changes.",
    "widget_plan": "Widget and selector wiring plan.",
    "run_id": "Optional verification run id.",
    "response_mode": "Read response projection mode.",
    "inline_char_budget": "Inline response character budget.",
    "snapshot_branch": "Snapshot branch.",
    "include_dormant_summary": "Include dormant workbook entry counts.",
    "artifact_retention": "Snapshot artifact retention policy.",
    "execute": "Whether to execute the runtime plan. Defaults to false.",
    "classification_path": "Path to Wizard classification JSON.",
    "plan_output_path": "Path for generated plan JSON.",
    "summary_output_path": "Path for generated summary Markdown.",
    "workbook_ids": "Up to 100 workbook ids for one ordered batch read; mutually exclusive with workbook_id.",
    "include_guarded_writes": "Whether to include guarded write methods in the catalog.",
    "scenario": "Pipeline scenario.",
    "dashboard_name": "Dashboard display name placeholder.",
    "path": "Memory-bank relative path.",
    "content": "Text content to write.",
    "append": "Append to the target file instead of replacing it.",
    "decision_text": "User decision or correction text.",
    "decision_id": "Stable decision id.",
}

COMPACT_SCHEMA_DESCRIPTION_PARAMS = {
    # Self-evident coordinates, identifiers, paging knobs, and enum-backed
    # selectors do not need to repeat their parameter names in every tool
    # schema. Safety-sensitive payload, configuration, write/delete, readback,
    # and current/proposed-state descriptions intentionally remain visible.
    "action",
    "artifact_paths",
    "artifact_retention",
    "authoring_profile",
    "branch",
    "chart_id",
    "chart_ids",
    "columns",
    "connection_id",
    "dashboard_id",
    "dashboard_name",
    "dataset_id",
    "dataset_alias",
    "decision_id",
    "delivery_intent_text",
    "entry_ids",
    "entries_payload",
    "environment",
    "error_payload",
    "execution_id",
    "include_dormant_summary",
    "include_guarded_writes",
    "include_references",
    "inline_char_budget",
    "limit",
    "local_config_path",
    "max_chars",
    "max_items",
    "method",
    "mode",
    "name",
    "object_id",
    "object_ids",
    "object_type",
    "operation",
    "page",
    "page_size",
    "project_id",
    "project_root",
    "query",
    "readback_mode",
    "required_fields",
    "response_mode",
    "role",
    "route",
    "run_id",
    "sample_limit",
    "scenario",
    "scope",
    "snapshot_branch",
    "source_adapter",
    "summary_path",
    "tab_id",
    "tab_operation",
    "table_ref",
    "target",
    "target_known",
    "target_dashboard_id",
    "target_chart_id",
    "target_url",
    "target_workbook_id",
    "timeout_sec",
    "widget_id",
    "workbook_id",
    "workbook_ids",
    "workflow_name",
    "planned_objects",
}

PARAM_OVERRIDES: dict[str, dict[str, Any]] = {
    "object_type": {
        "type": "string",
        "enum": [
            "dashboard",
            "chart",
            "editor_chart",
            "advanced_editor_chart",
            "wizard_chart",
            "markup_wizard_node",
            "table",
            "table_node",
            "control",
            "control_node",
            "markdown",
            "markdown_node",
            "dataset",
            "connector",
            "connection",
            "report",
            "workbook",
            "collection",
            "location",
            "folder",
            "permission",
            "workbook_permission",
            "workbook_entry",
            "ql_chart",
            "dataset_field",
            "calculated_field",
        ],
    },
    "branch": {"type": "string", "enum": ["saved", "published"], "default": "saved"},
    "snapshot_branch": {"type": "string", "enum": ["saved", "published", "both"], "default": "saved"},
    "artifact_retention": {"type": "string", "enum": ["latest_only", "hash_partitioned", "both"], "default": "latest_only"},
    "mode": {"type": "string", "enum": ["save", "publish"], "default": "save"},
    "operation": {"type": "string", "enum": ["create", "update", "validate"], "default": "update"},
    "tab_operation": {"type": "string", "enum": ["append", "replace"], "default": "append"},
    "affected_chart_payloads": {"type": "array", "items": {"type": "object"}},
    "layers": {"type": "array", "items": {"type": "object"}},
    "control_records": {"type": "array", "items": {"type": "object"}},
    "evidence_records": {"type": "array", "items": {"type": "object"}},
    "readback_mode": {"type": "string", "enum": ["none", "minimal", "full", "debug"], "default": "minimal"},
    "response_mode": {"type": "string", "enum": ["summary", "structure", "full", "artifact"], "default": "summary"},
    "inline_char_budget": {"type": "integer", "default": 20000},
    "route": {
        "type": "string",
        "enum": [
            "",
            "wizard_native",
            "wizard_map_native",
            "editor_advanced",
            "editor_table",
            "editor_markdown",
            "editor_js_control",
            "ql_explicit",
        ],
        "default": "",
    },
    "target": {"type": "string", "enum": ["dashboard", "editor_chart", "wizard_chart", "dataset", "connection"], "default": "dashboard"},
    "scenario": {"type": "string", "enum": ["new_dashboard", "redesign_existing", "enhance_existing", "wizard_to_js"]},
    "role": {"type": "string", "enum": ["dashboard", "source", "s2t", "data", "decision"], "default": "dashboard"},
    "action": {
        "type": "string",
        "enum": ["validate", "dry_run", "apply", "publish", "readback", "retire_legacy_objects"],
        "default": "dry_run",
    },
    "probe_operation": {
        "type": "string",
        "enum": [
            "table_discovery",
            "column_list",
            "bounded_row_count",
            "bounded_sample",
            "cte_stage_count",
            "link_direction",
            "source_freshness_availability",
        ],
        "default": "table_discovery",
    },
}

READ_OBJECT_TYPE_SCHEMA = {
    "type": "string",
    "enum": [
        "dashboard",
        "chart",
        "editor_chart",
        "advanced_editor_chart",
        "wizard_chart",
        "dataset",
        "connector",
        "connection",
        "report",
        "workbook",
        "collection",
        "folder",
        "compute",
        "permission",
        "workbook_permission",
        "ql_chart",
    ],
    "description": "Read-only object type.",
}
LIFECYCLE_OBJECT_TYPE_SCHEMA = {
    "type": "string",
    "enum": [
        "dashboard",
        "chart",
        "editor_chart",
        "advanced_editor_chart",
        "wizard_chart",
        "table",
        "table_node",
        "control",
        "control_node",
        "markdown",
        "markdown_node",
        "dataset",
        "connector",
        "connection",
        "ql_chart",
    ],
    "description": "Guarded lifecycle object type.",
}
PUBLISH_OBJECT_TYPE_SCHEMA = {
    "type": "string",
    "enum": ["dashboard", "editor_chart", "wizard_chart", "ql_chart"],
    "description": "Saved-branch publish object type.",
}
SELECTOR_CONTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "description": (
        "Complete Editor selector contract. Date ranges use either param or the "
        "param_from/param_to pair; Params values are generated only as arrays of strings."
    ),
    "properties": {
        "param": {"type": "string", "minLength": 1},
        "param_from": {"type": "string", "minLength": 1},
        "param_to": {"type": "string", "minLength": 1},
        "label": {"type": "string", "minLength": 1},
        "option_source": {"type": "string", "enum": ["static", "dataset", "dynamic", "none"]},
        "options": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string", "minLength": 1},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["title", "value"],
                        "properties": {
                            "title": {"type": "string", "minLength": 1},
                            "value": {"type": "string", "minLength": 1},
                        },
                    },
                ]
            },
        },
        "default_values": {"type": "array", "items": {"type": "string"}},
        "default_from": {"type": "string"},
        "default_to": {"type": "string"},
        "reset_behavior": {"type": "string", "enum": ["initial", "empty"]},
    },
    "required": ["label", "option_source", "reset_behavior"],
    "oneOf": [
        {
            "required": ["param"],
            "not": {
                "anyOf": [
                    {"required": ["param_from"]},
                    {"required": ["param_to"]},
                ]
            },
        },
        {
            "required": ["param_from", "param_to"],
            "not": {"required": ["param"]},
        },
    ],
}
MAINTENANCE_EVIDENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "description": (
        "Typed create/publish evidence with saved and published runtime proof."
    ),
    "properties": {
        "browser_runtime_required": {
            "type": "boolean",
            "default": True,
        },
        "non_rendering_exemption": {"type": "string"},
        "baseline_snapshot_path": {"type": "string"},
        "metadata_evidence_paths": {"type": "array", "items": {"type": "string"}},
        "source_availability_artifact": {"type": "string"},
        "changed_objects": {"type": "array", "items": {"type": "object"}},
        "allow_create": {
            "type": "boolean",
            "default": False,
        },
        "create_necessity_proof": {"type": "object"},
        "cleanup_mode": {"type": "string", "default": "plan_only"},
        "safe_apply_actions": {
            "type": "array",
            "items": {"type": "object"},
        },
        "guarded_requests": {"type": "array", "items": {"type": "object"}},
        "source_budget_evidence": {
            "anyOf": [
                {"type": "object"},
                {"type": "array", "items": {"type": "object"}},
            ]
        },
        "runtime_gate_evidence": {"type": "object"},
        "saved_runtime_gate_evidence": {"type": "object"},
        "published_runtime_gate_evidence": {"type": "object"},
        "safe_apply_execution_evidence": {"type": "object"},
        "saved_readback_evidence": {"type": "object"},
        "publish_from_saved_evidence": {"type": "object"},
        "published_readback_evidence": {"type": "object"},
        "baseline_dashboard": {"type": "object"},
        "proposed_dashboard": {"type": "object"},
    },
}

TOOL_PARAM_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("dl_generate_editor_bundle", "selector_contract"): SELECTOR_CONTRACT_SCHEMA,
    ("dl_get_workbook_entries", "workbook_id"): {
        "type": "string",
        "minLength": 1,
    },
    ("dl_get_workbook_entries", "workbook_ids"): {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "minItems": 1,
        "maxItems": 100,
        "uniqueItems": True,
    },
    ("dl_get_workbook_entries", "scope"): {
        "anyOf": [
            {"type": "string", "minLength": 1},
            {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 1,
                "uniqueItems": True,
            },
        ],
    },
    ("dl_validate_editor_runtime_contract", "artifact_paths"): {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "minItems": 1,
        "maxItems": 100,
        "uniqueItems": True,
    },
    ("dl_diagnose", "mode"): {
        "type": "string",
        "enum": [
            "sql",
            "aggregation_grain",
            "semantic_graph",
            "performance",
            "optimization",
            "synthetic_fleet_fixture",
            "acceptance",
        ],
        "description": "Diagnostic mode.",
    },
    ("dl_reference", "mode"): {
        "type": "string",
        "enum": [
            "search",
            "authoring_guidance",
            "recipe",
            "formula",
            "visualization",
            "error",
            "capability",
            "source_trace",
            "chart_selection",
            "route_selection",
            "renderer_contract",
            "datalens_editor_runtime",
            "dashboard_system_type",
            "negative_requirements",
            "delivery_intent",
            "target_lock",
            "object_granularity",
            "selector_layout",
            "native_table",
            "kpi_indicator",
            "source_route",
            "visual_quality",
            "performance_budget",
            "repo_size",
            "api_contract",
            "current_docs_delta",
            "tool_selection",
        ],
        "default": "search",
        "description": "Bounded reference mode.",
    },
    ("dl_run_live_maintenance_update", "maintenance_evidence"): MAINTENANCE_EVIDENCE_SCHEMA,
    ("dl_read_object", "inline_char_budget"): {
        "type": "integer",
        "default": 20_000,
        "minimum": 800,
    },
    ("dl_read_object", "object_type"): READ_OBJECT_TYPE_SCHEMA,
    ("dl_validate_object_payload", "object_type"): LIFECYCLE_OBJECT_TYPE_SCHEMA,
    ("dl_plan_object_create", "object_type"): LIFECYCLE_OBJECT_TYPE_SCHEMA,
    ("dl_plan_object_update", "object_type"): LIFECYCLE_OBJECT_TYPE_SCHEMA,
    ("dl_validate_object", "object_type"): LIFECYCLE_OBJECT_TYPE_SCHEMA,
    ("dl_plan_publish_from_saved", "object_type"): PUBLISH_OBJECT_TYPE_SCHEMA,
    ("dl_save_object_plan", "object_type"): LIFECYCLE_OBJECT_TYPE_SCHEMA,
    ("dl_publish_object_plan", "object_type"): PUBLISH_OBJECT_TYPE_SCHEMA,
    ("dl_plan_object_update", "lifecycle_operation"): {"type": "string", "enum": ["update"], "default": "update"},
}

TOOL_REQUIRED_FIELDS: dict[str, list[str]] = {
    "dl_get_dashboard": ["dashboard_id"],
    "dl_get_editor_chart": ["chart_id"],
    "dl_get_wizard_chart": ["chart_id"],
    "dl_get_dataset": ["dataset_id"],
    "dl_get_connection": ["connection_id"],
    "dl_get_entries_relations": ["entry_ids"],
    "dl_read_object": ["object_type", "object_id"],
    "dl_validate_object_payload": ["object_type", "payload"],
    "dl_plan_object_create": ["object_type", "payload"],
    "dl_plan_object_update": ["object_type", "payload"],
    "dl_validate_object": ["object_type", "payload"],
    "dl_plan_publish_from_saved": ["object_type", "saved_readback_path"],
    "dl_list_related_objects": ["entry_ids"],
    "dl_create_editor_chart_plan": ["entry"],
    "dl_update_editor_chart_plan": ["entry"],
    "dl_create_wizard_chart_plan": ["entry"],
    "dl_update_wizard_chart_plan": ["entry"],
    "dl_create_dashboard_plan": ["entry"],
    "dl_update_dashboard_plan": ["entry"],
    "dl_create_connector_plan": ["config"],
    "dl_update_connector_plan": ["config"],
    "dl_create_dataset_plan": ["config"],
    "dl_update_dataset_plan": ["config"],
    "dl_plan_guarded_dataset_update": ["dataset_id", "current_dataset", "proposed_dataset"],
    "dl_plan_dashboard_tab_update": ["current_dashboard", "tab"],
    "dl_save_object_plan": ["object_type", "entry"],
    "dl_publish_object_plan": ["object_type", "entry"],
    "dl_reconcile_partial_creates": ["workbook_id", "planned_objects"],
    "dl_get_api_method_schema": ["method"],
    "dl_rpc_readonly": ["method"],
    "dl_rpc_expert": ["method"],
    "dl_ingest_requirements_markdown": ["markdown_text"],
    "dl_populate_dashboard_map_canvas": ["source_text"],
    "dl_build_wizard_payload_template": ["config"],
    "dl_update_user_decision": ["decision_text"],
    "dl_validate_chart_plan_against_requirements": ["chart_plan"],
    "dl_list_project_live_workflows": ["project_root"],
    "dl_plan_project_manifest": ["project_root"],
    "dl_plan_project_live_workflow": ["project_root"],
    "dl_run_project_live_dry_run": ["project_root"],
    "dl_run_project_live_apply": ["project_root"],
    "dl_read_project_live_summary": ["project_root"],
    "dl_compile_guarded_rpc_request": ["method", "payload"],
    "dl_create_publish_from_saved_plan": ["project_root", "target", "object_type"],
    "dl_snapshot_dashboard": ["dashboard_id"],
    "dl_record_data_evidence": ["evidence"],
    "dl_evaluate_data_evidence": ["table_ref"],
    "dl_ingest_dq_control_summary": ["project_root", "control_summary"],
    "dl_classify_dq_reconciliation": ["control_records", "evidence_records"],
    "dl_build_dq_before_after_report": ["project_root", "before"],
    "dl_build_workbook_source_resolution": ["workbook_id", "entries_payload"],
    "dl_build_selector_wiring_summary": ["remote_entry", "proposed_entry", "widget_plan"],
    "dl_build_runtime_verification_plan": ["workbook_id"],
    "dl_classify_source_error": ["error_payload"],
    "dl_diagnose": ["mode"],
}


@lru_cache(maxsize=1)
def _all_tool_schemas() -> tuple[dict[str, Any], ...]:
    return (
        _tool_schema("dl_get_local_config", "Return resolved local MCP config and source metadata."),
        _tool_schema("dl_runtime_status", "Return secret-safe runtime flags, auth, config, and route status."),
        _tool_schema("dl_auth_probe", "Probe live auth with minimal getWorkbooksList read without secrets."),
        _tool_schema("dl_validate_editor_runtime_contract", "Validate Editor runtime before write."),
        _tool_schema("dl_classify_source_error", "Classify DataLens source/runtime errors without exposing query or secrets."),
        _tool_schema("dl_diagnose", "Bounded SQL/grain/graph/performance diagnostics with artifact-backed evidence."),
        _tool_schema("dl_reference", "Return bounded source-traced guidance."),
        _tool_schema("dl_start_pipeline", "Scaffold governed DataLens requirements and planning artifacts."),
        _tool_schema("dl_ingest_requirements", "Ingest requirements/S2T/data evidence into governed artifacts."),
        _tool_schema("dl_build_governance_brief", "Build dashboard governance brief and route decisions."),
        _tool_schema("dl_init_requirements_workspace", "Create the persistent Markdown requirements workspace."),
        _tool_schema("dl_ingest_requirements_markdown", "Persist user requirement Markdown and extract dashboard planning sections."),
        _tool_schema("dl_select_dashboard_blueprint", "Select and explain a Dashboard Map/Canvas blueprint from request text."),
        _tool_schema("dl_populate_dashboard_map_canvas", "Populate requirements Dashboard Map and Canvas from request or S2T text."),
        _tool_schema("dl_list_wizard_templates", "List canonical native Wizard visualization templates and seed policy."),
        _tool_schema("dl_build_wizard_payload_template", "Compile a validated native Wizard payload from bindings or a saved seed."),
        _tool_schema("dl_build_dashboard_blueprint_plan", "Build dashboard blueprint and chart plan from persisted requirements."),
        _tool_schema("dl_update_user_decision", "Record a user correction in requirements/user_decisions.md and change_log.md."),
        _tool_schema("dl_summarize_implementation_plan", "Summarize the generated implementation plan from persisted requirements."),
        _tool_schema(
            "dl_validate_chart_plan_against_requirements",
            "Validate chart plan metrics, fields, selectors, and chart families against persisted requirements.",
        ),
        _tool_schema("dl_generate_editor_bundle", "Generate route-specific JS Editor bundle files."),
        _tool_schema("dl_validate_project", "Run offline route/editor/artifact/privacy validation."),
        _tool_schema("dl_build_payload_plan", "Compile generated bundles into dry-run DataLens payload plan."),
        _tool_schema("dl_detect_project_adapter", "Detect standard bundle or unsupported custom project layout."),
        _tool_schema("dl_detect_project_live_workflows", "Detect manifest-backed project live workflows or request an adapter."),
        _tool_schema("dl_list_project_live_workflows", "List manifest-backed project live workflows."),
        _tool_schema("dl_plan_project_manifest", "Preview or write a local project workflow manifest."),
        _tool_schema("dl_plan_project_live_workflow", "Plan a manifest-declared project live workflow without execution."),
        _tool_schema("dl_run_project_live_dry_run", "Run manifest dry-run command with secret-safe env."),
        _tool_schema(
            "dl_run_project_live_apply",
            "Run a guarded manifest apply/publish command; retire_legacy_objects alone needs confirmation.",
        ),
        _tool_schema("dl_read_project_live_summary", "Read and normalize a project live workflow summary JSON."),
        _tool_schema(
            "dl_run_live_maintenance_update",
            "Validate supplied live-maintenance evidence.",
        ),
        _tool_schema("dl_build_dashboard_source_availability_matrix", "Build Delta v7 supplied-evidence source availability matrix."),
        _tool_schema("dl_validate_source_availability_consumers", "Validate dashboard consumers against one source availability matrix."),
        _tool_schema("dl_plan_source_availability_patch", "Plan source availability corrections without querying source systems."),
        _tool_schema("dl_create_safe_apply_plan", "Create a target-locked guarded safe-apply plan from the user request."),
        _tool_schema("dl_execute_safe_apply", "Execute target-locked guarded safe apply when runtime write gates are enabled."),
        _tool_schema("dl_create_publish_from_saved_plan", "Create publish plan only from a saved-branch readback artifact."),
        _tool_schema("dl_readback_and_report", "Create readback summary and deployment report."),
        _tool_schema("dl_snapshot_dashboard", "Snapshot dashboard graph and sanitized object artifacts."),
        _tool_schema("dl_build_validation_evidence_report", "Build static/readback/runtime validation evidence report."),
        _tool_schema("dl_build_data_evidence_probe_plan", "Plan neutral read-only schema/data evidence probes."),
        _tool_schema("dl_record_data_evidence", "Record sanitized read-only schema/data evidence under a project."),
        _tool_schema("dl_evaluate_data_evidence", "Evaluate table availability without trusting truncated inventories."),
        _tool_schema("dl_ingest_dq_control_summary", "Record aggregated DQ control-file summary without raw rows."),
        _tool_schema(
            "dl_build_dq_layer_reconciliation_plan",
            "Plan DQ layer reconciliation across control/raw/history/current/mart/dashboard.",
        ),
        _tool_schema("dl_classify_dq_reconciliation", "Classify DQ records and build amount/count bridge evidence."),
        _tool_schema("dl_build_dq_before_after_report", "Build guarded before/after DQ report for dashboard-side fixes."),
        _tool_schema("dl_list_workbooks", "Read-only DataLens workbook list."),
        _tool_schema("dl_get_workbook_entries", "Read-only workbook entries."),
        _tool_schema("dl_get_dashboard", "Read-only dashboard hydration."),
        _tool_schema("dl_get_editor_chart", "Read-only Editor chart hydration."),
        _tool_schema("dl_get_wizard_chart", "Read-only Wizard chart hydration."),
        _tool_schema("dl_get_dataset", "Read-only dataset metadata."),
        _tool_schema("dl_get_connection", "Read-only connection metadata."),
        _tool_schema("dl_get_entries_relations", "Read-only entry relation graph."),
        _tool_schema("dl_probe_auth", "Run minimal read-only auth probe with structured errors."),
        _tool_schema("dl_read_object", "Read a supported DataLens object by type and id."),
        _tool_schema("dl_validate_object_payload", "Validate object payload shape and sensitive-key safety."),
        _tool_schema("dl_plan_object_create", "Plan OpenAPI-backed object creation with named source adapters."),
        _tool_schema("dl_plan_object_update", "Plan OpenAPI-backed object update with named source adapters."),
        _tool_schema("dl_validate_object", "Validate an OpenAPI-backed object payload without mutation."),
        _tool_schema("dl_compile_guarded_rpc_request", "Compile a Delta v7 guarded RPC request contract."),
        _tool_schema("dl_plan_publish_from_saved", "Plan publish from a saved-branch readback artifact."),
        _tool_schema("dl_list_related_objects", "List related DataLens objects for entry ids."),
        _tool_schema("dl_get_dataset_schema", "Extract dataset schema and validate requested fields."),
        _tool_schema("dl_create_editor_chart_plan", "Plan guarded createEditorChart payload; does not execute."),
        _tool_schema("dl_update_editor_chart_plan", "Plan guarded updateEditorChart payload; save by default."),
        _tool_schema("dl_create_wizard_chart_plan", "Plan guarded createWizardChart for a supported native visualization."),
        _tool_schema(
            "dl_update_wizard_chart_plan",
            "Plan a Wizard update derived from fresh saved readback while preserving visualization technology.",
        ),
        _tool_schema("dl_create_dashboard_plan", "Plan guarded createDashboard payload; does not execute."),
        _tool_schema("dl_update_dashboard_plan", "Plan guarded updateDashboard payload; save by default."),
        _tool_schema("dl_create_connector_plan", "Plan guarded createConnection payload; does not execute."),
        _tool_schema("dl_update_connector_plan", "Plan guarded updateConnection payload; does not execute."),
        _tool_schema("dl_create_dataset_plan", "Plan guarded createDataset payload; does not execute."),
        _tool_schema("dl_update_dataset_plan", "Plan guarded updateDataset payload; does not execute."),
        _tool_schema("dl_plan_guarded_dataset_update", "Plan validateDataset/updateDataset with GUID preservation and saved readback."),
        _tool_schema("dl_plan_dashboard_tab_update", "Plan append/replace of one dashboard tab while preserving unrelated tabs."),
        _tool_schema("dl_create_dataset_field_plan", "Schema-only dataset field create spec; API method not implemented."),
        _tool_schema("dl_update_dataset_field_plan", "Schema-only dataset field update spec; API method not implemented."),
        _tool_schema("dl_create_calculated_field_plan", "Schema-only calculated field create spec; API method not implemented."),
        _tool_schema("dl_update_calculated_field_plan", "Schema-only calculated field update spec; API method not implemented."),
        _tool_schema("dl_save_object_plan", "Plan guarded object update with mode save."),
        _tool_schema("dl_publish_object_plan", "Plan guarded object update with mode publish."),
        _tool_schema("dl_reconcile_partial_creates", "Match planned creates to existing workbook objects without deletion."),
        _tool_schema("dl_list_api_methods", "List curated DataLens API method catalog."),
        _tool_schema("dl_get_api_method_schema", "Return compact method schema from curated catalog."),
        _tool_schema("dl_rpc_readonly", "Call a curated read-only DataLens RPC method."),
        _tool_schema("dl_rpc_expert", "Expert raw RPC call, disabled unless explicitly enabled."),
        _tool_schema("dl_build_workbook_source_resolution", "Build workbook source resolution from read-only evidence."),
        _tool_schema("dl_build_selector_wiring_summary", "Validate selector wiring preservation for dashboard updates."),
        _tool_schema("dl_build_runtime_verification_plan", "Build a saved-only disposable runtime verification plan."),
        _tool_schema("dl_run_wizard_to_js_plan", "Build a Wizard-to-JS plan from local classification artifacts."),
    )


def list_tools(profile: str | None = None) -> list[dict[str, Any]]:
    names = STANDARD_TOOL_NAMES if profile is None else tool_names_for_profile(profile)
    return [deepcopy(tool) for tool in _all_tool_schemas() if tool["name"] in names]


def list_test_tools(profile: str = "all") -> list[dict[str, Any]]:
    return list_tools(profile)


def tool_names_for_profile(profile: str) -> set[str]:
    normalized = normalize_tool_profile(profile)
    return TOOL_PROFILE_MEMBERS[normalized]


def normalize_tool_profile(profile: str) -> str:
    normalized = str(profile or DEFAULT_TOOL_SURFACE).strip().lower()
    if normalized not in TOOL_PROFILE_MEMBERS:
        allowed = ", ".join(sorted(TOOL_PROFILE_MEMBERS))
        raise ValueError(f"unknown MCP tool profile {normalized!r}; allowed profiles: {allowed}; policy=error")
    return normalized


def _input_schema_for_tool(
    name: str,
    *,
    properties: dict[str, Any] | None,
    required: list[str] | None,
) -> dict[str, Any]:
    schema_properties = dict(properties or {})
    fn = TOOLS.get(name)
    if fn:
        for param_name, param in inspect.signature(fn).parameters.items():
            if param_name == "client" or param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
                continue
            if name in STANDARD_TOOL_NAMES and param_name in {
                "approved",
                "approval_source",
                "approved_plan_path",
                "approval_provenance",
            }:
                continue
            schema_properties.setdefault(param_name, _schema_for_parameter(name, param_name, param))
        if name in HEAVY_TOOL_NAMES:
            schema_properties.setdefault(
                "response_mode",
                {"type": "string", "enum": ["summary", "full"], "default": "summary"},
            )
            schema_properties.setdefault(
                "inline_char_budget",
                {"type": "integer", "minimum": 1000, "default": DEFAULT_HEAVY_INLINE_CHAR_BUDGET},
            )
        if name in PROJECT_CONTEXT_AWARE_TOOLS:
            schema_properties.setdefault(
                "context_ref",
                {"type": "object"},
            )
            schema_properties.setdefault(
                "evidence_refs",
                {
                    "type": "array",
                    "items": {"type": "object"},
                },
            )
    required_fields = required if required is not None else TOOL_REQUIRED_FIELDS.get(name, [])
    schema: dict[str, Any] = {
        "type": "object",
        "properties": schema_properties,
        "additionalProperties": False,
    }
    if required_fields:
        schema["required"] = required_fields
    if name == "dl_get_workbook_entries":
        schema["properties"]["workbook_id"].pop("default", None)
        schema["oneOf"] = [
            {"required": ["workbook_id"]},
            {"required": ["workbook_ids"]},
        ]
    elif name == "dl_validate_editor_runtime_contract":
        schema["oneOf"] = [
            {"required": ["entry"]},
            {"required": ["sections"]},
            {"required": ["artifact_paths"]},
        ]
    return schema


def _schema_for_parameter(tool_name: str, name: str, param: inspect.Parameter) -> dict[str, Any]:
    schema = dict(TOOL_PARAM_OVERRIDES.get((tool_name, name), PARAM_OVERRIDES.get(name, _schema_from_annotation(param.annotation))))
    description = PARAM_DESCRIPTIONS.get(name)
    if name not in COMPACT_SCHEMA_DESCRIPTION_PARAMS and description:
        schema.setdefault("description", description)
    if (
        param.default is not inspect._empty
        and param.default is not None
        and param.default != ""
        and _json_scalar(param.default)
    ):
        schema.setdefault("default", param.default)
    return schema


def _schema_from_annotation(annotation: Any) -> dict[str, Any]:
    text = str(annotation).replace(" ", "")
    has_dict_list = "list[dict" in text
    has_standalone_dict = text.startswith("dict[") or "|dict[" in text
    if has_dict_list and has_standalone_dict:
        return {
            "anyOf": [
                {"type": "object"},
                {"type": "array", "items": {"type": "object"}},
            ]
        }
    if has_dict_list:
        return {"type": "array", "items": {"type": "object"}}
    if "list" in text:
        if "list[bool" in text:
            item_type = "boolean"
        elif "list[int" in text:
            item_type = "integer"
        elif "list[float" in text:
            item_type = "number"
        elif "list[Any" in text:
            return {"type": "array", "items": {}}
        else:
            item_type = "string"
        return {"type": "array", "items": {"type": item_type}}
    if "bool" in text:
        return {"type": "boolean"}
    if "int" in text:
        return {"type": "integer"}
    if "float" in text:
        return {"type": "number"}
    if "dict" in text or "Any" in text:
        return {"type": "object"}
    return {"type": "string"}


def _json_scalar(value: Any) -> bool:
    return isinstance(value, str | int | float | bool)


def _translate_legacy_standard_tool_arguments(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    arguments = dict(raw)
    if name in {"dl_auth_probe", "dl_validate_object"}:
        arguments.pop("project_root", None)
    legacy_plan_path = arguments.pop("approved_plan_path", None)
    if legacy_plan_path and not arguments.get("plan_path"):
        arguments["plan_path"] = legacy_plan_path
    legacy_approved = arguments.pop("approved", None)
    arguments.pop("approval_source", None)
    arguments.pop("approval_provenance", None)
    if name == "dl_plan_project_manifest" and legacy_approved is not None and "write_manifest" not in arguments:
        arguments["write_manifest"] = bool(legacy_approved)
    legacy_guid_changes = arguments.pop("approve_guid_changes", None)
    if (
        name == "dl_plan_guarded_dataset_update"
        and legacy_guid_changes is not None
        and "allow_guid_changes" not in arguments
    ):
        arguments["allow_guid_changes"] = bool(legacy_guid_changes)
    return arguments


class JsonRpcServer:
    def __init__(self, *, project_root: str = ".", local_config_path: str | None = None) -> None:
        # Fill missing values from the canonical env file without replacing
        # explicit process-level hard-off switches.
        load_env_file(
            os.getenv("DATALENS_ENV_FILE"),
            override=False,
            skip_keys=EXECUTION_SWITCH_ENV_NAMES,
        )
        self.project_root = str(Path(project_root).expanduser().resolve())
        self.local_config = load_local_config(local_config_path, project_root=self.project_root)

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if "id" not in message:
            return None
        method = message.get("method")
        params = message.get("params") or {}
        try:
            if method == "initialize":
                tool_count = len(list_tools())
                result = {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    "serverInfo": {"name": "datalens-dev-mcp", "version": __version__},
                    "instructions": (
                        f"DataLens MCP standard tool surface: {tool_count} tools. "
                        "Normal sequence: resolve target; snapshot/read; reference/diagnose; "
                        "generate/validate locally; plan; safe apply; saved readback; "
                        "publish from saved readback; published readback and runtime check. "
                        "An explicit create/fix/update/redesign request authorizes guarded save and publish without another question. "
                        "Review, audit, diagnose, plan-only, save-only, and no-publish wording limits execution accordingly. "
                        "Arbitrary whole-object deletion is unsupported; "
                        "retire_legacy_objects alone requires a second call with "
                        "confirm_delete=true for the unchanged plan. "
                        "Writes remain guarded by runtime enablement, target lock, fresh reads, "
                        "revision preservation, save semantics, and readback."
                    ),
                }
            elif method == "tools/list":
                tools = list_tools()
                result = {"tools": tools, "tool_surface": DEFAULT_TOOL_SURFACE, "tool_count": len(tools)}
            elif method == "tools/call":
                result = self._call_tool(params)
            elif method == "resources/list":
                result = {"resources": list_resources()}
            elif method == "resources/read":
                uri = params["uri"]
                resource = read_resource(uri, project_root=self.project_root)
                public_text = project_public_resource_text(
                    resource["text"],
                    allowed_tool_names=STANDARD_TOOL_NAMES,
                )
                result = {"contents": [{"uri": uri, "mimeType": resource["mimeType"], "text": public_text}]}
            elif method == "prompts/list":
                result = {"prompts": list_prompts()}
            elif method == "prompts/get":
                result = get_prompt(params["name"])
            else:
                return self._error(message["id"], -32601, f"Method not found: {method}")
            return {"jsonrpc": "2.0", "id": message["id"], "result": result}
        except Exception as exc:  # noqa: BLE001
            return self._error(message["id"], -32000, _safe_error(exc))

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params["name"]
        if name not in TOOLS:
            raise KeyError(f"Unknown tool {name}")
        if name not in STANDARD_TOOL_NAMES and not hidden_tool_calls_enabled():
            raise DataLensSafetyError(f"{name} is not exposed on the standard MCP tool surface")
        fn = TOOLS[name]
        signature = _cached_tool_signature(fn)
        raw_arguments = _translate_legacy_standard_tool_arguments(name, params.get("arguments") or {})
        arguments = apply_tool_defaults(
            name,
            raw_arguments,
            self.local_config,
            project_root=self.project_root,
            supports_project_root="project_root" in signature.parameters,
            supports_workbook_id="workbook_id" in signature.parameters,
            supports_readback_mode="readback_mode" in signature.parameters,
        )
        heavy_response_mode = "summary"
        heavy_inline_char_budget = DEFAULT_HEAVY_INLINE_CHAR_BUDGET
        if name in HEAVY_TOOL_NAMES:
            heavy_response_mode = str(arguments.pop("response_mode", "summary") or "summary")
            heavy_inline_char_budget = int(
                arguments.pop("inline_char_budget", DEFAULT_HEAVY_INLINE_CHAR_BUDGET)
                or DEFAULT_HEAVY_INLINE_CHAR_BUDGET
            )
        context_ref = arguments.pop("context_ref", None)
        evidence_refs = arguments.pop("evidence_refs", None)
        if "local_config_path" in signature.parameters and not arguments.get("local_config_path"):
            arguments["local_config_path"] = str((self.local_config.get("_meta") or {}).get("config_path") or "")
        try:
            normalized_context = None
            normalized_evidence: list[dict[str, Any]] = []
            if name in PROJECT_CONTEXT_AWARE_TOOLS:
                normalized_context, normalized_evidence = validate_project_contract_inputs(
                    arguments.get("project_root", self.project_root),
                    context_ref,
                    evidence_refs,
                )
            with use_api_defaults(self.local_config.get("api_defaults") or {}):
                output = fn(**arguments)
            if name in PROJECT_CONTEXT_AWARE_TOOLS:
                output = finalize_project_contract_result(
                    name,
                    output,
                    project_root=arguments.get("project_root", self.project_root),
                    context_ref=normalized_context,
                    consumed_evidence=normalized_evidence,
                )
            if name in HEAVY_TOOL_NAMES:
                output = project_heavy_tool_response(
                    name,
                    output,
                    response_mode=heavy_response_mode,
                    inline_char_budget=heavy_inline_char_budget,
                    project_root=arguments.get("project_root", self.project_root),
                    run_id="",
                )
        except Exception as exc:  # noqa: BLE001
            public_error = sanitize_response(
                project_public_response(
                    _structured_tool_error(name, exc),
                    allowed_tool_names=STANDARD_TOOL_NAMES,
                )
            )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            public_error,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                    }
                ],
                "isError": True,
            }
        public_output = sanitize_response(
            project_public_response(
                output,
                allowed_tool_names=STANDARD_TOOL_NAMES,
            )
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(public_output, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                }
            ],
            "isError": False,
        }

    @staticmethod
    def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


@lru_cache(maxsize=None)
def _cached_tool_signature(fn: Callable[..., Any]) -> inspect.Signature:
    return inspect.signature(fn)


def _safe_error(exc: Exception) -> str:
    text = redact_text(str(exc))
    return text or exc.__class__.__name__


def _structured_tool_error(name: str, exc: Exception) -> dict[str, Any]:
    category = "unknown_runtime_error"
    if isinstance(exc, DataLensSafetyError):
        category = "unsafe_sensitive_input"
    elif isinstance(exc, RuntimeResourceError):
        category = exc.category
    elif isinstance(exc, DataLensApiError):
        lowered = str(exc).lower()
        if "auth" in lowered or "401" in lowered or "blocked_live_credentials" in lowered or "missing datalens" in lowered:
            category = "auth_failure"
        elif "required" in lowered:
            category = "missing_input"
        else:
            category = "datalens_api_error"
    elif isinstance(exc, FileNotFoundError):
        category = "missing_input"
    elif isinstance(exc, TypeError) and "required positional argument" in str(exc):
        category = "missing_input"
    elif isinstance(exc, ValueError):
        lowered = str(exc).lower()
        category = (
            "missing_input"
            if "required" in lowered or "must be provided" in lowered
            else "datalens_validation_error"
        )
    return {"ok": False, "tool": name, "error": {"category": category, "message": _safe_error(exc)}}


def serve_stdio(*, project_root: str = ".", local_config_path: str | None = None) -> None:
    server = JsonRpcServer(project_root=project_root, local_config_path=local_config_path)
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
            response = server.handle(message)
        except Exception:  # noqa: BLE001
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            print(traceback.format_exc(), file=sys.stderr)
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the datalens-dev-mcp stdio server.")
    parser.add_argument("--project-root", default=".", help="Default project root for resource/tool calls.")
    parser.add_argument("--local-config", default=None, help="Optional local MCP config JSON path.")
    args = parser.parse_args(argv)
    serve_stdio(project_root=args.project_root, local_config_path=args.local_config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
