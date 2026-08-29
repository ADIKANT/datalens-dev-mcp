from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

DEFAULT_DATALENS_UI_BASE_URL = "https://datalens.ru"
URL_SOURCES = frozenset({"api_inventory", "route_builder", "provider_readback"})
_URL_RE = re.compile(r"https?://[^\s)\]>]+")
_RELATIVE_PATH_RE = re.compile(
    r"(?:^|\]\()(?P<path>/(?:collections|connections|datasets|editor|pages|ql|reports|wizard|workbooks)/[^\s)\]>]+)"
)
_OBJECT_ID_RE = re.compile(r"^[A-Za-z0-9_]{8,64}")
_ROUTE_PREFIXES = {
    "collection": "collections",
    "connection": "connections",
    "dataset": "datasets",
    "editor_chart": "editor",
    "html_page": "pages",
    "ql_chart": "ql",
    "report": "reports",
    "wizard_chart": "wizard",
    "workbook": "workbooks",
}
_PATH_OBJECT_TYPES = {
    "collections": "collection",
    "connections": "connection",
    "datasets": "dataset",
    "editor": "editor_chart",
    "pages": "html_page",
    "ql": "ql_chart",
    "reports": "report",
    "wizard": "wizard_chart",
    "workbooks": "workbook",
}
_NAVIGATION_TYPE_ALIASES = {
    "advanced_editor_chart": "editor_chart",
    "chart": "editor_chart",
    "control": "editor_chart",
    "control_node": "editor_chart",
    "d3_node": "editor_chart",
    "dash": "dashboard",
    "dashboard_node": "dashboard",
    "editor": "editor_chart",
    "editor_markdown": "editor_chart",
    "editor_table": "editor_chart",
    "markdown_node": "editor_chart",
    "ql": "ql_chart",
    "table_node": "editor_chart",
    "wizard": "wizard_chart",
}


def build_canonical_direct_url(
    object_type: str,
    object_id: str,
    *,
    base_url: str = DEFAULT_DATALENS_UI_BASE_URL,
) -> str:
    """Build an ID-only DataLens navigation route without inventory search."""

    normalized_type = _navigation_object_type(object_type)
    normalized_id = str(object_id or "").strip()
    if not normalized_id:
        return ""
    root = str(base_url or DEFAULT_DATALENS_UI_BASE_URL).rstrip("/")
    prefix = _ROUTE_PREFIXES.get(normalized_type)
    if normalized_type == "dashboard":
        return f"{root}/{normalized_id}"
    if not prefix:
        return ""
    return f"{root}/{prefix}/{normalized_id}"


def normalize_object_locator(
    value: Any = "",
    *,
    object_type: str = "",
    object_id: str = "",
    workbook_id: str = "",
    url_source: str = "route_builder",
) -> dict[str, str]:
    """Normalize Markdown, query and direct paths to one typed locator."""

    if url_source not in URL_SOURCES:
        raise ValueError(f"url_source must be one of {sorted(URL_SOURCES)}")
    source_url = _first_datalens_url(value)
    parsed = urlparse(source_url) if source_url else None
    inferred_type, inferred_id = _type_and_id_from_url(parsed) if parsed else ("", "")
    resolved_type = _navigation_object_type(object_type or inferred_type)
    resolved_id = str(object_id or inferred_id).strip()
    direct_url = ""
    if parsed and inferred_id and (not resolved_id or inferred_id == resolved_id):
        direct_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))
    if not direct_url:
        direct_url = build_canonical_direct_url(resolved_type, resolved_id)
    return {
        "object_id": resolved_id,
        "object_type": resolved_type,
        "workbook_id": str(workbook_id or "").strip(),
        "canonical_direct_url": direct_url,
        "url_source": url_source,
    }


def provider_direct_url(value: Any) -> str:
    """Return only an explicit DataLens object URL from provider readback."""

    if isinstance(value, dict):
        for key in ("canonicalDirectUrl", "canonical_direct_url", "directUrl", "direct_url", "url", "link"):
            candidate = value.get(key)
            direct = _first_datalens_url(candidate)
            if direct:
                return direct
        for nested in value.values():
            direct = provider_direct_url(nested)
            if direct:
                return direct
    elif isinstance(value, list):
        for nested in value:
            direct = provider_direct_url(nested)
            if direct:
                return direct
    return ""


def _first_datalens_url(value: Any) -> str:
    text = str(value or "").strip()
    for match in _URL_RE.finditer(text):
        candidate = match.group(0).rstrip(".,;:}")
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
        if host == "datalens.ru" or host.endswith(".datalens.ru"):
            return candidate
    relative = _RELATIVE_PATH_RE.search(text)
    if relative:
        return f"{DEFAULT_DATALENS_UI_BASE_URL}{relative.group('path').rstrip('.,;:}')}"
    return ""


def _type_and_id_from_url(parsed: Any) -> tuple[str, str]:
    query = parse_qs(parsed.query)
    query_types = (
        ("dashboard", ("dashboardId", "dashboard_id")),
        ("dataset", ("datasetId", "dataset_id")),
        ("connection", ("connectionId", "connection_id")),
        ("workbook", ("workbookId", "workbook_id")),
        ("editor_chart", ("chartId", "chart_id")),
    )
    for object_type, keys in query_types:
        for key in keys:
            candidate = str((query.get(key) or [""])[0])
            if candidate:
                return object_type, candidate
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return "", ""
    inferred_type = _PATH_OBJECT_TYPES.get(segments[0], "dashboard")
    candidate = segments[-1]
    match = _OBJECT_ID_RE.match(candidate)
    return inferred_type, match.group(0) if match else ""


def _navigation_object_type(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return _NAVIGATION_TYPE_ALIASES.get(normalized, normalized)
