from __future__ import annotations

import re
from typing import Any

from datalens_dev_mcp.pipeline.task_contract import BrowserPolicyContract


FORBIDDEN_PATTERNS = (
    r"\b(?:do not|don't|never)\s+(?:use|open)\s+(?:the\s+)?browser\b",
    r"\b(?:without|no)\s+browser\b",
    r"(?:не надо|не нужно|не используй|не открывай|без)\s+(?:в\s+)?браузер",
)
REQUIRED_PATTERNS = (
    r"\b(?:use|open|check|verify)\s+(?:(?:in|with)\s+)?(?:the\s+)?browser\b",
    r"\bbrowser\s+(?:is\s+)?required\b",
    r"(?:используй|открой|проверь|верифицируй)\s+(?:в\s+)?браузер",
    r"браузер\s+обязател",
)


def compile_browser_policy(
    raw_request: str,
    *,
    corrections: list[str] | tuple[str, ...] | None = None,
    workspace_policy: dict[str, Any] | None = None,
) -> BrowserPolicyContract:
    current_text = "\n".join((raw_request, *(corrections or ())))
    if _matches(current_text, FORBIDDEN_PATTERNS):
        return BrowserPolicyContract(mode="forbidden", source="explicit_user")
    if _matches(current_text, REQUIRED_PATTERNS):
        return BrowserPolicyContract(mode="required", source="explicit_user")
    workspace_mode = str((workspace_policy or {}).get("browser_mode") or "").strip().lower()
    if workspace_mode in {"forbidden", "optional", "required"}:
        return BrowserPolicyContract(mode=workspace_mode, source="workspace_policy")  # type: ignore[arg-type]
    return BrowserPolicyContract(mode="optional", source="compiled_default")


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
