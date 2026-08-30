from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from datalens_dev_mcp.pipeline.evidence_matrix import normalize_browser_policy


BrowserQaStatus = Literal[
    "browser_pass",
    "browser_fail",
    "browser_auth_required",
    "browser_tool_timeout",
    "browser_not_authorized_by_user",
    "not_checked",
]

RUNTIME_ERROR_MARKERS = [
    "ERR.DS_API.FIELD.NOT_FOUND",
    "FIELD.NOT_FOUND",
    "UNKNOWN_IDENTIFIER",
    "DB::Exception",
    "502 Bad Gateway",
    "Using non-existent field",
    "Unknown field",
    "Data fetching error",
]

BROWSER_QA_PLAN_SCHEMA_ID = "datalens.browser-qa-plan"
BROWSER_QA_RESULT_SCHEMA_ID = "datalens.browser-qa-result"
BROWSER_QA_DEFAULT_VIEWPORTS = (
    {"id": "desktop", "width": 1200, "height": 900},
)
BROWSER_QA_RESPONSIVE_VIEWPORTS = (
    {"id": "narrow", "width": 720, "height": 900},
    {"id": "compact_desktop", "width": 1200, "height": 900},
    {"id": "wide", "width": 1440, "height": 900},
)
BROWSER_QA_ASSERTIONS = (
    {
        "id": "objects_visible_nonempty",
        "description": "Every expected dashboard object has visible, non-empty rendered content.",
    },
    {
        "id": "no_error_retry_markers",
        "description": "The rendered dashboard contains no Error or Retry marker.",
    },
    {
        "id": "document_no_horizontal_overflow",
        "description": "The document does not overflow the viewport horizontally.",
    },
    {
        "id": "objects_not_clipped_or_paint_overflow",
        "description": "Expected objects stay in the viewport and painted descendants stay in their containers.",
    },
    {
        "id": "kpi_surface_contract",
        "description": "KPI surfaces have no border, radius, outline, shadow, or opaque background.",
    },
    {
        "id": "kpi_content_visibility_contract",
        "description": (
            "Every strict KPI has a visible non-empty value inside an unclipped tile, "
            "and KPI tiles use one height within the dashboard set."
        ),
    },
    {
        "id": "legend_typography_consistent",
        "description": "Legend typography has one size and matches the render contract.",
    },
    {
        "id": "active_series_legend_consistent",
        "description": "Legend entries match the series marks produced from filtered result rows.",
    },
    {
        "id": "coordinate_plot_insets_consistent",
        "description": "Coordinate plot areas use the registered top, right, and bottom insets.",
    },
    {
        "id": "selector_interaction_layout_contract",
        "description": (
            "Selectors use left labels, immediate changes, no apply control, "
            "44 px rows, and at most 94% width."
        ),
    },
    {
        "id": "selector_order_row_contract",
        "description": (
            "Configured selectors preserve their declared order, keep the period first when present, "
            "stay on one row, and occupy the registered aggregate width."
        ),
    },
    {
        "id": "comparison_context_cardinality",
        "description": "Comparison context count is exactly one when enabled and zero otherwise.",
    },
    {
        "id": "comparison_context_placement",
        "description": (
            "When comparison is enabled, one visible non-empty context follows the "
            "contiguous selector group in the same column and precedes the first content object."
        ),
    },
    {
        "id": "semantic_height_contract",
        "description": "Comparison context uses its registered minimum height without clipping.",
    },
    {
        "id": "tooltip_owner_shell_cardinality",
        "description": "A visible tooltip has one shell, one owner, and a borderless square flat surface.",
    },
    {
        "id": "tooltip_comparison_mode_contract",
        "description": (
            "Strict chart tooltips use normalized periods and expose comparison labels only for "
            "widgets whose persisted visual contract enables comparison."
        ),
    },
    {
        "id": "stable_scrollbar_gutter",
        "description": "A required horizontal-rank scroll container reserves a stable scrollbar gutter.",
    },
    {
        "id": "no_redundant_row_title_tooltips",
        "description": "Chart rows do not repeat their visible label in a native title tooltip.",
    },
    {
        "id": "role_owned_title_contract",
        "description": "Every title and hint is rendered by exactly the surface assigned by title_mode.",
    },
    {
        "id": "semantic_row_geometry_contract",
        "description": "Adjacent semantic blocks have equal heights and no undeclared vertical gap.",
    },
    {
        "id": "kpi_density_contract",
        "description": "A standard row contains at most three KPI objects unless the attested override applies.",
    },
    {
        "id": "selector_clear_contract",
        "description": "Blank multiselect means all values and Clear does not restore a default value.",
    },
    {
        "id": "table_readability_contract",
        "description": "Tables have non-empty headers, meaningful sticky columns, and no unlabelled clipping.",
    },
    {
        "id": "lazy_full_scroll_contract",
        "description": "Every expected object initializes after each tab is checked at top and after full scroll.",
    },
)
BROWSER_QA_UNIVERSAL_ASSERTION_IDS = frozenset(
    {
        "objects_visible_nonempty",
        "document_no_horizontal_overflow",
        "objects_not_clipped_or_paint_overflow",
        "lazy_full_scroll_contract",
    }
)
BROWSER_QA_UNIVERSAL_ASSERTIONS = tuple(
    item for item in BROWSER_QA_ASSERTIONS if item["id"] in BROWSER_QA_UNIVERSAL_ASSERTION_IDS
)
BROWSER_QA_PROFILE_ASSERTIONS = tuple(
    item for item in BROWSER_QA_ASSERTIONS if item["id"] not in BROWSER_QA_UNIVERSAL_ASSERTION_IDS
)
BROWSER_QA_FORBIDDEN_SOURCE_TOKENS = (
    ".click(",
    ".focus(",
    ".blur(",
    "dispatchevent(",
    "setattribute(",
    "removeattribute(",
    "appendchild(",
    "removechild(",
    "replacechildren(",
    "insertadjacent",
    "innerhtml =",
    "outerhtml =",
    "textcontent =",
    "location.reload(",
    "history.pushstate(",
    "history.replacestate(",
    "window.location =",
    "document.location =",
    "new mutationobserver",
)


def build_browser_qa_plan(
    *,
    dashboard_id: str,
    tab_ids: list[str],
    expected_object_ids: list[str],
    dashboard_url: str = "",
    selector_contracts: list[dict[str, Any]] | None = None,
    comparison_enabled: bool = False,
    comparison_context_object_ids: list[str] | None = None,
    tooltip_comparison_modes: dict[str, str] | None = None,
    render_contract: dict[str, Any] | None = None,
    title_contracts: list[dict[str, Any]] | None = None,
    dashboard_composition: dict[str, Any] | None = None,
    saved_revision: str = "",
    published_revision: str = "",
    final_payload_attestation_sha256: str = "",
    payload_set_sha256: str = "",
    browser_policy: dict[str, Any] | None = None,
    api_diagnostics_receipt_hash: str = "",
    task_id: str = "",
    contract_revision: int = 0,
    plan_hash: str = "",
    candidate_build_identity: str = "",
    workbook_id: str = "",
    responsive_acceptance: bool = False,
    profile_assertions: list[dict[str, Any]] | None = None,
    active_provenance_hash: str = "",
    tab_object_ids: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Build a candidate-bound, read-only browser QA traversal plan."""

    normalized_dashboard_id = str(dashboard_id or "").strip()
    if not normalized_dashboard_id:
        raise ValueError("dashboard_id is required")
    normalized_object_ids = _normalized_string_list(expected_object_ids)
    if not normalized_object_ids:
        raise ValueError("expected_object_ids must contain at least one object id")
    normalized_tabs = _normalized_string_list(tab_ids)
    normalized_tab_objects = {
        str(tab_id): _normalized_string_list(list(object_ids or []))
        for tab_id, object_ids in (tab_object_ids or {}).items()
        if str(tab_id) in normalized_tabs
    }
    normalized_policy = normalize_browser_policy(
        browser_policy,
        change_class="dashboard_layout",
    )
    final_visual = normalized_policy["purpose"] == "final_visual_acceptance"
    normalized_dashboard_url = str(dashboard_url or "").strip()
    normalized_saved_revision = str(saved_revision or "").strip()
    normalized_published_revision = str(published_revision or "").strip()
    normalized_api_diagnostics_hash = str(api_diagnostics_receipt_hash or "").strip()
    normalized_plan_hash = str(plan_hash or "").strip()
    normalized_build_identity = str(candidate_build_identity or "").strip()
    if final_visual:
        if normalized_policy["mode"] == "forbidden":
            raise ValueError("forbidden browser policy cannot produce a final visual plan")
        if not normalized_dashboard_url:
            raise ValueError("final visual acceptance requires the canonical dashboard URL")
        if not normalized_tabs:
            raise ValueError("final visual acceptance requires API-derived tab ids")
        if len(normalized_tabs) == 1 and not normalized_tab_objects:
            normalized_tab_objects = {normalized_tabs[0]: normalized_object_ids}
        if set(normalized_tab_objects) != set(normalized_tabs):
            raise ValueError("final visual acceptance requires expected objects for every tab")
        if not normalized_saved_revision or not normalized_published_revision:
            raise ValueError("final visual acceptance requires exact saved and published revisions")
        if not re.fullmatch(r"[a-f0-9]{64}", normalized_api_diagnostics_hash):
            raise ValueError("final visual acceptance requires a completed API diagnostics receipt hash")
        if not str(task_id or "") or int(contract_revision or 0) < 1:
            raise ValueError("final visual acceptance requires task and contract revision binding")
        if not re.fullmatch(r"[a-f0-9]{64}", normalized_plan_hash):
            raise ValueError("final visual acceptance requires the exact plan hash")
        if not re.fullmatch(r"[a-f0-9]{64}", normalized_build_identity):
            raise ValueError("final visual acceptance requires the candidate build identity")
    normalized_selectors = _normalize_selector_contracts(selector_contracts or [])
    normalized_comparison_ids = _normalized_string_list(comparison_context_object_ids or [])
    normalized_tooltip_modes = _normalize_tooltip_comparison_modes(
        tooltip_comparison_modes or {}
    )
    normalized_render_contract = _normalize_browser_render_contract(render_contract or {})
    normalized_title_contracts = _normalize_title_contracts(title_contracts or [])
    normalized_composition = _normalize_composition_binding(dashboard_composition or {})
    viewports = [
        dict(viewport)
        for viewport in (
            BROWSER_QA_RESPONSIVE_VIEWPORTS if responsive_acceptance else BROWSER_QA_DEFAULT_VIEWPORTS
        )
    ]
    normalized_profile_assertions = _normalize_profile_assertions(
        profile_assertions or [],
        active_provenance_hash=str(active_provenance_hash or ""),
    )
    required_assertions = [
        *[dict(item) for item in BROWSER_QA_UNIVERSAL_ASSERTIONS],
        *normalized_profile_assertions,
    ]
    evaluation_input = {
        "expected_object_ids": normalized_object_ids,
        "required_assertion_ids": [assertion["id"] for assertion in required_assertions],
        "selector_contracts": normalized_selectors,
        "comparison_enabled": bool(comparison_enabled),
        "comparison_context_object_ids": normalized_comparison_ids,
        "tooltip_comparison_modes": normalized_tooltip_modes,
        "render_contract": normalized_render_contract,
        "title_contracts": normalized_title_contracts,
        "dashboard_composition": normalized_composition,
    }
    evaluate_source = _build_browser_qa_evaluate_source(evaluation_input)
    artifact_stem = _safe_artifact_stem(normalized_dashboard_id)
    plan: dict[str, Any] = {
        "schema_id": BROWSER_QA_PLAN_SCHEMA_ID,
        "browser_policy": normalized_policy,
        "prerequisites": {
            "published_readback_complete": bool(normalized_saved_revision and normalized_published_revision),
            "api_diagnostics_complete": bool(normalized_api_diagnostics_hash),
            "api_diagnostics_receipt_hash": normalized_api_diagnostics_hash,
            "task_id": str(task_id or ""),
            "contract_revision": int(contract_revision or 0),
            "plan_hash": normalized_plan_hash,
            "candidate_build_identity": normalized_build_identity,
        },
        "target": {
            "dashboard_id": normalized_dashboard_id,
            "dashboard_url": normalized_dashboard_url,
            "object_kind": "dashboard",
            "workbook_id": str(workbook_id or ""),
            "tab_ids": normalized_tabs,
            "expected_object_ids": normalized_object_ids,
            "tab_object_ids": normalized_tab_objects,
            "saved_revision": normalized_saved_revision,
            "published_revision": normalized_published_revision,
        },
        "attestation_binding": {
            "final_payload_attestation_sha256": str(final_payload_attestation_sha256 or "").strip(),
            "payload_set_sha256": str(payload_set_sha256 or "").strip(),
            "dashboard_composition_sha256": str((dashboard_composition or {}).get("sha256") or ""),
            "api_diagnostics_receipt_hash": normalized_api_diagnostics_hash,
            "candidate_build_identity": normalized_build_identity,
            "contract_revision": int(contract_revision or 0),
            "plan_hash": normalized_plan_hash,
            "task_id": str(task_id or ""),
        },
        "viewports": viewports,
        "render_contract": normalized_render_contract,
        "selector_contracts": normalized_selectors,
        "comparison_enabled": bool(comparison_enabled),
        "comparison_context_object_ids": normalized_comparison_ids,
        "tooltip_comparison_modes": normalized_tooltip_modes,
        "title_contracts": normalized_title_contracts,
        "dashboard_composition": normalized_composition,
        "assertion_scope": {
            "universal_assertion_ids": [item["id"] for item in BROWSER_QA_UNIVERSAL_ASSERTIONS],
            "profile_assertions": normalized_profile_assertions,
            "active_provenance_hash": str(active_provenance_hash or ""),
        },
        "execution": {
            "browser_route": "internal_browser_adapter",
            "bounded_call_count": 2,
            "navigation_count": 1,
            "reload_count": 0,
            "retry_count": 0,
            "dom_mutation_allowed": False,
            "actual_tab_activation_required": final_visual,
            "viewport_increment_scroll_required": final_visual,
            "condition_based_wait_required": final_visual,
            "allowed_interactions": list(normalized_policy["allowed_interactions"]),
            "forbidden_interactions": [
                "change_selector",
                "clear_selector",
                "apply_filter",
                "reset_filter",
                "cross_filter_click",
                "mutation",
            ],
            "calls": [
                {
                    "ordinal": 1,
                    "operation": "navigate_once",
                    "dashboard_url": str(dashboard_url or "").strip(),
                    "dashboard_id": normalized_dashboard_id,
                    "resolve_url_when_missing": not bool(str(dashboard_url or "").strip()),
                },
                {
                    "ordinal": 2,
                    "operation": "traverse_tabs_and_capture",
                    "viewport_ids": [viewport["id"] for viewport in viewports],
                    "tab_ids": normalized_tabs,
                    "required_observations": [
                        "activation_observed",
                        "top_observed",
                        "scroll_checkpoint_count",
                        "scroll_reached_bottom",
                        "observed_object_ids",
                        "loading_object_ids",
                        "visible_error_object_ids",
                        "global_error_markers",
                        "no_data_object_ids",
                        "layout_findings",
                        "screenshot_ref",
                    ],
                    "wait_for_lazy_initialization": True,
                    "ephemeral_interactions": [],
                    "persisted_state_mutation_allowed": False,
                    "evaluate_source_ref": "#/evaluate/source",
                    "compact_screenshot_per_tab": True,
                },
            ],
        },
        "evaluate": {
            "language": "javascript",
            "read_only": True,
            "source": evaluate_source,
            "assertions": required_assertions,
        },
        "expected_result": {
            "schema_id": BROWSER_QA_RESULT_SCHEMA_ID,
            "required_fields": ["viewport", "passed", "assertions", "observations"],
            "assertion_ids": [assertion["id"] for assertion in required_assertions],
            "pass_condition": "all_assertions_true",
            "maximum_failed_assertions": 0,
        },
        "artifacts": {
            "directory": "artifacts/browser_qa",
            "plan": f"{artifact_stem}.plan.json",
            "summary": f"{artifact_stem}.summary.json",
            "viewports": [
                {
                    "viewport_id": viewport["id"],
                    "evaluation": f"{artifact_stem}.{viewport['width']}x{viewport['height']}.result.json",
                    "screenshot": f"{artifact_stem}.{viewport['width']}x{viewport['height']}.png",
                }
                for viewport in viewports
            ],
        },
    }
    plan["canonical_sha256"] = browser_qa_plan_sha256(plan)
    return plan


def execute_browser_qa_by_policy(
    *,
    browser_policy: dict[str, Any],
    adapter: Any,
    plan: dict[str, Any],
    execute_optional: bool = False,
) -> dict[str, Any]:
    """Call the internal adapter only when policy permits it; forbidden means zero calls."""
    policy = normalize_browser_policy(browser_policy, change_class="dashboard_layout")
    mode = policy["mode"]
    if mode == "forbidden":
        return {
            "ok": True,
            "status": "browser_forbidden_skipped",
            "adapter_calls": 0,
            "proof_level": "contract_runtime",
            "browser_rendered": False,
        }
    if mode == "optional" and not execute_optional:
        return {
            "ok": True,
            "status": "browser_optional_skipped",
            "adapter_calls": 0,
            "proof_level": "contract_runtime",
            "browser_rendered": False,
        }
    if policy["applicability"] == "not_applicable":
        return {
            "ok": True,
            "status": "browser_not_applicable_skipped",
            "adapter_calls": 0,
            "proof_level": "contract_runtime",
            "browser_rendered": False,
        }
    result = adapter(plan)
    return {
        "ok": bool(isinstance(result, dict) and result.get("ok")),
        "status": str((result or {}).get("status") or "browser_adapter_completed"),
        "adapter_calls": 1,
        "proof_level": "browser_rendered",
        "browser_rendered": True,
        "result": result,
    }


def browser_qa_plan_sha256(plan: dict[str, Any]) -> str:
    canonical = {key: value for key, value in plan.items() if key != "canonical_sha256"}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_browser_qa_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate the deterministic browser plan without executing it."""

    issues: list[str] = []
    if not isinstance(plan, dict) or plan.get("schema_id") != BROWSER_QA_PLAN_SCHEMA_ID:
        return {"ok": False, "issues": ["invalid_schema_id"]}

    viewports = plan.get("viewports")
    if not isinstance(viewports, list) or not viewports:
        issues.append("applicable_viewport_missing")

    execution = plan.get("execution") if isinstance(plan.get("execution"), dict) else {}
    policy = normalize_browser_policy(
        plan.get("browser_policy") if isinstance(plan.get("browser_policy"), dict) else {},
        change_class="dashboard_layout",
    )
    final_visual = policy["purpose"] == "final_visual_acceptance"
    calls = execution.get("calls") if isinstance(execution.get("calls"), list) else []
    bounded_calls = execution.get("bounded_call_count")
    if not isinstance(bounded_calls, int) or bounded_calls < 1 or bounded_calls != len(calls):
        issues.append("browser_call_ledger_mismatch")
    expected_operations = ["navigate_once", "traverse_tabs_and_capture"]
    if [call.get("operation") for call in calls if isinstance(call, dict)] != expected_operations:
        issues.append("browser_call_sequence_changed")
    if execution.get("navigation_count") != 1:
        issues.append("navigation_count_changed")
    if execution.get("reload_count") != 0 or execution.get("retry_count") != 0:
        issues.append("reload_or_retry_not_allowed")
    if execution.get("dom_mutation_allowed") is not False:
        issues.append("dom_mutation_must_be_disabled")
    evaluation_call = next(
        (call for call in calls if isinstance(call, dict) and call.get("operation") == "traverse_tabs_and_capture"),
        {},
    )
    if evaluation_call.get("wait_for_lazy_initialization") is not True:
        issues.append("lazy_initialization_wait_missing")
    if evaluation_call.get("ephemeral_interactions") != []:
        issues.append("default_visual_qa_must_not_change_selectors_or_filters")
    if evaluation_call.get("persisted_state_mutation_allowed") is not False:
        issues.append("persisted_state_mutation_must_be_disabled")
    if evaluation_call.get("tab_ids") != (plan.get("target") or {}).get("tab_ids"):
        issues.append("all_tabs_not_bound_to_evaluation")
    forbidden_interactions = set(execution.get("forbidden_interactions") or [])
    if not {"change_selector", "clear_selector", "apply_filter", "reset_filter"}.issubset(
        forbidden_interactions
    ):
        issues.append("visual_interaction_boundary_missing")
    if final_visual:
        target = plan.get("target") if isinstance(plan.get("target"), dict) else {}
        prerequisites = plan.get("prerequisites") if isinstance(plan.get("prerequisites"), dict) else {}
        if target.get("object_kind") != "dashboard" or not str(target.get("dashboard_url") or ""):
            issues.append("final_visual_target_must_be_exact_dashboard_url")
        if not target.get("saved_revision") or not target.get("published_revision"):
            issues.append("final_visual_revision_binding_missing")
        if prerequisites.get("published_readback_complete") is not True:
            issues.append("published_readback_prerequisite_missing")
        if prerequisites.get("api_diagnostics_complete") is not True or not re.fullmatch(
            r"[a-f0-9]{64}", str(prerequisites.get("api_diagnostics_receipt_hash") or "")
        ):
            issues.append("api_diagnostics_prerequisite_missing")
        for field_name in ("task_id", "contract_revision", "plan_hash", "candidate_build_identity"):
            if not prerequisites.get(field_name):
                issues.append(f"candidate_binding_missing:{field_name}")
        if policy["mode"] == "forbidden":
            issues.append("forbidden_policy_cannot_produce_browser_plan")
        if execution.get("actual_tab_activation_required") is not True:
            issues.append("actual_tab_activation_required")
        if execution.get("viewport_increment_scroll_required") is not True:
            issues.append("viewport_increment_scroll_required")
        if execution.get("condition_based_wait_required") is not True:
            issues.append("condition_based_wait_required")

    evaluate = plan.get("evaluate") if isinstance(plan.get("evaluate"), dict) else {}
    source = evaluate.get("source")
    if not isinstance(source, str) or not source.strip():
        issues.append("evaluate_source_missing")
        source = ""
    lowered_source = source.lower()
    for token in BROWSER_QA_FORBIDDEN_SOURCE_TOKENS:
        if token in lowered_source:
            issues.append(f"forbidden_evaluate_token:{token}")
    for primitive in ("querySelector", "getComputedStyle", "getBoundingClientRect"):
        if primitive not in source:
            issues.append(f"required_read_primitive_missing:{primitive}")

    assertions = evaluate.get("assertions") if isinstance(evaluate.get("assertions"), list) else []
    assertion_ids = {
        str(assertion.get("id") or "")
        for assertion in assertions
        if isinstance(assertion, dict)
    }
    required_assertion_ids = {assertion["id"] for assertion in BROWSER_QA_UNIVERSAL_ASSERTIONS}
    if not required_assertion_ids.issubset(assertion_ids):
        issues.append("required_assertions_missing")

    comparison_ids = plan.get("comparison_context_object_ids")
    if (
        not isinstance(comparison_ids, list)
        or any(not isinstance(item, str) or not item.strip() for item in comparison_ids)
        or comparison_ids != sorted(set(comparison_ids))
    ):
        issues.append("comparison_context_object_ids_not_sorted_unique")
        comparison_ids = []
    encoded_comparison_ids = json.dumps(
        comparison_ids,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if f'"comparison_context_object_ids":{encoded_comparison_ids}' not in source:
        issues.append("comparison_context_object_ids_not_bound_to_evaluate_source")
    if not isinstance(plan.get("comparison_enabled"), bool):
        issues.append("comparison_enabled_must_be_boolean")
    selector_contracts = plan.get("selector_contracts")
    selector_ids: list[str] = []
    if not isinstance(selector_contracts, list):
        issues.append("selector_contracts_invalid")
        selector_contracts = []
    else:
        for index, item in enumerate(selector_contracts):
            if not isinstance(item, dict):
                issues.append("selector_contracts_invalid")
                continue
            selector_id = str(item.get("selector_id") or "")
            if (
                not selector_id
                or item.get("ordinal") != index
                or str(item.get("role") or "") not in {"", "period"}
            ):
                issues.append("selector_contracts_invalid")
            selector_ids.append(selector_id)
        if len(selector_ids) != len(set(selector_ids)):
            issues.append("selector_contract_ids_not_unique")
    encoded_selector_contracts = json.dumps(
        selector_contracts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if f'"selector_contracts":{encoded_selector_contracts}' not in source:
        issues.append("selector_contracts_not_bound_to_evaluate_source")
    tooltip_modes = plan.get("tooltip_comparison_modes")
    if (
        not isinstance(tooltip_modes, dict)
        or list(tooltip_modes) != sorted(tooltip_modes)
        or any(
            not isinstance(object_id, str)
            or not object_id.strip()
            or mode not in {"single_period", "comparison"}
            for object_id, mode in tooltip_modes.items()
        )
    ):
        issues.append("tooltip_comparison_modes_invalid")
        tooltip_modes = {}
    encoded_tooltip_modes = json.dumps(
        tooltip_modes,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if f'"tooltip_comparison_modes":{encoded_tooltip_modes}' not in source:
        issues.append("tooltip_comparison_modes_not_bound_to_evaluate_source")
    title_contracts = plan.get("title_contracts")
    if not isinstance(title_contracts, list):
        issues.append("title_contracts_invalid")
        title_contracts = []
    encoded_title_contracts = json.dumps(
        title_contracts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if f'"title_contracts":{encoded_title_contracts}' not in source:
        issues.append("title_contracts_not_bound_to_evaluate_source")
    composition = plan.get("dashboard_composition")
    if not isinstance(composition, dict):
        issues.append("dashboard_composition_binding_invalid")
        composition = {}
    encoded_composition = json.dumps(
        composition,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if f'"dashboard_composition":{encoded_composition}' not in source:
        issues.append("dashboard_composition_not_bound_to_evaluate_source")

    render_contract = (
        plan.get("render_contract")
        if isinstance(plan.get("render_contract"), dict)
        else {}
    )
    horizontal_rank = (
        render_contract.get("horizontal_rank")
        if isinstance(render_contract.get("horizontal_rank"), dict)
        else {}
    )
    scroll_object_ids = horizontal_rank.get("scroll_object_ids")
    if (
        not isinstance(scroll_object_ids, list)
        or any(not isinstance(item, str) or not item.strip() for item in scroll_object_ids)
        or scroll_object_ids != sorted(set(scroll_object_ids))
    ):
        issues.append("horizontal_scroll_object_ids_not_sorted_unique")

    expected_hash = plan.get("canonical_sha256")
    if not isinstance(expected_hash, str) or expected_hash != browser_qa_plan_sha256(plan):
        issues.append("canonical_sha256_mismatch")
    return {"ok": not issues, "issues": issues}


def _build_browser_qa_evaluate_source(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return """(() => {
  "use strict";
  const input = __QA_INPUT__;
  const all = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = (node) => String(node && node.textContent || "").replace(/\\s+/g, " ").trim();
  const rect = (node) => node.getBoundingClientRect();
  const computed = (node) => window.getComputedStyle(node);
  const visible = (node) => {
    const box = rect(node);
    const css = computed(node);
    return box.width > 0 && box.height > 0 && css.display !== "none" &&
      css.visibility !== "hidden" && Number(css.opacity || 1) > 0;
  };
  const findObject = (objectId) => all("[data-widget-id],[data-object-id],[data-qa],[id]").find((node) =>
    node.getAttribute("data-widget-id") === objectId ||
    node.getAttribute("data-object-id") === objectId ||
    node.getAttribute("data-qa") === objectId ||
    node.id === objectId
  );
  const objectRows = input.expected_object_ids.map((objectId) => {
    const node = findObject(objectId);
    if (!node) return {object_id: objectId, found: false, visible: false, nonempty: false};
    const box = rect(node);
    const painted = all("canvas,svg,img", node).filter(visible);
    const paint_inside = painted.every((child) => {
      const childBox = rect(child);
      return childBox.left >= box.left - 1 && childBox.right <= box.right + 1 &&
        childBox.top >= box.top - 1 && childBox.bottom <= box.bottom + 1;
    });
    return {
      object_id: objectId,
      found: true,
      visible: visible(node),
      nonempty: text(node).length > 0 || painted.length > 0,
      viewport_contained: box.left >= -1 && box.right <= window.innerWidth + 1 && box.bottom >= 0,
      paint_inside
    };
  });
  const bodyText = text(document.querySelector("body"));
  const markerMatches = ["Error", "Retry"].filter((marker) =>
    new RegExp("\\\\b" + marker + "\\\\b", "i").test(bodyText)
  );
  const root = document.querySelector("html");
  const documentOverflow = root ? root.scrollWidth - root.clientWidth : 0;

  const kpis = all('[data-role="kpi"],[data-visualization="kpi"],.metric-tile,.kpi').filter(visible);
  const transparent = (value) => value === "transparent" || /^rgba\\([^)]*,\\s*0(?:\\.0+)?\\)$/.test(value);
  const kpiRows = kpis.map((node) => {
    const css = computed(node);
    const box = rect(node);
    const valueNode = node.querySelector('[data-role="kpi-value"]');
    const valueBox = valueNode ? rect(valueNode) : null;
    const borderNone = ["borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth"]
      .every((key) => Number.parseFloat(css[key] || "0") === 0);
    return {
      border_none: borderNone,
      radius_px: Number.parseFloat(css.borderRadius || "0"),
      outline_none: css.outlineStyle === "none" || Number.parseFloat(css.outlineWidth || "0") === 0,
      shadow_none: css.boxShadow === "none",
      background_transparent: transparent(css.backgroundColor),
      strict_contract: Boolean(node.getAttribute("data-render-contract")),
      height_px: box.height,
      value_marker_found: Boolean(valueNode),
      value_visible: Boolean(valueNode && visible(valueNode)),
      value_nonempty: Boolean(valueNode && text(valueNode).length > 0),
      value_inside: Boolean(valueBox &&
        valueBox.left >= box.left - 1 && valueBox.right <= box.right + 1 &&
        valueBox.top >= box.top - 1 && valueBox.bottom <= box.bottom + 1)
    };
  });
  const strictKpiRows = kpiRows.filter((row) => row.strict_contract);
  const strictKpiHeightSet = Array.from(new Set(
    strictKpiRows.map((row) => Math.round(row.height_px))
  ));
  const strictKpiHeightsConsistent =
    !input.render_contract.kpi.equal_height_within_set ||
    strictKpiHeightSet.length <= 1;

  const legends = all('[data-role="legend"],[aria-label="Legend"],.legend').filter(visible);
  const legendTypography = Array.from(new Set(legends.map((node) => {
    const css = computed(node);
    return `${Number.parseFloat(css.fontSize)}/${Number.parseFloat(css.lineHeight)}`;
  })));
  const expectedLegend = input.render_contract.legend;
  const seriesPolicyScopes = all('[data-series-policy="active_series_only"]').filter(visible);
  const uniqueIds = (nodes) => Array.from(new Set(nodes.map((node) =>
    String(node.getAttribute("data-series-id") || "").trim()
  ).filter(Boolean))).sort();
  const activeSeriesRows = seriesPolicyScopes.map((scope) => {
    const markIds = uniqueIds(all('[data-series-role="mark"]', scope));
    const legendIds = uniqueIds(all('[data-series-role="legend"]', scope));
    const legendRequired = markIds.length > 1;
    return {
      mark_ids: markIds,
      legend_ids: legendIds,
      legend_required: legendRequired,
      matches: markIds.length > 0 && (
        legendRequired
          ? JSON.stringify(markIds) === JSON.stringify(legendIds)
          : legendIds.length === 0 || JSON.stringify(markIds) === JSON.stringify(legendIds)
      )
    };
  });
  const plotPolicyScopes = all('[data-plot-area-policy="contract_insets"]').filter(visible);
  const expectedPlot = input.render_contract.plot_area;
  const allowedRightInsets = [
    expectedPlot.right_compact_px,
    expectedPlot.right_normal_px
  ];
  const coordinatePlotRows = plotPolicyScopes.map((scope) => {
    const plotAreas = all('[data-role="plot-area"]', scope);
    const expectedTop = Number(scope.getAttribute("data-plot-inset-top"));
    const expectedRight = Number(scope.getAttribute("data-plot-inset-right"));
    const expectedBottom = Number(scope.getAttribute("data-plot-inset-bottom"));
    const markerRows = plotAreas.map((node) => ({
      top: Number(node.getAttribute("data-inset-top")),
      right: Number(node.getAttribute("data-inset-right")),
      bottom: Number(node.getAttribute("data-inset-bottom"))
    }));
    return {
      plot_area_count: plotAreas.length,
      expected: {top: expectedTop, right: expectedRight, bottom: expectedBottom},
      markers: markerRows,
      matches: plotAreas.length === 1 && markerRows.every((row) =>
        row.top === expectedTop && row.right === expectedRight && row.bottom === expectedBottom &&
        row.top === expectedPlot.top_px && row.bottom === expectedPlot.bottom_px &&
        allowedRightInsets.includes(row.right)
      )
    };
  });

  const selectors = all('[data-role="selector"],[data-widget-type="selector"],.selector').filter(visible);
  const explicitSelectorRows = all(
    '[data-role="selector-row"],[data-selector-row],.selector-row'
  ).filter(visible);
  const inferredSelectorRows = Array.from(new Set(selectors.map((node) => node.parentElement)))
    .filter((node) => node && visible(node));
  const selectorRows = explicitSelectorRows.length > 0 ? explicitSelectorRows : inferredSelectorRows;
  const selectorChecks = selectors.map((node) => {
    const label = node.querySelector('[data-role="label"],label,.label');
    const mode = String(node.getAttribute("data-apply-mode") || "immediate").toLowerCase();
    return {
      label_left: !label || computed(label).textAlign === "left" || computed(label).textAlign === "start",
      immediate: mode === "immediate"
    };
  });
  const applyControls = all('[data-action="apply"],button').filter((node) =>
    visible(node) && /^(apply|применить)$/i.test(text(node))
  );
  const selectorRowChecks = selectorRows.map((node) => {
    const box = rect(node);
    const parentBox = node.parentElement ? rect(node.parentElement) : box;
    const widthPercent = parentBox.width > 0 ? (box.width / parentBox.width) * 100 : 100;
    return {
      height_px: box.height,
      width_percent: widthPercent,
      within_max_width: widthPercent <= input.render_contract.selector.max_row_width_percent + 0.1
    };
  });

  const useExactComparisonContextIds = input.comparison_context_object_ids.length > 0;
  const exactComparisonContextNodes = useExactComparisonContextIds
    ? input.comparison_context_object_ids.map((objectId) => ({
      object_id: objectId,
      node: findObject(objectId)
    }))
    : [];
  const exactComparisonContextRows = exactComparisonContextNodes.map((item) => {
      const node = item.node;
      return {
        object_id: item.object_id,
        found: Boolean(node),
        visible: Boolean(node && visible(node)),
        nonempty: Boolean(node && text(node).length > 0),
        height_px: node ? rect(node).height : 0
      };
    });
  const fallbackComparisonContexts = useExactComparisonContextIds
    ? []
    : all('[data-role="comparison-context"],[data-comparison-context],.comparison-context');
  const visibleFallbackComparisonContexts = fallbackComparisonContexts.filter((node) =>
    visible(node) && text(node).length > 0
  );
  const visibleExactComparisonContexts = exactComparisonContextNodes
    .map((item) => item.node)
    .filter((node) => node && visible(node) && text(node).length > 0);
  const visibleComparisonContexts = useExactComparisonContextIds
    ? visibleExactComparisonContexts
    : visibleFallbackComparisonContexts;
  const visibleNonemptyComparisonCount = useExactComparisonContextIds
    ? exactComparisonContextRows.filter((row) => row.found && row.visible && row.nonempty).length
    : visibleFallbackComparisonContexts.length;

  const placementTolerancePx = 12;
  const selectorObjectIds = new Set(
    input.selector_contracts.map((item) => String(item.selector_id || "")).filter(Boolean)
  );
  const configuredSelectorEntries = input.selector_contracts
    .map((item) => ({
      contract: item,
      node: findObject(String(item.selector_id || ""))
    }))
    .filter((item) => item.node && visible(item.node));
  const configuredSelectorNodes = configuredSelectorEntries.map((item) => item.node);
  const placementSelectorNodes = Array.from(new Set(
    configuredSelectorNodes.length > 0 ? configuredSelectorNodes : selectorRows
  ));
  const selectorPlacementRows = placementSelectorNodes.map((node) => {
    const box = rect(node);
    return {
      left: box.left,
      right: box.right,
      top: box.top,
      bottom: box.bottom,
      width: box.width,
      height: box.height
    };
  }).sort((left, right) => left.top - right.top || left.left - right.left);
  let selectorRowsContiguous = selectorPlacementRows.length > 0;
  let selectorRunningBottom = selectorPlacementRows.length > 0
    ? selectorPlacementRows[0].bottom
    : Number.NaN;
  selectorPlacementRows.slice(1).forEach((row) => {
    if (row.top > selectorRunningBottom + placementTolerancePx) {
      selectorRowsContiguous = false;
    }
    selectorRunningBottom = Math.max(selectorRunningBottom, row.bottom);
  });
  const selectorGroupBox = selectorPlacementRows.length > 0 ? {
    left: Math.min(...selectorPlacementRows.map((row) => row.left)),
    right: Math.max(...selectorPlacementRows.map((row) => row.right)),
    top: Math.min(...selectorPlacementRows.map((row) => row.top)),
    bottom: Math.max(...selectorPlacementRows.map((row) => row.bottom))
  } : null;
  const configuredSelectorDomOrder = configuredSelectorEntries
    .map((item) => {
      const box = rect(item.node);
      return {
        selector_id: String(item.contract.selector_id || ""),
        role: String(item.contract.role || ""),
        ordinal: Number(item.contract.ordinal),
        top: box.top,
        left: box.left,
        height: box.height
      };
    })
    .sort((left, right) => left.top - right.top || left.left - right.left);
  const configuredSelectorOrder = input.selector_contracts.map((item) =>
    String(item.selector_id || "")
  );
  const actualSelectorOrder = configuredSelectorDomOrder.map((item) => item.selector_id);
  const selectorOrderMatches = configuredSelectorOrder.length === 0 ||
    JSON.stringify(actualSelectorOrder) === JSON.stringify(configuredSelectorOrder);
  const configuredPeriodSelectors = input.selector_contracts.filter((item) =>
    String(item.role || "") === "period"
  );
  const periodFirstMatches = configuredPeriodSelectors.length === 0 || (
    String(input.selector_contracts[0] && input.selector_contracts[0].role || "") === "period" &&
    actualSelectorOrder[0] === String(configuredPeriodSelectors[0].selector_id || "")
  );
  const selectorTopValues = configuredSelectorDomOrder.map((item) => item.top);
  const selectorsSingleRow = selectorTopValues.length <= 1 ||
    Math.max(...selectorTopValues) - Math.min(...selectorTopValues) <= placementTolerancePx;
  const configuredSelectorHeightsMatch = configuredSelectorDomOrder.every((item) =>
    Math.abs(item.height - input.render_contract.selector.row_height_px) <= 1
  );
  const selectorContainer = placementSelectorNodes.length > 0
    ? (
      (
        typeof placementSelectorNodes[0].closest === "function" &&
        placementSelectorNodes[0].closest(
          '[data-role="dashboard-content"],[data-dashboard-content],.dash-body,main'
        )
      ) ||
      placementSelectorNodes[0].parentElement ||
      document.documentElement
    )
    : null;
  const selectorContainerBox = selectorContainer ? rect(selectorContainer) : null;
  const selectorGroupWidthPercent = selectorGroupBox
    ? (
      (selectorGroupBox.right - selectorGroupBox.left) /
      Math.max(1, selectorContainerBox ? selectorContainerBox.width : window.innerWidth)
    ) * 100
    : null;
  const selectorAggregateWidthMatches = configuredSelectorOrder.length === 0 || (
    selectorGroupWidthPercent != null &&
    Math.abs(
      selectorGroupWidthPercent - input.render_contract.selector.row_target_width_percent
    ) <= input.render_contract.selector.row_width_tolerance_percent + 0.1
  );
  const comparisonPlacementNode = visibleComparisonContexts.length === 1
    ? visibleComparisonContexts[0]
    : null;
  const comparisonPlacementBox = comparisonPlacementNode ? (() => {
    const box = rect(comparisonPlacementNode);
    return {
      left: box.left,
      right: box.right,
      top: box.top,
      bottom: box.bottom
    };
  })() : null;
  const comparisonPlacementCandidates = visibleComparisonContexts;
  const expectedContentNodes = input.expected_object_ids
    .filter((objectId) =>
      !selectorObjectIds.has(objectId) &&
      !input.comparison_context_object_ids.includes(objectId))
    .map((objectId) => ({object_id: objectId, node: findObject(objectId)}))
    .filter((item) => item.node && visible(item.node))
    .filter((item) => !placementSelectorNodes.some((selectorNode) =>
      selectorNode === item.node || selectorNode.contains(item.node) || item.node.contains(selectorNode)))
    .filter((item) => !comparisonPlacementCandidates.some((contextNode) =>
      contextNode === item.node || contextNode.contains(item.node) || item.node.contains(contextNode)))
    .map((item) => {
      const box = rect(item.node);
      return {
        object_id: item.object_id,
        left: box.left,
        right: box.right,
        top: box.top,
        bottom: box.bottom
      };
    })
    .sort((left, right) => left.top - right.top || left.left - right.left);
  const firstContentBox = expectedContentNodes.length > 0 ? expectedContentNodes[0] : null;
  const horizontalOverlap = (left, right) =>
    Math.max(0, Math.min(left.right, right.right) - Math.max(left.left, right.left));
  const sameColumn = (left, right) => {
    if (!left || !right) return false;
    const leftWidth = Math.max(0, left.right - left.left);
    const rightWidth = Math.max(0, right.right - right.left);
    const narrowerWidth = Math.min(leftWidth, rightWidth);
    return Math.abs(left.left - right.left) <= placementTolerancePx &&
      narrowerWidth > 0 &&
      horizontalOverlap(left, right) >= narrowerWidth * 0.5;
  };
  const selectorToContextGapPx = selectorGroupBox && comparisonPlacementBox
    ? comparisonPlacementBox.top - selectorGroupBox.bottom
    : null;
  const contextToFirstContentGapPx = comparisonPlacementBox && firstContentBox
    ? firstContentBox.top - comparisonPlacementBox.bottom
    : null;
  const comparisonPlacementMatches = !input.comparison_enabled || (
    visibleNonemptyComparisonCount === 1 &&
    placementSelectorNodes.length > 0 &&
    selectorRowsContiguous &&
    Boolean(selectorGroupBox && comparisonPlacementBox && firstContentBox) &&
    selectorToContextGapPx >= -1 &&
    selectorToContextGapPx <= placementTolerancePx &&
    sameColumn(selectorGroupBox, comparisonPlacementBox) &&
    contextToFirstContentGapPx >= -1 &&
    sameColumn(comparisonPlacementBox, firstContentBox)
  );
  const tooltipShells = all('[role="tooltip"],[data-role="tooltip"],.tooltip').filter(visible);
  const tooltipOwners = all("[aria-describedby]").filter((node) => {
    if (!visible(node)) return false;
    const describedBy = String(node.getAttribute("aria-describedby") || "").split(/\\s+/);
    return tooltipShells.some((shell) => shell.id && describedBy.includes(shell.id));
  });
  const tooltipSurfaceRows = tooltipShells.map((shell) => {
    const surface = shell.querySelector('[data-role="tooltip-surface"],.tooltip-surface') || shell;
    const css = computed(surface);
    const borderNone = ["borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth"]
      .every((key) => Number.parseFloat(css[key] || "0") === 0);
    return {
      border_none: borderNone,
      radius_px: Number.parseFloat(css.borderRadius || "0"),
      outline_none: css.outlineStyle === "none" || Number.parseFloat(css.outlineWidth || "0") === 0,
      shadow_none: css.boxShadow === "none"
    };
  });
  const tooltipComparisonRows = Object.entries(input.tooltip_comparison_modes).map(
    ([objectId, expectedMode]) => {
      const objectNode = findObject(objectId);
      const markerNode = objectNode && (
        objectNode.getAttribute("data-tooltip-comparison-mode")
          ? objectNode
          : objectNode.querySelector("[data-tooltip-comparison-mode]")
      );
      return {
        object_id: objectId,
        expected_mode: expectedMode,
        object_found: Boolean(objectNode),
        marker_found: Boolean(markerNode),
        actual_mode: markerNode
          ? String(markerNode.getAttribute("data-tooltip-comparison-mode") || "")
          : "",
        period_value_source: markerNode
          ? String(markerNode.getAttribute("data-tooltip-period-source") || "")
          : ""
      };
    }
  );
  const tooltipComparisonModeMatches = tooltipComparisonRows.every((row) =>
    row.object_found && row.marker_found &&
    row.actual_mode === row.expected_mode &&
    row.period_value_source === input.render_contract.tooltip.period_value_source
  );
  const visibleComparisonPeriodNodes = tooltipShells.flatMap((shell) =>
    all('[data-role="comparison-period"],[data-tooltip-comparison-period]', shell)
  ).filter(visible);
  const singlePeriodTooltipShells = tooltipShells.filter((shell) => {
    const owner = shell.closest && shell.closest("[data-tooltip-comparison-mode]");
    return owner && owner.getAttribute("data-tooltip-comparison-mode") === "single_period";
  });
  const singlePeriodHasComparisonChrome = singlePeriodTooltipShells.some((shell) =>
    all('[data-role="comparison-period"],[data-role="tooltip-vs"],[data-role="tooltip-current"]', shell)
      .some(visible)
  );
  const horizontalContract = input.render_contract.horizontal_rank;
  const stableGutterRequired = horizontalContract.scroll === true &&
    horizontalContract.stable_scrollbar_gutter === true;
  const scrollObjectIds = horizontalContract.scroll_object_ids || [];
  const horizontalScrollScopes = scrollObjectIds.length > 0
    ? scrollObjectIds.map((objectId) => ({object_id: objectId, node: findObject(objectId)}))
    : [{object_id: "", node: document}];
  const horizontalScrollRows = horizontalScrollScopes.map((scope) => {
    const scopeVisible = scope.node === document || Boolean(scope.node && visible(scope.node));
    const descendants = scope.node
      ? all('[data-component="horizontal_rank"]', scope.node)
      : [];
    const components = scope.node && scope.node !== document &&
      scope.node.getAttribute("data-component") === "horizontal_rank"
      ? [scope.node, ...descendants]
      : descendants;
    const containers = Array.from(new Set(components.flatMap((component) =>
      [component, ...all("*", component)]
    ))).filter((node) => {
      if (!scopeVisible || !visible(node)) return false;
      const css = computed(node);
      return css.overflowY === "auto" || css.overflowY === "scroll";
    });
    return {
      object_id: scope.object_id,
      object_found: Boolean(scope.node),
      component_count: components.length,
      scroll_container_count: containers.length,
      gutter_values: containers.map((node) => computed(node).scrollbarGutter),
      stable: containers.some((node) =>
        String(computed(node).scrollbarGutter).split(/\\s+/).includes("stable"))
    };
  });
  const stableGutterMatches = !stableGutterRequired ||
    (horizontalScrollRows.length > 0 && horizontalScrollRows.every((row) =>
      row.object_found && row.component_count > 0 &&
      row.scroll_container_count > 0 && row.stable));

  const chartRows = all('[data-role="chart-row"],[data-row],.chart-row').filter(visible);
  const redundantRowTitles = chartRows.filter((row) => {
    const label = row.querySelector('[data-role="label"],[data-label],.label');
    const labelText = text(label);
    if (!labelText) return false;
    return all("[title]", row).some((node) => String(node.getAttribute("title") || "").trim() === labelText);
  });

  const titleRows = input.title_contracts.map((contract) => {
    const node = findObject(String(contract.widget_id || ""));
    const candidates = node ? {
      embedded: all('[data-role="embedded-title"]', node).filter(visible),
      content: all('[data-role="content-label"]', node).filter(visible),
      native: all('[data-role="native-title"],[data-qa="widget-title"],.dashkit-grid-item__title', node).filter(visible)
    } : {embedded: [], content: [], native: []};
    const mode = String(contract.mode || "");
    const expected = mode === "embedded_title"
      ? candidates.embedded
      : mode === "content_label"
        ? candidates.content
        : (mode === "native_title" || mode === "tab_strip")
          ? candidates.native
          : [];
    const visibleSurfaceCount = candidates.embedded.length + candidates.content.length + candidates.native.length;
    const expectedText = String(contract.display_title || "");
    const titleMatches = mode === "tab_only"
      ? visibleSurfaceCount === 0
      : expected.length === 1 && text(expected[0]).startsWith(expectedText) && expectedText.length > 0;
    return {
      widget_id: String(contract.widget_id || ""),
      mode,
      found: Boolean(node),
      visible_surface_count: visibleSurfaceCount,
      title_matches: titleMatches,
      mutually_exclusive: visibleSurfaceCount <= 1
    };
  });

  const compositionRows = (input.dashboard_composition.rows || []).map((row) => {
    const nodes = (row.items || []).map((item) => findObject(String(item.widget_id || "")))
      .filter((node) => node && visible(node));
    const boxes = nodes.map((node) => rect(node));
    const heights = boxes.map((box) => Math.round(box.height));
    return {
      row_id: String(row.id || ""),
      expected_count: (row.items || []).length,
      visible_count: nodes.length,
      heights,
      equal_heights: heights.length <= 1 || Math.max(...heights) - Math.min(...heights) <= 1,
      horizontal_alignment: boxes.length <= 1 || Math.max(...boxes.map((box) => box.top)) - Math.min(...boxes.map((box) => box.top)) <= 12
    };
  });
  const visibleKpiBoxes = kpis.map((node) => rect(node)).sort((left, right) => left.top - right.top || left.left - right.left);
  const visualKpiRows = [];
  visibleKpiBoxes.forEach((box) => {
    const row = visualKpiRows.find((candidate) => Math.abs(candidate.top - box.top) <= 12);
    if (row) row.count += 1;
    else visualKpiRows.push({top: box.top, count: 1});
  });
  const kpiDensityMatches = visualKpiRows.every((row) => row.count <= 3) ||
    input.dashboard_composition.four_kpi_override_verified === true;

  const selectorClearRows = input.selector_contracts
    .filter((contract) => contract.multiple === true)
    .map((contract) => {
      const node = findObject(String(contract.selector_id || ""));
      const marker = node && (
        node.hasAttribute("data-empty-means-all")
          ? node
          : node.querySelector("[data-empty-means-all]")
      );
      return {
        selector_id: String(contract.selector_id || ""),
        found: Boolean(node),
        empty_means_all: contract.empty_means_all === true,
        restore_after_clear: contract.restore_default_after_clear === false,
        runtime_marker_found: Boolean(marker)
      };
    });

  const visibleTables = all('table,[role="table"],[data-role="table"]').filter(visible);
  const tableRows = visibleTables.map((table) => {
    const headers = all('th,[role="columnheader"]', table).filter(visible);
    const sticky = all('[data-sticky="true"],.sticky', table).filter(visible);
    const clipped = all('th,td,[role="columnheader"],[role="cell"]', table).filter((cell) =>
      visible(cell) && cell.scrollWidth > cell.clientWidth + 1
    );
    return {
      headers_nonempty: headers.length > 0 && headers.every((header) => text(header).length > 0),
      sticky_meaningful: sticky.every((cell) => cell.getAttribute("data-column-cardinality") !== "1"),
      clipping_labelled: clipped.every((cell) =>
        Boolean(String(cell.getAttribute("data-display-label") || cell.getAttribute("title") || "").trim())
      )
    };
  });

  const expectedSelector = input.render_contract.selector;
  const comparisonContextMatches = input.comparison_enabled
    ? visibleNonemptyComparisonCount === 1
    : visibleNonemptyComparisonCount === 0;
  const comparisonHeightRows = useExactComparisonContextIds
    ? exactComparisonContextRows
    : visibleFallbackComparisonContexts.map((node) => ({
      found: true,
      visible: true,
      nonempty: true,
      height_px: rect(node).height
    }));
  const semanticHeightMatches = !input.comparison_enabled ||
    (comparisonHeightRows.length === 1 && comparisonHeightRows.every((row) =>
      row.found && row.visible && row.nonempty &&
      row.height_px >= input.render_contract.comparison_context.minimum_height_px - 1
    ));
  const tooltipMatches = tooltipShells.length === 0
    ? tooltipOwners.length === 0
    : tooltipShells.length === 1 && tooltipOwners.length === 1 &&
      tooltipSurfaceRows.every((row) => row.border_none && row.radius_px === 0 &&
        row.outline_none && row.shadow_none);
  const assertions = {
    objects_visible_nonempty: objectRows.every((row) => row.found && row.visible && row.nonempty),
    no_error_retry_markers: markerMatches.length === 0,
    document_no_horizontal_overflow: documentOverflow <= 1,
    objects_not_clipped_or_paint_overflow: objectRows.every((row) => row.viewport_contained && row.paint_inside),
    kpi_surface_contract: kpiRows.every((row) => row.border_none && row.radius_px === 0 &&
      row.outline_none && row.shadow_none && row.background_transparent),
    kpi_content_visibility_contract: kpiRows.every((row) =>
      !row.strict_contract || (
        row.value_marker_found && row.value_visible && row.value_nonempty && row.value_inside
      )) && strictKpiHeightsConsistent,
    legend_typography_consistent: legendTypography.length <= 1 && legendTypography.every((value) =>
      value === `${expectedLegend.font_size_px}/${expectedLegend.line_height_px}`),
    active_series_legend_consistent: activeSeriesRows.every((row) => row.matches),
    coordinate_plot_insets_consistent: coordinatePlotRows.every((row) => row.matches),
    selector_interaction_layout_contract: applyControls.length === 0 &&
      selectorChecks.every((row) => row.label_left && row.immediate) &&
      selectorRowChecks.every((row) => row.within_max_width &&
        Math.abs(row.height_px - expectedSelector.row_height_px) <= 1),
    selector_order_row_contract: selectorOrderMatches && periodFirstMatches &&
      (!expectedSelector.single_row || selectorsSingleRow) &&
      configuredSelectorHeightsMatch &&
      selectorAggregateWidthMatches,
    comparison_context_cardinality: comparisonContextMatches,
    comparison_context_placement: comparisonPlacementMatches,
    semantic_height_contract: semanticHeightMatches,
    tooltip_owner_shell_cardinality: tooltipMatches,
    tooltip_comparison_mode_contract: tooltipComparisonModeMatches &&
      !singlePeriodHasComparisonChrome,
    stable_scrollbar_gutter: stableGutterMatches,
    no_redundant_row_title_tooltips: redundantRowTitles.length === 0,
    role_owned_title_contract: titleRows.every((row) =>
      row.found && row.title_matches && row.mutually_exclusive),
    semantic_row_geometry_contract: compositionRows.every((row) =>
      row.visible_count === row.expected_count && row.equal_heights && row.horizontal_alignment),
    kpi_density_contract: kpiDensityMatches,
    selector_clear_contract: selectorClearRows.every((row) =>
      row.found && row.empty_means_all && row.restore_after_clear),
    table_readability_contract: tableRows.every((row) =>
      row.headers_nonempty && row.sticky_meaningful && row.clipping_labelled),
    lazy_full_scroll_contract: objectRows.every((row) => row.found && row.visible && row.nonempty)
  };
  return {
    schema_id: "datalens.browser-qa-result",
    viewport: {width: window.innerWidth, height: window.innerHeight},
    passed: input.required_assertion_ids.every((assertionId) => assertions[assertionId] === true),
    global_error_markers: markerMatches.map((marker, index) => ({
      error_id: `global-marker-${index + 1}`,
      marker,
      screen_location: "dashboard-body",
      candidate_object_ids: [],
      attribution: {status: "unknown", object_id: "", reason: ""},
      runtime_diagnostic_ref: "",
      acceptance_effect: "partial"
    })),
    assertions,
    observations: {
      object_rows: objectRows,
      marker_matches: markerMatches,
      document_horizontal_overflow_px: documentOverflow,
      kpi_rows: kpiRows,
      strict_kpi_height_set_px: strictKpiHeightSet,
      legend_typography: legendTypography,
      active_series_rows: activeSeriesRows,
      coordinate_plot_rows: coordinatePlotRows,
      selector_checks: selectorChecks,
      selector_row_checks: selectorRowChecks,
      selector_order_row_contract: {
        configured_order: configuredSelectorOrder,
        actual_order: actualSelectorOrder,
        order_matches: selectorOrderMatches,
        period_first_matches: periodFirstMatches,
        single_row: selectorsSingleRow,
        configured_heights_match: configuredSelectorHeightsMatch,
        configured_heights_px: configuredSelectorDomOrder.map((item) => item.height),
        container_width_px: selectorContainerBox ? selectorContainerBox.width : null,
        aggregate_width_percent: selectorGroupWidthPercent,
        target_width_percent: expectedSelector.row_target_width_percent,
        width_tolerance_percent: expectedSelector.row_width_tolerance_percent
      },
      comparison_context_resolution: useExactComparisonContextIds ? "exact_object_ids" : "dom_class_fallback",
      comparison_context_rows: exactComparisonContextRows,
      comparison_context_count: useExactComparisonContextIds
        ? exactComparisonContextRows.length
        : fallbackComparisonContexts.length,
      visible_nonempty_comparison_context_count: visibleNonemptyComparisonCount,
      comparison_context_placement: {
        tolerance_px: placementTolerancePx,
        selector_node_count: placementSelectorNodes.length,
        selector_rows_contiguous: selectorRowsContiguous,
        selector_group_box: selectorGroupBox,
        comparison_box: comparisonPlacementBox,
        selector_to_context_gap_px: selectorToContextGapPx,
        first_content: firstContentBox,
        context_to_first_content_gap_px: contextToFirstContentGapPx,
        same_selector_column: sameColumn(selectorGroupBox, comparisonPlacementBox),
        same_content_column: sameColumn(comparisonPlacementBox, firstContentBox)
      },
      tooltip_shell_count: tooltipShells.length,
      tooltip_owner_count: tooltipOwners.length,
      tooltip_surface_rows: tooltipSurfaceRows,
      tooltip_comparison_rows: tooltipComparisonRows,
      visible_comparison_period_node_count: visibleComparisonPeriodNodes.length,
      single_period_has_comparison_chrome: singlePeriodHasComparisonChrome,
      stable_scrollbar_gutter_required: stableGutterRequired,
      horizontal_scroll_object_ids: scrollObjectIds,
      horizontal_scroll_rows: horizontalScrollRows,
      redundant_row_title_tooltip_count: redundantRowTitles.length,
      title_rows: titleRows,
      composition_rows: compositionRows,
      visual_kpi_rows: visualKpiRows,
      selector_clear_rows: selectorClearRows,
      table_rows: tableRows
    }
  };
})()""".replace("__QA_INPUT__", encoded)


def _normalize_browser_render_contract(render_contract: dict[str, Any]) -> dict[str, Any]:
    effective_tokens = (
        render_contract.get("effective_tokens")
        if isinstance(render_contract.get("effective_tokens"), dict)
        else render_contract
    )
    typography = (
        effective_tokens.get("typography")
        if isinstance(effective_tokens.get("typography"), dict)
        else {}
    )
    legend_tokens = (
        typography.get("legend")
        if isinstance(typography.get("legend"), dict)
        else {}
    )
    active_legend = (
        legend_tokens.get("active")
        if isinstance(legend_tokens.get("active"), dict)
        else {}
    )
    legend = (
        effective_tokens.get("legend")
        if isinstance(effective_tokens.get("legend"), dict)
        else {}
    )
    selector = (
        effective_tokens.get("selector")
        if isinstance(effective_tokens.get("selector"), dict)
        else {}
    )
    kpi = (
        effective_tokens.get("kpi")
        if isinstance(effective_tokens.get("kpi"), dict)
        else {}
    )
    kpi_layout = (
        kpi.get("layout")
        if isinstance(kpi.get("layout"), dict)
        else {}
    )
    tooltip = (
        effective_tokens.get("tooltip")
        if isinstance(effective_tokens.get("tooltip"), dict)
        else {}
    )
    horizontal_rank = (
        effective_tokens.get("horizontal_rank")
        if isinstance(effective_tokens.get("horizontal_rank"), dict)
        else {}
    )
    plot_area = (
        effective_tokens.get("plot_area")
        if isinstance(effective_tokens.get("plot_area"), dict)
        else {}
    )
    plot_insets = (
        plot_area.get("inset_px")
        if isinstance(plot_area.get("inset_px"), dict)
        else {}
    )
    right_insets = (
        plot_insets.get("right")
        if isinstance(plot_insets.get("right"), dict)
        else {}
    )
    series_visibility = (
        effective_tokens.get("series_visibility")
        if isinstance(effective_tokens.get("series_visibility"), dict)
        else {}
    )
    comparison_context = (
        effective_tokens.get("comparison_context")
        if isinstance(effective_tokens.get("comparison_context"), dict)
        else {}
    )
    layout_grid = (
        effective_tokens.get("layout_grid")
        if isinstance(effective_tokens.get("layout_grid"), dict)
        else {}
    )
    return {
        "kpi": {
            "border": "none",
            "border_radius_px": 0,
            "outline": "none",
            "shadow": "none",
            "background": "transparent",
            "value_marker": str(
                (
                    kpi.get("content")
                    if isinstance(kpi.get("content"), dict)
                    else {}
                ).get("value_marker")
                or "kpi-value"
            ),
            "height_update_policy": str(
                kpi_layout.get("update_policy") or "preserve_fresh_saved_geometry"
            ),
            "equal_height_within_set": (
                kpi_layout.get("equal_height_within_kpi_set") is not False
            ),
            "creation_default_grid_height_units": _positive_number(
                (
                    layout_grid.get("native_height_units")
                    if isinstance(layout_grid.get("native_height_units"), dict)
                    else {}
                ).get("kpi_creation_default"),
                default=6,
            ),
        },
        "legend": {
            "font_size_px": _positive_number(
                legend.get("font_size_px", active_legend.get("font_size_px")),
                default=12,
            ),
            "line_height_px": _positive_number(
                legend.get("line_height_px", active_legend.get("line_height_px")),
                default=16,
            ),
            "maximum_typography_set_size": 1,
        },
        "plot_area": {
            "top_px": _positive_number(plot_insets.get("top"), default=22),
            "right_compact_px": _positive_number(
                right_insets.get("compact"),
                default=10,
            ),
            "right_normal_px": _positive_number(
                right_insets.get("normal"),
                default=16,
            ),
            "bottom_px": _positive_number(plot_insets.get("bottom"), default=34),
        },
        "series_visibility": {
            "source": str(series_visibility.get("source") or "filtered_result_rows"),
            "legend": str(series_visibility.get("legend") or "active_series_only"),
            "marks": str(series_visibility.get("marks") or "active_series_only"),
        },
        "selector": {
            "label_alignment": "left",
            "interaction": "immediate",
            "apply_control": False,
            "row_width": "bounded",
            "max_row_width_percent": 94,
            "row_height_px": _positive_number(selector.get("row_height_px"), default=44),
            "period_first_if_present": selector.get("period_first_if_present") is not False,
            "single_row": selector.get("single_row") is not False,
            "row_target_width_percent": _positive_number(
                selector.get("row_target_width_percent"),
                default=95,
            ),
            "row_width_tolerance_percent": _positive_number(
                selector.get("row_width_tolerance_percent"),
                default=1,
            ),
        },
        "tooltip": {
            "max_visible_shells": 1,
            "single_owner": True,
            "border": "none",
            "border_radius_px": 0,
            "outline": "none",
            "shadow": "none",
            "redundant_row_title": False,
            "comparison_adaptive": tooltip.get("comparison_adaptive") is not False,
            "period_value_source": str(
                tooltip.get("period_value_source") or "normalized"
            ),
        },
        "comparison_context": {
            "minimum_height_px": _positive_number(
                comparison_context.get("minimum_height_px"),
                default=70,
            ),
            "dashboard_grid_height_units": _positive_number(
                (
                    layout_grid.get("native_height_units")
                    if isinstance(layout_grid.get("native_height_units"), dict)
                    else {}
                ).get("comparison_context_minimum"),
                default=3,
            ),
        },
        "layout_grid": {
            "selector_creation_default_units": _positive_number(
                (
                    layout_grid.get("native_height_units")
                    if isinstance(layout_grid.get("native_height_units"), dict)
                    else {}
                ).get("selector_creation_default"),
                default=2,
            ),
            "kpi_creation_default_units": _positive_number(
                (
                    layout_grid.get("native_height_units")
                    if isinstance(layout_grid.get("native_height_units"), dict)
                    else {}
                ).get("kpi_creation_default"),
                default=6,
            ),
            "update_policy": str(
                layout_grid.get("update_policy") or "preserve_fresh_saved_geometry"
            ),
            "runtime_relation": str(
                layout_grid.get("runtime_relation")
                or "measured_independently_from_native_units"
            ),
            "overflow_policy": str(
                layout_grid.get("overflow_policy") or "expand_or_scroll_never_clip"
            ),
        },
        "horizontal_rank": {
            "scroll": horizontal_rank.get("scroll") is True,
            "stable_scrollbar_gutter": horizontal_rank.get("stable_scrollbar_gutter") is True,
            "scroll_object_ids": _normalized_string_list(
                horizontal_rank.get("scroll_object_ids")
                if isinstance(horizontal_rank.get("scroll_object_ids"), list)
                else []
            ),
        },
    }


def _normalize_selector_contracts(selector_contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in selector_contracts:
        if not isinstance(item, dict):
            continue
        selector_id = str(item.get("selector_id") or item.get("id") or "").strip()
        if not selector_id or selector_id in seen:
            continue
        seen.add(selector_id)
        family = str(item.get("family") or "").strip()
        requested_role = str(item.get("role") or "").strip().lower()
        role = (
            "period"
            if requested_role == "period" or family == "date_range_selector"
            else ""
        )
        normalized.append(
            {
                "selector_id": selector_id,
                "label": str(item.get("label") or "").strip(),
                "family": family,
                "role": role,
                "ordinal": len(normalized),
                "interaction": "immediate",
                "apply_control": False,
                "multiple": bool(item.get("multiple")),
                "empty_means_all": bool(item.get("emptyMeansAll") or item.get("empty_means_all")),
                "restore_default_after_clear": bool(
                    item.get("restoreDefaultAfterClear") or item.get("restore_default_after_clear")
                ),
            }
        )
    return normalized


def _normalize_title_contracts(values: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, dict):
            continue
        widget_id = str(item.get("widget_id") or item.get("id") or "").strip()
        mode = str(item.get("mode") or item.get("title_mode") or "").strip()
        if not widget_id or widget_id in seen or not mode:
            continue
        seen.add(widget_id)
        normalized.append(
            {
                "widget_id": widget_id,
                "mode": mode,
                "display_title": str(item.get("display_title") or item.get("title") or "").strip(),
                "hint": str(item.get("hint") or "").strip(),
                "sha256": str(item.get("sha256") or item.get("title_contract_sha256") or "").strip(),
            }
        )
    return sorted(normalized, key=lambda item: item["widget_id"])


def _normalize_composition_binding(value: dict[str, Any]) -> dict[str, Any]:
    tabs = value.get("tabs") if isinstance(value.get("tabs"), list) else []
    rows: list[dict[str, Any]] = []
    four_kpi_override_verified = False
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        for row in tab.get("rows") or []:
            if not isinstance(row, dict):
                continue
            items = [
                {
                    "widget_id": str(item.get("widget_id") or ""),
                    "role": str(item.get("role") or ""),
                    "w": item.get("w"),
                    "h": item.get("h"),
                    "title_mode": str(item.get("title_mode") or ""),
                }
                for item in row.get("items") or []
                if isinstance(item, dict) and str(item.get("widget_id") or "").strip()
            ]
            rows.append(
                {
                    "tab_id": str(tab.get("id") or ""),
                    "id": str(row.get("id") or ""),
                    "role": str(row.get("role") or ""),
                    "gap_after": int(row.get("gap_after") or 0),
                    "items": items,
                }
            )
            four_kpi_override_verified = four_kpi_override_verified or bool(
                row.get("density_override") == "four_kpi_9_columns"
                and isinstance(row.get("browser_proof"), dict)
                and row["browser_proof"].get("passed") is True
            )
    return {
        "schema_id": str(value.get("schema_id") or ""),
        "sha256": str(value.get("sha256") or ""),
        "rows": rows,
        "four_kpi_override_verified": four_kpi_override_verified,
    }


def _normalize_tooltip_comparison_modes(values: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for object_id, raw_mode in values.items():
        key = str(object_id or "").strip()
        mode = str(raw_mode or "").strip().lower()
        if not key:
            continue
        if mode not in {"single_period", "comparison"}:
            raise ValueError(
                "tooltip comparison mode must be single_period or comparison"
            )
        normalized[key] = mode
    return dict(sorted(normalized.items()))


def _normalize_profile_assertions(
    values: list[dict[str, Any]],
    *,
    active_provenance_hash: str,
) -> list[dict[str, Any]]:
    if not values:
        return []
    if not re.fullmatch(r"[a-f0-9]{64}", active_provenance_hash):
        raise ValueError("profile assertions require an active provenance hash")
    allowed_ids = {item["id"] for item in BROWSER_QA_PROFILE_ASSERTIONS}
    normalized: list[dict[str, Any]] = []
    for value in values:
        assertion_id = str(value.get("assertion_id") or value.get("id") or "").strip()
        scope = str(value.get("scope") or "").strip()
        source_ref = str(value.get("source_ref") or "").strip()
        source_hash = str(value.get("profile_or_exemplar_hash") or "").strip()
        if assertion_id not in allowed_ids:
            raise ValueError(f"unsupported profile assertion: {assertion_id or 'missing'}")
        if scope not in {"portfolio", "project", "task", "exemplar"}:
            raise ValueError("profile assertion scope is invalid")
        if not source_ref or source_hash != active_provenance_hash:
            raise ValueError("profile assertion provenance does not match the active binding")
        definition = next(item for item in BROWSER_QA_PROFILE_ASSERTIONS if item["id"] == assertion_id)
        normalized.append(
            {
                **dict(definition),
                "scope": scope,
                "source_ref": source_ref,
                "profile_or_exemplar_hash": source_hash,
                "applies_to_object_ids": _normalized_string_list(
                    list(value.get("applies_to_object_ids") or [])
                ),
                "expected": value.get("expected"),
                "status": "required",
            }
        )
    return sorted(normalized, key=lambda item: (item["id"], item["source_ref"]))


def _normalized_string_list(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _unattributed_markers_from_observations(value: Any) -> list[dict[str, Any]]:
    observations = value if isinstance(value, dict) else {}
    return [
        {
            "error_id": f"global-marker-{index}",
            "marker": str(marker),
            "screen_location": "dashboard-body",
            "candidate_object_ids": [],
            "attribution": {"status": "unknown", "object_id": "", "reason": ""},
            "runtime_diagnostic_ref": "",
            "acceptance_effect": "partial",
        }
        for index, marker in enumerate(observations.get("marker_matches") or [], start=1)
        if str(marker)
    ]


def _merge_global_error_markers(current: list[dict[str, Any]], incoming: Any) -> list[dict[str, Any]]:
    rows = [dict(item) for item in current if isinstance(item, dict)]
    rows.extend(dict(item) for item in incoming or [] if isinstance(item, dict))
    deduplicated: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = json.dumps(
            {
                "error_id": str(row.get("error_id") or ""),
                "marker": str(row.get("marker") or ""),
                "screen_location": str(row.get("screen_location") or ""),
                "attribution": row.get("attribution") if isinstance(row.get("attribution"), dict) else {},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        deduplicated[key] = row
    return list(deduplicated.values())


def _global_error_marker_issues(tab_id: str, markers: Any) -> list[str]:
    issues: list[str] = []
    for index, raw in enumerate(markers or [], start=1):
        if not isinstance(raw, dict):
            issues.append(f"unattributed global error marker remains on tab {tab_id}: marker {index}")
            continue
        marker_id = str(raw.get("error_id") or f"marker-{index}")
        attribution = raw.get("attribution") if isinstance(raw.get("attribution"), dict) else {}
        status = str(attribution.get("status") or "unknown")
        reason = str(attribution.get("reason") or "").strip()
        effect = str(raw.get("acceptance_effect") or "partial")
        if status == "unknown":
            issues.append(f"unattributed global error marker remains on tab {tab_id}: {marker_id}")
        elif status == "attributed":
            issues.append(f"attributed visible error fails tab {tab_id}: {marker_id}")
        elif status in {"irrelevant_ui", "transient_resolved"}:
            if not reason or effect != "none":
                issues.append(f"global error attribution is incomplete on tab {tab_id}: {marker_id}")
        else:
            issues.append(f"global error attribution status is invalid on tab {tab_id}: {marker_id}")
    return issues


def _positive_number(value: Any, *, default: int) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return int(number) if number.is_integer() else number


def _safe_artifact_stem(value: str) -> str:
    stem = "".join(character.lower() if character.isalnum() else "-" for character in value)
    compact = "-".join(part for part in stem.split("-") if part)
    return (compact or "dashboard")[:80]


def browser_qa_evidence(
    *,
    status: str = "not_checked",
    artifact_paths: list[str] | None = None,
    message: str = "",
    checked_url: str = "",
) -> dict[str, Any]:
    normalized = _normalize_status(status)
    paths = [str(path) for path in artifact_paths or [] if str(path)]
    blocked_reasons: list[str] = []
    if normalized == "browser_pass" and not paths:
        normalized = "not_checked"
        blocked_reasons.append("browser_pass_requires_rendered_artifact")
    elif normalized in {"browser_auth_required", "browser_tool_timeout", "browser_not_authorized_by_user", "not_checked"}:
        blocked_reasons.append(normalized)
    return {
        "schema_id": "datalens.browser-runtime-qa",
        "status": normalized,
        "proof_level": "browser_rendered" if normalized in {"browser_pass", "browser_fail"} else "source_static",
        "browser_verified": normalized == "browser_pass",
        "checked_url": checked_url,
        "artifact_paths": paths,
        "artifact_hashes": {path: _file_sha256(path) for path in paths if Path(path).is_file()},
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "message": message,
        "blocked_reasons": blocked_reasons,
    }


def build_qa_attestation(
    *,
    plan: dict[str, Any],
    viewport_results: list[dict[str, Any]],
    dashboard_id: str,
    saved_revision: str,
    published_revision: str = "",
    runtime_errors: list[str] | None = None,
    artifact_paths: list[str] | None = None,
    browser_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind successful top-to-bottom browser evidence to one payload and revision."""

    plan_validation = validate_browser_qa_plan(plan)
    normalized_dashboard_id = str(dashboard_id or "").strip()
    normalized_saved_revision = str(saved_revision or "").strip()
    normalized_published_revision = str(published_revision or "").strip()
    target = plan.get("target") if isinstance(plan.get("target"), dict) else {}
    policy = normalize_browser_policy(
        plan.get("browser_policy") if isinstance(plan.get("browser_policy"), dict) else {},
        change_class="dashboard_layout",
    )
    final_visual = policy["purpose"] == "final_visual_acceptance"
    expected_tabs = list((plan.get("target") or {}).get("tab_ids") or []) or [""]
    required_widths = [
        int(item["width"])
        for item in plan.get("viewports") or []
        if isinstance(item, dict) and isinstance(item.get("width"), int)
    ]
    required_assertions = [
        str(item.get("id") or "")
        for item in (plan.get("evaluate") or {}).get("assertions") or []
        if isinstance(item, dict) and item.get("id")
    ]
    normalized_errors = [str(item) for item in runtime_errors or [] if str(item)]
    coverage: set[tuple[int, str, str]] = set()
    tab_runtime: dict[str, dict[str, Any]] = {
        tab_id: {
            "tab_id": tab_id,
            "activation_observed": False,
            "activation_method": "",
            "top_observed": False,
            "scroll_checkpoint_count": 0,
            "scroll_reached_bottom": False,
            "expected_object_ids": list(
                (target.get("tab_object_ids") or {}).get(tab_id) or []
            ),
            "observed_object_ids": [],
            "loading_object_ids": [],
            "visible_error_object_ids": [],
            "no_data_object_ids": [],
            "layout_findings": [],
            "global_error_markers": [],
            "screenshot_ref": "",
            "published_revision": normalized_published_revision,
        }
        for tab_id in expected_tabs
    }
    result_issues: list[str] = []
    for index, result in enumerate(viewport_results):
        if not isinstance(result, dict):
            result_issues.append(f"viewport_results[{index}] must be an object")
            continue
        width = (result.get("viewport") or {}).get("width")
        tab_id = str(result.get("tab_id") or "")
        scroll_position = str(result.get("scroll_position") or "")
        if isinstance(width, int) and not isinstance(width, bool):
            coverage.add((width, tab_id, scroll_position))
        if tab_id in tab_runtime:
            receipt = tab_runtime[tab_id]
            if result.get("activation_observed") is True:
                receipt["activation_observed"] = True
                receipt["activation_method"] = str(result.get("activation_method") or "tab_control")
            if scroll_position == "top" and result.get("top_observed") is True:
                receipt["top_observed"] = True
            checkpoints = result.get("scroll_checkpoint_count")
            if isinstance(checkpoints, int) and not isinstance(checkpoints, bool):
                receipt["scroll_checkpoint_count"] = max(
                    int(receipt["scroll_checkpoint_count"]), checkpoints
                )
            if scroll_position == "bottom" and result.get("scroll_reached_bottom") is True:
                receipt["scroll_reached_bottom"] = True
            for field_name in (
                "observed_object_ids",
                "loading_object_ids",
                "visible_error_object_ids",
                "no_data_object_ids",
                "layout_findings",
            ):
                receipt[field_name] = sorted(
                    set(receipt[field_name])
                    | {str(item) for item in result.get(field_name) or [] if str(item)}
                )
            receipt["global_error_markers"] = _merge_global_error_markers(
                list(receipt["global_error_markers"]),
                result.get("global_error_markers")
                or _unattributed_markers_from_observations(result.get("observations"))
                or [],
            )
            if result.get("screenshot_ref"):
                receipt["screenshot_ref"] = str(result["screenshot_ref"])
        if result.get("schema_id") != BROWSER_QA_RESULT_SCHEMA_ID:
            result_issues.append(f"viewport_results[{index}] has an unsupported schema_id")
        if result.get("passed") is not True:
            result_issues.append(f"viewport_results[{index}] did not pass every assertion")
        assertions = result.get("assertions") if isinstance(result.get("assertions"), dict) else {}
        observations = result.get("observations") if isinstance(result.get("observations"), dict) else {}
        missing = [
            assertion_id
            for assertion_id in required_assertions
            if assertions.get(assertion_id) is not True
        ]
        if missing:
            result_issues.append(
                f"viewport_results[{index}] failed or omitted assertions: {', '.join(missing)}"
            )
    expected_coverage = {
        (width, tab_id, scroll_position)
        for width in required_widths
        for tab_id in expected_tabs
        for scroll_position in ("top", "bottom")
    }
    missing_coverage = sorted(expected_coverage - coverage)
    if missing_coverage:
        result_issues.append(
            "missing tab/viewport/scroll coverage: "
            + ", ".join(f"{width}:{tab_id or 'main'}:{position}" for width, tab_id, position in missing_coverage)
        )
    if final_visual:
        incomplete_tabs = [
            tab_id
            for tab_id, receipt in tab_runtime.items()
            if receipt["activation_observed"] is not True
            or receipt["top_observed"] is not True
            or int(receipt["scroll_checkpoint_count"]) < 1
            or receipt["scroll_reached_bottom"] is not True
            or not receipt["screenshot_ref"]
        ]
        if incomplete_tabs:
            result_issues.append(
                "actual bottom scroll was not proven for: " + ", ".join(incomplete_tabs)
            )
        loading_tabs = [
            tab_id
            for tab_id, receipt in tab_runtime.items()
            if receipt["loading_object_ids"]
        ]
        if loading_tabs:
            result_issues.append("charts remained loading on: " + ", ".join(loading_tabs))
        error_tabs = [
            tab_id
            for tab_id, receipt in tab_runtime.items()
            if receipt["visible_error_object_ids"]
        ]
        if error_tabs:
            result_issues.append("visible chart errors remained on: " + ", ".join(error_tabs))
        global_error_issues = [
            issue
            for tab_id, receipt in tab_runtime.items()
            for issue in _global_error_marker_issues(tab_id, receipt["global_error_markers"])
        ]
        result_issues.extend(global_error_issues)
        missing_objects = [
            f"{tab_id}:{object_id}"
            for tab_id, receipt in tab_runtime.items()
            for object_id in receipt["expected_object_ids"]
            if object_id not in set(receipt["observed_object_ids"])
            and object_id not in set(receipt["no_data_object_ids"])
        ]
        if missing_objects:
            result_issues.append("expected objects were not observed: " + ", ".join(missing_objects))
    if not normalized_dashboard_id:
        result_issues.append("dashboard_id is required")
    elif str(target.get("dashboard_id") or "") != normalized_dashboard_id:
        result_issues.append("dashboard_id differs from the browser QA plan")
    if not normalized_saved_revision:
        result_issues.append("saved_revision is required")
    elif str(target.get("saved_revision") or "") and str(target.get("saved_revision")) != normalized_saved_revision:
        result_issues.append("saved_revision differs from the browser QA plan")
    if not normalized_published_revision:
        result_issues.append("published_revision is required")
    elif str(target.get("published_revision") or "") and str(target.get("published_revision")) != normalized_published_revision:
        result_issues.append("published_revision differs from the browser QA plan")
    if normalized_errors:
        result_issues.append("runtime or network errors were observed")
    issues = [*plan_validation["issues"], *result_issues]
    binding = plan.get("attestation_binding") if isinstance(plan.get("attestation_binding"), dict) else {}
    paths = [str(path) for path in artifact_paths or [] if str(path)]
    artifact_hashes = {
        path: _file_sha256(path)
        for path in paths
        if Path(path).is_file()
    }
    if not paths or len(artifact_hashes) != len(paths):
        issues.append("browser QA requires readable screenshot or evaluation artifacts")
    metrics = dict(browser_metrics or {})
    if final_visual:
        expected_metrics = {
            "browser_calls_before_final_visual_stage": 0,
            "browser_calls_to_non_dashboard_objects": 0,
            "browser_mutation_attempts": 0,
            "browser_tabs_fully_scrolled": len(expected_tabs),
        }
        for key, expected_value in expected_metrics.items():
            if metrics.get(key) != expected_value:
                issues.append(f"browser metric {key} must equal {expected_value}")
    attestation: dict[str, Any] = {
        "schema_id": "qa_attestation",
        "ok": not issues,
        "status": "passed" if not issues else "failed",
        "proof_level": "browser_rendered",
        "browser_route": "internal_browser_adapter",
        "dashboard_id": normalized_dashboard_id,
        "saved_revision": normalized_saved_revision,
        "published_revision": normalized_published_revision,
        "final_payload_attestation_sha256": str(
            binding.get("final_payload_attestation_sha256") or ""
        ),
        "payload_set_sha256": str(binding.get("payload_set_sha256") or ""),
        "dashboard_composition_sha256": str(
            binding.get("dashboard_composition_sha256") or ""
        ),
        "api_diagnostics_receipt_hash": str(
            binding.get("api_diagnostics_receipt_hash") or ""
        ),
        "browser_qa_plan_sha256": str(plan.get("canonical_sha256") or ""),
        "browser_policy_mode": str(policy.get("mode") or ""),
        "browser_policy_purpose": str(policy.get("purpose") or ""),
        "task_id": str(binding.get("task_id") or ""),
        "contract_revision": int(binding.get("contract_revision") or 0),
        "plan_hash": str(binding.get("plan_hash") or ""),
        "candidate_build_identity": str(binding.get("candidate_build_identity") or ""),
        "viewport_widths": required_widths,
        "tab_ids": expected_tabs,
        "full_scroll_checked": not missing_coverage and (
            not final_visual
            or all(receipt["scroll_reached_bottom"] is True for receipt in tab_runtime.values())
        ),
        "tab_receipts": list(tab_runtime.values()),
        "coverage": [
            {"width": width, "tab_id": tab_id, "scroll_position": position}
            for width, tab_id, position in sorted(coverage)
        ],
        "runtime_errors": normalized_errors,
        "issues": issues,
        "artifact_paths": paths,
        "artifact_hashes": artifact_hashes,
        "browser_metrics": metrics,
        "chart_query_equivalence": "incomplete" if final_visual else "not_evaluated",
    }
    attestation["sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in attestation.items() if key != "sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return attestation


def validate_qa_attestation_binding(
    qa: dict[str, Any],
    *,
    dashboard_id: str,
    saved_revision: str,
    published_revision: str,
    final_payload_attestation_sha256: str,
    payload_set_sha256: str,
    dashboard_composition_sha256: str,
    task_id: str = "",
    contract_revision: int = 0,
    plan_hash: str = "",
    candidate_build_identity: str = "",
) -> list[str]:
    """Validate that browser evidence owns the exact revision and payload being completed."""

    if not isinstance(qa, dict) or not qa:
        return ["qa_attestation is required"]
    issues: list[str] = []
    if qa.get("schema_id") != "qa_attestation":
        issues.append("qa_attestation schema_id is unsupported")
    if qa.get("ok") is not True or qa.get("status") != "passed":
        issues.append("qa_attestation must have status=passed")
    expected = {
        "dashboard_id": str(dashboard_id or ""),
        "saved_revision": str(saved_revision or ""),
        "published_revision": str(published_revision or ""),
        "final_payload_attestation_sha256": str(final_payload_attestation_sha256 or ""),
        "payload_set_sha256": str(payload_set_sha256 or ""),
        "dashboard_composition_sha256": str(dashboard_composition_sha256 or ""),
    }
    for key, value in expected.items():
        if not value:
            issues.append(f"expected {key} is required")
        elif str(qa.get(key) or "") != value:
            issues.append(f"qa_attestation {key} does not match")
    exact_candidate = {
        "task_id": str(task_id or ""),
        "contract_revision": int(contract_revision or 0),
        "plan_hash": str(plan_hash or ""),
        "candidate_build_identity": str(candidate_build_identity or ""),
    }
    for key, value in exact_candidate.items():
        if value and qa.get(key) != value:
            issues.append(f"qa_attestation {key} does not match")
    widths = sorted(
        int(item)
        for item in qa.get("viewport_widths") or []
        if isinstance(item, int) and not isinstance(item, bool)
    )
    if not widths:
        issues.append("qa_attestation must cover at least one applicable viewport")
    tab_ids = [str(item) for item in qa.get("tab_ids") or [] if str(item)]
    coverage = {
        (
            item.get("width"),
            str(item.get("tab_id") or ""),
            str(item.get("scroll_position") or ""),
        )
        for item in qa.get("coverage") or []
        if isinstance(item, dict)
    }
    expected_coverage = {
        (width, tab_id, position)
        for width in widths
        for tab_id in tab_ids
        for position in ("top", "bottom")
    }
    if not tab_ids or coverage != expected_coverage or qa.get("full_scroll_checked") is not True:
        issues.append("qa_attestation must cover every tab at top and after full scroll")
    if qa.get("browser_policy_purpose") == "final_visual_acceptance":
        if not re.fullmatch(r"[a-f0-9]{64}", str(qa.get("api_diagnostics_receipt_hash") or "")):
            issues.append("final visual attestation requires API diagnostics binding")
        for field_name in ("task_id", "contract_revision", "plan_hash", "candidate_build_identity"):
            if not qa.get(field_name):
                issues.append(f"final visual attestation requires {field_name}")
        tab_receipts = {
            str(item.get("tab_id") or ""): item
            for item in qa.get("tab_receipts") or []
            if isinstance(item, dict)
        }
        if set(tab_receipts) != set(tab_ids) or any(
            item.get("scroll_reached_bottom") is not True
            or item.get("activation_observed") is not True
            or item.get("top_observed") is not True
            or int(item.get("scroll_checkpoint_count") or 0) < 1
            or bool(item.get("loading_object_ids"))
            or bool(item.get("visible_error_object_ids"))
            or not item.get("screenshot_ref")
            for item in tab_receipts.values()
        ):
            issues.append("final visual attestation requires compact successful per-tab scroll receipts")
        marker_issues = [
            issue
            for tab_id, item in tab_receipts.items()
            for issue in _global_error_marker_issues(tab_id, item.get("global_error_markers") or [])
        ]
        if marker_issues:
            issues.extend(marker_issues)
        metrics = qa.get("browser_metrics") if isinstance(qa.get("browser_metrics"), dict) else {}
        expected_metrics = {
            "browser_calls_before_final_visual_stage": 0,
            "browser_calls_to_non_dashboard_objects": 0,
            "browser_mutation_attempts": 0,
            "browser_tabs_fully_scrolled": len(tab_ids),
        }
        if any(metrics.get(key) != value for key, value in expected_metrics.items()):
            issues.append("final visual attestation browser call ledger is incomplete")
        if qa.get("chart_query_equivalence") != "incomplete":
            issues.append("final visual attestation must state API chart-query equivalence limitation")
    if qa.get("runtime_errors") != []:
        issues.append("qa_attestation contains runtime or network errors")
    artifact_paths = [str(item) for item in qa.get("artifact_paths") or [] if str(item)]
    artifact_hashes = qa.get("artifact_hashes") if isinstance(qa.get("artifact_hashes"), dict) else {}
    if not artifact_paths or set(artifact_hashes) != set(artifact_paths):
        issues.append("qa_attestation artifact hashes are incomplete")
    elif any(not re.fullmatch(r"[a-f0-9]{64}", str(value or "")) for value in artifact_hashes.values()):
        issues.append("qa_attestation artifact hash is invalid")
    expected_sha = hashlib.sha256(
        json.dumps(
            {key: value for key, value in qa.items() if key != "sha256"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if qa.get("sha256") != expected_sha:
        issues.append("qa_attestation hash is stale")
    return issues


def delivery_status_from_qa_attestation(
    qa: dict[str, Any] | None,
    **expected: str,
) -> str:
    """Return done only for a successful attestation matching the published revision."""

    if not qa:
        return "runtime_not_verified"
    return (
        "done"
        if not validate_qa_attestation_binding(qa, **expected)
        else "blocked"
    )


def build_runtime_publish_gate(
    *,
    status: str = "not_run",
    dashboard_id: str,
    tab_id: str = "",
    dashboard_url: str = "",
    changed_object_ids: list[str] | None = None,
    checked_error_markers: list[str] | None = None,
    proof_artifacts: list[str] | None = None,
    runtime_messages: list[str] | None = None,
    visible_object_ids: list[str] | None = None,
    selector_statuses: list[dict[str, Any]] | None = None,
    blocked_reason: str = "",
) -> dict[str, Any]:
    normalized = _normalize_gate_status(status)
    changed = [str(item) for item in changed_object_ids or [] if str(item)]
    markers = checked_error_markers or RUNTIME_ERROR_MARKERS
    artifacts = [str(path) for path in proof_artifacts or [] if str(path)]
    blocking_errors = _runtime_blocking_errors(runtime_messages or [], markers)
    visible_missing = (
        sorted(set(changed) - {str(item) for item in visible_object_ids or [] if str(item)})
        if visible_object_ids is not None
        else []
    )
    selector_errors = _selector_blocking_errors(selector_statuses or [])
    blocking_errors.extend(selector_errors)
    if visible_missing:
        blocking_errors.extend(
            {
                "marker": "changed_object_not_visible",
                "message": f"changed object {object_id} was not visible in runtime",
                "object_id": object_id,
            }
            for object_id in visible_missing
        )
    if normalized == "passed" and blocking_errors:
        normalized = "failed"
    if normalized == "passed" and not artifacts:
        normalized = "blocked"
        blocked_reason = blocked_reason or "runtime proof artifact is required"
    if normalized == "not_run" and blocked_reason:
        normalized = "blocked"
    return {
        "schema_id": "datalens.runtime-publish-gate",
        "status": normalized,
        "dashboard_id": dashboard_id,
        "tab_id": tab_id,
        "dashboard_url": dashboard_url,
        "changed_object_ids": changed,
        "checked_error_markers": markers,
        "blocking_errors": blocking_errors,
        "visible_assertions": [
            {"object_id": object_id, "visible": object_id not in visible_missing}
            for object_id in changed
        ],
        "selector_statuses": selector_statuses or [],
        "proof_artifacts": artifacts,
        "blocked_reason": blocked_reason if normalized in {"blocked", "not_run"} else "",
    }


def delivery_status_from_runtime_gate(runtime_gate: dict[str, Any]) -> str:
    status = str(runtime_gate.get("status") or "").strip()
    if status == "passed":
        return "done"
    if status in {"blocked", "not_run", ""}:
        return "runtime_not_verified"
    return "blocked"


def write_timestamped_evidence(root: str | Path, subdir: str, payload: dict[str, Any]) -> dict[str, Any]:
    base = Path(root) / "artifacts" / subdir
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), "sha256": _file_sha256(path)}


def _normalize_status(status: str) -> BrowserQaStatus:
    normalized = str(status or "not_checked").strip().lower()
    aliases = {
        "pass": "browser_pass",
        "passed": "browser_pass",
        "fail": "browser_fail",
        "failed": "browser_fail",
        "auth": "browser_auth_required",
        "auth_required": "browser_auth_required",
        "timeout": "browser_tool_timeout",
        "tool_timeout": "browser_tool_timeout",
        "not_authorized": "browser_not_authorized_by_user",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {
        "browser_pass",
        "browser_fail",
        "browser_auth_required",
        "browser_tool_timeout",
        "browser_not_authorized_by_user",
        "not_checked",
    }:
        return normalized  # type: ignore[return-value]
    return "not_checked"


def _normalize_gate_status(status: str) -> str:
    normalized = str(status or "not_run").strip().lower()
    aliases = {
        "pass": "passed",
        "browser_pass": "passed",
        "ok": "passed",
        "fail": "failed",
        "browser_fail": "failed",
        "auth": "blocked",
        "auth_required": "blocked",
        "browser_auth_required": "blocked",
        "timeout": "blocked",
        "browser_tool_timeout": "blocked",
        "not_checked": "not_run",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"passed", "failed", "blocked", "not_run"}:
        return normalized
    return "not_run"


def _runtime_blocking_errors(messages: list[str], markers: list[str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for message in messages:
        text = str(message)
        lowered = text.lower()
        for marker in markers:
            if str(marker).lower() in lowered:
                errors.append({"marker": str(marker), "message": text[:500]})
                break
    return errors


def _selector_blocking_errors(selector_statuses: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for selector in selector_statuses:
        status = str(selector.get("status") or "").strip().lower()
        if status in {"", "passed", "loaded", "ok"}:
            continue
        selector_id = str(selector.get("selector_id") or selector.get("id") or "")
        errors.append(
            {
                "marker": "selector_load_status",
                "message": f"selector {selector_id or '<unknown>'} runtime status is {status}",
                "object_id": selector_id,
            }
        )
    return errors


def _file_sha256(path: str | Path) -> str:
    target = Path(path)
    if not target.is_file():
        return ""
    return hashlib.sha256(target.read_bytes()).hexdigest()
