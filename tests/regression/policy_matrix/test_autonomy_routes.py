from __future__ import annotations

import unittest

from tests.regression.policy_matrix._corpus import load_cases


class AutonomyRouteRegressionTests(unittest.TestCase):
    def test_no_browser_and_browser_required_are_not_inferred(self):
        cases = load_cases()
        forbidden = [case for case in cases if case["scenario"] == "no_browser_explicit"]
        required = [case for case in cases if case["scenario"] == "browser_required_explicit"]
        self.assertTrue(forbidden and required)
        self.assertTrue(all(case["expected_calls"]["browser"] == 0 for case in forbidden))
        self.assertTrue(all(case["expected_calls"]["browser"] == 1 for case in required))
        self.assertTrue(all(case["expected_task_contract"]["browser_policy"] == "forbidden" for case in forbidden))
        self.assertTrue(all(case["expected_task_contract"]["browser_policy"] == "required" for case in required))

    def test_exact_style_preserves_runtime_and_technology(self):
        cases = [case for case in load_cases() if case["scenario"] == "exact_reference_style"]
        self.assertTrue(cases)
        for case in cases:
            self.assertEqual(case["expected_route"], "editor_advanced")
            self.assertIn("protected_runtime_hash_unchanged", case["expected_invariants"])
            self.assertIn("technology_unchanged", case["expected_invariants"])

    def test_no_ql_fallback_and_no_unnecessary_questions(self):
        cases = load_cases()
        self.assertTrue(all(case["expected_task_contract"]["route_policy"]["ql_allowed"] is False for case in cases))
        self.assertTrue(all(case["expected_calls"]["questions"] == 0 for case in cases))
        self.assertTrue(all(case["expected_calls"]["high_level_budget"] <= 20 for case in cases))
