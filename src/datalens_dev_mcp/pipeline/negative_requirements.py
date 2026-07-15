from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import ensure_project_dirs, read_json, write_json


LEDGER_PATH = "requirements/negative_requirements.json"
SCAN_SURFACES = [
    "requirements_workspace",
    "chart_decision_record",
    "renderer_visual_spec",
    "generated_js",
    "generated_sql",
    "generated_config",
    "control_specs",
    "payload_plan",
    "dashboard_layout_titles_hints",
    "readback_summary",
]
DEFAULT_ALLOWED_EXCEPTIONS = [
    "negative requirement ledger entry",
    "forbidden-token documentation",
    "test fixture asserting the guardrail",
]
IMPLICIT_PERIOD_TOKENS = [
    "previousPeriodBounds",
    "previous_period",
    "previous period",
    "period_bucket",
    "comparison_type",
    "previous_value",
    "delta_abs",
    "delta_pct",
    "absolute delta",
    "percent delta",
    "абсолютная дельта",
    "процентная дельта",
]
NON_TABLE_CHART_FAMILIES = [
    "kpi_value_only",
    "kpi_value_delta",
    "kpi_value_sparkline",
    "kpi_value_delta_sparkline",
    "line_chart",
    "multiline_chart",
    "area_completion",
    "vertical_bar_time_bucket",
    "combo_time_series_combo",
    "horizontal_bar",
    "grouped_bar",
    "stacked_100",
    "bullet_assignees",
    "heatmap",
    "waterfall",
    "funnel_snapshot",
    "sankey_status_flow",
    "histogram",
    "box_plot",
    "scatter",
    "bubble",
    "pie",
    "donut",
    "treemap",
    "grouped_sticky_table_exception",
]


@dataclass(frozen=True)
class NegativeRequirement:
    requirement_id: str
    source_text: str
    scope: str = "project"
    forbidden_concepts: list[str] = field(default_factory=list)
    forbidden_fields: list[str] = field(default_factory=list)
    forbidden_sql_tokens: list[str] = field(default_factory=list)
    forbidden_js_tokens: list[str] = field(default_factory=list)
    forbidden_chart_families: list[str] = field(default_factory=list)
    forbidden_output_columns: list[str] = field(default_factory=list)
    forbidden_titles_hints: list[str] = field(default_factory=list)
    scan_surfaces: list[str] = field(default_factory=lambda: list(SCAN_SURFACES))
    allowed_exceptions: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_EXCEPTIONS))
    severity: str = "error"
    replacement_policy: str = ""
    status: str = "active"
    created_from_user_decision: str = ""
    schema_version: str = "2026-06-30.negative_requirement.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_negative_requirements(source_text: str, *, decision_id: str = "") -> list[NegativeRequirement]:
    text = source_text.strip()
    if not text:
        return []
    lowered = text.lower()
    if not (_has_negative_action(lowered) or _mentions_only_table(lowered)):
        return []
    requirements: list[NegativeRequirement] = []
    if _mentions_implicit_period_comparison(lowered):
        requirements.append(
            NegativeRequirement(
                requirement_id=_stable_requirement_id("implicit_period_comparison", decision_id or text),
                source_text=text,
                forbidden_concepts=["implicit_period_comparison"],
                forbidden_fields=["previous_period", "previous_value"],
                forbidden_sql_tokens=["previousPeriodBounds", "previous_period", "period_bucket", "comparison_type"],
                forbidden_js_tokens=["previousPeriodBounds", "previous_period", "period_bucket", "comparison_type"],
                forbidden_chart_families=["kpi_value_delta", "kpi_value_delta_sparkline"],
                forbidden_output_columns=[
                    "previous_value",
                    "delta_abs",
                    "delta_pct",
                    "absolute delta",
                    "percent delta",
                ],
                forbidden_titles_hints=["previous period", "предыдущий период", "дельта", "delta"],
                replacement_policy="show current value, declared period, and explicit plan/target only if present",
                created_from_user_decision=decision_id,
            )
        )
    if _mentions_pie_or_donut(lowered):
        requirements.append(
            NegativeRequirement(
                requirement_id=_stable_requirement_id("chart_family_pie_donut", decision_id or text),
                source_text=text,
                forbidden_concepts=["chart_family_pie_donut"],
                forbidden_fields=["pie", "donut"],
                forbidden_js_tokens=["pie", "donut"],
                forbidden_chart_families=["pie", "donut"],
                forbidden_titles_hints=["pie", "donut", "круговая", "кольцевая"],
                replacement_policy="use horizontal bars, stacked bars, or a table according to the analytical task",
                created_from_user_decision=decision_id,
            )
        )
    if _mentions_legend(lowered):
        requirements.append(
            NegativeRequirement(
                requirement_id=_stable_requirement_id("legend", decision_id or text),
                source_text=text,
                forbidden_concepts=["legend"],
                forbidden_fields=["legend"],
                forbidden_js_tokens=["legend"],
                forbidden_titles_hints=["legend", "легенда"],
                replacement_policy="use direct labels when needed or omit the legend",
                created_from_user_decision=decision_id,
            )
        )
    if _mentions_only_table(lowered):
        requirements.append(
            NegativeRequirement(
                requirement_id=_stable_requirement_id("table_only_output", decision_id or text),
                source_text=text,
                forbidden_concepts=["table_only_output"],
                forbidden_chart_families=list(NON_TABLE_CHART_FAMILIES),
                forbidden_titles_hints=["chart", "diagram", "график", "диаграмма"],
                replacement_policy="use native table output; markdown and controls remain allowed only as supporting objects",
                created_from_user_decision=decision_id,
            )
        )
    if _mentions_red_green_palette(lowered):
        requirements.append(
            NegativeRequirement(
                requirement_id=_stable_requirement_id("red_green_palette", decision_id or text),
                source_text=text,
                forbidden_concepts=["red_green_palette"],
                forbidden_fields=["red", "green"],
                forbidden_js_tokens=["#2e7d32", "#c62828", "green", "red"],
                forbidden_titles_hints=["red", "green", "красный", "зеленый", "зелёный"],
                replacement_policy="use neutral/focus colors or a blue-orange semantic pair when contrast is required",
                created_from_user_decision=decision_id,
            )
        )
    return _dedupe_requirements(requirements)


def load_negative_requirement_ledger(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root)
    payload = read_json(root / LEDGER_PATH, default={"requirements": []})
    return list(payload.get("requirements") or [])


def record_negative_requirements(
    project_root: str | Path,
    source_text: str,
    *,
    decision_id: str = "",
) -> list[dict[str, Any]]:
    root = ensure_project_dirs(project_root)
    detected = detect_negative_requirements(source_text, decision_id=decision_id)
    if not detected:
        return []
    existing = load_negative_requirement_ledger(root)
    by_id = {str(item.get("requirement_id")): item for item in existing}
    for requirement in detected:
        by_id[requirement.requirement_id] = requirement.to_dict()
    payload = {
        "schema_version": "2026-06-30.negative_requirement_ledger.v1",
        "requirements": list(by_id.values()),
    }
    write_json(root / LEDGER_PATH, payload)
    return [item.to_dict() for item in detected]


def active_negative_requirement_ids(requirements: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("requirement_id"))
        for item in requirements
        if item.get("status", "active") == "active" and item.get("requirement_id")
    ]


def active_forbidden_concepts(requirements: list[dict[str, Any]]) -> list[str]:
    concepts: list[str] = []
    for item in requirements:
        if item.get("status", "active") != "active":
            continue
        concepts.extend(str(value) for value in (item.get("forbidden_concepts") or []) if value)
    return sorted(set(concepts))


def active_forbidden_chart_families(requirements: list[dict[str, Any]]) -> list[str]:
    families: list[str] = []
    for item in requirements:
        if item.get("status", "active") != "active":
            continue
        families.extend(str(value) for value in (item.get("forbidden_chart_families") or []) if value)
    return sorted(set(families))


def validate_no_negative_requirement_drift(
    project_root: str | Path,
    *,
    extra_objects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    requirements = load_negative_requirement_ledger(root)
    active = [item for item in requirements if item.get("status", "active") == "active"]
    findings: list[dict[str, Any]] = []
    for path in _candidate_paths(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(_scan_text(text, path=str(path.relative_to(root)), requirements=active))
    for index, obj in enumerate(extra_objects or []):
        findings.extend(_scan_text(_stable_text(obj), path=f"<extra_objects[{index}]>", requirements=active))
    return {
        "ok": not findings,
        "checked_requirement_count": len(active),
        "findings": findings,
    }


def sanitize_user_decision_line(decision_text: str, detected: list[dict[str, Any]]) -> str:
    if not detected:
        return decision_text.strip()
    parts = []
    for item in detected:
        concepts = ", ".join(item.get("forbidden_concepts") or [])
        replacement = item.get("replacement_policy") or "do not regenerate forbidden concept"
        parts.append(f"negative requirement recorded: {concepts}; replacement: {replacement}")
    return "; ".join(parts)


def _scan_text(text: str, *, path: str, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for requirement in requirements:
        tokens = _forbidden_tokens(requirement, path=path)
        for token in tokens:
            pattern = re.compile(re.escape(token), re.IGNORECASE)
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                if _allowed_context(text, match.start()):
                    continue
                findings.append(
                    {
                        "requirement_id": requirement.get("requirement_id"),
                        "concepts": requirement.get("forbidden_concepts") or [],
                        "path": path,
                        "line": line,
                        "token": token,
                        "replacement_policy": requirement.get("replacement_policy") or "",
                    }
                )
    return findings


def _forbidden_tokens(requirement: dict[str, Any], *, path: str = "") -> list[str]:
    tokens: list[str] = []
    suffix = Path(path).suffix.lower()
    keys = [
        "forbidden_fields",
        "forbidden_sql_tokens",
        "forbidden_js_tokens",
        "forbidden_chart_families",
        "forbidden_output_columns",
    ]
    if suffix in {"", ".json", ".md", ".txt"}:
        keys.append("forbidden_titles_hints")
    for key in keys:
        tokens.extend(str(value) for value in (requirement.get(key) or []) if value)
    return sorted(set(tokens), key=str.lower)


def _candidate_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for base in (root / "dashboard", root / "artifacts", root / "reports"):
        if base.is_dir():
            candidates.extend(
                path
                for path in base.rglob("*")
                if path.is_file()
                and path.name != "bundle.json"
                and not path.name.endswith(".payload.json")
                and path.suffix in {".json", ".js", ".md", ".txt"}
            )
    req = root / "requirements"
    for name in (
        "charts.md",
        "dashboard_canvas.md",
        "dashboard_map.md",
        "object_relations.md",
        "implementation_plan.md",
    ):
        path = req / name
        if path.is_file():
            candidates.append(path)
    return sorted(set(candidates))


def _allowed_context(text: str, offset: int) -> bool:
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].lower()
    context_start = text.rfind("\n", 0, max(0, line_start - 2))
    if context_start == -1:
        context_start = 0
    context_end = line_end
    for _ in range(2):
        next_end = text.find("\n", context_end + 1)
        if next_end == -1:
            context_end = len(text)
            break
        context_end = next_end
    context = text[context_start:context_end].lower()
    allowed_markers = (
        "forbidden",
        "negative requirement",
        "negative_requirement_concepts",
        "replacement",
        "implicit_comparator_default",
        "previous-period is never implicit",
        "guardrail",
        "allowed exception",
        "rejected_families",
        "forbidden_chart_families",
        "forbidden_titles_hints",
        "forbidden_js_tokens",
        "forbidden_sql_tokens",
        "forbidden_fields",
        "allowed_exceptions",
        "scan_surfaces",
    )
    if any(marker in line for marker in allowed_markers):
        return True
    return "legend" in context and '"show": false' in context


def _has_negative_action(lowered: str) -> bool:
    negative_words = (
        "убери",
        "убрать",
        "удали",
        "удалить",
        "не показы",
        "не использ",
        "скрой",
        "скрыть",
        "исключи",
        "исключить",
        "без ",
        "remove",
        "hide",
        "exclude",
        "do not",
        "don't",
        "dont",
        "no ",
        "without ",
        "not use",
        "not show",
    )
    return any(word in lowered for word in negative_words)


def _mentions_implicit_period_comparison(lowered: str) -> bool:
    previous_words = ("предыдущ", "previous period", "previous_period", "дельт", "delta", "period comparison")
    return any(word in lowered for word in previous_words)


def _mentions_pie_or_donut(lowered: str) -> bool:
    return any(word in lowered for word in ("pie", "donut", "кругов", "кольцев"))


def _mentions_legend(lowered: str) -> bool:
    return any(word in lowered for word in ("legend", "легенд"))


def _mentions_only_table(lowered: str) -> bool:
    patterns = (
        r"\bonly\s+(?:a\s+)?table\b",
        r"\btable\s+only\b",
        r"\bonly\s+tables\b",
        r"оставь(?:те)?\s+только\s+таблиц",
        r"только\s+таблиц",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def _mentions_red_green_palette(lowered: str) -> bool:
    red = any(word in lowered for word in ("red", "красн"))
    green = any(word in lowered for word in ("green", "зелен", "зелён"))
    return red and green


def _dedupe_requirements(requirements: list[NegativeRequirement]) -> list[NegativeRequirement]:
    by_id: dict[str, NegativeRequirement] = {}
    for requirement in requirements:
        by_id[requirement.requirement_id] = requirement
    return list(by_id.values())


def _stable_requirement_id(concept: str, source: str) -> str:
    import hashlib

    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10]
    return f"NEG-{concept}-{digest}"


def _stable_text(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
