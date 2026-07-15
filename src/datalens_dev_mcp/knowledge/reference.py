from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from datalens_dev_mcp.knowledge.formulas import validate_formula_expression
from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_json, resource_text

ARTIFACT_DIR = Path(os.environ.get("DATALENS_REFERENCE_ARTIFACT_DIR", "artifacts/reference_runs"))
KNOWLEDGE_RESOURCE_ROOT = "schemas/datalens-knowledge"
RECIPE_REGISTRY_RESOURCE = "templates/datalens/recipes/recipe-registry.json"
REFERENCE_VERSION = "2026-06-30.tool_navigation.v1"
REFERENCE_DATE = "2026-06-30"


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def build_reference_response(
    mode: str = "search",
    query: str = "",
    name: str = "",
    limit: int = 5,
    max_chars: int = 6000,
    project_root: str = ".",
) -> dict[str, Any]:
    normalized = (mode or "search").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in {"authoring", "authoring_plan", "plan"}:
        normalized = "authoring_guidance"
    if normalized in {"object", "contract", "object_contract"}:
        normalized = "object_contract"
    term = (name or query or "").strip()
    limit = max(1, min(int(limit or 5), 10))
    max_chars = max(1000, min(int(max_chars or 6000), 12000))
    if normalized == "recipe":
        result = _recipe(term, limit)
    elif normalized == "formula":
        result = _formula(term, limit)
    elif normalized in {"chart_selection", "visual_decision", "dataviz_chart_decision"}:
        result = _chart_selection(term, limit)
        normalized = "chart_selection"
    elif normalized in {"route_selection", "route_selection_policy", "route_selection_policy_v3", "route_policy", "route_policy_v4"}:
        result = _runtime_quality_reference("route_selection", term)
        normalized = "route_selection"
    elif normalized in {"renderer_visual_spec", "renderer_contract", "visual_contract"}:
        result = _renderer_visual_spec(term, limit)
        normalized = "renderer_contract"
    elif normalized in {"datalens_editor_runtime", "editor_runtime", "advanced_editor_runtime"}:
        result = _datalens_editor_runtime(term, limit)
        normalized = "datalens_editor_runtime"
    elif normalized in {"dashboard_system_type", "dashboard_system", "dashboard_type"}:
        result = _dashboard_system_type(term, limit)
        normalized = "dashboard_system_type"
    elif normalized in {"negative_requirements", "negative_requirement", "negative_ledger"}:
        result = _negative_requirements(term, limit)
        normalized = "negative_requirements"
    elif normalized in {"delivery_intent", "delivery_policy", "write_intent"}:
        result = _delivery_intent(term, limit)
        normalized = "delivery_intent"
    elif normalized in {"delivery_approval", "approval_intent", "approval_policy_v3"}:
        result = _runtime_quality_reference("delivery_approval", term)
        normalized = "delivery_approval"
    elif normalized in {"target_lock", "target_delivery", "target_delivery_lock"}:
        result = _runtime_quality_reference("target_lock", term)
        normalized = "target_lock"
    elif normalized in {"object_granularity", "dashboard_object_granularity", "dashboard_object_graph"}:
        result = _runtime_quality_reference("object_granularity", term)
        normalized = "object_granularity"
    elif normalized in {"selector_layout", "selector_wiring", "selector_layout_contract"}:
        result = _runtime_quality_reference("selector_layout", term)
        normalized = "selector_layout"
    elif normalized in {"native_table", "native_table_contract", "table_contract"}:
        result = _runtime_quality_reference("native_table", term)
        normalized = "native_table"
    elif normalized in {"kpi_indicator", "indicator_contract", "kpi_contract"}:
        result = _runtime_quality_reference("kpi_indicator", term)
        normalized = "kpi_indicator"
    elif normalized in {"source_route", "source_route_policy", "source_route_resolver"}:
        result = _runtime_quality_reference("source_route", term)
        normalized = "source_route"
    elif normalized in {"visual_quality", "visual_readback", "visual_quality_gate"}:
        result = _runtime_quality_reference("visual_quality", term)
        normalized = "visual_quality"
    elif normalized in {"performance_budget", "performance_gate"}:
        result = _runtime_quality_reference("performance_budget", term)
        normalized = "performance_budget"
    elif normalized in {"repo_size", "repo_size_budget", "repository_size"}:
        result = _runtime_quality_reference("repo_size", term)
        normalized = "repo_size"
    elif normalized in {"api_contract", "api_contracts", "openapi_contract"}:
        result = _api_contract(term, limit)
        normalized = "api_contract"
    elif normalized in {"current_docs_delta", "docs_delta", "current_docs"}:
        result = _current_docs_delta(term, limit)
        normalized = "current_docs_delta"
    elif normalized in {"tool_selection", "tools", "tool_navigation"}:
        result = _tool_selection(term, limit)
        normalized = "tool_selection"
    elif normalized == "visualization":
        result = _visualization(term, limit)
    elif normalized == "error":
        result = _error(term, limit)
    elif normalized == "capability":
        result = _capability(term, limit)
    elif normalized == "source_trace":
        result = _source_trace(term, limit)
    elif normalized == "authoring_guidance":
        result = _authoring_guidance(term, limit)
    elif normalized == "object_contract":
        result = _object_contract(term, limit)
    else:
        result = _search(term, limit)
        normalized = "search"
    envelope = _reference_envelope(normalized, term, result)
    payload = {
        "ok": True,
        "schema_version": "2026-06-25.datalens_reference.v1",
        "reference_version": REFERENCE_VERSION,
        "reference_date": REFERENCE_DATE,
        "mode": normalized,
        "query": term,
        **envelope,
        "source_precedence": [
            "current_openapi",
            "current_official_documentation",
            "release_notes_and_dated_changes",
            "observed_live_runtime_evidence",
            "local_safety_governance_policy",
        ],
        **result,
    }
    return _bound_payload(payload, max_chars=max_chars, project_root=Path(project_root))


def lookup_error_reference(text: str, limit: int = 3) -> list[dict[str, Any]]:
    return _error(text, limit).get("results", [])


def _load_json(relative: str, default: Any) -> Any:
    try:
        return resource_json(f"{KNOWLEDGE_RESOURCE_ROOT}/{relative}")
    except RuntimeResourceError:
        return default


def _resource_or_file_json(relative: str, default: Any) -> Any:
    try:
        return resource_json(relative)
    except RuntimeResourceError:
        path = Path(relative)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return default


def _load_jsonl(relative: str) -> list[dict[str, Any]]:
    try:
        text = resource_text(f"{KNOWLEDGE_RESOURCE_ROOT}/{relative}")
    except RuntimeResourceError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _reference_envelope(mode: str, term: str, result: dict[str, Any]) -> dict[str, Any]:
    del term
    rules_by_mode = {
        "chart_selection": [
            "Start from business question, audience, analytical task, and data shape.",
            "Apply negative requirements before choosing the final family.",
            "Use the closed Wizard-first registry; JS needs an explicit request or registered capability gap and QL is explicit-only.",
            "KPI deltas require an explicit comparator or baseline.",
            "Persist chart decision records before payload generation.",
        ],
        "renderer_contract": [
            "Use native title/hint metadata; chart body must not duplicate dashboard chrome.",
            "Keep colors neutral first; semantic colors require declared direction.",
            "Do not emit decorative CSS, shadows, 3D effects, or gradients.",
            "Pre-shape data before render and respect wrapFn runtime budgets.",
            "Native table bars use table formatting, not custom HTML bars.",
        ],
        "negative_requirements": [
            "Record user removals and exclusions in the negative-requirement ledger.",
            "Compile each negative into forbidden concepts, tokens, families, surfaces, and severity.",
            "Sanitize user-decision logs so forbidden wording is not reintroduced.",
            "Validate generated dashboard, artifact, report, and requirement surfaces.",
            "Treat drift findings as project validation failures.",
        ],
        "delivery_intent": [
            "Read-only review stays read-only.",
            "Draft/save-only language plans saved-branch writes without publish.",
            "Save-plus-publish requires known target, enabled writes, explicit approval, fresh read, and saved readback.",
            "Never guess workbook, dashboard, chart, dataset, or connection ids.",
            "Keep saved and published readback as separate proof classes.",
        ],
        "delivery_approval": [
            "Normal implement/fix/enhance/redesign/update with a locked target does not require a literal I approve phrase.",
            (
                "Current user request, goal objective file, Codex tool approval, manifest approval, "
                "or explicit chat approval are valid approval sources."
            ),
            "Destructive, credential, permission, move, delete, and ambiguous-target work still requires extra confirmation.",
            "Draft/save-only/no-publish/plan-only text overrides publish.",
            "Approved live delivery uses save, saved readback, publish, and published readback after safe gates.",
        ],
        "target_lock": [
            "Parse workbook, dashboard, and chart ids from user URL, manifest, workbook entry, or explicit text.",
            "Every plan, save, publish, readback, and final report must carry the same target lock hash.",
            "Wrong-target saved or published readback blocks completion.",
            "A target dashboard with zero active widgets while generated widgets exist is a hard failure.",
            "Final reports must not cite a different dashboard id than the user target.",
        ],
        "route_selection": [
            "Preserve an existing object route unless the user explicitly requests conversion.",
            "Explicit JS or Advanced Editor requests use Advanced Editor JS.",
            "Explicit Wizard/native requests use Wizard only where current docs/API and local route policy support it.",
            "Unsupported explicit Wizard requests return docs/API evidence and no silent JS fallback.",
            "Tables, selectors, KPI/indicators, markdown, and dataset-backed sources use canonical object routes.",
        ],
        "object_granularity": [
            "A dashboard is a DataLens object graph, not one full-page Advanced Editor app.",
            "Every business visual needs a separate object reference in the dashboard manifest.",
            "Advanced Editor objects may render one visual only.",
            "Composite selector bars, KPI card grids, methodology pages, and HTML tables inside one chart are blocked.",
            "Readback object counts must match the manifest before completion.",
        ],
        "selector_layout": [
            "Selectors are native control widgets with explicit dashboard relation targets.",
            "Selector width is computed from kind and label length, and rows must stay at or below 96 percent.",
            "Overflow creates another selector row instead of shrinking below the minimum width.",
            "Targets must exist in dashboard objects and fields must exist in dataset/source schema.",
            "Selector-looking labels inside chart bodies are not valid selectors.",
        ],
        "native_table": [
            "Tabular output uses table_node/editor_table unless the user explicitly requests custom JS or docs/API block the native route.",
            "Non-empty source evidence must not render as a skeleton table.",
            "Tables require columns, rows or query proof, sorting, formatting, and empty-state policy.",
            "In-cell bars require value, min, max, barColor, readable labels, and contrast policy.",
            "Zero-row sources need an explicit empty state, not a blank grid.",
        ],
        "kpi_indicator": [
            "Each KPI/indicator is a separate object unless a supported native grouped object preserves native metadata.",
            "Formula, unit, grain, and comparator policy are required.",
            "Previous-period deltas are explicit only.",
            "KPI card grids inside Advanced Editor are blocked.",
            "Native title and hint metadata stay outside chart bodies.",
        ],
        "source_route": [
            "Existing dataset ids and discovered workbook datasets take precedence over embedded JS data.",
            "Existing connections require a dataset plan before chart payloads.",
            "Unsupported local file upload becomes a manual upload handoff, not an embedded final dashboard.",
            "Embedded static mode requires explicit approval and bounded data size.",
            "Deployment reports record source mode and dataset/schema readback evidence.",
        ],
        "visual_quality": [
            "Bar and period charts need direct labels or readable axes/gridlines.",
            "KPI comparators are explicit only; no implicit previous-period deltas.",
            "Use color for grouping, focus, alerting, or semantic status, not decoration.",
            "Redundant adjacent visuals are removed unless each answers a distinct business question.",
            "Unavailable browser/visual QA is reported as unavailable, not pass.",
        ],
        "performance_budget": [
            "Tab render estimate above 10 seconds warns, above 15 seconds blocks publish, and around 20 seconds is a hard fail.",
            "Publish plans include per-tab widgets, heavy sources, duplicate SQL fingerprints, JS size, embedded data size, and warnings.",
            "Duplicated heavy source SQL without cache/reuse is blocked.",
            "Unbounded detail queries, CROSS JOIN totals, broad OR after JOIN, and heavy client transforms are blocked.",
            "Large embedded data requires explicit static/embedded approval.",
        ],
        "repo_size": [
            "Tracked source excluding .git must stay under the configured repository budget.",
            "Build, dist, wheel, tarball, clean-room, package, mcp_runs, and bytecode artifacts must not be tracked.",
            "Runtime package assets must be compact and manifest-synced.",
            "Keep compact reports, hashes, manifests, and fixtures instead of bulky generated evidence.",
            "Use scripts/check_repo_size_budget.py and check_no_generated_artifacts_tracked.py before completion.",
        ],
        "api_contract": [
            "Use the current OpenAPI-derived operation policy as the method index.",
            "Supported tools use guarded adapters; unsupported methods return structured unavailable responses.",
            "QL read/create/update is explicit-only; it is never selected automatically and delete remains closed.",
            "Delete, move, permission, and blind-write operations stay unsupported unless explicitly guarded.",
            "Fixture hashes must match request and response schema references.",
        ],
        "current_docs_delta": [
            "Use the current docs reconciliation report before changing runtime behavior.",
            "Classify new official features as supported, guarded plan-only, read-only reference, or unsupported.",
            "Keep raw mirror material outside packaged runtime artifacts.",
            "Preserve route policy when official docs describe unsupported chart creation routes.",
            "Regenerate reconciliation artifacts before asserting current-doc coverage.",
        ],
        "tool_selection": [
            "Use one standard tools/list surface for normal Codex workflows.",
            "Start with runtime/auth status and a project_context_ref.v1 supplied by Project Memory Bank.",
            "Use dl_reference for bounded policy lookup instead of reading long docs repeatedly.",
            "Use read/snapshot tools before planning writes.",
            "Safe apply and publish tools require approval gates and readback artifacts.",
        ],
    }
    tools_by_mode = {
        "chart_selection": [
            "dl_reference(mode='renderer_contract')",
            "dl_validate_project",
            "dl_build_payload_plan",
        ],
        "renderer_contract": ["dl_validate_editor_runtime_contract", "dl_validate_project", "dl_build_payload_plan"],
        "negative_requirements": [
            "dl_validate_project",
            "dl_build_payload_plan",
        ],
        "delivery_intent": [
            "dl_build_payload_plan",
            "dl_create_safe_apply_plan",
            "dl_execute_safe_apply",
            "dl_create_publish_from_saved_plan",
            "dl_readback_and_report",
        ],
        "delivery_approval": [
            "dl_build_payload_plan",
            "dl_create_safe_apply_plan",
            "dl_create_publish_from_saved_plan",
            "dl_readback_and_report",
        ],
        "target_lock": ["dl_build_payload_plan", "dl_create_safe_apply_plan", "dl_readback_and_report"],
        "route_selection": ["dl_reference(mode='current_docs_delta')", "dl_validate_project", "dl_build_payload_plan"],
        "object_granularity": ["dl_validate_project", "dl_build_payload_plan", "dl_create_safe_apply_plan"],
        "selector_layout": ["dl_validate_project", "dl_build_payload_plan", "dl_readback_and_report"],
        "native_table": ["dl_validate_project", "dl_build_payload_plan", "dl_create_safe_apply_plan"],
        "kpi_indicator": ["dl_validate_project", "dl_build_payload_plan", "dl_create_safe_apply_plan"],
        "source_route": ["dl_get_workbook_entries", "dl_read_object", "dl_build_payload_plan"],
        "visual_quality": ["dl_validate_editor_runtime_contract", "dl_validate_project", "dl_build_validation_evidence_report"],
        "performance_budget": ["dl_diagnose(mode='performance')", "dl_validate_project", "dl_create_safe_apply_plan"],
        "repo_size": ["dl_reference(mode='tool_selection')"],
        "api_contract": ["dl_list_api_methods", "dl_get_api_method_schema", "dl_read_object", "dl_plan_object_update"],
        "current_docs_delta": ["dl_reference(mode='api_contract')", "dl_validate_editor_runtime_contract", "dl_validate_project"],
        "tool_selection": ["dl_runtime_status", "dl_auth_probe", "dl_reference", "dl_diagnose"],
    }
    artifacts_by_mode = {
        "chart_selection": [
            "config/datalens_chart_decision_rules.json",
            "schemas/dataviz_chart_decision.schema.json",
            "docs/datalens/chart_selection_decision_matrix.md",
        ],
        "renderer_contract": [
            "config/datalens_visual_style_tokens.json",
            "src/datalens_dev_mcp/assets/validators/editor_runtime_contract.json",
            "artifacts/visual_runtime_contract/summary.json",
        ],
        "negative_requirements": [
            "schemas/negative_requirement.schema.json",
            "requirements/negative_requirements.json",
            "artifacts/validation_report.json",
        ],
        "delivery_intent": [
            "config/datalens_delivery_policy.json",
            "docs/mcp/delivery_intent_policy.md",
            "artifacts/safe_apply/",
        ],
        "delivery_approval": [
            "config/runtime_quality_contracts.json",
            "src/datalens_dev_mcp/pipeline/approval_intent.py",
            "artifacts/delivery/approval_intent_decision.json",
        ],
        "target_lock": [
            "schemas/target_lock.schema.json",
            "src/datalens_dev_mcp/pipeline/target_lock.py",
            "artifacts/delivery/target_lock.json",
        ],
        "route_selection": [
            "config/route_selection_policy_v5.json",
            "src/datalens_dev_mcp/pipeline/route_selection_policy.py",
            "config/datalens_api_operation_policy.json",
        ],
        "object_granularity": [
            "src/datalens_dev_mcp/pipeline/dashboard_object_granularity.py",
            "scripts/run_dashboard_object_granularity_suite.py",
            "artifacts/dashboard_object_granularity/",
        ],
        "selector_layout": [
            "src/datalens_dev_mcp/pipeline/selector_layout_contract.py",
            "scripts/run_selector_layout_contract_suite.py",
            "artifacts/selector_layout_contract/",
        ],
        "native_table": [
            "src/datalens_dev_mcp/pipeline/native_table_contract.py",
            "templates/datalens/editor_table/table_node/",
            "artifacts/table_render_contract/",
        ],
        "kpi_indicator": [
            "src/datalens_dev_mcp/pipeline/kpi_indicator_contract.py",
            "config/runtime_quality_contracts.json",
            "artifacts/dashboard_object_granularity/",
        ],
        "source_route": [
            "src/datalens_dev_mcp/pipeline/source_route_resolver.py",
            "config/route_selection_policy_v5.json",
            "artifacts/source_route_contract/",
        ],
        "visual_quality": [
            "config/runtime_quality_contracts.json",
            "src/datalens_dev_mcp/pipeline/visual_quality.py",
            "artifacts/visual_runtime_contract/",
        ],
        "performance_budget": [
            "src/datalens_dev_mcp/pipeline/performance_budget.py",
            "artifacts/performance_budget/",
            "artifacts/sql_performance/",
        ],
        "repo_size": [
            "scripts/check_repo_size_budget.py",
            "scripts/check_no_generated_artifacts_tracked.py",
            "config/runtime_quality_contracts.json",
        ],
        "api_contract": [
            "config/datalens_api_operation_policy.json",
            "docs/datalens/api_contract_coverage.md",
            "tests/fixtures/api_contracts/",
        ],
        "current_docs_delta": [
            "config/datalens_docs_feature_policy.json",
            "docs/datalens/current_docs_reconciliation.md",
            "schemas/datalens-api/openapi.lock.json",
        ],
        "tool_selection": [
            "docs/mcp/tool_selection_policy.md",
            "docs/mcp/token_and_response_budget.md",
            "docs/mcp/tools.md",
        ],
    }
    summary_by_mode = {
        "chart_selection": "Bounded chart-family and route selection guidance.",
        "renderer_contract": "Bounded renderer visual, runtime, and styling contract.",
        "negative_requirements": "Bounded negative-requirement ledger and drift-check contract.",
        "delivery_intent": "Bounded read/save/publish intent and gate selection contract.",
        "delivery_approval": "Bounded approval-source and save-plus-publish policy contract.",
        "target_lock": "Bounded exact-target lock and wrong-target completion contract.",
        "route_selection": (
            "Bounded RouteSelectionPolicyV5 contract for Wizard-first defaults, registered JS gaps, "
            "explicit-only QL, existing-route preservation, and source routing."
        ),
        "object_granularity": "Bounded dashboard object graph and one-visual-per-object contract.",
        "selector_layout": "Bounded selector row, width, native control, and wiring contract.",
        "native_table": "Bounded native table, empty-state, and in-cell bar contract.",
        "kpi_indicator": "Bounded KPI/indicator semantics and separate-object contract.",
        "source_route": "Bounded dataset/connection/manual/static source route contract.",
        "visual_quality": "Bounded visual/readback quality and unavailable-browser status contract.",
        "performance_budget": "Bounded performance budget and pre-publish block contract.",
        "repo_size": "Bounded repository size and generated-artifact tracking contract.",
        "api_contract": "Bounded OpenAPI operation coverage and MCP ownership contract.",
        "current_docs_delta": "Bounded current official-docs delta and feature-policy contract.",
        "tool_selection": "Bounded MCP stage-to-tool navigation policy.",
    }
    return {
        "summary": result.get("summary") or summary_by_mode.get(mode, "Bounded DataLens reference response."),
        "rules": (rules_by_mode.get(mode) or [])[:5],
        "exact_next_tools": tools_by_mode.get(mode) or ["dl_reference"],
        "artifact_paths": artifacts_by_mode.get(mode) or [],
    }


def _runtime_quality_reference(mode: str, term: str) -> dict[str, Any]:
    del term
    records = {
        "route_selection": {
            "summary": (
                "RouteSelectionPolicyV5 uses Wizard for standard creates, keeps JS for explicit requests or registered capability gaps, "
                "preserves existing technology on update, and permits QL only after a direct user request."
            ),
            "policy_artifact": "config/route_selection_policy_v5.json",
            "implementation": "src/datalens_dev_mcp/pipeline/route_selection_policy.py",
        },
        "delivery_approval": {
            "summary": (
                "ApprovalIntentResolver treats normal known-target implementation/fix/enhance/redesign/update "
                "requests plus safe gates as sufficient for save and publish without a literal chat phrase."
            ),
            "policy_artifact": "config/runtime_quality_contracts.json",
            "implementation": "src/datalens_dev_mcp/pipeline/approval_intent.py",
        },
        "target_lock": {
            "summary": (
                "TargetLock binds workbook/dashboard/chart ids from URL, manifest, workbook entry, goal objective, "
                "or text and carries a stable lock hash through plan, save, publish, readback, and final report."
            ),
            "schema": "schemas/target_lock.schema.json",
            "implementation": "src/datalens_dev_mcp/pipeline/target_lock.py",
        },
        "object_granularity": {
            "summary": (
                "DashboardObjectGranularityValidator blocks one giant Advanced Editor dashboard widgets and requires "
                "the object manifest/readback counts to match the planned business visuals."
            ),
            "implementation": "src/datalens_dev_mcp/pipeline/dashboard_object_granularity.py",
        },
        "selector_layout": {
            "summary": (
                "SelectorLayoutContract computes percentage widths from selector kind and label length, splits rows at 96%, "
                "and validates native control targets and fields."
            ),
            "implementation": "src/datalens_dev_mcp/pipeline/selector_layout_contract.py",
        },
        "native_table": {
            "summary": (
                "NativeTableContract blocks skeleton tables for non-empty sources and validates columns, query/row proof, "
                "explicit empty state, and readable in-cell bars."
            ),
            "implementation": "src/datalens_dev_mcp/pipeline/native_table_contract.py",
        },
        "kpi_indicator": {
            "summary": (
                "KpiIndicatorContract requires separate KPI objects, formula, unit, grain, comparator policy, native title/hint, "
                "and blocks KPI HTML card grids."
            ),
            "implementation": "src/datalens_dev_mcp/pipeline/kpi_indicator_contract.py",
        },
        "source_route": {
            "summary": (
                "SourceRouteResolver prefers existing datasets and connections, returns manual upload handoff where needed, "
                "and only permits embedded static data with explicit approval."
            ),
            "implementation": "src/datalens_dev_mcp/pipeline/source_route_resolver.py",
        },
        "visual_quality": {
            "summary": (
                "VisualReadbackQualityGate keeps backend pass separate from visual pass and blocks unreadable bars, "
                "implicit KPI comparators, decorative color, redundant visuals, and false visual QA passes."
            ),
            "implementation": "src/datalens_dev_mcp/pipeline/visual_quality.py",
        },
        "performance_budget": {
            "summary": (
                "PerformanceBudget blocks publish for slow tabs, duplicated heavy SQL, unbounded detail queries, "
                "heavy generated JS, and large embedded data without explicit static approval."
            ),
            "implementation": "src/datalens_dev_mcp/pipeline/performance_budget.py",
        },
        "repo_size": {
            "summary": (
                "RepoSizeBudget keeps tracked runtime sources compact and blocks tracked "
                "build/dist/package/clean-room/runtime-spill artifacts."
            ),
            "implementation": "scripts/check_repo_size_budget.py",
        },
    }
    record = records.get(mode, {})
    return {"results": [record] if record else [], "result_count": 1 if record else 0, **record}


def _recipe(term: str, limit: int) -> dict[str, Any]:
    registry = resource_json(RECIPE_REGISTRY_RESOURCE)
    rows = _rank(
        registry.get("recipes") or [],
        term,
        fields=("recipe_id", "title", "aliases", "route", "source_contract", "output_contract"),
    )
    return {"results": [_compact_recipe(row) for row in rows[:limit]], "result_count": len(rows)}


def _compact_recipe(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "recipe_id": row["recipe_id"],
        "title": row["title"],
        "aliases": row.get("aliases") or [],
        "route": row["route"],
        "widget_contract": row["widget_contract"],
        "source_contract": row["source_contract"],
        "required_tabs": row["required_tabs"],
        "output_contract": row["output_contract"],
        "official_status": row["official_status"],
        "observed_runtime_overrides": row["observed_runtime_overrides"],
        "local_policy_status": row["local_policy_status"],
        "implementation_status": row["implementation_status"],
        "cardinality_limits": row["cardinality_limits"],
        "algorithmic_bound": row["algorithmic_bound"],
        "validation_checklist": row["validation_checklist"],
        "executable_bundle": row.get("executable_bundle") or {},
        "source_traces": row["source_traces"],
    }


def _formula(term: str, limit: int) -> dict[str, Any]:
    registry = _load_json("formula-registry.json", {"functions": []})
    functions = registry.get("functions") or []
    lowered = term.strip().lower()
    validation = validate_formula_expression(term, registry) if "(" in term else None
    if lowered == "lod":
        rows = [item for item in functions if item.get("lod_support") != "not_detected"]
    elif lowered == "window":
        rows = [item for item in functions if item.get("window_status") == "window"]
    else:
        rows = _rank(
            functions,
            term,
            fields=(
                "name",
                "title",
                "aliases",
                "category",
                "syntax",
                "syntax_variants",
                "lod_support",
                "window_status",
                "before_filter_by",
            ),
        )
    if validation and not rows:
        by_name = {str(item.get("name") or "").upper(): item for item in functions}
        seen: set[str] = set()
        rows = []
        for name in validation.get("function_calls") or []:
            key = str(name or "").upper()
            if key in by_name and key not in seen:
                rows.append(by_name[key])
                seen.add(key)
    return {
        "results": rows[:limit],
        "result_count": len(rows),
        "validation": validation,
    }


def _visualization(term: str, limit: int) -> dict[str, Any]:
    registry = _load_json("visualization-registry.json", {"visualizations": []})
    rows = _rank(registry.get("visualizations") or [], term, fields=("id", "title", "analytical_intent"))
    return {"results": rows[:limit], "result_count": len(rows)}


def _error(term: str, limit: int) -> dict[str, Any]:
    registry = _load_json("error-registry.json", {"errors": []})
    rows = _rank(
        registry.get("errors") or [],
        term,
        fields=("code", "title", "affected_layer", "likely_causes", "patterns", "observed_runtime_codes"),
    )
    return {"results": rows[:limit], "result_count": len(rows)}


def _capability(term: str, limit: int) -> dict[str, Any]:
    registry = _load_json("capability-matrix.json", {"capabilities": []})
    capability_rows = _rank(
        registry.get("capabilities") or [],
        term,
        fields=(
            "capability_id",
            "title",
            "official_status",
            "implementation_status",
            "route",
            "evidence_state",
            "local_policy_status",
            "source_traces",
        ),
    )
    route_registry = _load_json("route-capability-matrix.json", {"routes": []})
    route_rows = _rank(
        route_registry.get("routes") or [],
        term,
        fields=("route_id", "evidence", "blocked_reason", "create_supported", "plan_supported", "read_supported"),
    )
    rows = _rank(capability_rows + route_rows, term, fields=tuple())
    lowered = term.lower()
    route_hints = []
    if "wizard" in lowered:
        route_hints.append("wizard_native")
    if "ql" in lowered:
        route_hints.append("ql_explicit")
    if "dashboard" in lowered:
        route_hints.append("dashboard")
    if route_hints:
        hinted = [row for route_id in route_hints for row in route_rows if row.get("route_id") == route_id]
        rows = hinted + [row for row in rows if row not in hinted]
    return {"results": rows[:limit], "result_count": len(rows)}


def _source_trace(term: str, limit: int) -> dict[str, Any]:
    pages = (_load_json("page-registry.json", {"pages": []}).get("pages") or [])
    chunks = _load_jsonl("chunk-registry.jsonl")
    rows = _rank(
        pages + chunks,
        term,
        fields=("chunk_id", "mirror_path", "title", "heading", "source_url", "anchor", "classification"),
    )
    compact = []
    for row in rows[:limit]:
        compact.append(
            {
                "title": row.get("title") or row.get("heading") or "",
                "source_url": row.get("source_url") or "",
                "mirror_path": row.get("mirror_path") or "",
                "anchor": row.get("anchor") or "",
                "chunk_id": row.get("chunk_id") or "",
                "sha256": row.get("sha256") or "",
            }
        )
    return {"results": compact, "result_count": len(rows)}


def _authoring_guidance(term: str, limit: int) -> dict[str, Any]:
    recipe_results = _recipe(term, min(limit, 3)).get("results", [])
    capability_results = _capability(term, min(limit, 3)).get("results", [])
    selected = recipe_results[0] if recipe_results else {}
    unsupported_parts = []
    implementation_state = selected.get("implementation_status") or ""
    route = selected.get("route") or "manual_review"
    if "blocked" in implementation_state or route == "documented_reference":
        unsupported_parts.append(selected.get("title") or term or "requested route")
    if "gravity" in term.lower() and route != "documented_reference":
        unsupported_parts.append("Gravity UI Charts creation is blocked by local route policy")
    plan = {
        "interpreted_intent": _interpreted_intent(term, selected),
        "recommended_route": route,
        "object_type": selected.get("widget_contract") or route,
        "route_reason": _route_reason(selected),
        "required_files_or_tabs": selected.get("required_tabs") or [],
        "source_query_contract": selected.get("source_contract") or "",
        "selected_recipe": selected.get("recipe_id") or "",
        "code_skeletons": _code_skeletons_for_recipe(selected),
        "layout_selector_cross_filter_guidance": _layout_guidance(selected),
        "known_constraints": {
            "cardinality_limits": selected.get("cardinality_limits") or {},
            "algorithmic_bound": selected.get("algorithmic_bound") or "",
            "local_policy": selected.get("local_policy_status") or "",
        },
        "unsupported_parts": unsupported_parts,
        "validation_checklist": selected.get("validation_checklist") or [],
        "expected_lifecycle": "plan_only_until_safe_apply_approval; no DataLens mutation in this milestone",
        "exact_source_traces": selected.get("source_traces") or [],
        "implementation_evidence_state": (selected.get("executable_bundle") or {}).get("status")
        or selected.get("implementation_status")
        or "unknown_due_to_missing_evidence",
    }
    return {
        "guidance": {
            "official": "Use source-traced recipes and registries; source wording stays external.",
            "observed": "Observed runtime overrides are reported separately when present.",
            "policy": "Writes remain behind safe apply; Gravity UI Charts stay reference-only under local policy.",
            "implementation": "Prefer implemented recipes; documented-only capabilities report missing evidence.",
        },
        "authoring_plan": plan,
        "recipes": recipe_results,
        "capabilities": capability_results,
    }


def _object_contract(term: str, limit: int) -> dict[str, Any]:
    contracts = _load_json("editor-visualization-contracts.json", {"contracts": []}).get("contracts") or []
    rows = _rank(
        contracts,
        term,
        fields=("contract_id", "title", "mirror_path", "methods", "html_tags_or_attributes", "editor_route", "native_route"),
    )[:limit]
    return {
        "results": [
            {
                "contract_id": row.get("contract_id") or "",
                "title": row.get("title") or "",
                "kind": row.get("kind") or "",
                "required_tabs": row.get("required_tabs") or [],
                "methods": row.get("methods") or [],
                "html_tags_or_attributes": row.get("html_tags_or_attributes") or [],
                "native_route": row.get("native_route") or "",
                "editor_route": row.get("editor_route") or "",
                "limits": row.get("limits") or [],
                "local_policy_status": row.get("local_policy_status") or "",
                "source_trace": row.get("source_trace") or {},
            }
            for row in rows
        ],
        "result_count": len(rows),
    }


def _chart_selection(term: str, limit: int) -> dict[str, Any]:
    rules = resource_json("config/datalens_chart_decision_rules.json").get("rules") or []
    rows = _rank(rules, term, fields=("task", "prefer", "route", "reason")) or rules
    compact = []
    for row in rows[:limit]:
        compact.append(
            {
                "task": row.get("task") or "",
                "prefer": row.get("prefer") or row.get("prefer_order") or "",
                "route": row.get("route") or "",
                "reject": row.get("reject") or [],
                "required": {
                    key: row.get(key)
                    for key in ("required_measures", "allowed_when", "allowed_pie_when", "comparator", "sort", "axis")
                    if row.get(key) is not None
                },
            }
        )
    return {
        "result_count": len(rows),
        "results": compact,
        "guidance": {
            "decision_order": [
                "business question",
                "audience and owner",
                "analytical task",
                "data shape and metric semantics",
                "negative requirements",
                "approved family and route",
                "renderer visual spec",
            ],
            "kpi_policy": "Use kpi_value_sparkline or kpi_value_only by default; delta variants require an explicit comparator.",
            "route_policy": "Wizard-first standard creation; JS only by explicit request or registered gap; QL explicit-only.",
        },
    }


def _renderer_visual_spec(term: str, limit: int) -> dict[str, Any]:
    tokens = resource_json("config/datalens_visual_style_tokens.json")
    chart_rules = resource_json("config/datalens_chart_decision_rules.json").get("rules") or []
    rows = _rank(chart_rules, term, fields=("task", "prefer", "route"))[:limit]
    return {
        "result_count": len(rows),
        "results": [
            {
                "task": row.get("task") or "",
                "family": row.get("prefer") or row.get("prefer_order") or "",
                "route": row.get("route") or "",
                "renderer_requirements": [
                    "native title and hint only",
                    "neutral-first color with semantic colors only when direction is declared",
                    "no decorative CSS, shadows, 3D, or gradient styling",
                    "pre-shape data before render and respect wrapFn runtime budgets",
                    "native table bars use table formatting, not custom HTML bars",
                ],
            }
            for row in rows
        ],
        "style_tokens": {
            "font": tokens.get("font") or {},
            "colors": tokens.get("colors") or {},
            "limits": tokens.get("limits") or {},
            "table_defaults": tokens.get("table_defaults") or {},
        },
        "forbidden_css_patterns": tokens.get("forbidden_css_patterns") or [],
    }


def _datalens_editor_runtime(term: str, limit: int) -> dict[str, Any]:
    contract = resource_json("validators/editor_runtime_contract.json")
    return {
        "result_count": 1,
        "results": [
            {
                "rule_version": contract.get("rule_version") or "",
                "supported_layers": contract.get("official_sanitizer", {}).get("layers") or [],
                "budgets_ms": contract.get("official_sanitizer", {}).get("documented_execution_budgets_ms") or {},
                "blocked_patterns": sorted(
                    (contract.get("observed_runtime_overrides", {}).get("blocked_patterns") or {}).keys()
                ),
                "project_governance": sorted(
                    (contract.get("project_governance", {}).get("warning_patterns") or {}).keys()
                ),
                "visual_governance": [
                    "decorative_css_shadow",
                    "decorative_css_gradient",
                    "decorative_css_3d",
                    "html_table_bar",
                    "selector_option_value_not_string",
                ],
            }
        ][:limit],
    }


def _dashboard_system_type(term: str, limit: int) -> dict[str, Any]:
    model = resource_json("config/datalens_dashboard_type_model.json")
    rows: list[dict[str, Any]] = []
    for dashboard_type, spec in (model.get("dashboard_types") or {}).items():
        row = dict(spec)
        row["dashboard_type"] = dashboard_type
        rows.append(row)
    ranked = _rank(rows, term, fields=("dashboard_type", "purpose", "audience", "recommended_families")) or rows
    return {
        "result_count": len(ranked),
        "results": [
            {
                "dashboard_type": row.get("dashboard_type") or "",
                "purpose": row.get("purpose") or row.get("description") or "",
                "audience": row.get("audience") or [],
                "recommended_families": row.get("recommended_families") or [],
                "layout_rules": row.get("layout_rules") or row.get("rules") or [],
            }
            for row in ranked[:limit]
        ],
        "guidance": {
            "system_rule": "Pick dashboard type before chart family; optimize for repeated task and owner action.",
            "artifact_rule": "Persist dashboard map, canvas, chart plan, and object relations before payload planning.",
        },
    }


def _negative_requirements(term: str, limit: int) -> dict[str, Any]:
    schema = resource_json("schemas/negative_requirement.schema.json")
    return {
        "result_count": 1,
        "results": [
            {
                "schema": schema.get("title") or "Negative Requirement",
                "required": schema.get("required") or [],
                "tracked_fields": [
                    "forbidden_concepts",
                    "forbidden_fields",
                    "forbidden_sql_tokens",
                    "forbidden_js_tokens",
                    "forbidden_chart_families",
                    "forbidden_output_columns",
                    "forbidden_titles_hints",
                    "replacement_policy",
                ],
                "known_detection": (
                    "negative wording records forbidden period comparison, pie/donut, legend, "
                    "table-only, and red/green palette concepts"
                ),
                "drift_check": (
                    "dl_validate_project scans requirements, chart decisions, renderer specs, generated JS/SQL/config, "
                    "payload plans, layout titles/hints, readback summaries, artifacts, and reports."
                ),
            }
        ][:limit],
        "guidance": {
            "ledger_path": "requirements/negative_requirements.json",
            "sanitize_user_decision": "Store a compact replacement policy instead of restating forbidden output text.",
        },
    }


def _delivery_intent(term: str, limit: int) -> dict[str, Any]:
    policy = resource_json("config/datalens_delivery_policy.json")
    intents = []
    for intent, spec in (policy.get("intents") or {}).items():
        intents.append(
            {
                "intent": intent,
                "triggers": spec.get("triggers") or [],
                "writes": bool(spec.get("writes")),
                "publish": bool(spec.get("publish")),
                "required_gates": spec.get("required_gates") or [],
            }
        )
    ranked = _rank(intents, term, fields=("intent", "triggers")) or intents
    return {
        "result_count": len(ranked),
        "results": ranked[:limit],
        "blocked": policy.get("blocked") or {},
        "guidance": {
            "default": "Review/audit language stays read-only.",
            "delivery": (
                "Known target plus enabled writes plus approved safe apply can plan "
                "save+publish delivery with explicit readback gates."
            ),
            "never_guess": "Unknown target IDs block writes instead of guessing workbook or dashboard IDs.",
        },
    }


def _api_contract(term: str, limit: int) -> dict[str, Any]:
    policy = _resource_or_file_json("config/datalens_api_operation_policy.json", {"operations": [], "expected_counts": {}})
    operations = policy.get("operations") or []
    ranked = _rank(
        operations,
        term,
        fields=("method_name", "operation_id", "path", "status", "owning_mcp_tool", "tag"),
    ) or operations
    status_counts: dict[str, int] = {}
    for item in operations:
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "result_count": len(ranked),
        "expected_counts": policy.get("expected_counts") or {},
        "status_counts": status_counts,
        "documentation_paths": [
            "config/datalens_api_operation_policy.json",
            "docs/datalens/api_contract_coverage.md",
        ],
        "guidance": {
            "operator": "Use these compact artifacts and exact API tool lookups instead of pasting OpenAPI pages into chat.",
            "next_reference": "dl_reference(mode='current_docs_delta')",
        },
        "results": [
            {
                "method_name": row.get("method_name") or row.get("operation_id") or "",
                "path": row.get("path") or "",
                "http_method": row.get("http_method") or "",
                "status": row.get("status") or "",
                "owning_mcp_tool": row.get("owning_mcp_tool") or "",
                "live_probe_policy": row.get("live_probe_policy") or "",
                "request_schema_ref": row.get("request_schema_ref") or "",
                "response_schema_ref": row.get("response_schema_ref") or "",
                "doc_url": (row.get("source") or {}).get("doc_url") or "",
                "fixture_path": row.get("fixture_path") or "",
            }
            for row in ranked[:limit]
        ],
    }


def _current_docs_delta(term: str, limit: int) -> dict[str, Any]:
    policy = _resource_or_file_json("config/datalens_docs_feature_policy.json", {"clusters": [], "summary": {}})
    clusters = policy.get("clusters") or []
    ranked = _rank(
        clusters,
        term,
        fields=("id", "title", "classification", "mcp_surface", "runtime_contract", "server_decision"),
    ) or clusters
    classification_counts: dict[str, int] = {}
    for item in clusters:
        classification = str(item.get("classification") or "unknown")
        classification_counts[classification] = classification_counts.get(classification, 0) + 1
    return {
        "result_count": len(ranked),
        "cluster_count": len(clusters),
        "classification_counts": classification_counts,
        "documentation_paths": [
            "config/datalens_docs_feature_policy.json",
            "docs/datalens/current_docs_reconciliation.md",
        ],
        "guidance": {
            "operator": "Use the compact reconciliation artifacts before changing route or API behavior.",
            "next_reference": "dl_reference(mode='api_contract')",
        },
        "results": [
            {
                "id": row.get("id") or "",
                "title": row.get("title") or "",
                "classification": row.get("classification") or "",
                "mcp_surface": row.get("mcp_surface") or "",
                "runtime_contract": row.get("runtime_contract") or "",
                "server_decision": row.get("server_decision") or "",
                "source_urls": (row.get("source_urls") or [])[:3],
            }
            for row in ranked[:limit]
        ],
    }


def _tool_selection(term: str, limit: int) -> dict[str, Any]:
    stages = [
        {
            "stage": "startup",
            "tools": ["dl_runtime_status", "dl_auth_probe"],
            "rule": "Confirm local mode and auth readiness; Project Memory Bank supplies compact project context.",
        },
        {
            "stage": "reference",
            "tools": ["dl_reference", "dl_diagnose"],
            "rule": "Use bounded reference and diagnostics instead of reading long docs or raw SQL inline.",
        },
        {
            "stage": "readback",
            "tools": ["dl_get_workbook_entries", "dl_read_object", "dl_snapshot_dashboard", "dl_get_entries_relations"],
            "rule": "Read current objects and relations before planning any mutation.",
        },
        {
            "stage": "local_validation",
            "tools": ["dl_validate_editor_runtime_contract", "dl_validate_object", "dl_validate_project"],
            "rule": "Validate runtime, object payloads, and project artifacts before payload planning.",
        },
        {
            "stage": "guarded_apply",
            "tools": [
                "dl_build_payload_plan",
                "dl_create_safe_apply_plan",
                "dl_execute_safe_apply",
                "dl_create_publish_from_saved_plan",
                "dl_readback_and_report",
            ],
            "rule": "Plan, approve, save, read back, publish from saved, then read back published proof separately.",
        },
    ]
    ranked = _rank(stages, term, fields=("stage", "tools", "rule")) or stages
    return {
        "result_count": len(ranked),
        "results": ranked[:limit],
        "standard_surface": "tools/list",
        "duplicate_workflows": "hidden compatibility tools are excluded from the standard surface",
    }


def _interpreted_intent(term: str, recipe: dict[str, Any]) -> dict[str, Any]:
    text = term or recipe.get("title") or ""
    language = "ru" if any("а" <= char.lower() <= "я" for char in text) else "en"
    return {
        "language": language,
        "raw_request": term,
        "normalized_family": recipe.get("recipe_id") or "unknown",
        "needs_write": False,
    }


def _route_reason(recipe: dict[str, Any]) -> str:
    if not recipe:
        return "No source-traced recipe matched; return structured no-answer rather than inventing a route."
    if recipe.get("route") == "documented_reference":
        return "Official docs describe the object, but local route policy lacks an executable safe authoring route."
    return "Recipe route is selected from source-traced official contracts and executable fixture state."


def _code_skeletons_for_recipe(recipe: dict[str, Any]) -> dict[str, str]:
    if not recipe:
        return {}
    tabs = set(recipe.get("required_tabs") or [])
    skeletons = {
        "meta.json": '{"links": {}, "name": "semantic_authoring_draft"}',
        "params.js": "module.exports = {lang: 'ru'};",
        "sources.js": "module.exports = {data: []};",
    }
    if "Config" in tabs:
        skeletons["config.js"] = "module.exports = {paginator: {enabled: true, limit: 50}};"
    if "Controls" in tabs:
        skeletons["controls.js"] = "module.exports = {controls: []};"
    if "Prepare" in tabs:
        skeletons["prepare.js"] = "module.exports = function prepare(input) { return {head: [], rows: []}; };"
    return skeletons


def _layout_guidance(recipe: dict[str, Any]) -> list[str]:
    route = recipe.get("route") or ""
    guidance = ["Use dashboard relation validation before safe apply."]
    if route == "editor_table":
        guidance.append("Keep table output deterministic; validate head, rows, footer and cardinality guards.")
    if route == "editor_js_control":
        guidance.append("Use left label placement and bounded percentage widths for controls.")
    if recipe.get("recipe_id") == "cross_filter":
        guidance.append("Record selector impact and source-target relation evidence.")
    return guidance


def _search(term: str, limit: int) -> dict[str, Any]:
    combined = []
    for relative, key, fields in [
        ("page-registry.json", "pages", ("mirror_path", "title", "section")),
        ("capability-matrix.json", "capabilities", ("capability_id", "title", "implementation_status")),
        ("formula-registry.json", "functions", ("name", "title", "category")),
        ("error-registry.json", "errors", ("code", "title", "affected_layer")),
        (
            "editor-visualization-contracts.json",
            "contracts",
            ("contract_id", "title", "mirror_path", "methods", "html_tags_or_attributes", "editor_route"),
        ),
    ]:
        payload = _load_json(relative, {key: []})
        combined.extend(_rank(payload.get(key) or [], term, fields=fields)[:limit])
    combined.extend(_rank(_load_jsonl("rule-cards.jsonl"), term, fields=("rule_id", "kind", "title", "summary"))[:limit])
    combined.extend(
        _rank(
            _load_jsonl("chunk-registry.jsonl"),
            term,
            fields=("chunk_id", "mirror_path", "title", "heading", "source_url", "anchor", "classification"),
        )[:limit]
    )
    rows = _rank(combined, term, fields=tuple())[:limit]
    lowered = term.lower()
    exact_method_rows = [
        row
        for row in combined
        if any(str(method).lower() in lowered for method in (row.get("methods") or []))
    ]
    if exact_method_rows:
        rows = exact_method_rows + [row for row in rows if row not in exact_method_rows]
    if len(rows) < limit:
        rows.extend(_search_index(term, limit - len(rows)))
    return {"results": [_compact_search_row(row) for row in rows[:limit]], "result_count": len(rows)}


def _search_index(term: str, limit: int) -> list[dict[str, Any]]:
    return []


def _compact_search_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": row.get("title") or row.get("heading") or row.get("name") or row.get("code") or row.get("capability_id") or "",
        "kind": row.get("kind") or row.get("section") or row.get("route") or row.get("category") or "",
        "source_url": row.get("source_url") or (row.get("source_trace") or {}).get("source_url") or "",
        "mirror_path": row.get("mirror_path") or (row.get("source_trace") or {}).get("mirror_path") or "",
        "anchor": row.get("anchor") or (row.get("source_trace") or {}).get("anchor") or "",
        "chunk_id": row.get("chunk_id") or row.get("record_id") or "",
        "sha256": row.get("sha256") or (row.get("source_trace") or {}).get("sha256") or "",
        "official_status": row.get("official_status") or "official_docs_indexed",
        "observed_runtime_overrides": row.get("observed_runtime_overrides") or [],
        "local_policy_status": row.get("local_policy_status") or "",
        "implementation_status": row.get("implementation_status") or "",
        "methods": (row.get("methods") or [])[:40],
        "matched_terms": (row.get("html_tags_or_attributes") or row.get("aliases") or [])[:60],
        "summary": row.get("bounded_excerpt") or row.get("summary") or "",
    }


def _rank(rows: list[dict[str, Any]], term: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not term:
        return rows
    terms = _query_terms(term)
    scored = []
    for index, row in enumerate(rows):
        haystack = stable_json(row).lower() if not fields else " ".join(str(row.get(field) or "") for field in fields).lower()
        score = sum(2 if token in haystack else 0 for token in terms)
        if term.lower() in haystack:
            score += 5
        if score:
            scored.append((score, -index, row))
    return [row for _, _, row in sorted(scored, reverse=True)] or rows[:0]


def _query_terms(term: str) -> list[str]:
    normalized = term.replace("_", " ").replace("-", " ").lower()
    stopwords = {
        "a",
        "an",
        "and",
        "for",
        "in",
        "included",
        "labels",
        "read-only",
        "relevant",
        "review",
        "russian",
        "the",
        "with",
        "weekly",
        "where",
        "и",
        "с",
    }
    terms = [part for part in normalized.split() if part.strip() and not part.startswith("#") and part not in stopwords]
    synonyms = {
        "таблица": ["table"],
        "сводная": ["pivot"],
        "план": ["plan"],
        "факт": ["fact"],
        "итоги": ["totals", "footer"],
        "футер": ["footer", "totals"],
        "футером": ["footer", "totals"],
        "барами": ["bar", "bars"],
        "закрепленной": ["pinned", "sticky"],
        "закрепленную": ["pinned", "sticky"],
        "колонкой": ["column"],
        "колонка": ["column"],
        "пагинация": ["pagination"],
        "пагинацией": ["pagination"],
        "обычная": ["flat", "simple"],
        "динамический": ["dynamic"],
        "динамическим": ["dynamic"],
        "источник": ["source"],
        "атрибут": ["attribute"],
        "разрешенный": ["allowed"],
        "nested": ["concat"],
        "strings": ["string", "concat"],
        "commas": ["concat"],
        "parentheses": ["concat"],
        "селектор": ["selector", "control"],
        "фильтр": ["filter"],
        "кросс": ["cross"],
        "уведомления": ["notifications"],
        "ссылки": ["links"],
        "действия": ["actions"],
        "кастомная": ["custom", "advanced"],
        "график": ["chart"],
        "ошибка": ["error", "code"],
        "синтаксис": ["syntax"],
    }
    expanded = list(terms)
    for term_part in terms:
        expanded.extend(synonyms.get(term_part, []))
    return expanded


def _bound_payload(payload: dict[str, Any], *, max_chars: int, project_root: Path) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) <= max_chars:
        payload["response_chars"] = len(text)
        return payload
    artifact_root = (project_root / ARTIFACT_DIR).resolve() if not ARTIFACT_DIR.is_absolute() else ARTIFACT_DIR
    artifact_root.mkdir(parents=True, exist_ok=True)
    digest = sha256_text(text)[:16]
    path = artifact_root / f"reference_{digest}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    slim = {
        "ok": True,
        "schema_version": payload["schema_version"],
        "mode": payload["mode"],
        "query": payload["query"],
        "source_precedence": payload.get("source_precedence") or [],
        "result_count": payload.get("result_count", len(payload.get("results") or payload.get("recipes") or [])),
        "spilled": True,
        "artifact": {"path": str(path), "sha256": sha256_text(text), "serialized_chars": len(text)},
    }
    if payload.get("results"):
        slim["results"] = [_compact_spill_row(row) for row in (payload.get("results") or [])[:3]]
    if payload.get("recipes"):
        recipe_limit = 2 if payload.get("mode") == "authoring_guidance" else 3
        slim["recipes"] = [_compact_authoring_row(row) for row in (payload.get("recipes") or [])[:recipe_limit]]
    if payload.get("capabilities"):
        capability_limit = 1 if payload.get("mode") == "authoring_guidance" else 3
        slim["capabilities"] = [
            _compact_authoring_row(row) for row in (payload.get("capabilities") or [])[:capability_limit]
        ]
    if payload.get("guidance"):
        slim["guidance"] = payload["guidance"]
    if payload.get("authoring_plan"):
        plan = dict(payload["authoring_plan"])
        plan["exact_source_traces"] = (plan.get("exact_source_traces") or [])[:3]
        plan["validation_checklist"] = (plan.get("validation_checklist") or [])[:6]
        plan["layout_selector_cross_filter_guidance"] = (plan.get("layout_selector_cross_filter_guidance") or [])[:4]
        plan["code_skeletons"] = {
            key: (value[:220] + "..." if len(value) > 220 else value)
            for key, value in (plan.get("code_skeletons") or {}).items()
        }
        slim["authoring_plan"] = plan
    if payload.get("validation") is not None:
        slim["validation"] = payload["validation"]
    if "results" not in slim and "recipes" not in slim and "capabilities" not in slim:
        slim["results"] = []
    slim["response_chars"] = len(json.dumps(slim, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return slim


def _compact_authoring_row(row: dict[str, Any]) -> dict[str, Any]:
    trace = row.get("source_trace") or {}
    if not trace and row.get("source_traces"):
        trace = row["source_traces"][0]
    return {
        "name": row.get("recipe_id") or row.get("capability_id") or row.get("route_id") or row.get("name") or "",
        "title": row.get("title") or "",
        "route": row.get("route") or row.get("editor_route") or row.get("route_id") or "",
        "status": row.get("implementation_evidence_state")
        or (row.get("executable_bundle") or {}).get("status")
        or row.get("evidence_state")
        or row.get("implementation_status")
        or row.get("official_status")
        or "",
        "source_trace": trace,
    }


def _compact_spill_row(row: dict[str, Any]) -> dict[str, Any]:
    trace = row.get("source_trace") or {}
    if not trace and row.get("section_traces"):
        trace = next((value for value in row["section_traces"].values() if value), {})
    return {
        "name": row.get("name") or row.get("recipe_id") or row.get("code") or row.get("route_id") or "",
        "recipe_id": row.get("recipe_id") or "",
        "title": row.get("title") or "",
        "kind": row.get("category") or row.get("route") or row.get("affected_layer") or "",
        "source_trace": trace,
        "source_traces": row.get("source_traces") or ([trace] if trace else []),
        "status": row.get("contract_status") or row.get("implementation_status") or row.get("official_status") or "",
        "syntax": row.get("syntax") or "",
        "methods": (row.get("methods") or [])[:40],
        "observed_runtime_codes": row.get("observed_runtime_codes") or [],
        "matched_terms": (row.get("matched_terms") or row.get("html_tags_or_attributes") or [])[:80],
        "clauses": sorted(
            {
                clause
                for variant in row.get("syntax_variants") or []
                for clause in (variant.get("clauses") or [])
            }
        ),
    }
