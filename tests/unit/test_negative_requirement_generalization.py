import unittest


class NegativeRequirementGeneralizationTests(unittest.TestCase):
    def test_detector_generalizes_required_negative_phrases(self):
        from datalens_dev_mcp.pipeline.negative_requirements import detect_negative_requirements

        cases = [
            ("Do not show previous period delta or previous value.", "implicit_period_comparison"),
            ("Do not use pie for this share chart.", "chart_family_pie_donut"),
            ("Remove legend from the monthly trend.", "legend"),
            ("Only table for this output.", "table_only_output"),
            ("Do not use red/green semantic colors.", "red_green_palette"),
            ("Убери легенду и не используй красный зеленый цвет.", "legend"),
        ]
        for text, expected_concept in cases:
            with self.subTest(text=text):
                detected = [item.to_dict() for item in detect_negative_requirements(text, decision_id="DEC")]
                concepts = {concept for item in detected for concept in item["forbidden_concepts"]}

                self.assertIn(expected_concept, concepts)
                self.assertTrue(all(item["scan_surfaces"] for item in detected))
                self.assertTrue(all(item["severity"] == "error" for item in detected))

    def test_table_only_forbids_non_table_chart_families(self):
        from datalens_dev_mcp.pipeline.negative_requirements import detect_negative_requirements

        detected = detect_negative_requirements("Оставь только таблицу.", decision_id="DEC")
        table_only = detected[0].to_dict()

        self.assertEqual(table_only["forbidden_concepts"], ["table_only_output"])
        self.assertIn("horizontal_bar", table_only["forbidden_chart_families"])
        self.assertIn("pie", table_only["forbidden_chart_families"])


if __name__ == "__main__":
    unittest.main()
