import tempfile
import unittest
from pathlib import Path


class NegativeRequirementEndToEndTests(unittest.TestCase):
    def test_user_decision_ledger_drives_chart_decision_and_generated_drift_scan(self):
        from datalens_dev_mcp.pipeline.negative_requirements import (
            load_negative_requirement_ledger,
            validate_no_negative_requirement_drift,
        )
        from datalens_dev_mcp.pipeline.requirements_workspace import update_user_decision
        from datalens_dev_mcp.pipeline.visual_decisions import decide_chart, validate_chart_decision_record

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            update_user_decision(
                root,
                decision_text="Do not use pie. Remove legend. Do not use red/green semantic colors.",
                decision_id="DEC-negative",
            )
            ledger = load_negative_requirement_ledger(root)
            concepts = {concept for item in ledger for concept in item["forbidden_concepts"]}

            self.assertEqual(
                concepts,
                {"chart_family_pie_donut", "legend", "red_green_palette"},
            )

            decision = decide_chart(
                chart_id="share_no_pie",
                business_question="Share of orders by status from the source dataset.",
                audience=["ops owner"],
                requested_family="pie",
                negative_requirements=ledger,
            )
            payload = decision.to_dict()

            self.assertEqual(decision.selected_family, "horizontal_bar")
            self.assertFalse(decision.legend_spec["show"])
            self.assertEqual(decision.color_spec["positive"], "")
            self.assertTrue(validate_chart_decision_record(payload)["ok"])

            (root / "dashboard" / "share_no_pie").mkdir(parents=True)
            (root / "dashboard" / "share_no_pie" / "prepare.js").write_text(
                "const legend = rows.map((row) => row.label).join(',');\n",
                encoding="utf-8",
            )
            drift = validate_no_negative_requirement_drift(root)

            self.assertFalse(drift["ok"])
            self.assertEqual(drift["findings"][0]["path"], "dashboard/share_no_pie/prepare.js")
            self.assertEqual(drift["findings"][0]["token"], "legend")


if __name__ == "__main__":
    unittest.main()
