import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.pipeline.dataset_preview import (
    compile_dataset_preview_request,
    preview_dataset_data,
    rows_to_typed_dicts,
)


FIELDS = [
    {"guid": "guid-id", "name": "ID", "type": "integer", "unique": True},
    {"guid": "guid-date", "name": "Date", "type": "date"},
    {"guid": "guid-active", "name": "Active", "type": "boolean"},
]


class FakeClient:
    def __init__(self):
        self.calls = []

    def rpc_readonly(self, method, payload):
        self.calls.append((method, dict(payload)))
        if method == "getDataset":
            return {"data": {"dataset": {"fields": FIELDS}}}
        if method == "getDatasetData":
            offset = payload.get("offset", 0)
            rows = [[1, "2026-08-26", "true"], [2, "2026-08-27", False]] if offset == 0 else []
            return {
                "schema": [
                    {"guid": "guid-id", "name": "ID", "type": "integer"},
                    {"guid": "guid-date", "name": "Date", "type": "date"},
                    {"guid": "guid-active", "name": "Active", "type": "boolean"},
                ],
                "rows": rows,
            }
        raise AssertionError(method)


class DatasetPreviewTests(unittest.TestCase):
    def test_offset_with_stable_sort_is_valid(self):
        result = compile_dataset_preview_request(
            dataset_id="dataset",
            columns=["guid-date", "guid-id"],
            dataset_fields=FIELDS,
            sort=[{"guid": "guid-date", "direction": "asc"}, {"guid": "guid-id", "direction": "asc"}],
            offset=100,
            max_pages=2,
            tie_breaker_fields=["guid-id"],
        )

        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(result["paging"]["deterministic"])

    def test_offset_without_sort_and_unknown_filter_operation_are_blocked(self):
        result = compile_dataset_preview_request(
            dataset_id="dataset",
            columns=["guid-id"],
            dataset_fields=FIELDS,
            filters=[{"guid": "guid-id", "operation": "mystery", "values": [1]}],
            offset=1,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(any("unsupported" in issue for issue in result["issues"]))
        self.assertTrue(any("offset" in issue for issue in result["issues"]))

    def test_sort_field_must_be_returned_and_paging_needs_tie_breaker(self):
        result = compile_dataset_preview_request(
            dataset_id="dataset",
            columns=["guid-date"],
            dataset_fields=[{**field, "unique": False} for field in FIELDS],
            sort=[{"guid": "guid-id", "direction": "asc"}],
            max_pages=2,
        )

        self.assertFalse(result["ok"])
        self.assertTrue(any("present in columns" in issue for issue in result["issues"]))
        self.assertTrue(any("tie-breaker" in issue for issue in result["issues"]))

    def test_schema_rows_are_converted_to_typed_guid_dictionaries(self):
        result = rows_to_typed_dicts(
            [
                {"guid": "guid-id", "type": "integer"},
                {"guid": "guid-active", "type": "boolean"},
            ],
            [["7", "false"]],
        )

        self.assertEqual(result, [{"guid-id": 7, "guid-active": False}])

    def test_full_result_is_externalized_and_inline_rows_are_bounded(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = preview_dataset_data(
                dataset_id="dataset",
                columns=["guid-id", "guid-date", "guid-active"],
                sort=[{"guid": "guid-id", "direction": "asc"}],
                tie_breaker_fields=["guid-id"],
                inline_row_limit=1,
                project_root=tmp,
                client=client,
            )
            artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertTrue(result["experimental"])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(len(result["rows"]), 1)
        self.assertTrue(result["truncated"])
        self.assertEqual(artifact["rows"][0]["guid-id"], 1)
        self.assertEqual([call[0] for call in client.calls], ["getDataset", "getDatasetData"])

    def test_unknown_tie_breaker_returns_one_specific_question(self):
        client = FakeClient()
        result = preview_dataset_data(
            dataset_id="dataset",
            columns=["guid-date"],
            sort=[{"guid": "guid-date", "direction": "asc"}],
            max_pages=2,
            dataset_readback={"fields": [{"guid": "guid-date", "name": "Date", "type": "date"}]},
            client=client,
        )

        self.assertFalse(result["ok"])
        self.assertIn("уникальный ключ", result["question"])
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
