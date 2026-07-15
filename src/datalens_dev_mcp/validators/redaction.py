from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from typing import Any

REDACTED = "<redacted>"
MIN_SECRET_VALUE_LENGTH = 8
COMMON_NON_SECRET_VALUES = {
    "0",
    "1",
    "auto",
    "false",
    "none",
    "null",
    "off",
    "on",
    "true",
    "yes",
    "no",
}

SENSITIVE_KEY_RE = re.compile(
    r"(?:^|[_\-.])(?:token|authorization|subjecttoken|password|secret|iam|cookie|session|"
    r"api[_\-.]?key|apikey|dsn|connection[_\-.]?string)(?:$|[_\-.])",
    re.IGNORECASE,
)
BEARER_RE = re.compile(
    r"\bBearer\s+(?:[A-Za-z0-9._~+/=-]{12,}|(?=[A-Za-z0-9._~+/=-]*[._~+/=-])[A-Za-z0-9._~+/=-]{3,})\b",
    re.IGNORECASE,
)
YC_TOKEN_RE = re.compile(r"\by0_[A-Za-z0-9_-]{20,}\b")
SECRET_LIKE_VALUE_RE = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{16,}|"
    r"gh[pousr]_[A-Za-z0-9_]{16,}|"
    r"github_pat_[A-Za-z0-9_]{16,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_-]{20,}|"
    r"ya29\.[0-9A-Za-z._-]{16,}|"
    r"xox[baprs]-[0-9A-Za-z-]{16,}|"
    r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r")\b"
)
HEADER_SECRET_RE = re.compile(
    r"\b(?:x-api-key|api-key|apikey|authorization|cookie|set-cookie)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)
KEY_VALUE_SECRET_RE = re.compile(
    r"\b(?:token|api[_\-.]?key|apikey|password|secret|cookie|session|dsn|connection[_\-.]?string)"
    r"\s*[:=]\s*['\"]?[^'\"\s,;]+",
    re.IGNORECASE,
)
URL_USERINFO_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@[^\s]+", re.IGNORECASE)


def is_sensitive_key(key: Any) -> bool:
    return bool(SENSITIVE_KEY_RE.search(str(key)))


def looks_like_secret_value(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) < MIN_SECRET_VALUE_LENGTH or text.lower() in COMMON_NON_SECRET_VALUES:
        return False
    return bool(
        BEARER_RE.search(text)
        or YC_TOKEN_RE.search(text)
        or SECRET_LIKE_VALUE_RE.search(text)
        or URL_USERINFO_RE.search(text)
        or HEADER_SECRET_RE.search(text)
        or KEY_VALUE_SECRET_RE.search(text)
    )


def secret_values_from_mapping(values: Mapping[str, Any] | None = None) -> list[str]:
    source = os.environ if values is None else values
    secrets: list[str] = []
    seen: set[str] = set()
    for key, value in source.items():
        text = str(value or "")
        if not _redactable_secret_value(text):
            continue
        if not is_sensitive_key(key) and not looks_like_secret_value(text):
            continue
        if text not in seen:
            seen.add(text)
            secrets.append(text)
    return secrets


def redact_text(
    text: str,
    *,
    secret_values: Iterable[Any] | None = None,
    include_env: bool = True,
) -> str:
    redacted = str(text or "")
    for secret in _redactable_secret_values(secret_values or ()):
        redacted = redacted.replace(secret, REDACTED)
    if include_env:
        for secret in secret_values_from_mapping():
            redacted = redacted.replace(secret, REDACTED)
    redacted = BEARER_RE.sub(REDACTED, redacted)
    redacted = YC_TOKEN_RE.sub(REDACTED, redacted)
    redacted = SECRET_LIKE_VALUE_RE.sub(REDACTED, redacted)
    redacted = URL_USERINFO_RE.sub(REDACTED, redacted)
    redacted = HEADER_SECRET_RE.sub(lambda match: _redact_assignment(match.group(0)), redacted)
    redacted = KEY_VALUE_SECRET_RE.sub(lambda match: _redact_assignment(match.group(0)), redacted)
    return redacted


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            sanitized[key] = REDACTED if is_sensitive_key(key) else sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _redact_assignment(text: str) -> str:
    separator_index = min((index for index in (text.find(":"), text.find("=")) if index >= 0), default=-1)
    if separator_index < 0:
        return REDACTED
    return text[: separator_index + 1] + REDACTED


def _redactable_secret_values(values: Iterable[Any]) -> list[str]:
    secrets: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "")
        if _redactable_secret_value(text) and text not in seen:
            seen.add(text)
            secrets.append(text)
    return secrets


def _redactable_secret_value(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) >= MIN_SECRET_VALUE_LENGTH and stripped.lower() not in COMMON_NON_SECRET_VALUES
