from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from datalens_dev_mcp.validators.uri_safety import assess_uri


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200
MAX_COLUMNS = 200
MAX_CELLS = 20_000


@dataclass(frozen=True)
class NativeTableFinding:
    rule: str
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NativeTableValidation:
    ok: bool
    publish_allowed: bool
    checked_column_count: int
    checked_row_count: int | None
    checked_cell_count: int
    effective_page_size: int
    findings: list[NativeTableFinding] = field(default_factory=list)
    schema_version: str = "2026-07-01.native_table_contract_v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def validate_native_table_contract(table_payload: dict[str, Any], *, source_rows: int | None = None) -> NativeTableValidation:
    findings: list[NativeTableFinding] = []
    route = str(table_payload.get("route") or table_payload.get("selected_route") or "")
    if not route:
        findings.append(_finding("missing_table_route", "$.route", "native table payload must declare table_node/editor_table route"))
    elif route not in {"editor_table", "native_table", "table_node"}:
        findings.append(_finding("table_route", "$.route", f"table route must be native table/editor_table, got {route}"))
    body_text = _joined_strings(table_payload).lower()
    if (
        "<table" in body_text
        or "<svg" in body_text
        or "div-grid table" in body_text
        or "html_table" in body_text
        or "table-grid" in body_text
        or "table_grid" in body_text
        or re.search(r"role\s*=\s*['\"]table['\"]", body_text)
    ):
        findings.append(
            _finding(
                "html_svg_div_table_blocked",
                "$",
                "tables must be native table_node/editor_table payloads, not HTML/SVG/div-grid tables",
            )
        )
    columns = _columns(table_payload)
    rows = _rows(table_payload)
    leaf_column_count = _leaf_column_count(columns)
    inferred_source_rows = _source_rows(table_payload, source_rows)
    effective_row_count = max(len(rows), inferred_source_rows or 0)
    checked_cell_count = effective_row_count * leaf_column_count
    page_size, page_size_findings = _page_size(table_payload)
    findings.extend(page_size_findings)
    if leaf_column_count > MAX_COLUMNS:
        findings.append(
            _finding("table_column_cap_exceeded", "$.columns", f"table has {leaf_column_count} leaf columns; maximum is {MAX_COLUMNS}")
        )
    if checked_cell_count > MAX_CELLS:
        findings.append(
            _finding("table_cell_cap_exceeded", "$.rows", f"table has {checked_cell_count} cells; maximum is {MAX_CELLS}")
        )
    query_proof = _query_proof(table_payload)
    if not columns:
        findings.append(_finding("missing_columns", "$.columns", "native table payload must declare visible columns"))
    for index, column in enumerate(columns):
        findings.extend(_column_findings(column, path=f"$.columns[{index}]"))
    if inferred_source_rows is not None and inferred_source_rows > 0:
        if not rows and not query_proof:
            findings.append(
                _finding(
                    "non_empty_source_rendered_empty_table",
                    "$.rows",
                    "source evidence has rows but table payload has no rows or query proof",
                )
            )
    elif columns and not rows and not query_proof and inferred_source_rows != 0:
        findings.append(
            _finding(
                "missing_rows_or_query_proof",
                "$.rows",
                "native table payload must provide rows or source query/row-count proof",
            )
        )
    if inferred_source_rows == 0 and not _empty_state(table_payload):
        findings.append(_finding("missing_explicit_empty_state", "$.empty_state_policy", "zero-row sources need explicit empty state"))
    for index, column in enumerate(columns):
        if _is_bar_column(column):
            findings.extend(_bar_cell_findings(column, path=f"$.columns[{index}]"))
    for index, row in enumerate(rows):
        findings.extend(_row_bar_cell_findings(row, columns=columns, path=f"$.rows[{index}]"))
    findings.extend(_link_findings(table_payload))
    errors = [finding for finding in findings if finding.severity == "error"]
    return NativeTableValidation(
        ok=not errors,
        publish_allowed=not errors,
        checked_column_count=len(columns),
        checked_row_count=effective_row_count if rows or inferred_source_rows is not None else None,
        checked_cell_count=checked_cell_count,
        effective_page_size=page_size,
        findings=findings,
    )


def _columns(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("columns") or payload.get("head") or (payload.get("table_payload") or {}).get("columns") or []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("rows") or (payload.get("table_payload") or {}).get("rows") or []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _leaf_column_count(columns: list[dict[str, Any]]) -> int:
    total = 0
    for column in columns:
        sub = column.get("sub") if isinstance(column.get("sub"), list) else []
        nested = [item for item in sub if isinstance(item, dict)]
        total += _leaf_column_count(nested) if nested else 1
    return total


def _page_size(payload: dict[str, Any]) -> tuple[int, list[NativeTableFinding]]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    paginator = config.get("paginator") if isinstance(config.get("paginator"), dict) else {}
    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    raw = payload.get("page_size", pagination.get("limit", paginator.get("limit")))
    if raw in (None, ""):
        return DEFAULT_PAGE_SIZE, []
    if isinstance(raw, bool):
        return DEFAULT_PAGE_SIZE, [_finding("invalid_table_page_size", "$.page_size", "page size must be an integer from 1 to 200")]
    if isinstance(raw, float) and not raw.is_integer():
        return DEFAULT_PAGE_SIZE, [_finding("invalid_table_page_size", "$.page_size", "page size must be an integer from 1 to 200")]
    if isinstance(raw, str) and not re.fullmatch(r"[0-9]+", raw.strip()):
        return DEFAULT_PAGE_SIZE, [_finding("invalid_table_page_size", "$.page_size", "page size must be an integer from 1 to 200")]
    try:
        page_size = int(raw)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_PAGE_SIZE, [_finding("invalid_table_page_size", "$.page_size", "page size must be an integer from 1 to 200")]
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        return DEFAULT_PAGE_SIZE, [_finding("invalid_table_page_size", "$.page_size", "page size must be an integer from 1 to 200")]
    return page_size, []


def _link_findings(payload: dict[str, Any]) -> list[NativeTableFinding]:
    policy = payload.get("uri_policy") if isinstance(payload.get("uri_policy"), dict) else {}
    allow_http = policy.get("allow_http") is True
    allow_relative = policy.get("allow_relative") is not False
    findings: list[NativeTableFinding] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            link = value.get("link")
            if isinstance(link, dict) and "href" in link:
                decision = assess_uri(link.get("href"), allow_http=allow_http, allow_relative=allow_relative)
                if not decision.allowed:
                    findings.append(
                        _finding(
                            "unsafe_link_uri",
                            f"{path}.link.href",
                            f"unsafe link must fall back to plain text ({decision.reason})",
                        )
                    )
            for key, item in value.items():
                visit(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(payload, "$")
    return findings


def _query_proof(payload: dict[str, Any]) -> bool:
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    query = str(source.get("query") or payload.get("query") or "")
    row_proof = source.get("row_count") or payload.get("row_count")
    return bool(query.strip() or (isinstance(row_proof, int) and row_proof > 0))


def _source_rows(payload: dict[str, Any], supplied: int | None) -> int | None:
    if supplied is not None:
        return supplied
    for container in (payload, payload.get("source") if isinstance(payload.get("source"), dict) else {}):
        raw = container.get("source_rows")
        if raw is None:
            raw = container.get("row_count")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return None


def _empty_state(payload: dict[str, Any]) -> bool:
    state = payload.get("empty_state_policy") or payload.get("emptyState") or {}
    if isinstance(state, dict):
        return bool(state.get("message") or state.get("render"))
    return bool(str(state or "").strip())


def _column_findings(column: dict[str, Any], *, path: str) -> list[NativeTableFinding]:
    findings: list[NativeTableFinding] = []
    for key in ("id", "title"):
        if not column.get(key) and not column.get("name" if key == "title" else key):
            findings.append(_finding(f"missing_column_{key}", f"{path}.{key}", f"column {key} is required"))
    if not column.get("type") and not column.get("role"):
        findings.append(_finding("missing_column_type", f"{path}.type", "column type or role is required"))
    return findings


def _is_bar_column(column: dict[str, Any]) -> bool:
    marker = str(column.get("type") or column.get("view") or column.get("role") or "").lower()
    formatting = column.get("formatting") if isinstance(column.get("formatting"), dict) else {}
    return marker == "bar" or str(formatting.get("type") or formatting.get("view") or "").lower() == "bar"


def _bar_cell_findings(column: dict[str, Any], *, path: str) -> list[NativeTableFinding]:
    findings: list[NativeTableFinding] = []
    bar = {**column}
    if isinstance(column.get("formatting"), dict):
        bar.update(column["formatting"])
    for key in ("min", "max"):
        if key not in bar:
            findings.append(_finding(f"bar_missing_{key}", f"{path}.{key}", f"bar cell requires {key}"))
    if "barColor" not in bar and "bar_color" not in bar:
        findings.append(_finding("bar_missing_barColor", f"{path}.barColor", "bar cell requires barColor"))
    if "min" in bar and "max" in bar and isinstance(bar.get("min"), (int, float)) and isinstance(bar.get("max"), (int, float)):
        if float(bar["max"]) <= float(bar["min"]):
            findings.append(_finding("bar_invalid_min_max", f"{path}.max", "bar max must be greater than min"))
    bar_color = str(bar.get("barColor") or bar.get("bar_color") or "")
    if bar_color and _hex_rgb(bar_color) is None:
        findings.append(_finding("bar_invalid_color", f"{path}.barColor", "barColor must be a 6-digit hex color"))
    show_label = bool(
        bar.get("showLabel")
        or bar.get("show_label")
        or bar.get("labelVisible")
        or bar.get("label_visible")
        or bar.get("label_position") == "outside"
        or bar.get("labelPosition") == "outside"
    )
    if not show_label:
        findings.append(_finding("bar_missing_label", f"{path}.showLabel", "bar cell values must be readable"))
    label_position = str(bar.get("label_position") or bar.get("labelPosition") or "").lower()
    if label_position == "inside":
        contrast = _contrast_ratio(str(bar.get("barColor") or bar.get("bar_color") or "#2f80ed"), str(bar.get("labelColor") or "#ffffff"))
        if contrast < 4.5:
            findings.append(
                _finding(
                    "low_contrast_text_on_bar",
                    f"{path}.barColor",
                    f"inside bar label contrast {contrast:.2f} is below 4.5",
                )
            )
    elif label_position in {"outside", "right"} and bar.get("labelColor") and bar.get("backgroundColor"):
        contrast = _contrast_ratio(str(bar["backgroundColor"]), str(bar["labelColor"]))
        if contrast < 4.5:
            findings.append(
                _finding(
                    "low_contrast_table_label",
                    f"{path}.labelColor",
                    f"outside bar label contrast {contrast:.2f} is below 4.5",
                )
            )
    return findings


def _row_bar_cell_findings(row: dict[str, Any], *, columns: list[dict[str, Any]], path: str) -> list[NativeTableFinding]:
    findings: list[NativeTableFinding] = []
    bar_indices = [index for index, column in enumerate(columns) if _is_bar_column(column)]
    cells = row.get("cells") if isinstance(row.get("cells"), list) else []
    for index in bar_indices:
        cell = cells[index] if index < len(cells) and isinstance(cells[index], dict) else {}
        if not cell:
            continue
        if "value" not in cell:
            findings.append(_finding("bar_cell_missing_value", f"{path}.cells[{index}].value", "bar cell requires value"))
    return findings


def _contrast_ratio(bg: str, fg: str) -> float:
    bg_rgb = _hex_rgb(bg)
    fg_rgb = _hex_rgb(fg)
    if bg_rgb is None or fg_rgb is None:
        return 0.0
    bg_lum = _relative_luminance(bg_rgb)
    fg_lum = _relative_luminance(fg_rgb)
    lighter = max(bg_lum, fg_lum)
    darker = min(bg_lum, fg_lum)
    return (lighter + 0.05) / (darker + 0.05)


def _hex_rgb(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not match:
        return None
    raw = match.group(1)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for value in rgb:
        channel = value / 255
        channels.append(channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _finding(rule: str, path: str, message: str, *, severity: str = "error") -> NativeTableFinding:
    return NativeTableFinding(rule=rule, severity=severity, path=path, message=message)


def _joined_strings(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            parts.append(_joined_strings(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(_joined_strings(item))
    elif isinstance(value, str):
        parts.append(value)
    return "\n".join(parts)
