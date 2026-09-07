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
    items: list[dict[str, Any]]
    errors: list[dict[str, str]]
    provider_writes: int
    proof_level: str
