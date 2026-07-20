import unittest


class SelectorContractTests(unittest.TestCase):
    def test_static_contract_normalizes_labels_values_and_defaults(self):
        from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract

        contract = normalize_selector_contract(
            family="single_select_dropdown",
            title="Ignored fallback",
            selector_contract={
                "param": "status",
                "label": "Status",
                "option_source": "static",
                "options": [
                    {"title": "All records", "value": "all"},
                    {"title": "Open records", "value": "open"},
                ],
                "default_values": ["all"],
                "reset_behavior": "initial",
            },
        )

        self.assertTrue(contract["ok"], contract["issues"])
        self.assertEqual(contract["param"], "status")
        self.assertEqual(
            contract["options"],
            [
                {"title": "All records", "value": "all"},
                {"title": "Open records", "value": "open"},
            ],
        )
        self.assertEqual(contract["default_values"], ["all"])

    def test_missing_contract_and_incomplete_explicit_contract_fail_closed(self):
        from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract

        missing = normalize_selector_contract(
            family="single_select_dropdown",
            title="Status",
            selector_contract=None,
        )
        incomplete = normalize_selector_contract(
            family="single_select_dropdown",
            title="Status fallback",
            selector_contract={
                "param": "status",
                "option_source": "static",
                "options": ["open"],
                "reset_behavior": "empty",
            },
        )

        self.assertFalse(missing["ok"])
        self.assertFalse(incomplete["ok"])
        self.assertIn("missing_selector_param", {issue["code"] for issue in missing["issues"]})
        self.assertIn("missing_selector_options", {issue["code"] for issue in missing["issues"]})
        self.assertIn("missing_selector_label", {issue["code"] for issue in incomplete["issues"]})

    def test_non_string_options_and_defaults_are_rejected(self):
        from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract

        contract = normalize_selector_contract(
            family="single_select_dropdown",
            title="Status",
            selector_contract={
                "param": "status",
                "label": "Status",
                "option_source": "static",
                "options": [{"title": "Open", "value": 1}],
                "default_values": [1],
                "reset_behavior": "initial",
            },
        )

        codes = {issue["code"] for issue in contract["issues"]}
        self.assertFalse(contract["ok"])
        self.assertIn("invalid_selector_option", codes)
        self.assertIn("invalid_default_values", codes)

    def test_paired_date_contract_is_valid_and_incomplete_or_duplicate_pair_is_rejected(self):
        from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract, selector_params

        valid = normalize_selector_contract(
            family="date_range_selector",
            title="Period",
            selector_contract={
                "param_from": "date_from",
                "param_to": "date_to",
                "label": "Period",
                "option_source": "none",
                "default_from": "2026-01-01",
                "default_to": "__relative_0d",
                "reset_behavior": "initial",
            },
        )
        incomplete = normalize_selector_contract(
            family="date_range_selector",
            title="Period",
            selector_contract={
                "param_from": "date_from",
                "label": "Period",
                "option_source": "none",
                "reset_behavior": "empty",
            },
        )
        duplicate = normalize_selector_contract(
            family="date_range_selector",
            title="Period",
            selector_contract={
                "param_from": "date",
                "param_to": "date",
                "label": "Period",
                "option_source": "none",
                "reset_behavior": "empty",
            },
        )

        self.assertTrue(valid["ok"], valid["issues"])
        self.assertEqual(selector_params(valid), ["date_from", "date_to"])
        self.assertIn(
            "incomplete_date_parameter_pair",
            {issue["code"] for issue in incomplete["issues"]},
        )
        self.assertIn(
            "duplicate_date_parameter",
            {issue["code"] for issue in duplicate["issues"]},
        )

    def test_reset_empty_cannot_carry_defaults(self):
        from datalens_dev_mcp.editor.selector_contract import normalize_selector_contract

        contract = normalize_selector_contract(
            family="single_select_dropdown",
            title="Status",
            selector_contract={
                "param": "status",
                "label": "Status",
                "option_source": "static",
                "options": ["open"],
                "default_values": ["open"],
                "reset_behavior": "empty",
            },
        )

        self.assertIn(
            "empty_reset_with_defaults",
            {issue["code"] for issue in contract["issues"]},
        )


if __name__ == "__main__":
    unittest.main()
