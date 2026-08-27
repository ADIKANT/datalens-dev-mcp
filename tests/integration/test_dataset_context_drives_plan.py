from __future__ import annotations

from datalens_dev_mcp.pipeline.dataset_context_profile import (
    build_dataset_context_profile,
    derive_dataset_plan_context,
)


def _profile(*, include_date: bool) -> dict:
    fields = [{"guid": "metric_guid", "name": "revenue", "type": "float"}]
    row = {"metric_guid": 10.0}
    if include_date:
        fields.insert(0, {"guid": "date_guid", "name": "event_date", "type": "date"})
        row["date_guid"] = "2026-08-27"
    return build_dataset_context_profile(
        dataset_id="dataset_demo",
        workbook_id="",
        dataset_revision="r2",
        query_set_hash="a" * 64,
        schema_hash="b" * 64,
        field_catalog=fields,
        rows=[row],
        pages_read=1,
        requested_limit=100,
        deterministic=False,
    )


def test_live_context_binds_date_metric_and_recommends_trend_granularity() -> None:
    decision = derive_dataset_plan_context(
        _profile(include_date=True),
        {"acceptance": [{"kind": "business", "statement": "Show revenue trend"}]},
    )
    assert decision["ok"] is True
    assert decision["field_bindings"]["date"] == ["date_guid"]
    assert decision["field_bindings"]["measure"] == ["metric_guid"]
    assert "trend" in decision["visual_candidates"]
    assert decision["recommended_granularity"] == "day"


def test_trend_without_date_field_is_rejected_as_meaningless_design() -> None:
    decision = derive_dataset_plan_context(
        _profile(include_date=False),
        {"acceptance": [{"kind": "business", "statement": "Show revenue trend"}]},
    )
    assert decision["ok"] is False
    assert "no observed date field" in decision["issues"][0]
