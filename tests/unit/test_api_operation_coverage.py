import importlib.util
import json
import unittest
from pathlib import Path

from datalens_dev_mcp.api.methods import list_methods
from datalens_dev_mcp.mcp.tools.rpc import dl_list_api_methods


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "validate_api_contract_coverage.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_api_contract_coverage", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ApiOperationCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()
        cls.policy = json.loads((ROOT / "config" / "datalens_api_operation_policy.json").read_text(encoding="utf-8"))

    def test_strict_validator_accepts_current_policy_and_fixtures(self):
        report = self.validator.validate(strict=True)

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["checked"]["operation_count"], 91)
        self.assertEqual(report["checked"]["path_count"], 91)
        self.assertEqual(report["checked"]["fixture_count"], 91)

    def test_every_operation_has_stable_status_owner_and_fixture(self):
        records = self.policy["operations"]

        self.assertEqual(len(records), 91)
        self.assertEqual(len({record["operation_id"] for record in records}), 91)
        self.assertEqual(len({record["path"] for record in records}), 91)
        for record in records:
            self.assertIn(record["status"], self.policy["status_enum"])
            self.assertTrue(record["owning_mcp_tool"])
            self.assertTrue((ROOT / record["fixture_path"]).is_file(), record["fixture_path"])
            self.assertTrue(record["live_probe_policy"])
            if record["status"] in {"readonly_reference", "unsupported_explicit"}:
                self.assertTrue(record["unavailable_response"])

    def test_runtime_api_method_list_is_equivalent_to_policy_catalog(self):
        runtime_names = {item.name for item in list_methods(include_guarded_writes=True)}
        policy_names = {record["method_name"] for record in self.policy["operations"]}
        listed = dl_list_api_methods(include_guarded_writes=True, limit=200)

        self.assertTrue(listed["ok"])
        self.assertEqual(runtime_names, policy_names)
        self.assertEqual(listed["method_count"], 91)

    def test_entry_lock_operations_are_known_but_fail_closed(self):
        by_method = {record["method_name"]: record for record in self.policy["operations"]}

        for method in ("createEntryLock", "extendEntryLock", "deleteEntryLock"):
            with self.subTest(method=method):
                self.assertEqual(by_method[method]["status"], "unsupported_explicit")
                self.assertEqual(by_method[method]["owning_mcp_tool"], "explicit_unavailable_method_spec")


if __name__ == "__main__":
    unittest.main()
