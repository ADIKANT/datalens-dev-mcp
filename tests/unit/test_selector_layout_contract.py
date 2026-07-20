import unittest


class SelectorLayoutContractTests(unittest.TestCase):
    def test_long_selectors_split_rows_under_94_percent(self):
        from datalens_dev_mcp.pipeline.selector_layout_contract import (
            SelectorLayoutContract,
            validate_selector_layout_contract,
        )

        selectors = [
            {
                "id": "period",
                "object_type": "control_node",
                "kind": "date_range",
                "label": "Reporting period date range",
                "target_widget_ids": ["trend"],
                "target_field_or_parameter": "paid_dttm",
                "default_value_policy": "last_30_days",
            },
            {
                "id": "team",
                "object_type": "control_node",
                "kind": "multi_select",
                "label": "Delivery team multi select",
                "target_widget_ids": ["trend"],
                "target_field_or_parameter": "team",
                "default_value_policy": "all",
            },
            {
                "id": "sprint",
                "object_type": "control_node",
                "kind": "single_select",
                "label": "Sprint selection control",
                "target_widget_ids": ["trend"],
                "target_field_or_parameter": "sprint",
                "default_value_policy": "all",
            },
            {
                "id": "rcp_category",
                "object_type": "control_node",
                "kind": "search_select",
                "label": "RCP category with very long readable label",
                "target_widget_ids": ["trend"],
                "target_field_or_parameter": "rcp_category",
                "default_value_policy": "all",
            },
            {
                "id": "grain",
                "object_type": "control_node",
                "kind": "granularity",
                "label": "Reporting granularity",
                "target_widget_ids": ["trend"],
                "target_field_or_parameter": "grain",
                "default_value_policy": "week",
            },
        ]
        rows = SelectorLayoutContract().compute_rows(selectors)
        result = validate_selector_layout_contract(
            {
                "selector_rows": rows,
                "objects": [{"object_id": "trend"}],
                "fields": ["paid_dttm", "team", "sprint", "rcp_category", "grain"],
            }
        )

        self.assertGreaterEqual(len(rows), 2)
        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])
        self.assertTrue(all(width <= 94 for width in result.row_widths_pct))

    def test_unknown_target_fails(self):
        from datalens_dev_mcp.pipeline.selector_layout_contract import validate_selector_layout_contract

        result = validate_selector_layout_contract(
            {
                "selector_rows": [
                    [
                        {
                            "id": "team",
                            "object_type": "control_node",
                            "kind": "single_select",
                            "width": "20%",
                            "target_widget_ids": ["missing"],
                            "target_field_or_parameter": "team",
                            "default_value_policy": "all",
                        }
                    ]
                ],
                "objects": [{"object_id": "trend"}],
                "fields": ["team"],
            }
        )

        self.assertFalse(result.ok)
        self.assertIn("selector_unknown_target_id", {finding.rule for finding in result.findings})


if __name__ == "__main__":
    unittest.main()
