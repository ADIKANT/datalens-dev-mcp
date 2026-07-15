from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from typing import Any


_SAFE_RE = re.compile(r"^[a-z0-9_-]+$")
_UNSAFE_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")
_DUPLICATE_SEPARATOR_RE = re.compile(r"[_-]{2,}")
_TECHNICAL_NAME_PARENTS = {"data", "meta", "body", "config", "entry", "chart", "payload"}
_SERIALIZED_CONTAINER_KEYS = {"data", "meta", "body", "config", "entry", "chart", "payload"}
_CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "і": "i",
        "ї": "yi",
        "є": "e",
        "ґ": "g",
        "ў": "u",
    }
)


def sanitize_datalens_internal_name(value: str) -> str:
    source = "" if value is None else str(value)
    if not source:
        return "object"
    lowered = source.lower()
    transliterated = lowered.translate(_CYRILLIC_TRANSLITERATION)
    ascii_text = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode("ascii")
    normalized = _UNSAFE_SEPARATOR_RE.sub("_", ascii_text.lower())
    normalized = _DUPLICATE_SEPARATOR_RE.sub("_", normalized).strip("_-")
    if normalized:
        if _has_untransliterated_alnum(lowered):
            digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
            return f"{normalized}_{digest}"
        return normalized
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    return f"object_{digest}"


def _has_untransliterated_alnum(source: str) -> bool:
    for char in source:
        if char.isascii() or not char.isalnum():
            continue
        expanded = unicodedata.normalize("NFKD", char.translate(_CYRILLIC_TRANSLITERATION))
        if not expanded.encode("ascii", "ignore"):
            return True
    return False


def validate_datalens_internal_name(value: str) -> list[str]:
    text = "" if value is None else str(value)
    issues: list[str] = []
    if not text:
        return ["internal name is empty"]
    if text != text.lower():
        issues.append("internal name must be lowercase")
    if not _SAFE_RE.match(text):
        issues.append("internal name contains characters outside a-z, 0-9, underscore, hyphen")
    if text != text.strip("_-"):
        issues.append("internal name must not start or end with a separator")
    if _DUPLICATE_SEPARATOR_RE.search(text):
        issues.append("internal name must not contain duplicate separators")
    return issues


def find_unsafe_internal_names(payload: dict[str, Any]) -> list[dict[str, str]]:
    return _find_unsafe(payload, [])


def sanitize_generated_internal_names(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = deepcopy(payload)
    _sanitize_in_place(sanitized, [])
    return sanitized


def format_unsafe_internal_name_issues(issues: list[dict[str, str]]) -> str:
    parts = []
    for issue in issues:
        parts.append(f"{issue['path']}={issue['value']!r} -> {issue['suggested']!r}")
    return "; ".join(parts)


def _find_unsafe(value: Any, path: list[str]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = [*path, str(key)]
            if key == "name" and _is_internal_name_path(child_path):
                reasons = validate_datalens_internal_name(str(item or ""))
                if reasons:
                    issues.append(
                        {
                            "path": _format_path(child_path),
                            "value": "" if item is None else str(item),
                            "reason": "; ".join(reasons),
                            "suggested": sanitize_datalens_internal_name(str(item or "")),
                        }
                    )
            issues.extend(_find_unsafe(item, child_path))
            issues.extend(_find_serialized_unsafe(key=str(key), value=item, path=child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_find_unsafe(item, [*path[:-1], f"{path[-1]}[{index}]"] if path else [f"[{index}]"]))
    return issues


def _find_serialized_unsafe(*, key: str, value: Any, path: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, str) or key not in _SERIALIZED_CONTAINER_KEYS:
        return []
    stripped = value.strip()
    if not stripped.startswith(("{", "[")):
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    return _find_unsafe(parsed, path)


def _sanitize_in_place(value: Any, path: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            child_path = [*path, str(key)]
            if key == "name" and _is_internal_name_path(child_path):
                reasons = validate_datalens_internal_name(str(item or ""))
                if reasons:
                    value[key] = sanitize_datalens_internal_name(str(item or ""))
            else:
                _sanitize_in_place(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _sanitize_in_place(item, [*path[:-1], f"{path[-1]}[{index}]"] if path else [f"[{index}]"])


def _is_internal_name_path(path: list[str]) -> bool:
    if len(path) < 2 or path[-1] != "name":
        return False
    return _strip_index(path[-2]) in _TECHNICAL_NAME_PARENTS


def _strip_index(part: str) -> str:
    return part.split("[", 1)[0]


def _format_path(path: list[str]) -> str:
    rendered = ""
    for part in path:
        if part.startswith("["):
            rendered += part
        elif "[" in part:
            rendered += ("." if rendered else "") + part
        else:
            rendered += ("." if rendered else "") + part
    return rendered
