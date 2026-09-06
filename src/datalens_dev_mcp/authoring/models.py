from __future__ import annotations

from typing import Any, TypedDict


class DraftBundle(TypedDict):
    ok: bool
    recipe_id: str
    draft: dict[str, Any]
    files: dict[str, str]
    summary: dict[str, Any]
    defaults: dict[str, Any]


class ValidationResult(TypedDict):
    ok: bool
    issues: list[dict[str, str]]
