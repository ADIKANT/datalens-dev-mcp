import unittest


class ExplicitWizardRequestNotSilentlyJsTests(unittest.TestCase):
    def test_explicit_wizard_request_returns_supported_route_or_blocker(self):
        from datalens_dev_mcp.pipeline.route_selection_policy import select_route_v3

        decision = select_route_v3("Build this through Wizard")

        self.assertEqual(decision.status, "approved")
        self.assertEqual(decision.selected_route, "wizard_native")
        self.assertEqual(decision.selection_origin, "explicit_user_request")
        self.assertTrue(decision.docs_api_evidence)
        self.assertFalse(decision.forbidden_fallback)
        self.assertNotEqual(decision.selected_route, "editor_advanced")


if __name__ == "__main__":
    unittest.main()
