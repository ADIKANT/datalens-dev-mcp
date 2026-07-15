import unittest


class LayoutIntentRecordTests(unittest.TestCase):
    def test_one_scroll_plus_quality_tab_intent(self):
        from datalens_dev_mcp.pipeline.layout_intent import build_layout_intent_record, validate_layout_against_intent

        intent = build_layout_intent_record("Need one scrollable main page plus quality tab")
        result = validate_layout_against_intent(
            intent,
            {"tabs": [{"id": "main_scroll", "sections": ["overview"]}, {"id": "data_quality", "sections": ["data_quality"]}]},
        )

        self.assertEqual([tab.tab_id for tab in intent.intended_tabs], ["main_scroll", "data_quality"])
        self.assertTrue(result["ok"], result["findings"])

    def test_six_tabs_allowed_when_specified(self):
        from datalens_dev_mcp.pipeline.layout_intent import build_layout_intent_record

        intent = build_layout_intent_record("Accepted spec asks for six tabs")

        self.assertEqual(len(intent.intended_tabs), 6)
        self.assertEqual(intent.conflict_status, "none")


if __name__ == "__main__":
    unittest.main()
