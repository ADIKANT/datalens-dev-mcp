from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

EDITOR_CONTRACTS = {
    "table_node": {
        "required_tabs": {"meta.json", "params.js", "sources.js", "prepare.js", "config.js"},
        "optional_tabs": {"controls.js", "activities.js"},
        "runtime": "editor_table",
    },
    "d3_node": {
        "required_tabs": {"meta.json", "params.js", "sources.js", "prepare.js", "controls.js"},
        "optional_tabs": {"config.js", "activities.js"},
        "runtime": "gravity_charts",
    },
    "advanced-chart_node": {
        "required_tabs": {"meta.json", "params.js", "sources.js", "prepare.js", "controls.js"},
        "runtime": "advanced_chart",
    },
    "markdown_node": {"required_tabs": {"meta.json", "params.js", "prepare.js"},
                      "optional_tabs": {"sources.js", "controls.js"}, "runtime": "markdown"},
    "control_node": {
        "required_tabs": {"meta.json", "params.js", "controls.js"},
        "optional_tabs": {"sources.js", "activities.js"},
        "runtime": "selector",
    },
}

# This matrix describes static drafts, not response.required. SDK create fills
# omitted provider-required tabs with empty source; narrow updates preserve them.
TAB_FIELDS = {"meta.json": "meta", **{f"{name}.js": name for name in
              ("params", "sources", "prepare", "controls", "config", "activities")}}


def allowed_editor_fields(variant: str) -> set[str]:
    variant = {"table": "table_node", "gravity_charts": "d3_node", "markdown": "markdown_node",
               "selector": "control_node", "advanced_chart": "advanced-chart_node"}.get(variant, variant)
    contract = EDITOR_CONTRACTS.get(variant, {})
    return {TAB_FIELDS[name] for name in contract.get("required_tabs", set()) |
            contract.get("optional_tabs", set())}


def validate_editor_draft(draft: Mapping[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    variant = str(draft.get("variant") or "")
    contract = EDITOR_CONTRACTS.get(variant)
    tabs = draft.get("tabs") if isinstance(draft.get("tabs"), Mapping) else {}
    if contract is None:
        issues.append(
            {
                "code": "editor_variant_unsupported",
                "path": "variant",
                "message": f"unsupported Editor variant: {variant}",
            }
        )
        required: set[str] = set()
        runtime = "unknown"
    else:
        required = set(contract["required_tabs"])
        runtime = str(contract["runtime"])
    scope = draft.get("validation_scope", "complete_draft")
    if not isinstance(scope, str) or scope not in {"complete_draft", "supplied_tabs"}:
        issues.append({"code": "editor_validation_scope_invalid", "path": "validation_scope",
                       "message": "validation_scope must be complete_draft or supplied_tabs"})
    missing = sorted(required - set(tabs)) if scope != "supplied_tabs" else []
    if not isinstance(draft.get("tabs"), Mapping) or not tabs:
        issues.append({"code": "editor_tabs_invalid", "path": "tabs", "message": "tabs must be a nonempty source mapping"})
    if missing:
        issues.append(
            {"code": "editor_tabs_missing", "path": "tabs", "message": "missing required tabs: " + ", ".join(missing)}
        )
    if contract is not None:
        unknown = sorted(set(tabs) - required - set(contract.get("optional_tabs", set())))
        if unknown:
            issues.append(
                {
                    "code": "editor_tabs_unsupported",
                    "path": "tabs",
                    "message": "unsupported tabs for variant: " + ", ".join(unknown),
                }
            )
    for name, source in tabs.items():
        if not isinstance(source, str):
            issues.append({"code": "editor_tab_source_invalid", "path": f"tabs/{name}",
                           "message": "Editor tab must contain source text"})
    aliases = draft.get("source_aliases") or []
    if not isinstance(aliases, list) or any(
        not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias) for alias in aliases
    ):
        issues.append(
            {
                "code": "source_alias_invalid",
                "path": "source_aliases",
                "message": "source aliases must be JavaScript identifiers",
            }
        )
    elif len(aliases) != len(set(aliases)):
        issues.append(
            {"code": "source_alias_duplicate", "path": "source_aliases", "message": "source aliases must be unique"}
        )
    issues.extend(validate_editor_source(tabs))
    return {
        "ok": not issues,
        "variant": variant,
        "issues": issues,
        "runtime": {
            "kind": runtime,
            "validation_scope": scope,
            "checked_tabs": sorted(tabs),
            "static_source_checked": True,
            "live_result_checked": False,
            "live_result_status": "static/source contract checked; live result not checked",
            "node_runtime_assumed": False,
        },
    }


def validate_editor_source(tabs: Mapping[str, Any]) -> list[dict[str, str]]:
    """Validate supplied source fragments without requiring/re-authoring other tabs."""
    issues: list[dict[str, str]] = []
    source_text = "\n".join(str(value) for value in tabs.values())
    if "libs/sql/v1" in source_text:
        issues.append(
            {
                "code": "unsupported_sql_library",
                "path": "tabs",
                "message": "Editor runtime does not provide libs/sql/v1",
            }
        )
    if re.search(r"wrapFn\s*\(\s*\(\s*\)\s*=>", source_text):
        issues.append(
            {
                "code": "wrap_fn_arguments_dropped",
                "path": "tabs",
                "message": "wrapFn callback must preserve runtime arguments",
            }
        )
    return issues
