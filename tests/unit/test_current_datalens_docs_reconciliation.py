import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "validate_current_datalens_docs_reconciliation.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_current_datalens_docs_reconciliation", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CurrentDataLensDocsReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()
        try:
            cls.corpus_root = cls.validator.resolve_corpus_root()
        except FileNotFoundError as exc:
            raise unittest.SkipTest(str(exc)) from exc
        cls.policy = json.loads((ROOT / "config" / "datalens_docs_feature_policy.json").read_text(encoding="utf-8"))

    def test_strict_validator_accepts_current_corpus(self):
        report = self.validator.validate(self.corpus_root, strict=True)

        self.assertTrue(report["ok"], report["issues"])
        self.assertEqual(report["checked"]["pages"], 651)
        self.assertEqual(report["checked"]["chunks"], 4999)
        self.assertEqual(report["checked"]["assets"], 886)
        self.assertEqual(report["checked"]["new_pages"], 3)
        self.assertEqual(report["checked"]["openapi_operations"], 88)
        self.assertEqual(report["checked"]["openapi_paths"], 88)

    def test_required_clusters_and_new_pages_are_explicit(self):
        cluster_ids = {item["id"] for item in self.policy["clusters"]}

        self.assertEqual(set(self.validator.REQUIRED_CLUSTER_IDS) - cluster_ids, set())
        self.assertEqual(len(self.policy["covered_new_page_urls"]), 3)
        for url in self.policy["covered_new_page_urls"]:
            self.assertIn("/datalens/", url)

    def test_forbidden_or_non_runtime_docs_are_classified_explicitly(self):
        clusters = {item["id"]: item for item in self.policy["clusters"]}

        self.assertEqual(clusters["editor_widgets_gravity_ui"]["classification"], "unsupported_explicit")
        self.assertEqual(clusters["dashboard_ai_reference_tab"]["classification"], "unsupported_explicit")
        self.assertEqual(clusters["dashboard_ai_widget"]["classification"], "unsupported_explicit")
        self.assertEqual(clusters["chart_inspector"]["classification"], "import_only")
        self.assertIn("No Gravity UI chart creation route is added", clusters["editor_widgets_gravity_ui"]["runtime_contract"])

    def test_zero_delta_snapshot_cannot_replace_historical_applied_delta(self):
        reports = self.validator.load_update_reports(self.corpus_root)
        policy = self.validator.build_policy(self.corpus_root)

        self.assertEqual(reports["snapshot_summary"]["docs"]["changed_count"], 0)
        self.assertEqual(reports["snapshot_summary"]["docs"]["new_count"], 0)
        self.assertEqual(reports["delta_summary"]["docs"]["changed_count"], 12)
        self.assertEqual(reports["delta_summary"]["docs"]["new_count"], 3)
        self.assertEqual(policy["expected_counts"]["docs_changed_pages"], 12)
        self.assertEqual(policy["expected_counts"]["docs_new_pages"], 3)
        self.assertEqual(policy["source"]["applied_delta_report"], "reports/update_report_delta_2026-07-13.md")
        self.assertEqual(policy["source"]["openapi_sha256"], self.validator.EXPECTED_OPENAPI_SHA256)


if __name__ == "__main__":
    unittest.main()
