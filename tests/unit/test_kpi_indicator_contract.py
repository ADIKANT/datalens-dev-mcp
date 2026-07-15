import unittest


class KpiIndicatorContractTests(unittest.TestCase):
    def test_kpi_requires_explicit_semantics(self):
        from datalens_dev_mcp.pipeline.kpi_indicator_contract import validate_kpi_indicator_contract

        result = validate_kpi_indicator_contract(
            {
                "kpis": [
                    {
                        "object_type": "indicator_node",
                        "formula": "COUNTD([order_id])",
                        "unit": "orders",
                        "grain": "day",
                        "comparator_policy": "explicit_none",
                        "native_title": "Orders",
                        "native_hint": "Orders in selected period",
                    }
                ]
            }
        )

        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])

    def test_kpi_card_grid_fails(self):
        from datalens_dev_mcp.pipeline.kpi_indicator_contract import validate_kpi_indicator_contract

        result = validate_kpi_indicator_contract({"html": "<div class='kpi-card card-grid'></div>"})

        self.assertFalse(result.ok)
        self.assertIn("kpi_html_card_grid", {finding.rule for finding in result.findings})


if __name__ == "__main__":
    unittest.main()
