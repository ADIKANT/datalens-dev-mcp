import unittest


class ExplicitJsRequestRemainsJsTests(unittest.TestCase):
    def test_explicit_js_request_selects_advanced_editor(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v3

        decision = select_route_v3("Собери на JS")

        self.assertEqual(decision.status, "approved")
        self.assertEqual(decision.selected_route, "editor_advanced")


if __name__ == "__main__":
    unittest.main()
