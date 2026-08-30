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
FINAL_VISUAL_ONLY_PATTERNS = (
    r"browser\s+qa.{0,120}(?:only|exclusively).{0,120}(?:final|published)",
    r"browser.{0,120}(?:only|exclusively).{0,120}(?:final\s+(?:acceptance|visual)|published\s+dashboard)",
    r"браузер.{0,120}(?:только|исключительно).{0,120}(?:финаль|опубликован)",
)


def compile_browser_policy(
    raw_request: str,
    *,
    corrections: list[str] | tuple[str, ...] | None = None,
    workspace_policy: dict[str, Any] | None = None,
) -> BrowserPolicyContract:
    current_text = "\n".join((raw_request, *(corrections or ())))
    if _matches(current_text, FORBIDDEN_PATTERNS):
        return BrowserPolicyContract(
            mode="forbidden",
            source="explicit_user",
            applicability="not_applicable",
        )
    if _matches(current_text, FINAL_VISUAL_ONLY_PATTERNS):
        return _final_visual_policy(mode="required", source="explicit_user")
    if _matches(current_text, REQUIRED_PATTERNS):
        return _final_visual_policy(mode="required", source="explicit_user")
    workspace_mode = str((workspace_policy or {}).get("browser_mode") or "").strip().lower()
    if workspace_mode == "forbidden":
        return BrowserPolicyContract(
            mode="forbidden",
            source="workspace_policy",
            applicability="not_applicable",
        )
    if workspace_mode in {"optional", "required"}:
        return _final_visual_policy(mode=workspace_mode, source="workspace_policy")  # type: ignore[arg-type]
    return _final_visual_policy(mode="optional", source="compiled_default")


def _final_visual_policy(*, mode: str, source: str) -> BrowserPolicyContract:
    return BrowserPolicyContract(
        mode=mode,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        applicability="applicable",
        purpose="final_visual_acceptance",
        read_only=True,
        mutation_allowed=False,
        earliest_stage="published_readback_and_api_diagnostics_complete",
        calls_before_earliest_stage_allowed=False,
        allowed_interactions=(
            "activate_tab",
            "scroll",
            "hover_visual_detail",
            "read_only_error_detail",
        ),
    )


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
