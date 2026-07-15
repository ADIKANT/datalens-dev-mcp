import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = ROOT / "scripts" / "check_docs_consistency.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_docs_consistency", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load docs consistency checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DocsConsistencyTests(unittest.TestCase):
    def test_active_docs_policy_vocabulary_has_no_contradictions(self):
        checker = load_checker()
        report = checker.run_checks()

        self.assertTrue(report.ok, "\n".join(report.issues))

    def test_public_onboarding_and_provenance_are_active_inputs(self):
        checker = load_checker()
        report = checker.run_checks()
        self.assertIn("docs/mcp/codex_connection.md", report.checked_files)
        self.assertIn("docs/README.md", report.checked_files)
        self.assertIn("docs/tools.md", report.checked_files)
        self.assertIn("docs/usage-flow.md", report.checked_files)
        self.assertIn("docs/sources.md", report.checked_files)
        self.assertIn("docs/source_provenance.md", report.checked_files)
        self.assertIn("THIRD_PARTY_NOTICES.md", report.checked_files)

    def test_readme_variants_are_scanned(self):
        checker = load_checker()
        report = checker.run_checks()
        checked = set(report.checked_files)

        self.assertIn("README.md", checked)
        self.assertIn("README_en.md", checked)
        self.assertTrue(report.ok, "\n".join(report.issues))


if __name__ == "__main__":
    unittest.main()
