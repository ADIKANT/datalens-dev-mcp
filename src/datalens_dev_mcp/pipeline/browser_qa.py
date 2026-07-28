from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


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

BROWSER_QA_PLAN_SCHEMA_VERSION = "datalens.browser-qa-plan.v2"
BROWSER_QA_RESULT_SCHEMA_VERSION = "datalens.browser-qa-result.v2"
BROWSER_QA_MAX_CALLS = 3
BROWSER_QA_VIEWPORTS = (
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
        "description": "Every strict KPI has a visible non-empty value inside a compact unclipped tile.",
    },
    {
        "id": "legend_typography_consistent",
        "description": "Legend typography has one size and matches the render contract.",
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
) -> dict[str, Any]:
    """Build a deterministic three-call, read-only browser QA plan.

    The executor performs one navigation, one batched evaluation call covering
    both viewports, and one batched screenshot call covering both viewports.
    The evaluate source is intentionally self-contained so a browser adapter
    does not need exploratory DOM calls.
    """

    normalized_dashboard_id = str(dashboard_id or "").strip()
    if not normalized_dashboard_id:
        raise ValueError("dashboard_id is required")
    normalized_object_ids = _normalized_string_list(expected_object_ids)
    if not normalized_object_ids:
        raise ValueError("expected_object_ids must contain at least one object id")
    normalized_tabs = _normalized_string_list(tab_ids)
    normalized_selectors = _normalize_selector_contracts(selector_contracts or [])
    normalized_comparison_ids = _normalized_string_list(comparison_context_object_ids or [])
    normalized_tooltip_modes = _normalize_tooltip_comparison_modes(
        tooltip_comparison_modes or {}
    )
    normalized_render_contract = _normalize_browser_render_contract(render_contract or {})
    viewports = [dict(viewport) for viewport in BROWSER_QA_VIEWPORTS]
    evaluation_input = {
        "expected_object_ids": normalized_object_ids,
        "selector_contracts": normalized_selectors,
        "comparison_enabled": bool(comparison_enabled),
        "comparison_context_object_ids": normalized_comparison_ids,
        "tooltip_comparison_modes": normalized_tooltip_modes,
        "render_contract": normalized_render_contract,
    }
    evaluate_source = _build_browser_qa_evaluate_source(evaluation_input)
    artifact_stem = _safe_artifact_stem(normalized_dashboard_id)
    plan: dict[str, Any] = {
        "schema_version": BROWSER_QA_PLAN_SCHEMA_VERSION,
        "target": {
            "dashboard_id": normalized_dashboard_id,
            "dashboard_url": str(dashboard_url or "").strip(),
            "tab_ids": normalized_tabs,
            "expected_object_ids": normalized_object_ids,
        },
        "viewports": viewports,
        "render_contract": normalized_render_contract,
        "selector_contracts": normalized_selectors,
        "comparison_enabled": bool(comparison_enabled),
        "comparison_context_object_ids": normalized_comparison_ids,
        "tooltip_comparison_modes": normalized_tooltip_modes,
        "execution": {
            "max_browser_calls": BROWSER_QA_MAX_CALLS,
            "navigation_count": 1,
            "evaluation_count_per_viewport": 1,
            "screenshots_per_viewport": 1,
            "reload_count": 0,
            "retry_count": 0,
            "dom_mutation_allowed": False,
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
                    "operation": "evaluate_viewports_batch",
                    "viewport_ids": [viewport["id"] for viewport in viewports],
                    "evaluate_source_ref": "#/evaluate/source",
                },
                {
                    "ordinal": 3,
                    "operation": "screenshot_viewports_batch",
                    "viewport_ids": [viewport["id"] for viewport in viewports],
                    "full_page": True,
                },
            ],
        },
        "evaluate": {
            "language": "javascript",
            "read_only": True,
            "source": evaluate_source,
            "assertions": [dict(assertion) for assertion in BROWSER_QA_ASSERTIONS],
        },
        "expected_result": {
            "schema_version": BROWSER_QA_RESULT_SCHEMA_VERSION,
            "required_fields": ["viewport", "passed", "assertions", "observations"],
            "assertion_ids": [assertion["id"] for assertion in BROWSER_QA_ASSERTIONS],
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


def browser_qa_plan_sha256(plan: dict[str, Any]) -> str:
    canonical = {key: value for key, value in plan.items() if key != "canonical_sha256"}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_browser_qa_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate the deterministic browser plan without executing it."""

    issues: list[str] = []
    if not isinstance(plan, dict) or plan.get("schema_version") != BROWSER_QA_PLAN_SCHEMA_VERSION:
        return {"ok": False, "issues": ["invalid_schema_version"]}

    viewports = plan.get("viewports")
    expected_viewports = [dict(viewport) for viewport in BROWSER_QA_VIEWPORTS]
    if viewports != expected_viewports:
        issues.append("required_viewports_missing_or_changed")

    execution = plan.get("execution") if isinstance(plan.get("execution"), dict) else {}
    calls = execution.get("calls") if isinstance(execution.get("calls"), list) else []
    max_calls = execution.get("max_browser_calls")
    if not isinstance(max_calls, int) or max_calls > BROWSER_QA_MAX_CALLS or len(calls) > BROWSER_QA_MAX_CALLS:
        issues.append("browser_call_budget_exceeded")
    expected_operations = ["navigate_once", "evaluate_viewports_batch", "screenshot_viewports_batch"]
    if [call.get("operation") for call in calls if isinstance(call, dict)] != expected_operations:
        issues.append("browser_call_sequence_changed")
    if execution.get("navigation_count") != 1:
        issues.append("navigation_count_changed")
    if execution.get("evaluation_count_per_viewport") != 1:
        issues.append("evaluation_count_changed")
    if execution.get("screenshots_per_viewport") != 1:
        issues.append("screenshot_count_changed")
    if execution.get("reload_count") != 0 or execution.get("retry_count") != 0:
        issues.append("reload_or_retry_not_allowed")
    if execution.get("dom_mutation_allowed") is not False:
        issues.append("dom_mutation_must_be_disabled")

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
    required_assertion_ids = {assertion["id"] for assertion in BROWSER_QA_ASSERTIONS}
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

  const legends = all('[data-role="legend"],[aria-label="Legend"],.legend').filter(visible);
  const legendTypography = Array.from(new Set(legends.map((node) => {
    const css = computed(node);
    return `${Number.parseFloat(css.fontSize)}/${Number.parseFloat(css.lineHeight)}`;
  })));
  const expectedLegend = input.render_contract.legend;

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
        nonempty: Boolean(node && text(node).length > 0)
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

  const expectedSelector = input.render_contract.selector;
  const comparisonContextMatches = input.comparison_enabled
    ? visibleNonemptyComparisonCount === 1
    : visibleNonemptyComparisonCount === 0;
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
        row.value_marker_found && row.value_visible && row.value_nonempty && row.value_inside &&
        row.height_px >= input.render_contract.kpi.min_height_px - 1 &&
        row.height_px <= input.render_contract.kpi.max_height_px + 1
      )),
    legend_typography_consistent: legendTypography.length <= 1 && legendTypography.every((value) =>
      value === `${expectedLegend.font_size_px}/${expectedLegend.line_height_px}`),
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
    tooltip_owner_shell_cardinality: tooltipMatches,
    tooltip_comparison_mode_contract: tooltipComparisonModeMatches &&
      !singlePeriodHasComparisonChrome,
    stable_scrollbar_gutter: stableGutterMatches,
    no_redundant_row_title_tooltips: redundantRowTitles.length === 0
  };
  return {
    schema_version: "datalens.browser-qa-result.v2",
    viewport: {width: window.innerWidth, height: window.innerHeight},
    passed: Object.values(assertions).every(Boolean),
    assertions,
    observations: {
      object_rows: objectRows,
      marker_matches: markerMatches,
      document_horizontal_overflow_px: documentOverflow,
      kpi_rows: kpiRows,
      legend_typography: legendTypography,
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
      redundant_row_title_tooltip_count: redundantRowTitles.length
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
            "min_height_px": _positive_number(
                kpi_layout.get("min_height_px"),
                default=88,
            ),
            "max_height_px": _positive_number(
                kpi_layout.get("max_height_px"),
                default=112,
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
            }
        )
    return normalized


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


def _normalized_string_list(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


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
        "schema_version": "datalens.browser-runtime-qa.v1",
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
        "schema_version": "datalens.runtime-publish-gate.delta-v6",
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
