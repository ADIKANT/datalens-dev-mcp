import unittest


class VisualQualityGateTests(unittest.TestCase):
    def test_bar_chart_needs_labels_or_axes(self):
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

        result = validate_visual_quality_contract(
            {"family": "horizontal_bar", "labels": {"direct_labels": False}, "axes": {"show": False}, "gridlines": {"show": False}}
        )

        self.assertFalse(result.ok)
        self.assertIn("bar_chart_label_contract", {finding.rule for finding in result.findings})

    def test_visual_qa_unavailable_is_not_pass(self):
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_readback_quality

        result = validate_visual_readback_quality({"visual_qa_status": "unavailable_external_blocker", "visual_qa_pass": True})

        self.assertFalse(result.ok)
        self.assertIn("visual_qa_unavailable_marked_as_pass", {finding.rule for finding in result.findings})

    def test_generated_v2_spec_carries_responsive_and_value_semantics(self):
        from datalens_dev_mcp.editor.visual_spec import build_renderer_visual_spec
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

        spec = build_renderer_visual_spec(
            family="line_chart",
            route="editor_advanced",
            analytical_task="time_trend",
        ).to_dict()
        result = validate_visual_quality_contract(spec)

        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])
        self.assertEqual(spec["schema_version"], "2026-07-19.renderer_visual_spec.v2")
        self.assertEqual(spec["value_semantics"]["missing_label"], "N/A")
        self.assertTrue(spec["value_semantics"]["observed_zero_distinct_from_missing"])
        self.assertEqual(spec["formatting"]["axis_tick_strategy"], "nice_1_2_2_5_5_10")
        self.assertFalse(spec["responsive_layout"]["fixed_min_width"])
        self.assertTrue(spec["layout_contract"]["preserve_existing_geometry"])

    def test_v2_spec_blocks_future_zero_fill_and_fixed_min_width(self):
        from datalens_dev_mcp.editor.visual_spec import build_renderer_visual_spec
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

        spec = build_renderer_visual_spec(
            family="line_chart",
            route="editor_advanced",
            analytical_task="time_trend",
        ).to_dict()
        spec["value_semantics"]["future_periods"] = "zero_fill"
        spec["responsive_layout"]["fixed_min_width"] = True
        result = validate_visual_quality_contract(spec)
        rules = {finding.rule for finding in result.findings}

        self.assertFalse(result.ok)
        self.assertIn("future_period_zero_fill", rules)
        self.assertIn("fixed_desktop_min_width", rules)


if __name__ == "__main__":
    unittest.main()
