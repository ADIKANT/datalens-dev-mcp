from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from datalens_dev_mcp.pipeline.selector_semantics import serialize_selector_value


ASSERTION_KINDS = {
    "schema_matches",
    "not_empty",
    "expected_empty",
    "row_count_between",
    "row_count_range",
    "unique_key",
    "no_nulls",
    "null_ratio_between",
    "value_domain",
    "min_max_date",
    "date_coverage",
    "numeric_range",
    "non_negative",
    "ratio_consistency",
    "aggregation_consistency",
    "comparison_period_alignment",
    "pagination_complete",
    "selector_value_available",
    "selector_domain",
    "filter_effect",
    "selector_empty_means_no_filter",
    "sort_total_order",
    "sort_order",
    "saved_vs_published_consistency",
}

POPULATION_ASSERTIONS = frozenset(
    {
        "row_count_between",
        "row_count_range",
        "unique_key",
        "no_nulls",
        "null_ratio_between",
        "value_domain",
        "selector_domain",
        "min_max_date",
        "date_coverage",
        "numeric_range",
        "non_negative",
    }
)


def evaluate_data_assertions(
    *,
    assertions: list[dict[str, Any]],
    schema: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    paging: dict[str, Any] | None = None,
    selector_domains: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    results = [
        _evaluate_one(item, schema=schema, rows=rows, paging=paging or {}, selector_domains=selector_domains or {})
        for item in assertions
    ]
    status = "passed"
    if any(item["status"] == "failed" for item in results):
        status = "failed"
    elif any(item["status"] == "insufficient_evidence" for item in results):
        status = "insufficient_evidence"
    return {
        "schema_id": "data_assertion_result",
        "ok": status == "passed",
        "status": status,
        "assertion_count": len(results),
        "passed": sum(item["status"] == "passed" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "insufficient_evidence": sum(item["status"] == "insufficient_evidence" for item in results),
        "results": results,
    }


def unexpected_empty_diagnostics(spec: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("filters", "Verify filter values, operations, and field GUIDs against saved dataset readback."),
        ("params", "Verify initial static parameters and selector-driven dynamic parameters."),
        ("date_window", "Verify requested dates overlap the source freshness window."),
        ("selector_domain", "Verify selected values exist in the current option domain; empty means no filter."),
        ("source_availability", "Distinguish missing table, present empty source, and provider failure."),
        ("branch", "Compare saved and published dataset/chart branches for revision mismatch."),
    ]
    return [{"check": key, "explanation": message} for key, message in checks]


def _evaluate_one(
    assertion: dict[str, Any],
    *,
    schema: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    paging: dict[str, Any],
    selector_domains: dict[str, list[Any]],
) -> dict[str, Any]:
    if not isinstance(assertion, dict):
        return _result("unknown", "failed", "Assertion must be an object")
    kind = str(assertion.get("kind") or "")
    if kind not in ASSERTION_KINDS:
        return _result(kind or "unknown", "failed", "Unsupported assertion kind")
    fields = _fields(assertion)
    if (
        kind in POPULATION_ASSERTIONS
        and assertion.get("scope", "population") != "sample"
        and paging.get("complete") is False
    ):
        return _result(
            kind,
            "insufficient_evidence",
            "A bounded sample cannot prove a population-wide assertion",
            {"sample_only": True, "paging_complete": False},
        )
    missing = [field for field in fields if field not in {str(item.get("guid") or "") for item in schema}]
    if missing and kind not in {"schema_matches", "pagination_complete", "selector_empty_means_no_filter"}:
        return _result(kind, "failed", "Assertion references unknown field GUIDs", {"missing_fields": missing})
    if kind == "schema_matches":
        expected = assertion.get("expected") or assertion.get("columns") or []
        actual = {str(item.get("guid") or ""): str(item.get("type") or "") for item in schema}
        expected_map = {
            str(item.get("guid") or ""): str(item.get("type") or "")
            for item in expected
            if isinstance(item, dict)
        }
        ok = bool(expected_map) and all(actual.get(guid) == field_type for guid, field_type in expected_map.items())
        return _bool_result(kind, ok, {"expected": expected_map, "actual": actual})
    if kind == "not_empty":
        return _bool_result(kind, bool(rows), {"row_count": len(rows)})
    if kind == "expected_empty":
        return _bool_result(
            kind,
            not rows,
            {"row_count": len(rows)},
            success="Empty result matches the business expectation",
        )
    if kind in {"row_count_between", "row_count_range"}:
        return _between(kind, len(rows), assertion)
    if kind == "unique_key":
        keys = [tuple(row.get(field) for field in fields) for row in rows]
        return _bool_result(
            kind,
            bool(fields) and len(keys) == len(set(keys)),
            {"fields": fields, "duplicates": len(keys) - len(set(keys))},
        )
    if kind == "no_nulls":
        nulls = sum(row.get(field) is None for row in rows for field in fields)
        return _bool_result(kind, bool(fields) and nulls == 0, {"fields": fields, "null_count": nulls})
    if kind == "null_ratio_between":
        values = [row.get(field) for row in rows for field in fields]
        ratio = (sum(value is None for value in values) / len(values)) if values else None
        return _between(kind, ratio, assertion, extra={"fields": fields})
    if kind in {"value_domain", "selector_domain"}:
        allowed = {serialize_selector_value(item) for item in assertion.get("allowed") or []}
        outside = sorted({serialize_selector_value(row.get(fields[0])) for row in rows} - allowed) if fields else []
        return _bool_result(kind, bool(fields) and not outside, {"outside_domain": outside[:20], "outside_count": len(outside)})
    if kind in {"min_max_date", "date_coverage"}:
        values = [_as_date(row.get(fields[0])) for row in rows] if fields else []
        dates = [item for item in values if item is not None]
        if not dates:
            return _result(kind, "insufficient_evidence", "No parseable date values")
        observed = {"min": min(dates).isoformat(), "max": max(dates).isoformat()}
        expected_min = _as_date(assertion.get("min") or assertion.get("start"))
        expected_max = _as_date(assertion.get("max") or assertion.get("end"))
        ok = (expected_min is None or min(dates) <= expected_min) and (expected_max is None or max(dates) >= expected_max)
        return _bool_result(kind, ok, observed)
    if kind in {"numeric_range", "non_negative"}:
        values = [_decimal(row.get(field)) for row in rows for field in fields if row.get(field) is not None]
        if not values or any(item is None for item in values):
            return _result(kind, "insufficient_evidence", "No complete numeric evidence")
        numeric = [item for item in values if item is not None]
        minimum = Decimal("0") if kind == "non_negative" else _decimal(assertion.get("min"))
        maximum = None if kind == "non_negative" else _decimal(assertion.get("max"))
        ok = all((minimum is None or item >= minimum) and (maximum is None or item <= maximum) for item in numeric)
        return _bool_result(kind, ok, {"observed_min": str(min(numeric)), "observed_max": str(max(numeric))})
    if kind in {"ratio_consistency", "aggregation_consistency"}:
        numerator = str(assertion.get("numerator") or "")
        denominator = str(assertion.get("denominator") or "")
        ratio = str(assertion.get("ratio") or "")
        tolerance = _decimal(assertion.get("tolerance", "0.000001")) or Decimal("0")
        invalid = 0
        for row in rows:
            n, d, r = _decimal(row.get(numerator)), _decimal(row.get(denominator)), _decimal(row.get(ratio))
            if n is None or d in {None, Decimal("0")} or r is None or abs((n / d) - r) > tolerance:
                invalid += 1
        return _bool_result(kind, invalid == 0, {"inconsistent_rows": invalid})
    if kind == "comparison_period_alignment":
        left, right = (fields + ["", ""])[:2]
        delta_days = int(assertion.get("delta_days", 0))
        invalid = sum(
            1
            for row in rows
            if _as_date(row.get(left)) is None
            or _as_date(row.get(right)) is None
            or (_as_date(row.get(left)) - _as_date(row.get(right))).days != delta_days
        )
        return _bool_result(kind, bool(left and right) and invalid == 0, {"misaligned_rows": invalid})
    if kind == "pagination_complete":
        return _bool_result(kind, bool(paging.get("complete")), {"paging": paging})
    if kind == "selector_value_available":
        field = fields[0] if fields else str(assertion.get("field") or "")
        domain = {serialize_selector_value(item) for item in selector_domains.get(field, [])}
        selected = assertion.get("values") or []
        missing_values = [item for item in selected if serialize_selector_value(item) not in domain]
        return _bool_result(kind, bool(domain) and not missing_values, {"missing_values": missing_values})
    if kind == "selector_empty_means_no_filter":
        return _bool_result(kind, assertion.get("empty_means_no_filter", True) is True, {})
    if kind in {"sort_total_order", "sort_order"}:
        sort = assertion.get("sort") or []
        unique_fields = set(assertion.get("tie_breaker_fields") or [])
        sort_fields = [str(item.get("guid") or "") for item in sort if isinstance(item, dict)]
        total_order = bool(
            sort_fields
            and unique_fields
            and unique_fields.issubset(set(sort_fields))
            and _rows_follow_total_order(rows, sort)
        )
        return _bool_result(
            kind,
            total_order,
            {"sort_fields": sort_fields, "tie_breaker_fields": sorted(unique_fields)},
        )
    if kind == "filter_effect":
        baseline = assertion.get("baseline_row_count")
        applied = assertion.get("applied_row_count")
        if not isinstance(baseline, int) or not isinstance(applied, int):
            return _result(kind, "insufficient_evidence", "Baseline and filtered probe counts are required")
        expectation = str(assertion.get("expectation") or "changed")
        ok = applied < baseline if expectation == "reduced" else applied != baseline
        return _bool_result(kind, ok, {"baseline_row_count": baseline, "applied_row_count": applied})
    if kind == "saved_vs_published_consistency":
        return _result(
            kind,
            "insufficient_evidence",
            "getDatasetData has no revision parameter and cannot prove saved versus published consistency",
            {"dataset_data_semantics": "unknown_experimental"},
        )
    return _result(kind, "failed", "Assertion implementation is unavailable")


def _fields(assertion: dict[str, Any]) -> list[str]:
    values = assertion.get("fields")
    if not isinstance(values, list):
        values = [assertion.get("field")] if assertion.get("field") else []
    return [str(value) for value in values if str(value)]


def _between(kind: str, value: Any, assertion: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return _result(kind, "insufficient_evidence", "No values are available")
    minimum = assertion.get("min")
    maximum = assertion.get("max")
    ok = (minimum is None or value >= minimum) and (maximum is None or value <= maximum)
    return _bool_result(kind, ok, {"observed": value, "min": minimum, "max": maximum, **(extra or {})})


def _bool_result(kind: str, ok: bool, metrics: dict[str, Any], success: str = "Assertion passed") -> dict[str, Any]:
    return _result(kind, "passed" if ok else "failed", success if ok else "Assertion failed", metrics)


def _result(kind: str, status: str, explanation: str, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": kind, "status": status, "explanation": explanation, "metrics": metrics or {}}


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _rows_follow_total_order(rows: list[dict[str, Any]], sort: list[dict[str, Any]]) -> bool:
    sort_fields = [str(item.get("guid") or "") for item in sort if isinstance(item, dict)]
    keys = [tuple(row.get(field) for field in sort_fields) for row in rows]
    if len(keys) != len(set(keys)):
        return False
    for left, right in zip(rows, rows[1:]):
        comparison = 0
        for item in sort:
            field = str(item.get("guid") or "")
            left_value = left.get(field)
            right_value = right.get(field)
            try:
                comparison = (left_value > right_value) - (left_value < right_value)
            except TypeError:
                left_text, right_text = str(left_value), str(right_value)
                comparison = (left_text > right_text) - (left_text < right_text)
            if comparison:
                if item.get("direction") == "desc":
                    comparison *= -1
                break
        if comparison > 0:
            return False
    return True
