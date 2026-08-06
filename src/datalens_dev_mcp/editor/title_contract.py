from __future__ import annotations

import re
from typing import Any

from datalens_dev_mcp.editor.render_contract import canonical_sha256


TITLE_CONTRACT_SCHEMA_VERSION = "2026-08-06.dashboard_title_contract.v1"
TITLE_MODES = frozenset(
    {
        "embedded_title",
        "content_label",
        "tab_only",
        "native_title",
        "tab_strip",
    }
)
_KPI_FAMILIES = frozenset(
    {
        "kpi_value_only",
        "kpi_value_delta",
        "kpi_value_sparkline",
        "kpi_value_delta_sparkline",
    }
)


def default_title_mode(*, route: str, family: str) -> str:
    """Choose the role-owned title surface without duplicating dashboard chrome."""

    if route == "editor_advanced":
        return "content_label" if family in _KPI_FAMILIES else "embedded_title"
    if route in {"editor_js_control", "editor_markdown"}:
        return "tab_only"
    return "native_title"


def normalize_title_contract(
    *,
    route: str,
    family: str,
    display_title: str,
    hint: str = "",
    title_mode: str = "",
) -> dict[str, Any]:
    mode = str(title_mode or default_title_mode(route=route, family=family)).strip()
    title = str(display_title or "").strip()
    normalized_hint = str(hint or "").strip()
    issues: list[str] = []
    if mode not in TITLE_MODES:
        issues.append("title_mode must be one of: " + ", ".join(sorted(TITLE_MODES)))
    if mode in {"embedded_title", "content_label"} and route != "editor_advanced":
        issues.append(f"title_mode={mode} requires route=editor_advanced")
    if mode == "content_label" and family not in _KPI_FAMILIES:
        issues.append("title_mode=content_label is reserved for one-metric KPI families")
    if mode == "tab_strip" and route == "editor_js_control":
        issues.append("title_mode=tab_strip is not valid for a selector control")
    if mode != "tab_only" and not title:
        issues.append(f"title_mode={mode} requires a non-empty display_title")
    if title and looks_technical_title(title):
        issues.append("display_title looks like a technical object id; preserve the exact user-facing title")

    native_visible = mode in {"native_title", "tab_strip"}
    contract: dict[str, Any] = {
        "schema_version": TITLE_CONTRACT_SCHEMA_VERSION,
        "mode": mode,
        "route": str(route or ""),
        "family": str(family or ""),
        "display_title": title,
        "hint": normalized_hint,
        "native_metadata": {
            "title": title,
            "hint": normalized_hint,
            "hideTitle": not native_visible,
            "enableHint": bool(native_visible and normalized_hint),
        },
        "runtime": {
            "renders_title": mode == "embedded_title",
            "renders_hint": bool(mode == "embedded_title" and normalized_hint),
            "renders_content_label": mode == "content_label",
        },
        "mutual_exclusion": {
            "native_and_runtime_title": "forbidden",
            "native_and_runtime_hint": "forbidden",
        },
        "ok": not issues,
        "issues": issues,
    }
    contract["sha256"] = canonical_sha256(
        {key: value for key, value in contract.items() if key not in {"ok", "issues", "sha256"}}
    )
    return contract


def validate_title_contract(contract: dict[str, Any]) -> list[str]:
    if not isinstance(contract, dict):
        return ["title_contract must be an object"]
    expected = normalize_title_contract(
        route=str(contract.get("route") or ""),
        family=str(contract.get("family") or ""),
        display_title=str(contract.get("display_title") or ""),
        hint=str(contract.get("hint") or ""),
        title_mode=str(contract.get("mode") or ""),
    )
    issues = list(expected["issues"])
    for key in ("schema_version", "native_metadata", "runtime", "mutual_exclusion", "sha256"):
        if contract.get(key) != expected.get(key):
            issues.append(f"title_contract.{key} is stale or inconsistent")
    return issues


def looks_technical_title(value: str) -> bool:
    title = str(value or "").strip()
    if not title:
        return False
    if re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+){1,}", title):
        return True
    return bool(re.fullmatch(r"(?:widget|chart|selector|kpi)[_-]?\d+", title, flags=re.IGNORECASE))
