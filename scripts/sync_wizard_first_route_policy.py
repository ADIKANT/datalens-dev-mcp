#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "route_selection_policy_v5.json"
MATRIX_PATH = ROOT / "config" / "datalens_chart_param_matrix.json"
CHART_ROUTING_PATH = ROOT / "config" / "datalens_chart_routing.json"
ROUTING_MODEL_PATH = ROOT / "config" / "datalens_routing_model.json"
DECISION_RULES_PATH = ROOT / "config" / "datalens_chart_decision_rules.json"
GOLDEN_INVENTORY_PATH = ROOT / "config" / "golden_runtime_gallery_inventory.json"
RUNTIME_QUALITY_PATH = ROOT / "config" / "runtime_quality_contracts.json"
ASSET_ROOT = ROOT / "src" / "datalens_dev_mcp" / "assets"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _family_visualizations(policy: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for visualization_id, spec in (policy.get("wizard_visualizations") or {}).items():
        for family in spec.get("semantic_families") or []:
            result[str(family)] = str(visualization_id)
    return result


def _expected_matrix(policy: dict[str, Any]) -> dict[str, Any]:
    matrix = deepcopy(_read(MATRIX_PATH))
    mapping = _family_visualizations(policy)
    gaps = policy.get("js_capability_gaps") or {}
    matrix["schema_version"] = "2026-07-15.datalens_chart_param_matrix.public.v1"
    matrix["route_policy_ref"] = "config/route_selection_policy_v5.json"
    matrix["allowed_creation_routes"] = [
        "wizard_native",
        "editor_advanced",
        "editor_table",
        "editor_markdown",
        "editor_js_control",
        "ql_explicit",
    ]
    for family, spec in (matrix.get("families") or {}).items():
        if isinstance(spec.get("ask_user_when"), list):
            spec["ask_user_when"] = [
                token for token in spec["ask_user_when"] if token != "non_map_wizard_request_is_present"
            ]
        if spec.get("route") in {"editor_markdown", "editor_js_control"}:
            spec["selection_origin"] = "specialized_editor_route"
            spec.pop("visualization_id", None)
            spec.pop("capability_gap", None)
        elif family in gaps:
            spec["route"] = "editor_table" if family == "table_pivot_js" else "editor_advanced"
            spec["selection_origin"] = "registered_capability_gap"
            spec["capability_gap"] = gaps[family]
            spec.pop("visualization_id", None)
        elif family in mapping:
            spec["route"] = "wizard_native"
            spec["visualization_id"] = mapping[family]
            spec["selection_origin"] = "wizard_first_default"
            spec["template_dir"] = "templates/datalens/wizard/canonical_templates.json"
            spec.pop("capability_gap", None)
        else:
            raise ValueError(f"family {family!r} lacks a Wizard visualization or registered capability gap")
    for intent in matrix.get("intent_matrix") or []:
        family = str(intent.get("default_family") or "")
        if family in gaps:
            intent["route"] = "editor_table" if family == "table_pivot_js" else "editor_advanced"
            intent["selection_origin"] = "registered_capability_gap"
            intent["capability_gap"] = gaps[family]
            intent.pop("visualization_id", None)
        elif family in mapping:
            intent["route"] = "wizard_native"
            intent["visualization_id"] = mapping[family]
            intent["selection_origin"] = "wizard_first_default"
            intent.pop("capability_gap", None)
        else:
            raise ValueError(f"intent family {family!r} lacks a canonical route")
    return matrix


def _expected_chart_routing() -> dict[str, Any]:
    return {
        "schema_version": "2026-07-13.chart_routing.v3",
        "creation_routes": [
            "wizard_native",
            "editor_advanced",
            "editor_table",
            "editor_markdown",
            "editor_js_control",
            "ql_explicit",
        ],
        "compatibility_aliases": {"wizard_map_native": {"route": "wizard_native", "visualization_id": "geolayer"}},
        "ql_policy": "explicit_user_request_only; never automatic or fallback",
        "forbidden_methods": ["deleteQLChart"],
        "closed_routes": ["d3_node", "regular_editor_chart", "gravity_ui_charts", "automatic_ql_selection"],
        "fallback_policy": "Wizard-first is selected before transport; never retry a failed Wizard attempt as JS or QL.",
        "source_trace": [
            "AGENTS.md",
            "docs/route-policy.md",
            "config/route_selection_policy_v5.json",
            "config/datalens_chart_param_matrix.json",
            "OpenAPI create/update methods",
        ],
    }


def _expected_routing_model() -> dict[str, Any]:
    return {
        "schema_version": "2026-07-13.datalens_operation_routing.v3",
        "policy_registry": "config/route_selection_policy_v5.json",
        "selection_order": [
            "preserve_existing_saved_route_and_visualization",
            "explicit_user_route",
            "registered_capability_gap",
            "wizard_first_default",
        ],
        "operation_routes": {
            "wizard_native_chart": {
                "route": "wizard_native",
                "object_kind": "wizard_chart",
                "required_before": ["dataset_operation"],
            },
            "advanced_editor_chart": {
                "route": "editor_advanced",
                "object_kind": "editor_chart",
                "required_before": ["dataset_operation"],
            },
            "ql_explicit_chart": {
                "route": "ql_explicit",
                "object_kind": "ql_chart",
                "required_before": ["explicit_user_request", "explicit_payload_or_fresh_saved_seed"],
            },
            "dataset_operation": {"route": "dataset", "object_kind": "dataset", "required_before": []},
            "connector_operation": {"route": "connector", "object_kind": "connection", "required_before": []},
            "dashboard_relation_operation": {"route": "dashboard_relation", "object_kind": "dashboard", "required_before": []},
        },
        "rules": [
            "Updates preserve the technology and visualization id from fresh saved readback.",
            "Standard creates use Wizard canonical templates or a fresh saved seed of the same visualization id.",
            "JavaScript is selected only for a registered capability gap or an explicit JS request.",
            "QL is selected only for an explicit user request and is never a fallback.",
            "Delete, move, permission writes, d3_node, regular Editor Chart, and Gravity UI Charts remain closed.",
        ],
    }


def _expected_decision_rules(policy: dict[str, Any]) -> dict[str, Any]:
    rules = deepcopy(_read(DECISION_RULES_PATH))
    mapping = _family_visualizations(policy)
    gaps = policy.get("js_capability_gaps") or {}
    rules["schema_version"] = "2026-07-13.chart_family_rules.v2"
    rules["route_policy_ref"] = "config/route_selection_policy_v5.json"
    for rule in rules.get("rules") or []:
        preferred = str(rule.get("prefer") or "")
        if preferred == "wizard_map_native":
            preferred = "native_map_geo_widget"
            rule["prefer"] = preferred
        if preferred in gaps:
            rule["route"] = "editor_table" if preferred == "table_pivot_js" else "editor_advanced"
            rule["selection_origin"] = "registered_capability_gap"
            rule["capability_gap"] = gaps[preferred]
            rule.pop("visualization_id", None)
        elif preferred in mapping:
            rule["route"] = "wizard_native"
            rule["visualization_id"] = mapping[preferred]
            rule["selection_origin"] = "wizard_first_default"
            rule.pop("capability_gap", None)
        elif preferred:
            rule["selection_origin"] = "specialized_editor_route"
    removed = rules.get("removed_or_manual_review") or {}
    removed.pop("non_map_wizard", None)
    removed["automatic_ql_selection"] = "forbidden_explicit_user_request_only"
    return rules


def _expected_golden_inventory(policy: dict[str, Any]) -> dict[str, Any]:
    inventory = deepcopy(_read(GOLDEN_INVENTORY_PATH))
    family_visualizations = _family_visualizations(policy)
    gaps = policy.get("js_capability_gaps") or {}
    inventory["schema_version"] = "2026-07-13.golden_runtime_gallery_inventory.v2"
    inventory["policy_basis"] = [
        "AGENTS.md",
        "docs/route-policy.md",
        "config/route_selection_policy_v5.json",
        "src/datalens_dev_mcp/pipeline/route_contract.py",
        "templates/datalens/wizard/wizard_template_registry.json",
    ]
    wizard_params = (inventory.get("params_contracts") or {}).get("wizard_map_params")
    if isinstance(wizard_params, dict):
        wizard_params["rule"] = (
            "Wizard geolayer params require validated geo evidence and a canonical template "
            "or fresh same-ID saved seed."
        )
    standard_families = sorted(family_visualizations)
    js_families = sorted(gaps)
    inventory["route_inventory"] = {
        "supported": [
            {
                "route": "wizard_native",
                "entry_type": "wizard_chart",
                "families": standard_families,
                "generator": "build_wizard_payload_plan",
                "methods": {
                    "create": "createWizardChart",
                    "read": "getWizardChart",
                    "update": "updateWizardChart",
                },
                "known_limits": [
                    "Unknown visualization IDs are blocked for create.",
                    "Live verification is not claimed by canonical fixtures.",
                ],
                "do_not_change_runtime_contract": [
                    "Prefer a fresh saved seed of the same visualization id.",
                    "Never fall back to JS after a failed Wizard request.",
                ],
            },
            {
                "route": "editor_advanced",
                "entry_type": "advanced-chart_node",
                "families": js_families,
                "generator": "generate_editor_bundle",
                "methods": {"create": "createEditorChart", "read": "getEditorChart", "update": "updateEditorChart"},
                "known_limits": ["Selected only by direct request or registered capability gap."],
                "do_not_change_runtime_contract": ["Keep one visual per object and the Advanced Editor runtime allowlist."],
            },
            {
                "route": "editor_table",
                "entry_type": "table_node",
                "families": ["table_pivot_js"],
                "generator": "generate_editor_bundle",
                "methods": {"create": "createEditorChart", "read": "getEditorChart", "update": "updateEditorChart"},
                "known_limits": ["Reserved for specialized grouped or pinned JavaScript table semantics."],
                "do_not_change_runtime_contract": ["Ordinary flat and pivot tables default to Wizard."],
            },
            {
                "route": "editor_markdown",
                "entry_type": "markdown_node",
                "families": [
                    "md_methodology_block",
                    "md_section_header",
                    "md_dashboard_owner",
                    "md_contact_block",
                    "md_requirements_link_block",
                    "md_source_notes",
                ],
                "generator": "generate_editor_bundle",
                "methods": {"create": "createEditorChart", "read": "getEditorChart", "update": "updateEditorChart"},
                "known_limits": ["Text-only support blocks."],
                "do_not_change_runtime_contract": ["Keep Markdown on its dedicated Editor route."],
            },
            {
                "route": "editor_js_control",
                "entry_type": "control_node",
                "families": [
                    "single_select_dropdown",
                    "multi_select_dropdown",
                    "search_selector",
                    "date_range_selector",
                    "selector_family_static",
                    "selector_family_dynamic",
                ],
                "generator": "generate_editor_bundle",
                "methods": {"create": "createEditorChart", "read": "getEditorChart", "update": "updateEditorChart"},
                "known_limits": ["Controls require dashboard relation wiring."],
                "do_not_change_runtime_contract": ["Keep controls separate from chart-body HTML."],
            },
            {
                "route": "ql_explicit",
                "entry_type": "ql_chart",
                "families": ["ql_explicit"],
                "generator": "explicit_payload_fixture",
                "methods": {"create": "createQLChart", "read": "getQLChart", "update": "updateQLChart"},
                "known_limits": ["No generation from a general prompt; delete remains closed."],
                "do_not_change_runtime_contract": ["Require explicit-user-request provenance and explicit payload or fresh saved seed."],
            },
        ],
        "reference_only": [
            {
                "route": "grouped_sticky_table_exception",
                "reason": "Legacy HTML template remains blocked by the runtime validator.",
            },
            {
                "route": "unknown_wizard_visualization",
                "reason": "Unknown IDs may be updated only from fresh saved readback and cannot be created.",
            },
        ],
        "unsupported": [
            {"route": "regular_editor_chart", "reason": "No maintained creation route."},
            {"route": "gravity_ui_charts", "reason": "No maintained creation route."},
        ],
        "banned": [
            {"route": "d3_node", "reason": "Outside the local safety model."},
            {"route": "ql_delete", "methods": ["deleteQLChart"], "reason": "QL delete remains closed."},
            {"route": "automatic_ql_selection", "reason": "QL is explicit-only."},
            {"route": "runtime_route_fallback", "reason": "Route selection is deterministic before transport."},
            {"route": "guessed_id_write", "reason": "Writes to guessed IDs are blocked."},
            {
                "route": "blind_write_or_publish",
                "reason": "Fresh readback and the runtime write gates are required.",
            },
            {"route": "production_workbook_mutation", "reason": "Golden gallery is static and never mutates production."},
        ],
    }
    updated_families: list[dict[str, Any]] = []
    for family in inventory.get("supported_family_inventory") or []:
        row = deepcopy(family)
        family_id = str(row.get("family_id") or "")
        if family_id == "ql_explicit":
            continue
        if family_id == "wizard_map_native":
            family_id = "native_map_geo_widget"
            row["family_id"] = family_id
            row["template_family"] = "geolayer"
        if family_id in gaps:
            row["route"] = "editor_table" if family_id == "table_pivot_js" else "editor_advanced"
        elif family_id in family_visualizations or family_id == "native_map_geo_widget":
            row["route"] = "wizard_native"
        updated_families.append(row)
    updated_families.append(
        {
            "family_id": "ql_explicit",
            "route": "ql_explicit",
            "source_contract_ref": "metric_snapshot_rows",
            "params_contract_ref": "editor_advanced_metric_params",
            "known_limits": ["Explicit fixture only; no prompt-to-QL generation."],
            "do_not_change_runtime_contract": ["selection_origin must remain explicit_user_request."],
        }
    )
    inventory["supported_family_inventory"] = updated_families
    refused = (inventory.get("write_policy") or {}).get("refused_workbook_ids")
    if isinstance(refused, dict):
        refused["demo"] = ["<DEMO_WORKBOOK_ID>"]
        refused["production"] = ["<PRODUCTION_WORKBOOK_ID>"]
    return inventory


def _expected_runtime_quality(policy: dict[str, Any]) -> dict[str, Any]:
    contracts = deepcopy(_read(RUNTIME_QUALITY_PATH))
    route_policy = contracts["route_selection_policy"]
    route_policy["version"] = policy["schema_version"]
    route_policy["policy_artifact"] = "config/route_selection_policy_v5.json"
    route_policy["advanced_editor_default"] = "registered_capability_gap_or_explicit_js"
    route_policy["canonical_routes"] = {
        "standard_chart": "wizard_native",
        "ordinary_table": "wizard_native:flatTable",
        "pivot": "wizard_native:pivotTable",
        "map": "wizard_native:geolayer",
        "selector": "editor_js_control",
        "kpi": "wizard_native:metric",
        "markdown": "editor_markdown",
        "ql": "ql_explicit:explicit_user_request_only",
    }
    route_policy["forbidden_silent_fallbacks"] = [
        "failed_wizard_request_to_js",
        "automatic_ql_selection",
        "table_to_html",
        "selector_to_html",
        "kpi_group_to_html_card_grid",
        "dataset_to_embedded_js",
    ]
    native_table = contracts["native_table"]
    native_table["required_route"] = "wizard_native"
    native_table["visualization_id"] = "flatTable"
    native_table["specialized_js_route"] = "editor_table"
    return contracts


def _source_payloads(policy: dict[str, Any]) -> dict[Path, str]:
    return {
        MATRIX_PATH: _render(_expected_matrix(policy)),
        CHART_ROUTING_PATH: _render(_expected_chart_routing()),
        ROUTING_MODEL_PATH: _render(_expected_routing_model()),
        DECISION_RULES_PATH: _render(_expected_decision_rules(policy)),
        GOLDEN_INVENTORY_PATH: _render(_expected_golden_inventory(policy)),
        RUNTIME_QUALITY_PATH: _render(_expected_runtime_quality(policy)),
    }


def _mirrors() -> dict[Path, Path]:
    return {
        POLICY_PATH: ASSET_ROOT / "config" / POLICY_PATH.name,
        ROOT / "config/route_selection_policy_v4.json": ASSET_ROOT / "config/route_selection_policy_v4.json",
        ROOT / "config/route_selection_policy_v3.json": ASSET_ROOT / "config/route_selection_policy_v3.json",
        MATRIX_PATH: ASSET_ROOT / "config" / MATRIX_PATH.name,
        CHART_ROUTING_PATH: ASSET_ROOT / "config" / CHART_ROUTING_PATH.name,
        ROUTING_MODEL_PATH: ASSET_ROOT / "config" / ROUTING_MODEL_PATH.name,
        DECISION_RULES_PATH: ASSET_ROOT / "config" / DECISION_RULES_PATH.name,
        GOLDEN_INVENTORY_PATH: ASSET_ROOT / "config" / GOLDEN_INVENTORY_PATH.name,
        RUNTIME_QUALITY_PATH: ASSET_ROOT / "config" / RUNTIME_QUALITY_PATH.name,
        ROOT / "templates/datalens/wizard/wizard_template_registry.json": (
            ASSET_ROOT / "templates/datalens/wizard/wizard_template_registry.json"
        ),
        ROOT / "templates/datalens/wizard/canonical_templates.json": (
            ASSET_ROOT / "templates/datalens/wizard/canonical_templates.json"
        ),
        ROOT / "templates/datalens/wizard/native_map/README.md": (
            ASSET_ROOT / "templates/datalens/wizard/native_map/README.md"
        ),
        ROOT / "templates/datalens/wizard/native_map/example_input.json": (
            ASSET_ROOT / "templates/datalens/wizard/native_map/example_input.json"
        ),
        ROOT / "templates/datalens/wizard/native_map/example_output_payload_plan.json": (
            ASSET_ROOT / "templates/datalens/wizard/native_map/example_output_payload_plan.json"
        ),
        ROOT / "templates/wizard_map_native/wizard_payload_plan.json": ASSET_ROOT / "templates/wizard_map_native/wizard_payload_plan.json",
        ROOT / "schemas/wizard-chart-config.schema.json": ASSET_ROOT / "schemas/wizard-chart-config.schema.json",
        ROOT / "schemas/wizard-payload-plan.schema.json": ASSET_ROOT / "schemas/wizard-payload-plan.schema.json",
        ROOT / "schemas/datalens-mcp-local-config.schema.json": ASSET_ROOT / "schemas/datalens-mcp-local-config.schema.json",
        ROOT / "config/datalens_mcp.local.example.json": ASSET_ROOT / "config/datalens_mcp.local.example.json",
        ROOT / "schemas/route-contract.schema.json": ASSET_ROOT / "schemas/route-contract.schema.json",
        ROOT / "schemas/chart-spec.schema.json": ASSET_ROOT / "schemas/chart-spec.schema.json",
        ROOT / "schemas/dataviz_chart_decision.schema.json": ASSET_ROOT / "schemas/dataviz_chart_decision.schema.json",
        ROOT / "templates/project/AGENTS.md": ASSET_ROOT / "templates/project/AGENTS.md",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize the canonical Wizard-first route registry and packaged mirrors.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write and args.check:
        parser.error("choose --write or --check")
    policy = _read(POLICY_PATH)
    expected_sources = _source_payloads(policy)
    issues: list[str] = []
    if args.write:
        for path, text in expected_sources.items():
            path.write_text(text, encoding="utf-8")
        for source, target in _mirrors().items():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    else:
        for path, expected in expected_sources.items():
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                issues.append(f"stale source derivative: {path.relative_to(ROOT)}")
        for source, target in _mirrors().items():
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                issues.append(f"stale packaged mirror: {target.relative_to(ROOT)}")
    print(json.dumps({"ok": not issues, "issues": issues, "policy": policy.get("schema_version")}, ensure_ascii=False, sort_keys=True))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
