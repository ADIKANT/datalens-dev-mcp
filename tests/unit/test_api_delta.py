import json
import unittest
from pathlib import Path

from datalens_dev_mcp.pipeline.api_delta import classify_api_delta, sha256_json


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "openapi" / "95-to-96"


def snapshot_from_fixture(name: str) -> dict:
    fixture = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    count = int(fixture["operation_count"])
    existing_count = count - (1 if fixture.get("added_operation") else 0)
    operations = {}
    for index in range(existing_count):
        operation = f"{fixture['operation_prefix']}{index + 1:03d}"
        operations[operation] = {
            "operation": operation,
            "path": f"/rpc/{operation}",
            "http_method": "POST",
            "security": [["IAM token"], ["Organization ID"]],
            "request_required": [],
            "request_schema_hash": "request",
            "response_schema_hash": "response",
            "docs_ref": fixture["docs_ref_template"].format(operation=operation),
            "experimental": False,
        }
    added = fixture.get("added_operation")
    if added:
        operations[added] = {
            "operation": added,
            "path": f"/rpc/{added}",
            "http_method": "POST",
            "security": [["IAM token"], ["Organization ID"]],
            "request_required": ["columns", "datasetId"],
            "request_schema_hash": "dataset-request",
            "response_schema_hash": "dataset-response",
            "docs_ref": fixture["docs_ref_template"].format(operation=added),
            "experimental": True,
        }
    schemas = {f"Schema{index + 1:03d}": f"hash-{index + 1:03d}" for index in range(fixture["schema_count"])}
    payload = {"openapi_version": "3.1.0", "operations": operations, "schemas": schemas}
    return {**payload, "snapshot_hash": sha256_json(payload)}


class ApiDeltaTests(unittest.TestCase):
    def test_95_to_96_addition_is_non_breaking_and_typed(self):
        report = classify_api_delta(
            snapshot_from_fixture("baseline.json"),
            snapshot_from_fixture("candidate.json"),
            support_classification={"getDatasetData": "typed_supported"},
        )

        self.assertEqual(report["added_operations"], ["getDatasetData"])
        self.assertEqual(report["removed_operations"], [])
        self.assertEqual(report["support_classification"]["getDatasetData"], "typed_supported")
        self.assertFalse(report["breaking"])

    def test_removal_and_required_request_change_are_breaking(self):
        baseline = snapshot_from_fixture("baseline.json")
        candidate = json.loads(json.dumps(baseline))
        removed = sorted(candidate["operations"])[0]
        candidate["operations"].pop(removed)
        changed = sorted(candidate["operations"])[0]
        candidate["operations"][changed]["request_required"] = ["newRequiredField"]
        candidate["snapshot_hash"] = sha256_json({key: value for key, value in candidate.items() if key != "snapshot_hash"})

        report = classify_api_delta(baseline, candidate)

        self.assertEqual(report["removed_operations"], [removed])
        self.assertTrue(report["breaking"])
        self.assertEqual(report["breaking_changes"][0]["changed_fields"], ["request_required"])

    def test_docs_relocation_is_advisory_and_replay_is_stable(self):
        baseline = snapshot_from_fixture("baseline.json")
        candidate = json.loads(json.dumps(baseline))
        operation = sorted(candidate["operations"])[0]
        candidate["operations"][operation]["docs_ref"] = f"datalens/api-ref/Data/rpc{operation}-post.md"
        candidate["snapshot_hash"] = sha256_json({key: value for key, value in candidate.items() if key != "snapshot_hash"})

        first = classify_api_delta(baseline, candidate)
        second = classify_api_delta(baseline, candidate)

        self.assertEqual(first, second)
        self.assertEqual(first["changed_operations"], [])
        self.assertEqual(first["relocated_docs"][0]["operation"], operation)
        self.assertFalse(first["breaking"])


if __name__ == "__main__":
    unittest.main()
