from __future__ import annotations

from typing import Any


SEMANTIC_FIELD_TYPES = frozenset({"dimension", "measure"})
PHYSICAL_TYPE_ALIASES = {
    "datetime": "genericdatetime",
    "timestamp": "genericdatetime",
    "unsignedinteger": "uinteger",
}


def physical_dataset_field_type(value: dict[str, Any]) -> str:
    """Return the physical DataLens type without confusing it with field role."""
    candidates = (
        value.get("data_type"),
        value.get("dataType"),
        value.get("field_type"),
        value.get("fieldType"),
        value.get("cast"),
    )
    for candidate in candidates:
        normalized = _normalized_physical_token(candidate)
        if normalized:
            return PHYSICAL_TYPE_ALIASES.get(normalized, normalized)
    fallback = _normalized_physical_token(value.get("type"))
    if fallback and fallback not in SEMANTIC_FIELD_TYPES:
        return PHYSICAL_TYPE_ALIASES.get(fallback, fallback)
    return "unsupported"


def semantic_dataset_field_role(value: dict[str, Any]) -> str:
    for candidate in (value.get("semantic_type"), value.get("semanticType"), value.get("role"), value.get("type")):
        normalized = _normalized_token(candidate)
        if normalized in SEMANTIC_FIELD_TYPES:
            return normalized
    return ""


def _normalized_token(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").replace("_", "").casefold()


def _normalized_physical_token(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").casefold()
