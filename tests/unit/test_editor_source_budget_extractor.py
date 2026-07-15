import unittest


class EditorSourceBudgetExtractorTests(unittest.TestCase):
    def test_external_control_source_is_extracted_and_blocks_without_budget_evidence(self):
        from datalens_dev_mcp.pipeline.performance_budget import extract_editor_source_budget_evidence_v7

        evidence = extract_editor_source_budget_evidence_v7(
            {
                "entryId": "chart_qzy",
                "external_controls": [
                    {
                        "source_key": "periodData",
                        "consumer_type": "selector",
                        "sql": "select * from analytics.order_delivery_plan",
                    }
                ],
            }
        )

        self.assertEqual(evidence["sources"][0]["source_key"], "periodData")
        self.assertIn(evidence["sources"][0]["decision"], {"block", "insufficient_evidence"})
        self.assertTrue(evidence["blocked_reasons"])

    def test_bounded_deduped_source_passes_with_supplied_evidence(self):
        from datalens_dev_mcp.pipeline.performance_budget import extract_editor_source_budget_evidence_v7

        evidence = extract_editor_source_budget_evidence_v7(
            {
                "entryId": "chart_qzy",
                "external_controls": [
                    {
                        "source_key": "periodData",
                        "consumer_type": "selector",
                        "sql": (
                            "select order_id, week_start from analytics.order_delivery_plan "
                            "where week_start >= today() - 84 group by order_id, week_start"
                        ),
                    }
                ],
            },
            supplied_evidence=[
                {
                    "source_key": "periodData",
                    "physical_rows_before": 1_000_000,
                    "business_grain_rows_after": 250,
                    "bounded_in_sql": True,
                    "deduped_to_business_grain": True,
                }
            ],
        )

        self.assertIn(evidence["sources"][0]["decision"], {"pass", "warn"})
        self.assertEqual(evidence["blocked_reasons"], [])


if __name__ == "__main__":
    unittest.main()
