import tempfile
import unittest

from datalens_dev_mcp.pipeline.data_assertions import evaluate_data_assertions
from datalens_dev_mcp.pipeline.data_proof_planner import build_data_proof_plan
from datalens_dev_mcp.pipeline.data_sample_budget import DataSampleBudget, enforce_sample_budget
from datalens_dev_mcp.pipeline.selector_semantics import serialize_selector_value, validate_selector_semantics


SCHEMA = [
    {"guid": "id", "name": "ID", "type": "integer", "unique": True},
    {"guid": "date", "name": "Date", "type": "date"},
    {"guid": "amount", "name": "Amount", "type": "float"},
    {"guid": "email", "name": "Email", "type": "string"},
]
ROWS = [
    {"id": 1, "date": "2026-08-25", "amount": 10.0, "email": "one@example.test"},
    {"id": 2, "date": "2026-08-26", "amount": 20.0, "email": "two@example.test"},
]


class DataAssertionTests(unittest.TestCase):
    def test_no_null_unique_range_and_date_assertions(self):
        result = evaluate_data_assertions(
            assertions=[
                {"kind": "unique_key", "fields": ["id"]},
                {"kind": "no_nulls", "fields": ["id", "date"]},
                {"kind": "numeric_range", "field": "amount", "min": 0, "max": 30},
                {"kind": "min_max_date", "field": "date", "min": "2026-08-25", "max": "2026-08-26"},
            ],
            schema=SCHEMA,
            rows=ROWS,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["passed"], 4)

    def test_expected_empty_passes_and_unexpected_not_empty_fails(self):
        expected = evaluate_data_assertions(assertions=[{"kind": "expected_empty"}], schema=SCHEMA, rows=[])
        unexpected = evaluate_data_assertions(assertions=[{"kind": "not_empty"}], schema=SCHEMA, rows=[])
        self.assertTrue(expected["ok"])
        self.assertFalse(unexpected["ok"])

    def test_pagination_and_total_order_are_explicit(self):
        result = evaluate_data_assertions(
            assertions=[
                {"kind": "pagination_complete"},
                {
                    "kind": "sort_total_order",
                    "sort": [{"guid": "date", "direction": "asc"}, {"guid": "id", "direction": "asc"}],
                    "tie_breaker_fields": ["id"],
                },
            ],
            schema=SCHEMA,
            rows=ROWS,
            paging={"complete": True},
        )
        self.assertTrue(result["ok"])
        reversed_result = evaluate_data_assertions(
            assertions=[
                {
                    "kind": "sort_total_order",
                    "sort": [{"guid": "id", "direction": "asc"}],
                    "tie_breaker_fields": ["id"],
                }
            ],
            schema=SCHEMA,
            rows=list(reversed(ROWS)),
        )
        self.assertFalse(reversed_result["ok"])

    def test_duplicate_sort_values_without_tie_breaker_are_blocked(self):
        spec = {
            "dataset_id": "dataset",
            "columns": ["date"],
            "sort": [{"guid": "date", "direction": "asc"}],
            "sample": {"limit": 2, "max_pages": 2},
            "assertions": [{"kind": "not_empty"}],
        }
        result = build_data_proof_plan(spec, dataset_fields=SCHEMA)
        self.assertFalse(result["ok"])
        self.assertTrue(any("tie" in issue and "breaker" in issue for issue in result["issues"]))

    def test_sample_budget_is_enforced_before_any_data_request(self):
        spec = {
            "dataset_id": "dataset",
            "columns": ["id", "date"],
            "sort": [{"guid": "id", "direction": "asc"}],
            "sample": {"limit": 100, "max_pages": 10},
            "budget": {"max_rows": 500, "max_cells": 1_000},
            "assertions": [{"kind": "not_empty"}],
        }
        result = build_data_proof_plan(spec, dataset_fields=SCHEMA)
        self.assertFalse(result["ok"])
        self.assertTrue(any("row budget" in issue for issue in result["issues"]))

    def test_selector_empty_same_field_and_scalar_serialization(self):
        result = validate_selector_semantics(
            [{"field_guid": "id", "value": [], "empty_means_no_filter": True}],
            filters=[{"guid": "id", "operation": "eq", "values": [1]}],
        )
        self.assertTrue(result["ok"])
        self.assertTrue(any(item["rule"] == "same_field_selector_overrides_internal_filter" for item in result["issues"]))
        self.assertEqual(serialize_selector_value(True), "true")
        self.assertEqual(serialize_selector_value(2), "2")

    def test_sensitive_examples_are_redacted_and_raw_values_unchanged(self):
        original = [dict(row) for row in ROWS]
        result = enforce_sample_budget(ROWS, schema=SCHEMA)
        self.assertEqual(result["redacted_examples"][0]["email"], "[REDACTED]")
        self.assertEqual(ROWS, original)

    def test_large_sample_is_not_inlined_past_budget(self):
        rows = [{"id": index, "value": "x" * 100} for index in range(100)]
        result = enforce_sample_budget(
            rows,
            schema=[{"guid": "id", "name": "ID"}, {"guid": "value", "name": "Value"}],
            budget=DataSampleBudget(max_rows=10, max_cells=1000, max_bytes=1_000_000, inline_examples=2),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["redacted_examples"]), 2)
        self.assertNotIn("rows", result)


if __name__ == "__main__":
    unittest.main()
