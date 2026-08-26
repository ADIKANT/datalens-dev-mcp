from __future__ import annotations

import json
from typing import Any


def serialize_selector_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def validate_selector_semantics(
    selectors: list[dict[str, Any]] | None,
    *,
    filters: list[dict[str, Any]] | None = None,
    current_domains: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    filter_fields = [str(item.get("guid") or "") for item in filters or [] if isinstance(item, dict)]
    domains = current_domains or {}
    for index, selector in enumerate(selectors or []):
        if not isinstance(selector, dict):
            issues.append(_issue("error", "invalid_selector", f"selectors[{index}] must be an object"))
            continue
        field = str(selector.get("field_guid") or selector.get("guid") or "")
        value = selector.get("value")
        values = value if isinstance(value, list) else ([] if value in (None, "") else [value])
        empty_means_no_filter = bool(selector.get("empty_means_no_filter", True))
        if not field:
            issues.append(_issue("error", "missing_selector_field", f"selectors[{index}] needs field_guid"))
        if field in filter_fields:
            issues.append(
                _issue(
                    "warning",
                    "same_field_selector_overrides_internal_filter",
                    f"Selector for {field} overrides an internal filter on the same field; duplicate the field to require both.",
                )
            )
        if not values and not empty_means_no_filter:
            issues.append(_issue("error", "selector_empty_contract", f"Empty selector {field} must mean no filter"))
        if values and field in domains:
            allowed = {serialize_selector_value(item) for item in domains[field]}
            missing = [item for item in values if serialize_selector_value(item) not in allowed]
            if missing:
                issues.append(
                    _issue("error", "selector_value_unavailable", f"Selector {field} contains values outside the current domain")
                )
        if selector.get("initial_params_dynamic") is True:
            issues.append(_issue("error", "initial_params_must_be_static", "Initial parameters are static configuration"))
        if selector.get("changed_params_dynamic") is False:
            issues.append(_issue("error", "changed_params_must_be_dynamic", "Changed parameters are dynamic input"))
        if selector.get("kind") == "period":
            order = selector.get("field_order") or []
            if order and order != ["from", "to"]:
                issues.append(_issue("error", "period_selector_order", "Period selector fields must be ordered from, to"))
        normalized.append(
            {
                "field_guid": field,
                "serialized_values": [serialize_selector_value(item) for item in values],
                "empty_means_no_filter": empty_means_no_filter,
            }
        )
    return {
        "ok": not any(item["severity"] == "error" for item in issues),
        "issues": issues,
        "selectors": normalized,
        "rules": {
            "same_field": "selector_overrides_internal_filter",
            "empty_selection": "no_filter",
            "double_filter": "duplicate_field_required",
            "initial_params": "static",
            "changed_params": "dynamic",
        },
    }


def _issue(severity: str, rule: str, message: str) -> dict[str, Any]:
    return {"severity": severity, "rule": rule, "message": message}
