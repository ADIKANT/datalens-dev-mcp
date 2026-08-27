from __future__ import annotations

import unittest

from tests.regression.policy_matrix._corpus import load_cases


REQUIRED_VISUAL = {
    "period_selector_first", "exact_selector_rows_order_heights", "selector_block_not_too_tall",
    "light_dark_support", "opaque_sticky_header", "no_phantom_legend_statuses",
    "indicator_visible_partial_data", "expected_empty_state", "business_readable_columns",
    "no_redundant_technical_columns", "hints_lineage_na_reasons", "correct_pagination",
    "display_formatting_preserves_raw_semantics",
}


class VisualCorrectionRegressionTests(unittest.TestCase):
    def test_all_required_visual_corrections_are_explicit_contracts(self):
        cases = [case for case in load_cases() if case["category"] == "visual"]
        scenarios = {case["scenario"] for case in cases}
        self.assertEqual(REQUIRED_VISUAL - scenarios, set())
        for case in cases:
            self.assertIn(case["scenario"], case["visual_checks"])
            self.assertIn("save_readback_before_publish", case["expected_invariants"])

    def test_display_formatting_never_changes_raw_semantics(self):
        cases = [case for case in load_cases() if case["scenario"] == "display_formatting_preserves_raw_semantics"]
        self.assertEqual(len(cases), 2)
        self.assertTrue(all(case["expected_route"] == "wizard_native" for case in cases))
