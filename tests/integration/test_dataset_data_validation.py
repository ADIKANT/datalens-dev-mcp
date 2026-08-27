import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.pipeline.data_proof_planner import prove_dataset_data


FIELDS = [
    {"guid": "id", "name": "ID", "type": "integer", "unique": True},
    {"guid": "date", "name": "Date", "type": "date"},
    {"guid": "amount", "name": "Amount", "type": "float"},
    {"guid": "email", "name": "Email", "type": "string", "sensitive": True},
]
SCHEMA = [{key: field[key] for key in ("guid", "name", "type")} for field in FIELDS]


class PagingClient:
    def __init__(self, *, fail_data=False, empty=False):
        self.fail_data = fail_data
        self.empty = empty
        self.calls = []

    def rpc_readonly(self, method, payload):
        self.calls.append((method, dict(payload)))
        if method == "getDataset":
            return {"fields": FIELDS}
        if method == "getDatasetData":
            if self.fail_data:
                raise RuntimeError("experimental endpoint unavailable")
            if self.empty:
                return {"schema": SCHEMA, "rows": []}
            offset = payload["offset"]
            pages = {
                0: [[1, "2026-08-25", 10, "one@example.test"], [2, "2026-08-25", 20, "two@example.test"]],
                2: [[3, "2026-08-26", 30, "three@example.test"]],
            }
            return {"schema": SCHEMA, "rows": pages.get(offset, [])}
        raise AssertionError(method)


def spec(*, expected_empty=False):
    assertions = (
        [{"kind": "expected_empty"}, {"kind": "pagination_complete"}]
        if expected_empty
        else [
            {"kind": "not_empty"},
            {"kind": "unique_key", "fields": ["id"]},
            {"kind": "non_negative", "field": "amount"},
            {"kind": "pagination_complete"},
        ]
    )
    return {
        "dataset_id": "dataset",
        "columns": ["id", "date", "amount", "email"],
        "sort": [{"guid": "date", "direction": "asc"}, {"guid": "id", "direction": "asc"}],
        "tie_breaker_fields": ["id"],
        "sample": {"limit": 2, "max_pages": 3},
        "assertions": assertions,
    }


class DatasetDataValidationIntegrationTests(unittest.TestCase):
    def test_deterministic_pages_are_verified_and_full_sample_externalized(self):
        client = PagingClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = prove_dataset_data(spec(), project_root=tmp, client=client)
            artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
            summary = json.loads((Path(tmp) / "artifacts" / "data_assertion_result.json").read_text(encoding="utf-8"))
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["live_data_verified"])
        self.assertEqual(result["row_count"], 3)
        self.assertTrue(result["paging"]["complete"])
        self.assertFalse(result["raw_rows_inline"])
        self.assertEqual(len(artifact["rows"]), 3)
        self.assertNotIn("rows", summary)
        self.assertEqual(summary["sample_evidence"]["redacted_examples"][0]["email"], "[REDACTED]")
        self.assertEqual(client.calls[0], ("getDataset", {"datasetId": "dataset"}))

    def test_expected_empty_is_a_meaningful_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = prove_dataset_data(spec(expected_empty=True), project_root=tmp, client=PagingClient(empty=True))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["unexpected_empty_diagnostics"], [])

    def test_unexpected_empty_has_business_diagnostics(self):
        value = spec()
        value["assertions"] = [{"kind": "not_empty"}]
        with tempfile.TemporaryDirectory() as tmp:
            result = prove_dataset_data(value, project_root=tmp, client=PagingClient(empty=True))
        self.assertFalse(result["ok"])
        checks = {item["check"] for item in result["unexpected_empty_diagnostics"]}
        self.assertTrue({"filters", "params", "date_window", "source_availability", "branch"}.issubset(checks))

    def test_experimental_failure_falls_back_without_inventing_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = prove_dataset_data(spec(), project_root=tmp, client=PagingClient(fail_data=True))
        self.assertFalse(result["ok"])
        self.assertFalse(result["live_data_verified"])
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["proof_level"], "source_static")
        self.assertEqual(result["fallback_kind"], "dataset_schema_only")
        self.assertTrue(all(item["status"] == "insufficient_evidence" for item in result["results"]))


if __name__ == "__main__":
    unittest.main()
