import tempfile
import unittest
from pathlib import Path


class NegativeRequirementLedgerTests(unittest.TestCase):
    def test_user_decision_records_sanitized_negative_requirement(self):
        from datalens_dev_mcp.pipeline.requirements_workspace import update_user_decision

        with tempfile.TemporaryDirectory() as tmp:
            result = update_user_decision(
                tmp,
                decision_text="Do not show previous period delta or previous value.",
                decision_id="DEC-no-prev",
            )
            user_decisions = (Path(tmp) / "requirements" / "user_decisions.md").read_text(encoding="utf-8")

            self.assertEqual(len(result["negative_requirements"]), 1)
            self.assertIn("implicit_period_comparison", result["negative_requirements"][0]["forbidden_concepts"])
            self.assertIn("scan_surfaces", result["negative_requirements"][0])
            self.assertEqual(result["negative_requirements"][0]["severity"], "error")
            self.assertIn("negative requirement recorded", user_decisions)
            self.assertNotIn("Do not show previous period", user_decisions)

    def test_negative_requirement_drift_scans_generated_outputs(self):
        from datalens_dev_mcp.pipeline.negative_requirements import (
            record_negative_requirements,
            validate_no_negative_requirement_drift,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_negative_requirements(root, "Do not show previous period delta.", decision_id="DEC")
            (root / "dashboard" / "widget").mkdir(parents=True)
            (root / "dashboard" / "widget" / "prepare.js").write_text(
                "module.exports = {previous_value: 10};\n",
                encoding="utf-8",
            )

            result = validate_no_negative_requirement_drift(root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["findings"][0]["token"], "previous_value")


if __name__ == "__main__":
    unittest.main()
