from __future__ import annotations

from typing import Any


def semantic_object_payload(response: dict[str, Any]) -> dict[str, Any]:
    """Normalize a typed DataLens read envelope to the semantic object payload."""

    value: Any = response.get("result") if isinstance(response.get("result"), dict) else response
    if isinstance(value, dict):
        for key in ("dashboard", "chart", "entry"):
            if isinstance(value.get(key), dict):
                value = value[key]
                break
    if not isinstance(value, dict):
        return {}
    entry = dict(value.get("entry") or {}) if isinstance(value.get("entry"), dict) else {}
    data = value.get("data")
    if entry:
        if data is not None:
            entry["data"] = data
        return entry
    return dict(value)
