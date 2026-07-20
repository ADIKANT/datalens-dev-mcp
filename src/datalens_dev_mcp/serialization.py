from __future__ import annotations

import hashlib
import json
from typing import Any

from datalens_dev_mcp.validators.redaction import REDACTED, is_sensitive_key, redact_text


def stable_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(stable_json_text(value).encode("utf-8")).hexdigest()


def serialized_metadata(value: Any) -> dict[str, Any]:
    text = stable_json_text(value)
    return {
        "serialized_chars": len(text),
        "serialized_bytes": len(text.encode("utf-8")),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def sanitize_response(value: Any) -> Any:
    return _sanitize_response_value(value)


def _sanitize_response_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(key) and not _safe_sensitive_metadata(key, item):
                sanitized[key] = REDACTED
            else:
                sanitized[key] = _sanitize_response_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_response_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_response_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _safe_sensitive_metadata(key: Any, value: Any) -> bool:
    """Keep status metadata while still redacting credential material."""

    normalized = str(key).strip().lower().replace("-", "_").replace(".", "_")
    if isinstance(value, bool):
        return normalized.endswith(("_present", "_available", "_enabled", "_bootstrapped", "_expired")) or any(
            marker in normalized for marker in ("refresh", "token", "authorization")
        )
    if isinstance(value, int | float):
        return normalized.endswith(("_timeout_sec", "_expires_in", "_count"))
    if normalized in {"token_source", "authorization_source"} and isinstance(value, str):
        return value in {
            "canonical_env_file",
            "current_user_request",
            "env_file",
            "local_config",
            "missing",
            "process_env",
            "token_refresh",
            "tool_call_intent",
            "yc_cli",
            "yc_cli_bootstrap",
        }
    return False
