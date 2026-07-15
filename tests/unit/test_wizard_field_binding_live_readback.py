import unittest


class WizardFieldBindingLiveReadbackTests(unittest.TestCase):
    def test_stale_partial_field_fails_against_dataset_readback(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "chartId": "wizard_1",
                "chart_type": "line",
                "datasetsPartialFields": [{"guid": "stale_field"}],
                "labels": [{"guid": "stale_field"}],
            },
            [{"datasetId": "dataset_1", "result_schema": [{"guid": "fresh_field"}]}],
        )

        rules = {finding["rule"] for finding in report["findings"]}
        self.assertFalse(report["ok"])
        self.assertIn("wizard_partial_field_missing_from_dataset_readback", rules)

    def test_corrected_payload_passes_with_labels_and_dataset_guid(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "chartId": "wizard_1",
                "chart_type": "line",
                "datasetsPartialFields": [{"guid": "fresh_field"}],
                "labels": [{"guid": "fresh_field"}],
            },
            [{"datasetId": "dataset_1", "result_schema": [{"guid": "fresh_field"}]}],
        )

        self.assertTrue(report["ok"], report["findings"])


if __name__ == "__main__":
    unittest.main()
