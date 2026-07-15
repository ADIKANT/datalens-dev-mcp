import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SanitizationPolicyTests(unittest.TestCase):
    def test_policy_lists_local_placeholders_and_preserves_functionality(self):
        policy = ROOT / "docs" / "security" / "sanitization_policy.md"
        text = policy.read_text(encoding="utf-8")

        for placeholder in (
            "<DL_WORKBOOK_ID>",
            "<DL_DASHBOARD_ID>",
            "<DL_CHART_ID>",
            "<DL_DATASET_ID>",
            "<DL_CONNECTION_ID>",
            "<DL_TOKEN>",
            "<ORG_INTERNAL_URL>",
            "<INTERNAL_TABLE_NAME>",
            "<USER_EMAIL>",
        ):
            self.assertIn(placeholder, text)
        self.assertIn("Do not remove DataLens API method names", text)
        self.assertIn("unknown, needs manual review", text)

    def test_public_policies_and_local_scanner_enforce_material_boundary(self):
        policy = (ROOT / "docs" / "security" / "sanitization_policy.md").read_text(encoding="utf-8")
        materials_policy = (ROOT / "docs" / "materials_policy.md").read_text(encoding="utf-8")
        scanner = (ROOT / "scripts" / "scan_sensitive_artifacts.py").read_text(encoding="utf-8")

        self.assertIn("PDFs, screenshots, course materials", policy)
        self.assertIn("must not depend on ignored materials at runtime", policy)
        self.assertIn("third-party books, paid courses", materials_policy)
        self.assertIn("security_validator import scan_path", scanner)
        self.assertIn("scan_path(root)", scanner)


if __name__ == "__main__":
    unittest.main()
