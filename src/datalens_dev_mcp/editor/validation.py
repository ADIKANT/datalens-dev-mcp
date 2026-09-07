from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

EDITOR_CONTRACTS = {
    "table_node": {"required_tabs": {"meta.json", "params.js", "sources.js", "prepare.js", "config.js"}, "runtime": "editor_table"},
    "d3_node": {"required_tabs": {"meta.json", "params.js", "sources.js", "prepare.js", "controls.js"}, "runtime": "gravity_charts"},
    "advanced-chart_node": {"required_tabs": {"meta.json", "params.js", "sources.js", "prepare.js", "controls.js"}, "runtime": "advanced_chart"},
    "markdown_node": {"required_tabs": {"meta.json", "params.js", "prepare.js"}, "runtime": "markdown"},
    "control_node": {"required_tabs": {"meta.json", "params.js", "controls.js"}, "runtime": "selector"},
}


def validate_editor_draft(draft: Mapping[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    variant = str(draft.get("variant") or "")
    contract = EDITOR_CONTRACTS.get(variant)
    tabs = draft.get("tabs") if isinstance(draft.get("tabs"), Mapping) else {}
    if contract is None:
        issues.append({"code": "editor_variant_unsupported", "path": "variant", "message": f"unsupported Editor variant: {variant}"})
        required: set[str] = set()
        runtime = "unknown"
    else:
        required = set(contract["required_tabs"])
        runtime = str(contract["runtime"])
    missing = sorted(required - set(tabs))
    if missing:
        issues.append({"code": "editor_tabs_missing", "path": "tabs", "message": "missing required tabs: " + ", ".join(missing)})
    if contract is not None:
        unknown = sorted(set(tabs) - required)
        if unknown:
            issues.append({"code": "editor_tabs_unsupported", "path": "tabs",
                           "message": "unsupported tabs for variant: " + ", ".join(unknown)})
    aliases = draft.get("source_aliases") or []
    if not isinstance(aliases, list) or any(not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias) for alias in aliases):
        issues.append({"code": "source_alias_invalid", "path": "source_aliases", "message": "source aliases must be JavaScript identifiers"})
    elif len(aliases) != len(set(aliases)):
        issues.append({"code": "source_alias_duplicate", "path": "source_aliases", "message": "source aliases must be unique"})
    source_text = "\n".join(str(value) for value in tabs.values())
    if "libs/sql/v1" in source_text:
        issues.append({"code": "unsupported_sql_library", "path": "tabs", "message": "Editor runtime does not provide libs/sql/v1"})
    if re.search(r"wrapFn\s*\(\s*\(\s*\)\s*=>", source_text):
        issues.append({"code": "wrap_fn_arguments_dropped", "path": "tabs", "message": "wrapFn callback must preserve runtime arguments"})
    return {
        "ok": not issues,
        "variant": variant,
        "issues": issues,
        "runtime": {
            "kind": runtime,
            "static_source_checked": True,
            "live_result_checked": False,
            "live_result_status": "static/source contract checked; live result not checked",
            "node_runtime_assumed": False,
        },
    }
