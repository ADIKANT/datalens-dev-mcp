import unittest


class OneScrollPlusQualityTabIntentTests(unittest.TestCase):
    def test_intent_controls_tab_count(self):
        from datalens_dev_mcp.pipeline.layout_intent import build_layout_intent_record

        intent = build_layout_intent_record("one scrollable main page plus data quality tab")

        self.assertEqual([tab.tab_id for tab in intent.intended_tabs], ["main_scroll", "data_quality"])


if __name__ == "__main__":
    unittest.main()
