from __future__ import annotations

import pytest

from datalens_dev_mcp.pipeline.dataset_data_normalizer import (
    normalize_dataset_data_response,
    normalize_dataset_value,
)


@pytest.mark.parametrize(
    ("field_type", "value", "status", "normalized"),
    [
        ("integer", "7", "parsed", 7),
        ("uinteger", -1, "invalid", None),
        ("float", "2.5", "parsed", 2.5),
        ("boolean", "false", "parsed", False),
        ("date", "2026-08-27", "parsed", "2026-08-27"),
        ("genericdatetime", "2026-08-27T01:02:03", "parsed", "2026-08-27T01:02:03"),
        ("datetimetz", "2026-08-27T01:02:03+03:00", "parsed", "2026-08-27T01:02:03+03:00"),
        ("array_int", [1, "2"], "parsed", [1, 2]),
        ("array_float", [1, "2.5"], "parsed", [1.0, 2.5]),
        ("array_str", [1, "x"], "parsed", ["1", "x"]),
        ("array_str", "[x]", "raw_preserved", None),
        ("geopoint", [1, 2], "raw_preserved", None),
        ("geopolygon", [[1, 2]], "raw_preserved", None),
        ("hierarchy", {"x": 1}, "raw_preserved", None),
        ("tree_str", ["x"], "raw_preserved", None),
        ("tree_int", [1], "raw_preserved", None),
        ("tree_float", [1.5], "raw_preserved", None),
        ("markup", "<b>x</b>", "raw_preserved", None),
        ("heatmap", {"x": 1}, "raw_preserved", None),
        ("unsupported", "x", "unsupported", None),
        ("string", None, "null", None),
    ],
)
def test_all_declared_types_are_parsed_or_safely_preserved(
    field_type: str, value: object, status: str, normalized: object
) -> None:
    result = normalize_dataset_value(value, field_type)
    assert result["parse_status"] == status
    assert result["normalized"] == normalized
    assert result["raw"] == value


def test_positional_rows_are_mapped_only_by_exact_response_schema() -> None:
    result = normalize_dataset_data_response(
        {
            "schema": [
                {"guid": "date_guid", "name": "date", "type": "date"},
                {"guid": "value_guid", "name": "value", "type": "float"},
            ],
            "rows": [["2026-08-27", "4.5"]],
        },
        request_hash="a" * 64,
        observed_at="2026-08-27T00:00:00Z",
    )
    assert result["plain_rows"] == [{"date_guid": "2026-08-27", "value_guid": 4.5}]
    assert result["typed_rows"][0]["value_guid"]["declared_type"] == "float"


@pytest.mark.parametrize(
    "response",
    [
        {"schema": [{"guid": "dup"}, {"guid": "dup"}], "rows": [[1, 2]]},
        {"schema": [{"guid": "one"}, {"guid": "two"}], "rows": [[1]]},
    ],
)
def test_duplicate_guid_and_positional_mismatch_fail_closed(response: dict) -> None:
    with pytest.raises(ValueError):
        normalize_dataset_data_response(response, request_hash="a" * 64, observed_at="now")


def test_schema_drift_between_pages_fails_closed() -> None:
    with pytest.raises(ValueError, match="changed between pages"):
        normalize_dataset_data_response(
            {"schema": [{"guid": "new", "type": "string"}], "rows": []},
            request_hash="a" * 64,
            observed_at="now",
            expected_schema=[{"guid": "old", "type": "string"}],
        )
