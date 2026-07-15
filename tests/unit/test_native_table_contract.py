import unittest


class NativeTableContractTests(unittest.TestCase):
    def test_non_empty_source_cannot_be_skeleton(self):
        from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract

        result = validate_native_table_contract({"route": "editor_table", "columns": [], "rows": []}, source_rows=5)

        self.assertFalse(result.ok)
        self.assertFalse(result.publish_allowed)
        self.assertIn("non_empty_source_rendered_empty_table", {finding.rule for finding in result.findings})

    def test_bar_cell_requires_readable_label_contract(self):
        from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract

        result = validate_native_table_contract(
            {
                "route": "editor_table",
                "columns": [
                    {"id": "name", "title": "Name", "type": "text", "role": "dimension"},
                    {
                        "id": "value",
                        "title": "Value",
                        "type": "bar",
                        "role": "measure",
                        "min": 0,
                        "max": 10,
                        "barColor": "#2f80ed",
                        "showLabel": True,
                        "label_position": "outside",
                    },
                ],
                "rows": [{"cells": [{"value": "A"}, {"value": 4}]}],
            },
            source_rows=1,
        )

        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])


if __name__ == "__main__":
    unittest.main()
