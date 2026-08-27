from __future__ import annotations

import json
import unittest

from jsonschema import Draft202012Validator

from datalens_dev_mcp.runtime_resources import resource_json
from datalens_dev_mcp.serialization import stable_sha256
from tests.regression.policy_matrix._corpus import CORPUS_ROOT, load_cases


class SessionContractRegressionTests(unittest.TestCase):
    def test_corpus_has_at_least_eighty_schema_valid_sanitized_cases(self):
        schema = resource_json("schemas/session-regression-case.schema.json")
        validator = Draft202012Validator(schema)
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 80)
        self.assertEqual(len({case["case_id"] for case in cases}), len(cases))
        for case in cases:
            self.assertEqual(list(validator.iter_errors(case)), [], case["case_id"])
            expected_hash = case.pop("contract_sha256")
            self.assertEqual(expected_hash, stable_sha256(case), case["case_id"])
            case["contract_sha256"] = expected_hash

    def test_report_is_aggregate_only_and_matches_case_count(self):
        report = json.loads((CORPUS_ROOT / "corpus-report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["source_session_count"], 195)
        self.assertEqual(report["scenario_count"], len(load_cases()))
        self.assertEqual(report["private_literal_leakage"], 0)
        self.assertNotIn("source_path", report)
        self.assertNotIn("source_sha256", report)
