from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class KpiIndicatorFinding:
    rule: str
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KpiIndicatorValidation:
    ok: bool
    publish_allowed: bool
    checked_kpi_count: int
    findings: list[KpiIndicatorFinding] = field(default_factory=list)
    schema_version: str = "2026-07-01.kpi_indicator_contract.v1"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "findings": [finding.to_dict() for finding in self.findings]}


def validate_kpi_indicator_contract(payload: dict[str, Any]) -> KpiIndicatorValidation:
    kpis = _kpis(payload)
    findings: list[KpiIndicatorFinding] = []
    for index, kpi in enumerate(kpis):
        path = f"$.kpis[{index}]"
        object_type = _object_type(kpi)
        allowed_object_types = {
            "indicator_node",
            "kpi_indicator",
            "kpi_node",
            "advanced_editor_chart",
            "editor_advanced",
        }
        if object_type and object_type not in allowed_object_types:
            findings.append(
                _finding(
                    "kpi_not_separate_indicator_object",
                    f"{path}.object_type",
                    f"KPI object route is not governed: {object_type}",
                )
            )
        metric_contract = kpi.get("metric_contract") if isinstance(kpi.get("metric_contract"), dict) else {}
        metric_formula = str(kpi.get("formula") or metric_contract.get("formula") or metric_contract.get("metric") or "").strip()
        if not metric_formula:
            findings.append(_finding("kpi_missing_metric_contract", f"{path}.metric_contract", "KPI requires one metric contract/formula"))
        for key in ("unit", "grain", "comparator_policy"):
            if not str(kpi.get(key) or "").strip():
                findings.append(_finding(f"kpi_missing_{key}", f"{path}.{key}", f"KPI requires {key}"))
        findings.extend(_one_metric_findings(kpi, path=path))
        comparator = str(kpi.get("comparator_policy") or kpi.get("comparator") or "").strip().lower()
        explicit_comparators = {"none", "explicit_none", "target", "threshold", "previous_period_explicit"}
        explicit = bool(kpi.get("comparator_explicit") or comparator in explicit_comparators)
        if comparator in {"previous_period", "implicit_previous_period", "prev_period"} and not explicit:
            findings.append(
                _finding(
                    "kpi_implicit_previous_period",
                    f"{path}.comparator_policy",
                    "previous-period comparator must be explicit and traceable",
                )
            )
        if not kpi.get("native_title") and not kpi.get("title"):
            findings.append(_finding("kpi_missing_native_title", f"{path}.native_title", "KPI needs native dashboard title metadata"))
        if not kpi.get("native_hint") and not kpi.get("hint"):
            findings.append(_finding("kpi_missing_native_hint", f"{path}.native_hint", "KPI needs native dashboard hint metadata"))
    body = _joined_strings(payload).lower()
    if _contains_kpi_card_grid(body):
        findings.append(_finding("kpi_html_card_grid", "$", "KPI card grids are blocked; use separate KPI/indicator objects"))
    if payload.get("expected_kpi_count") and len(kpis) < int(payload["expected_kpi_count"]):
        findings.append(
            _finding(
                "kpi_object_count_below_expected",
                "$.kpis",
                f"expected {payload['expected_kpi_count']} KPI objects but found {len(kpis)}",
            )
        )
    errors = [finding for finding in findings if finding.severity == "error"]
    return KpiIndicatorValidation(
        ok=not errors,
        publish_allowed=not errors,
        checked_kpi_count=len(kpis),
        findings=findings,
    )


def _kpis(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("kpis") or payload.get("indicators") or []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    objects = payload.get("objects") or []
    if isinstance(objects, list):
        result = []
        for item in objects:
            if isinstance(item, dict) and _looks_like_kpi(item):
                result.append(item)
        return result
    return []


def _object_type(kpi: dict[str, Any]) -> str:
    return str(kpi.get("object_type") or kpi.get("entry_type") or kpi.get("route") or "").strip().lower()


def _looks_like_kpi(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key) or "") for key in ("id", "title", "role", "family", "object_type")).lower()
    return "kpi" in text or "indicator" in text or "индикатор" in text


def _one_metric_findings(kpi: dict[str, Any], *, path: str) -> list[KpiIndicatorFinding]:
    findings: list[KpiIndicatorFinding] = []
    for key in ("metrics", "measures", "formulas", "metric_contracts"):
        raw = kpi.get(key)
        if isinstance(raw, list) and len([item for item in raw if item]) > 1:
            findings.append(
                _finding(
                    "kpi_multiple_metrics",
                    f"{path}.{key}",
                    "one KPI object may declare exactly one metric; split multi-metric KPI grids into separate objects",
                )
            )
    if isinstance(kpi.get("metric_contract"), dict):
        contract = kpi["metric_contract"]
        raw = contract.get("metrics") or contract.get("measures")
        if isinstance(raw, list) and len([item for item in raw if item]) > 1:
            findings.append(
                _finding(
                    "kpi_multiple_metrics",
                    f"{path}.metric_contract",
                    "one KPI object may declare exactly one metric contract",
                )
            )
    return findings


def _contains_kpi_card_grid(body: str) -> bool:
    lowered = body.lower()
    if re.search(r"(kpi-card|metric-card|card-grid|cards-grid)", lowered):
        return True
    return bool("grid-template-columns" in lowered and re.search(r"\b(kpi|metric|indicator)\b", lowered))


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


def _finding(rule: str, path: str, message: str, *, severity: str = "error") -> KpiIndicatorFinding:
    return KpiIndicatorFinding(rule=rule, severity=severity, path=path, message=message)
