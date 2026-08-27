from __future__ import annotations

from datalens_dev_mcp.pipeline.dataset_context_profile import (
    build_dataset_context_profile,
    validate_dataset_context_profile,
)


def _profile(*, rows: list[dict], limit: int = 100) -> dict:
    return build_dataset_context_profile(
        dataset_id="dataset_demo",
        workbook_id="book_demo",
        dataset_revision="r2",
        query_set_hash="a" * 64,
        schema_hash="b" * 64,
        field_catalog=[
            {"guid": "date_guid", "name": "event_date", "type": "date"},
            {"guid": "value_guid", "name": "value", "type": "float"},
            {"guid": "email_guid", "name": "email", "type": "string"},
        ],
        rows=rows,
        pages_read=1,
        requested_limit=limit,
        deterministic=False,
        observed_at="2026-08-27T00:00:00Z",
    )


def test_profile_separates_sample_facts_from_population_claims_and_redacts_sensitive_values() -> None:
    profile = _profile(
        rows=[
            {"date_guid": "2026-08-26", "value_guid": 0.0, "email_guid": "person@example.test"},
            {"date_guid": "2026-08-27", "value_guid": -2.5, "email_guid": "other@example.test"},
        ]
    )
    assert not validate_dataset_context_profile(profile)
    assert "population_row_count" in profile["forbidden_claims"]
    assert profile["numeric"]["value_guid"]["observed_negative_count"] == 1
    assert profile["categorical"]["email_guid"]["values_redacted_or_hashed"] is True
    assert "person@example.test" not in str(profile)
    assert profile["raw_rows_inline"] is False


def test_exactly_limit_rows_do_not_claim_completeness() -> None:
    rows = [{"date_guid": "2026-08-27", "value_guid": index, "email_guid": None} for index in range(2)]
    profile = _profile(rows=rows, limit=2)
    assert profile["sample_scope"]["complete"] is False
    assert "bounded sample; not population" in profile["sample_scope"]["limitations"]


def test_sensitive_numeric_and_temporal_ranges_are_not_exposed() -> None:
    profile = build_dataset_context_profile(
        dataset_id="dataset_demo",
        workbook_id="book_demo",
        dataset_revision="r2",
        query_set_hash="a" * 64,
        schema_hash="b" * 64,
        field_catalog=[
            {"guid": "account_id", "name": "account_id", "type": "integer", "unique": True},
            {"guid": "private_date", "name": "private_date", "type": "date", "sensitive": True},
        ],
        rows=[{"account_id": 123456789, "private_date": "1990-01-02"}],
        pages_read=1,
        requested_limit=100,
        deterministic=True,
        observed_at="2026-08-27T00:00:00Z",
    )
    assert profile["numeric"]["account_id"]["observed_min"] is None
    assert profile["numeric"]["account_id"]["values_redacted_or_hashed"] is True
    assert profile["temporal"]["private_date"]["observed_min"] is None
    assert profile["temporal"]["private_date"]["values_redacted_or_hashed"] is True
    assert "123456789" not in str(profile)
    assert "1990-01-02" not in str(profile)


def test_high_cardinality_selector_is_sample_only_not_complete_domain() -> None:
    profile = build_dataset_context_profile(
        dataset_id="dataset_demo",
        workbook_id="book_demo",
        dataset_revision="r2",
        query_set_hash="a" * 64,
        schema_hash="b" * 64,
        field_catalog=[{"guid": "category", "name": "category", "type": "string"}],
        rows=[{"category": f"value-{index}"} for index in range(51)],
        pages_read=1,
        requested_limit=100,
        deterministic=False,
        observed_at="2026-08-27T00:00:00Z",
    )
    assert profile["categorical"]["category"]["high_cardinality_sample"] is True
    assert "category" not in profile["selector_candidates"]
    assert "complete_distinct_domain" in profile["forbidden_claims"]


def test_duplicate_declared_unique_value_revokes_deterministic_sample_claim() -> None:
    profile = build_dataset_context_profile(
        dataset_id="dataset_demo",
        workbook_id="book_demo",
        dataset_revision="r2",
        query_set_hash="a" * 64,
        schema_hash="b" * 64,
        field_catalog=[{"guid": "row_id", "name": "row_id", "type": "string", "unique": True}],
        rows=[{"row_id": "duplicate"}, {"row_id": "duplicate"}],
        pages_read=1,
        requested_limit=100,
        deterministic=True,
        observed_at="2026-08-27T00:00:00Z",
    )
    assert profile["sample_scope"]["deterministic"] is False
    assert {item["kind"] for item in profile["quality_findings"]} == {"declared_unique_duplicate"}
    assert "declared unique tie-breaker duplicated in sample" in profile["sample_scope"]["limitations"]
