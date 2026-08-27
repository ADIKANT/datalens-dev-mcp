from __future__ import annotations

from typing import Any


def extract_dashboard_parameter_defaults(value: Any) -> dict[str, str | int | float | bool]:
    """Extract only conflict-free scalar selector defaults from dashboard readback."""
    observed: dict[str, list[str | int | float | bool]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            source = item.get("source")
            defaults = item.get("defaults")
            if isinstance(source, dict) and isinstance(defaults, dict):
                guid = str(source.get("fieldName") or source.get("fieldGuid") or "").strip()
                if guid:
                    normalized = _scalar_default(defaults.get(guid, source.get("defaultValue")))
                    if normalized is not None:
                        observed.setdefault(guid, []).append(normalized)
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return {
        guid: values[0]
        for guid, values in sorted(observed.items())
        if values and all(value == values[0] for value in values)
    }


def parameter_payload(
    defaults: dict[str, str | int | float | bool],
    *,
    allowed_guids: set[str] | None = None,
) -> list[dict[str, Any]]:
    allowed = allowed_guids if allowed_guids is not None else set(defaults)
    return [
        {"guid": guid, "value": defaults[guid]}
        for guid in sorted(defaults)
        if guid in allowed
    ]


def _scalar_default(value: Any) -> str | int | float | bool | None:
    if isinstance(value, list):
        if len(value) != 1:
            return None
        value = value[0]
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    return None
