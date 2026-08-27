from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from datalens_dev_mcp.pipeline.dataset_data_contract import build_field_catalog
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

SENSITIVE_RE = re.compile(r"(^|[_\s-])(password|secret|token|authorization|email|phone|mobile|passport|name)([_\s-]|$)", re.IGNORECASE)
DATE_TYPES = frozenset({"date", "genericdatetime", "datetimetz"})
NUMERIC_TYPES = frozenset({"integer", "uinteger", "float"})


def build_dataset_context_profile(
    *,
    dataset_id: str,
    workbook_id: str,
    dataset_revision: str,
    query_set_hash: str,
    schema_hash: str,
    field_catalog: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    pages_read: int,
    requested_limit: int,
    deterministic: bool,
    limitations: list[str] | None = None,
    observed_at: str = "",
    proof_level: str = "live_read_only_api",
    fallback_kind: str = "",
) -> dict[str, Any]:
    catalog = build_field_catalog(field_catalog)
    field_profiles = []
    temporal: dict[str, Any] = {}
    numeric: dict[str, Any] = {}
    categorical: dict[str, Any] = {}
    quality: list[dict[str, Any]] = []
    unique_key_conflict = False
    for field in catalog:
        guid = field["guid"]
        field_type = field["type"]
        sensitive = bool(field.get("sensitive") or field.get("unique") or SENSITIVE_RE.search(f"{guid} {field['name']}"))
        values = [row.get(guid) for row in rows]
        non_null = [value for value in values if value is not None]
        null_count = len(values) - len(non_null)
        roles = _roles(field, non_null)
        field_profiles.append(
            {
                "guid": guid,
                "name": field["name"],
                "type": field_type,
                "role_candidates": roles,
                "sensitive": sensitive,
                "observed_non_null": len(non_null),
                "observed_null": null_count,
            }
        )
        if null_count:
            quality.append({"kind": "sample_nulls", "field_guid": guid, "observed_count": null_count})
        if field.get("unique") and len({canonical_hash(item) for item in non_null}) != len(non_null):
            unique_key_conflict = True
            quality.append({"kind": "declared_unique_duplicate", "field_guid": guid})
        if field_type in DATE_TYPES:
            values_text = sorted(str(item) for item in non_null)
            temporal[guid] = {
                "observed_min": values_text[0] if values_text and not sensitive else None,
                "observed_max": values_text[-1] if values_text and not sensitive else None,
                "values_redacted_or_hashed": sensitive,
            }
        elif field_type in NUMERIC_TYPES:
            parsed = [_decimal(item) for item in non_null]
            valid = [item for item in parsed if item is not None]
            numeric[guid] = {
                "observed_min": str(min(valid)) if valid and not sensitive else None,
                "observed_max": str(max(valid)) if valid and not sensitive else None,
                "observed_zero_count": sum(item == 0 for item in valid) if not sensitive else None,
                "observed_negative_count": sum(item < 0 for item in valid) if not sensitive else None,
                "values_redacted_or_hashed": sensitive,
            }
        else:
            serialized = [canonical_hash(item) if sensitive else str(item) for item in non_null]
            counts = Counter(serialized)
            categorical[guid] = {
                "observed_distinct_count": len(counts),
                "sample_values": [item for item, _ in counts.most_common(10)],
                "values_redacted_or_hashed": sensitive,
                "high_cardinality_sample": len(counts) > 50,
            }
    complete = not fallback_kind and len(rows) < requested_limit and pages_read == 1
    sample_limitations = list(limitations or [])
    if not complete:
        sample_limitations.append("bounded sample; not population")
    if unique_key_conflict:
        sample_limitations.append("declared unique tie-breaker duplicated in sample")
    effective_deterministic = deterministic and not unique_key_conflict
    if not effective_deterministic:
        sample_limitations.append("sample order/subset is not guaranteed without a proven total order")
    sample_limitations = sorted(set(sample_limitations))
    profile = {
        "schema_id": "dataset_context_profile",
        "dataset_id": dataset_id,
        "workbook_id": workbook_id,
        "dataset_revision": dataset_revision,
        "query_set_hash": query_set_hash,
        "schema_hash": schema_hash,
        "observed_at": observed_at or _utc_now(),
        "dataset_data_semantics": "unknown_experimental",
        "proof_level": proof_level,
        "fallback_kind": fallback_kind,
        "fields": field_profiles,
        "sample_scope": {
            "rows_observed": len(rows),
            "pages_read": pages_read,
            "complete": complete,
            "deterministic": effective_deterministic,
            "limitations": sample_limitations,
        },
        "temporal": temporal,
        "numeric": numeric,
        "categorical": categorical,
        "selector_candidates": [item["guid"] for item in field_profiles if "selector" in item["role_candidates"]],
        "quality_findings": quality,
        "admissible_claims": (
            ["saved_schema_fields", "provider_unavailable"]
            if fallback_kind
            else [
                "sample_empty" if not rows else "sample_non_empty",
                "observed_sample_null_counts",
                "observed_sample_min_max",
                "observed_sample_categories",
            ]
        ),
        "forbidden_claims": [
            "population_row_count", "complete_distinct_domain", "global_min_max",
            "global_uniqueness", "global_no_nulls", "population_distribution",
            "saved_vs_published_consistency",
        ],
        "raw_rows_inline": False,
    }
    profile["profile_hash"] = dataset_context_profile_hash(profile)
    return profile


def dataset_context_profile_hash(profile: dict[str, Any]) -> str:
    material = dict(profile)
    material.pop("profile_hash", None)
    return canonical_hash(material)


def validate_dataset_context_profile(profile: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if profile.get("schema_id") != "dataset_context_profile":
        issues.append("dataset context profile schema_id is invalid")
    if profile.get("profile_hash") != dataset_context_profile_hash(profile):
        issues.append("dataset context profile hash mismatch")
    if profile.get("raw_rows_inline") is not False:
        issues.append("dataset context profile must not contain raw rows inline")
    forbidden = set(profile.get("forbidden_claims") or [])
    if "population_row_count" not in forbidden:
        issues.append("sample profile must forbid unsupported population claims")
    return tuple(issues)


def derive_dataset_plan_context(
    profile: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    fields = [item for item in profile.get("fields") or [] if isinstance(item, dict)]
    date_fields = [str(item.get("guid") or "") for item in fields if "date_dimension" in item.get("role_candidates", [])]
    measure_fields = [str(item.get("guid") or "") for item in fields if "measure" in item.get("role_candidates", [])]
    selector_fields = [str(item) for item in profile.get("selector_candidates") or []]
    requested = " ".join(
        str(item.get("statement") or "")
        for item in contract.get("acceptance") or []
        if isinstance(item, dict) and item.get("kind") != "semantic_change"
    ).lower()
    issues: list[str] = []
    if any(token in requested for token in ("trend", "динамик", "time series")) and not date_fields:
        issues.append("trend request has no observed date field in the bounded dataset context")
    candidates: list[str] = []
    if date_fields and measure_fields:
        candidates.append("trend")
    if measure_fields:
        candidates.extend(["kpi", "table", "distribution"])
    elif fields:
        candidates.append("table")
    if selector_fields:
        candidates.append("selector")
    return {
        "ok": not issues,
        "issues": issues,
        "field_bindings": {
            "date": date_fields[:1],
            "measure": measure_fields[:2],
            "selector": selector_fields[:3],
        },
        "visual_candidates": list(dict.fromkeys(candidates)),
        "recommended_granularity": "day" if date_fields else "not_applicable",
        "empty_selection_semantics": "no_filter",
        "limitations": list((profile.get("sample_scope") or {}).get("limitations") or []),
    }


def _roles(field: dict[str, Any], values: list[Any]) -> list[str]:
    roles: list[str] = []
    field_type = str(field.get("type") or "")
    if field_type in DATE_TYPES:
        roles.append("date_dimension")
    if field_type in NUMERIC_TYPES:
        roles.append("measure")
    if field.get("unique"):
        roles.append("key")
    if field_type in {"string", "boolean"} and len({str(item) for item in values}) <= 50:
        roles.extend(["dimension", "selector"])
    return roles or ["dimension"]


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
