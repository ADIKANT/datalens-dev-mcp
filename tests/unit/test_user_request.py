from __future__ import annotations

import unittest


class UserRequestContractTests(unittest.TestCase):
    def test_browser_preference_is_first_class(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        forbidden = normalize_user_request("update chart:synthetic_chart_user; do not use the browser")
        required = normalize_user_request("update chart:synthetic_chart_user and verify in the browser")

        self.assertEqual(forbidden.browser_preference, "forbidden")
        self.assertEqual(required.browser_preference, "required")

    def test_explicit_corrections_are_retained_as_constraints(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request(
            "update chart:synthetic_chart_user\n"
            "do not change layout\n"
            "preserve this JS format"
        )

        self.assertEqual(request.explicit_constraints, ["do not change layout", "preserve this JS format"])

    def test_partial_content_removal_is_update_not_object_delete(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request("remove the legend from chart:synthetic_chart_user")

        self.assertEqual(request.task_intent, "update")
        self.assertEqual(request.destructive_actions, [])


if __name__ == "__main__":
    unittest.main()
