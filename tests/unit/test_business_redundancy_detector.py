import unittest


class BusinessRedundancyDetectorTests(unittest.TestCase):
    def test_adjacent_same_metric_question_is_redundant(self):
        from datalens_dev_mcp.pipeline.layout_intent import detect_business_redundancy

        result = detect_business_redundancy(
            [
                {"visual_id": "rcp_table", "metric": "cost", "dimension": "type", "business_question": "RCP balance"},
                {"visual_id": "rcp_chart", "metric": "cost", "dimension": "type", "business_question": "RCP balance"},
            ]
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["findings"][0]["rule"], "redundant_adjacent_visual")


if __name__ == "__main__":
    unittest.main()
