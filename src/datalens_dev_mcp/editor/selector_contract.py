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
SELECTOR_FAMILIES = STATIC_SELECTOR_FAMILIES | {
    DYNAMIC_SELECTOR_FAMILY,
    DATE_SELECTOR_FAMILY,
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
        "schema_version": "datalens.editor_selector_contract.v1",
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
    paired = [
        str(contract.get("param_from") or "").strip(),
        str(contract.get("param_to") or "").strip(),
    ]
    if all(paired):
        return paired
    parameter = str(contract.get("param") or "").strip()
    return [parameter] if parameter else []


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
