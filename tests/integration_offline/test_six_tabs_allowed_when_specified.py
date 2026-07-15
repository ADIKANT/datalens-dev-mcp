import unittest


class SixTabsAllowedWhenSpecifiedTests(unittest.TestCase):
    def test_six_tabs_is_allowed_when_explicit(self):
        from datalens_dev_mcp.pipeline.layout_intent import build_layout_intent_record

        intent = build_layout_intent_record("Accepted prompt explicitly asks for six tabs")

        self.assertEqual(len(intent.intended_tabs), 6)


if __name__ == "__main__":
    unittest.main()
