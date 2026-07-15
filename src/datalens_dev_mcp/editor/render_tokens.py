from __future__ import annotations

from functools import lru_cache
from typing import Any

from datalens_dev_mcp.runtime_resources import resource_json


STYLE_TOKENS_RESOURCE = "config/datalens_visual_style_tokens.json"


@lru_cache(maxsize=1)
def load_visual_style_tokens() -> dict[str, Any]:
    return resource_json(STYLE_TOKENS_RESOURCE)


def token_color(name: str, *, default: str = "#6b7280") -> str:
    colors = load_visual_style_tokens().get("colors") or {}
    return str(colors.get(name) or default)


def table_defaults() -> dict[str, Any]:
    return dict(load_visual_style_tokens().get("table_defaults") or {})


def runtime_limits() -> dict[str, Any]:
    return dict(load_visual_style_tokens().get("limits") or {})
