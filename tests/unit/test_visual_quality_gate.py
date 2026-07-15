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


if __name__ == "__main__":
    unittest.main()
