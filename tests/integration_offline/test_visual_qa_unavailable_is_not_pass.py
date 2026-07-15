import unittest


class VisualQaUnavailableIsNotPassTests(unittest.TestCase):
    def test_unavailable_visual_qa_cannot_be_pass(self):
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_readback_quality

        result = validate_visual_readback_quality({"visual_qa_status": "unavailable_external_blocker", "visual_qa_pass": True})

        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
