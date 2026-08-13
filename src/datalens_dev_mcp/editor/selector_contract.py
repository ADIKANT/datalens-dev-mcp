from __future__ import annotations

import re
from typing import Any


STATIC_SELECTOR_FAMILIES = frozenset(
    {
        "single_select_dropdown",
        "multi_select_dropdown",
        "search_selector",
        "selector_family_static",
    }
)
DYNAMIC_SELECTOR_FAMILY = "selector_family_dynamic"
DATE_SELECTOR_FAMILY = "date_range_selector"
SELECTOR_GROUP_FAMILY = "selector_group"
SELECTOR_FAMILIES = STATIC_SELECTOR_FAMILIES | {
    DYNAMIC_SELECTOR_FAMILY,
    DATE_SELECTOR_FAMILY,
    SELECTOR_GROUP_FAMILY,
}
_DATE_TOKEN_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|__relative_[^\s]+)$")


def normalize_selector_contract(
    *,
    family: str,
    title: str,
    selector_contract: dict[str, Any] | None,
    param: str | None = None,
    options: list[str] | None = None,
) -> dict[str, Any]:
    if family not in SELECTOR_FAMILIES:
        return {}
    if family == SELECTOR_GROUP_FAMILY:
        return _normalize_selector_group(selector_contract)

    explicit = selector_contract is not None
    if selector_contract is None:
        raw: dict[str, Any] = {
            "param": str(param or "").strip(),
            "label": title,
            "option_source": (
                "static"
                if family in STATIC_SELECTOR_FAMILIES
                else "dataset"
                if family == DYNAMIC_SELECTOR_FAMILY
                else "none"
            ),
            "options": list(options or []) if family in STATIC_SELECTOR_FAMILIES else [],
            "default_values": [],
            "reset_behavior": "empty",
        }
        if family == DATE_SELECTOR_FAMILY and len(options or []) == 2:
            start, end = (str(value).strip() for value in (options or []))
            if _DATE_TOKEN_RE.fullmatch(start) and _DATE_TOKEN_RE.fullmatch(end):
                raw["default_values"] = [f"__interval_{start}_{end}"]
                raw["reset_behavior"] = "initial"
    elif isinstance(selector_contract, dict):
        raw = dict(selector_contract)
    else:
        raw = {}

    issues: list[dict[str, str]] = []
    allowed = {
        "param",
        "param_from",
        "param_to",
        "label",
        "option_source",
        "options",
        "default_values",
        "default_from",
        "default_to",
        "reset_behavior",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        issues.append(
            _issue(
                "unknown_selector_contract_fields",
                "Unknown selector contract fields: " + ", ".join(unknown),
            )
        )

    label = str((raw.get("label") or "") if explicit else raw.get("label") or title).strip()
    parameter = str(raw.get("param") or "").strip()
    param_from = str(raw.get("param_from") or "").strip()
    param_to = str(raw.get("param_to") or "").strip()
    option_source = str(raw.get("option_source") or "").strip().lower()
    reset_behavior = str(raw.get("reset_behavior") or "").strip().lower()
    normalized_options = _normalize_options(raw.get("options"), issues=issues)
    default_values = _string_list(raw.get("default_values"), "default_values", issues=issues)
    default_from = str(raw.get("default_from") or "").strip()
    default_to = str(raw.get("default_to") or "").strip()

    if not label:
        issues.append(_issue("missing_selector_label", "Selector label is required."))
    if explicit and not reset_behavior:
        issues.append(
            _issue(
                "missing_selector_reset_behavior",
                "Explicit selector_contract requires reset_behavior=initial or empty.",
            )
        )
    if reset_behavior not in {"initial", "empty"}:
        issues.append(
            _issue(
                "invalid_selector_reset_behavior",
                "reset_behavior must be initial or empty.",
            )
        )

    if family == DATE_SELECTOR_FAMILY:
        has_interval_param = bool(parameter)
        has_pair = bool(param_from and param_to)
        if has_interval_param == has_pair:
            issues.append(
                _issue(
                    "invalid_date_parameter_contract",
                    "Date range requires either param or both param_from and param_to, but not both forms.",
                )
            )
        if bool(param_from) != bool(param_to):
            issues.append(
                _issue(
                    "incomplete_date_parameter_pair",
                    "param_from and param_to must be supplied together.",
                )
            )
        if has_pair and param_from == param_to:
            issues.append(
                _issue(
                    "duplicate_date_parameter",
                    "param_from and param_to must be distinct parameters.",
                )
            )
        if option_source != "none":
            issues.append(
                _issue(
                    "invalid_date_option_source",
                    "Date range option_source must be none.",
                )
            )
        if normalized_options:
            issues.append(
                _issue(
                    "date_options_not_supported",
                    "Date range defaults belong in default_values or default_from/default_to, not options.",
                )
            )
        if has_pair:
            if default_values:
                issues.append(
                    _issue(
                        "paired_date_default_values_forbidden",
                        "Paired date parameters use default_from and default_to instead of default_values.",
                    )
                )
            if bool(default_from) != bool(default_to):
                issues.append(
                    _issue(
                        "incomplete_date_default_pair",
                        "default_from and default_to must be supplied together.",
                    )
                )
            for name, value in (("default_from", default_from), ("default_to", default_to)):
                if value and not _DATE_TOKEN_RE.fullmatch(value):
                    issues.append(
                        _issue(
                            f"invalid_{name}",
                            f"{name} must be an ISO date or a DataLens relative-date string.",
                        )
                    )
        elif len(default_values) > 1:
            issues.append(
                _issue(
                    "date_interval_default_count",
                    "An interval parameter accepts at most one interval default string.",
                )
            )
        elif default_values and not default_values[0].startswith("__interval_"):
            issues.append(
                _issue(
                    "invalid_date_interval_default",
                    "An interval parameter default must be a DataLens __interval_ string.",
                )
            )
    else:
        if not parameter:
            issues.append(_issue("missing_selector_param", "Selector param is required."))
        if param_from or param_to or default_from or default_to:
            issues.append(
                _issue(
                    "date_fields_on_non_date_selector",
                    "param_from/param_to/default_from/default_to are valid only for date ranges.",
                )
            )
        expected_source = "dynamic" if family == DYNAMIC_SELECTOR_FAMILY else "static"
        accepted_sources = {"dataset", "dynamic"} if family == DYNAMIC_SELECTOR_FAMILY else {"static"}
        if option_source not in accepted_sources:
            issues.append(
                _issue(
                    "invalid_selector_option_source",
                    f"{family} requires option_source={expected_source}.",
                )
            )
        if family in STATIC_SELECTOR_FAMILIES and not normalized_options:
            issues.append(
                _issue(
                    "missing_selector_options",
                    "Static selectors require at least one explicit option.",
                )
            )
        if family == DYNAMIC_SELECTOR_FAMILY and normalized_options:
            issues.append(
                _issue(
                    "dynamic_selector_static_options",
                    "Dynamic selector options must come from the dataset source.",
                )
            )
        option_values = {item["value"] for item in normalized_options}
        missing_defaults = [value for value in default_values if value not in option_values]
        if family in STATIC_SELECTOR_FAMILIES and missing_defaults:
            issues.append(
                _issue(
                    "selector_default_not_in_options",
                    "Static selector defaults are absent from options: "
                    + ", ".join(missing_defaults),
                )
            )
        if family != "multi_select_dropdown" and len(default_values) > 1:
            issues.append(
                _issue(
                    "single_selector_default_count",
                    "Single-value selectors accept at most one default value.",
                )
            )

    has_defaults = bool(default_values or default_from or default_to)
    if reset_behavior == "empty" and has_defaults:
        issues.append(
            _issue(
                "empty_reset_with_defaults",
                "reset_behavior=empty cannot declare initial default values.",
            )
        )

    return {
        "schema_id": "datalens.editor_selector_contract",
        "family": family,
        "label": label,
        "param": parameter,
        "param_from": param_from,
        "param_to": param_to,
        "option_source": option_source or "none",
        "options": normalized_options,
        "default_values": default_values,
        "default_from": default_from,
        "default_to": default_to,
        "reset_behavior": reset_behavior,
        "ok": not issues,
        "issues": issues,
    }


def selector_params(contract: dict[str, Any]) -> list[str]:
    if not contract:
        return []
    controls = contract.get("controls")
    if isinstance(controls, list):
        values: list[str] = []
        for control in controls:
            if isinstance(control, dict):
                values.extend(selector_params(control))
        return list(dict.fromkeys(values))
    paired = [
        str(contract.get("param_from") or "").strip(),
        str(contract.get("param_to") or "").strip(),
    ]
    if all(paired):
        return paired
    parameter = str(contract.get("param") or "").strip()
    return [parameter] if parameter else []


def _normalize_selector_group(value: Any) -> dict[str, Any]:
    raw = dict(value) if isinstance(value, dict) else {}
    issues: list[dict[str, str]] = []
    allowed = {
        "controls",
        "update_mode",
        "apply_button",
        "row_width_target_percent",
        "blank_multiselect_semantics",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        issues.append(
            _issue(
                "unknown_selector_group_fields",
                "Unknown selector group fields: " + ", ".join(unknown),
            )
        )
    controls_raw = raw.get("controls")
    if not isinstance(controls_raw, list) or not controls_raw:
        issues.append(_issue("missing_selector_group_controls", "selector_group requires non-empty controls."))
        controls_raw = []
    if len(controls_raw) > 12:
        issues.append(_issue("selector_group_too_large", "selector_group supports at most 12 controls."))
    update_mode = str(raw.get("update_mode") or "immediate").strip().lower()
    apply_button = raw.get("apply_button", False)
    target = raw.get("row_width_target_percent", 94)
    blank_semantics = str(raw.get("blank_multiselect_semantics") or "all").strip().lower()
    if update_mode != "immediate":
        issues.append(_issue("selector_group_update_mode", "selector_group update_mode must be immediate."))
    if apply_button is not False:
        issues.append(_issue("selector_group_apply_button", "selector_group must not render an Apply button."))
    if target != 94:
        issues.append(_issue("selector_group_row_width", "selector_group row width target must be exactly 94 percent."))
    if blank_semantics != "all":
        issues.append(_issue("selector_group_blank_semantics", "Blank multiselect semantics must be all."))

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(controls_raw):
        if not isinstance(item, dict):
            issues.append(_issue("invalid_selector_group_control", f"controls[{index}] must be an object."))
            continue
        control_family = str(item.get("family") or item.get("kind") or "single_select_dropdown").strip()
        if control_family == SELECTOR_GROUP_FAMILY or control_family not in SELECTOR_FAMILIES:
            issues.append(
                _issue(
                    "invalid_selector_group_family",
                    f"controls[{index}].family must be a registered single selector family.",
                )
            )
            continue
        row = item.get("row", 1)
        if not isinstance(row, int) or isinstance(row, bool) or row not in {1, 2}:
            issues.append(_issue("invalid_selector_group_row", f"controls[{index}].row must be 1 or 2."))
            row = 1
        width = _width_percent(item.get("width"))
        if item.get("width") is not None and width is None:
            issues.append(
                _issue(
                    "invalid_selector_group_width",
                    f"controls[{index}].width must be an integer percent or a percentage string.",
                )
            )
        source_name = str(item.get("source_name") or "rows").strip()
        value_field = str(item.get("value_field") or "value").strip()
        single_raw = {
            key: child
            for key, child in item.items()
            if key not in {"family", "kind", "row", "width", "source_name", "value_field"}
        }
        single = normalize_selector_contract(
            family=control_family,
            title=str(single_raw.get("label") or ""),
            selector_contract=single_raw,
        )
        if not single.get("ok"):
            issues.extend(
                _issue(
                    f"selector_group_{issue.get('code') or 'invalid_control'}",
                    f"controls[{index}]: {issue.get('message') or issue}",
                )
                for issue in single.get("issues") or []
            )
        normalized.append(
            {
                **single,
                "family": control_family,
                "row": row,
                "width": width,
                "source_name": source_name,
                "value_field": value_field,
                "labelPlacement": "left",
                "updateOnChange": True,
                "multiple": control_family == "multi_select_dropdown",
                "emptyMeansAll": control_family == "multi_select_dropdown",
                "restoreDefaultAfterClear": False,
            }
        )

    for row in (1, 2):
        members = [item for item in normalized if item["row"] == row]
        if not members:
            continue
        explicit = [item["width"] for item in members]
        if all(value is None for value in explicit):
            widths = _equal_widths(len(members), target=94)
            for item, width in zip(members, widths, strict=True):
                item["width"] = width
        elif any(value is None for value in explicit):
            issues.append(
                _issue(
                    "mixed_selector_group_widths",
                    f"row {row} must either declare every width or let the server plan every width.",
                )
            )
        total = sum(int(item["width"] or 0) for item in members)
        if total != 94:
            issues.append(
                _issue(
                    "selector_group_row_width_total",
                    f"row {row} width total must be exactly 94 percent, got {total} percent.",
                )
            )
    populated_rows = sorted({int(item["row"]) for item in normalized})
    if populated_rows == [2]:
        issues.append(_issue("selector_group_missing_first_row", "selector_group row 2 requires row 1."))
    period_indexes = [
        index
        for index, item in enumerate(normalized)
        if item.get("family") == DATE_SELECTOR_FAMILY
        or any("period" in parameter.lower() for parameter in selector_params(item))
    ]
    if period_indexes and period_indexes[0] != 0:
        issues.append(_issue("selector_group_period_first", "Period control must be first when present."))
    rows = [
        {
            "row": row,
            "controls": [item for item in normalized if item.get("row") == row],
            "width_total_percent": sum(
                int(item.get("width") or 0)
                for item in normalized
                if item.get("row") == row
            ),
        }
        for row in populated_rows
    ]
    return {
        "schema_id": "datalens.editor_selector_group_contract",
        "family": SELECTOR_GROUP_FAMILY,
        "controls": normalized,
        "rows": rows,
        "row_count": len(populated_rows),
        "dashboard_grid_height_units": 2 if len(populated_rows) <= 1 else 3,
        "update_mode": update_mode,
        "apply_button": apply_button,
        "showApplyButton": False,
        "row_width_target_percent": target,
        "blank_multiselect_semantics": blank_semantics,
        "ok": not issues,
        "issues": issues,
    }


def _width_percent(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 1 <= value <= 94 else None
    if isinstance(value, str) and value.endswith("%"):
        try:
            parsed = int(value[:-1])
        except ValueError:
            return None
        return parsed if 1 <= parsed <= 94 else None
    return None


def _equal_widths(count: int, *, target: int) -> list[int]:
    if count < 1 or target // count < 8:
        return [0] * max(0, count)
    base, remainder = divmod(target, count)
    return [base + (1 if index < remainder else 0) for index in range(count)]


def _normalize_options(value: Any, *, issues: list[dict[str, str]]) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(_issue("invalid_selector_options", "options must be an array."))
        return []
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            title = item
            option_value = item
        elif isinstance(item, dict):
            raw_title = item.get("title")
            raw_value = item.get("value")
            if not isinstance(raw_title, str) or not isinstance(raw_value, str):
                issues.append(
                    _issue(
                        "invalid_selector_option",
                        f"options[{index}].title and options[{index}].value must be strings.",
                    )
                )
                continue
            title = raw_title.strip()
            option_value = raw_value.strip()
        else:
            issues.append(
                _issue(
                    "invalid_selector_option",
                    f"options[{index}] must be a string or an object with title and value.",
                )
            )
            continue
        if not title or not option_value:
            issues.append(
                _issue(
                    "invalid_selector_option",
                    f"options[{index}] requires non-empty string title and value.",
                )
            )
            continue
        normalized.append({"title": title, "value": option_value})
    values = [item["value"] for item in normalized]
    if len(values) != len(set(values)):
        issues.append(_issue("duplicate_selector_option_value", "Selector option values must be unique."))
    return normalized


def _string_list(value: Any, name: str, *, issues: list[dict[str, str]]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        issues.append(_issue(f"invalid_{name}", f"{name} must be an array of strings."))
        return []
    return [item for item in (value_item.strip() for value_item in value) if item]


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
