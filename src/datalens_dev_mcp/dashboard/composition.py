from __future__ import annotations

from copy import deepcopy
from typing import Any

from datalens_dev_mcp.objects.write import semantic_merge

RESERVED_PARAMETERS = frozenset(
    {
        "tab",
        "state",
        "mode",
        "focus",
        "grid",
        "scale",
        "tz",
        "timezone",
        "date",
        "datetime",
        "_action_params",
        "_autoupdate",
        "_opened_info",
        "report_page",
        "preview_mode",
    }
)


def compose_dashboard_patch(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply only the requested mapping paths; arrays and geometry remain untouched unless supplied."""
    return semantic_merge(current, patch)


def validate_dashboard_contract(contract: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    if "tabs" in contract:
        issues.extend(_validate_typed_dashboard_tabs(contract))
    parameter_names: set[str] = set()
    for index, parameter in enumerate(contract.get("parameters") or []):
        name = str(parameter.get("name") or "") if isinstance(parameter, dict) else ""
        if name in RESERVED_PARAMETERS:
            issues.append(
                {
                    "code": "reserved_parameter",
                    "path": f"parameters/{index}/name",
                    "message": f"{name} is reserved by DataLens",
                }
            )
        if name in parameter_names:
            issues.append(
                {
                    "code": "parameter_duplicate",
                    "path": f"parameters/{index}/name",
                    "message": f"duplicate dashboard parameter: {name}",
                }
            )
        elif name:
            parameter_names.add(name)
    widgets = contract.get("widgets") or {}
    for index, selector in enumerate(contract.get("selectors") or []):
        if not isinstance(selector, dict):
            continue
        param = str(selector.get("param_name") or "")
        if not param or param not in parameter_names:
            issues.append(
                {
                    "code": "selector_parameter_undeclared",
                    "path": f"selectors/{index}/param_name",
                    "message": f"selector parameter is not declared: {param or '<missing>'}",
                }
            )
        if selector.get("empty_selection") not in {"all", "none", "error"}:
            issues.append(
                {
                    "code": "selector_empty_semantics_missing",
                    "path": f"selectors/{index}/empty_selection",
                    "message": "selector must define empty selection as all, none or error",
                }
            )
        consumers = selector.get("consumers") or []
        if not consumers:
            issues.append(
                {
                    "code": "selector_without_consumers",
                    "path": f"selectors/{index}/consumers",
                    "message": "selector must name every consumer",
                }
            )
        for consumer in consumers:
            widget = widgets.get(consumer) if isinstance(widgets, dict) else None
            if not isinstance(widget, dict):
                issues.append(
                    {
                        "code": "consumer_missing",
                        "path": f"selectors/{index}/consumers",
                        "message": f"unknown consumer {consumer}",
                    }
                )
                continue
            params = widget.get("params") or {}
            if param and isinstance(params, dict) and param in params:
                issues.append(
                    {
                        "code": "stale_consumer_override",
                        "path": f"widgets/{consumer}/params/{param}",
                        "message": "widget override would reset selector state",
                    }
                )
    return {"ok": not issues, "issues": issues}


def _validate_typed_dashboard_tabs(contract: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    tabs = contract.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        return [
            {
                "code": "dashboard_tabs_missing",
                "path": "dashboard/tabs",
                "message": "typed dashboard requires a nonempty tabs array",
            }
        ]
    if not isinstance(contract.get("settings", {}), dict):
        issues.append(
            {
                "code": "dashboard_settings_invalid",
                "path": "dashboard/settings",
                "message": "dashboard settings must be an object",
            }
        )
    for tab_index, tab in enumerate(tabs):
        tab_path = f"dashboard/tabs/{tab_index}"
        if not isinstance(tab, dict):
            issues.append(
                {"code": "dashboard_tab_invalid", "path": tab_path, "message": "dashboard tab must be an object"}
            )
            continue
        if not isinstance(tab.get("title"), str) or not tab.get("title"):
            issues.append(
                {
                    "code": "dashboard_tab_title_missing",
                    "path": f"{tab_path}/title",
                    "message": "dashboard tab requires a nonempty title",
                }
            )
        items = tab.get("items")
        if not isinstance(items, list) or not items:
            issues.append(
                {
                    "code": "dashboard_items_missing",
                    "path": f"{tab_path}/items",
                    "message": "dashboard tab requires a nonempty items array",
                }
            )
            continue
        for item_index, item in enumerate(items):
            item_path = f"{tab_path}/items/{item_index}"
            if not isinstance(item, dict):
                issues.append(
                    {
                        "code": "dashboard_item_invalid",
                        "path": item_path,
                        "message": "dashboard item must be an object",
                    }
                )
                continue
            kind = item.get("kind")
            if kind not in {"chart", "external_selector", "title", "text"}:
                issues.append(
                    {
                        "code": "dashboard_item_kind_invalid",
                        "path": f"{item_path}/kind",
                        "message": "dashboard item kind must be chart, external_selector, title or text",
                    }
                )
            at = item.get("at")
            if not isinstance(at, (list, tuple)) or len(at) != 4 or any(type(value) is not int for value in at):
                issues.append(
                    {
                        "code": "dashboard_item_at_invalid",
                        "path": f"{item_path}/at",
                        "message": "dashboard item at must contain four integers",
                    }
                )
            if kind in {"chart", "external_selector"}:
                if not isinstance(item.get("chart_id"), str) or not item.get("chart_id"):
                    issues.append(
                        {
                            "code": "dashboard_item_chart_missing",
                            "path": f"{item_path}/chart_id",
                            "message": "dashboard chart item requires a chart_id",
                        }
                    )
                if not isinstance(item.get("title"), str) or not item.get("title"):
                    issues.append(
                        {
                            "code": "dashboard_item_title_missing",
                            "path": f"{item_path}/title",
                            "message": "dashboard chart item requires a title",
                        }
                    )
                if kind == "external_selector":
                    defaults = item.get("defaults")
                    if not isinstance(defaults, dict) or not defaults:
                        issues.append(
                            {
                                "code": "external_selector_defaults_missing",
                                "path": f"{item_path}/defaults",
                                "message": "external selector requires nonempty dashboard defaults for parameter dispatch",
                            }
                        )
            elif kind == "title" and (not isinstance(item.get("title"), str) or not item.get("title")):
                issues.append(
                    {
                        "code": "dashboard_item_title_missing",
                        "path": f"{item_path}/title",
                        "message": "dashboard title item requires a title",
                    }
                )
            elif kind == "text" and (not isinstance(item.get("text"), str) or not item.get("text")):
                issues.append(
                    {
                        "code": "dashboard_item_text_missing",
                        "path": f"{item_path}/text",
                        "message": "dashboard text item requires text",
                    }
                )
    return issues


def dependency_order(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable unbounded topological order for a concrete create batch."""
    by_ref: dict[str, dict[str, Any]] = {}
    position: dict[str, int] = {}
    for index, draft in enumerate(drafts):
        ref = str(draft.get("client_ref") or "")
        if not ref or ref in by_ref:
            raise ValueError("every draft requires a unique client_ref")
        by_ref[ref] = deepcopy(draft)
        position[ref] = index
    dependencies: dict[str, set[str]] = {}
    for ref, draft in by_ref.items():
        deps = {str(value) for value in (draft.get("depends_on") or [])} | object_references(draft)
        draft["depends_on"] = sorted(deps)
        missing = deps - by_ref.keys()
        if missing:
            raise ValueError(f"unknown dependency for {ref}: {sorted(missing)}")
        dependencies[ref] = deps
    ready = sorted((ref for ref, deps in dependencies.items() if not deps), key=position.get)
    result: list[dict[str, Any]] = []
    while ready:
        ref = ready.pop(0)
        result.append(deepcopy(by_ref[ref]))
        for candidate in by_ref:
            if ref in dependencies[candidate]:
                dependencies[candidate].remove(ref)
                if (
                    not dependencies[candidate]
                    and candidate not in {str(item["client_ref"]) for item in result}
                    and candidate not in ready
                ):
                    ready.append(candidate)
        ready.sort(key=position.get)
    if len(result) != len(drafts):
        raise ValueError("dependency cycle in create batch")
    return result


def object_references(value: Any) -> set[str]:
    if isinstance(value, dict):
        if "$object_ref" in value:
            if set(value) != {"$object_ref"} or not isinstance(value["$object_ref"], str) or not value["$object_ref"]:
                raise ValueError("object reference must contain only a nonempty $object_ref")
            return {value["$object_ref"]}
        return set().union(*(object_references(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(object_references(item) for item in value))
    return set()


def bind_object_references(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, dict):
        if "$object_ref" in value:
            ref = value["$object_ref"]
            if ref not in ids:
                raise ValueError(f"object reference has no verified created ID: {ref}")
            return ids[ref]
        return {key: bind_object_references(item, ids) for key, item in value.items()}
    if isinstance(value, list):
        return [bind_object_references(item, ids) for item in value]
    return value
