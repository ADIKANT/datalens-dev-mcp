import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WizardFieldBindingLiveReadbackTests(unittest.TestCase):
    def test_dataset_readback_must_match_chart_dataset_identity(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "data": {
                    "visualization": {
                        "id": "line",
                        "placeholders": [{"id": "x", "items": [{"guid": "date_guid"}]}],
                    },
                    "datasetsIds": ["dataset_expected"],
                    "datasetsPartialFields": [{"guid": "date_guid"}],
                    "labels": [{"guid": "date_guid"}],
                }
            },
            [
                {
                    "datasetId": "dataset_other",
                    "result_schema": [{"guid": "date_guid", "type": "date"}],
                }
            ],
        )

        rules = {finding["rule"] for finding in report["findings"]}
        self.assertFalse(report["ok"])
        self.assertIn("wizard_dataset_readback_mismatch", rules)

    def test_unrelated_dataset_cannot_supply_bound_field_evidence(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "data": {
                    "visualization": {
                        "id": "line",
                        "placeholders": [{"id": "x", "items": [{"guid": "date_guid"}]}],
                    },
                    "datasetsIds": ["dataset_expected"],
                    "datasetsPartialFields": [{"guid": "date_guid"}],
                    "labels": [{"guid": "date_guid"}],
                }
            },
            [
                {
                    "datasetId": "dataset_expected",
                    "result_schema": [{"guid": "other_guid", "type": "date"}],
                },
                {
                    "datasetId": "dataset_unrelated",
                    "result_schema": [{"guid": "date_guid", "type": "date"}],
                },
            ],
        )

        rules = {finding["rule"] for finding in report["findings"]}
        self.assertFalse(report["ok"])
        self.assertIn("wizard_partial_field_missing_from_dataset_readback", rules)

    def test_dataset_readback_evidence_is_compacted_to_referenced_fields(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import compact_wizard_dataset_readbacks

        compact = compact_wizard_dataset_readbacks(
            {
                "data": {
                    "visualization": {
                        "id": "column",
                        "placeholders": [
                            {"id": "x", "items": [{"guid": "category_guid"}]},
                            {"id": "y", "items": [{"guid": "value_guid"}]},
                        ],
                    },
                    "datasetsIds": ["dataset_1"],
                    "datasetsPartialFields": [
                        {"guid": "category_guid"},
                        {"guid": "value_guid"},
                    ],
                }
            },
            [
                {
                    "datasetId": "dataset_1",
                    "title": "discarded",
                    "result_schema": [
                        {"guid": "category_guid", "type": "string", "title": "Category"},
                        {"guid": "value_guid", "type": "float", "title": "Value"},
                        {"guid": "unused_guid", "type": "integer"},
                    ],
                    "unrelated_payload": {"large": True},
                }
            ],
        )

        self.assertEqual(
            compact,
            [
                {
                    "datasetId": "dataset_1",
                    "result_schema": [
                        {"guid": "category_guid", "data_type": "string"},
                        {"guid": "value_guid", "data_type": "float"},
                    ],
                }
            ],
        )

    def test_public_generator_omits_absent_readbacks_and_forwards_explicit_evidence(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_generate_editor_bundle,
            dl_start_pipeline,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl_start_pipeline(str(root), dashboard_name="Wizard evidence")
            Path(root, "artifacts", "dashboard_brief.json").write_text(
                json.dumps(
                    {
                        "dashboard_name": "Wizard evidence",
                        "dashboard_type": "overview",
                        "data_contract": {
                            "contract_id": "DATA-001",
                            "dataset_id": "dataset_1",
                            "fields": [],
                        },
                        "chart_decisions": [
                            {
                                "decision_id": "CD-001",
                                "widget_id": "trend",
                                "route": "wizard_native",
                                "family": "line_chart",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            stub = {"ok": False, "validation": {"errors": ["stub"]}}
            with patch(
                "datalens_dev_mcp.mcp.tools.pipeline.build_wizard_payload_plan",
                return_value=stub,
            ) as build:
                dl_generate_editor_bundle(
                    str(root),
                    widget_id="trend_without_evidence",
                    dataset_alias="dataset_1",
                    columns=["bucket_guid", "value_guid"],
                )
            omitted_config = build.call_args.args[0]

            evidence = [
                {
                    "datasetId": "dataset_1",
                    "result_schema": [
                        {"guid": "bucket_guid", "type": "date"},
                        {"guid": "value_guid", "type": "float"},
                    ],
                }
            ]
            with patch(
                "datalens_dev_mcp.mcp.tools.pipeline.build_wizard_payload_plan",
                return_value=stub,
            ) as build:
                dl_generate_editor_bundle(
                    str(root),
                    widget_id="trend_with_evidence",
                    dataset_alias="dataset_1",
                    columns=["bucket_guid", "value_guid"],
                    dataset_readbacks=evidence,
                )
            explicit_config = build.call_args.args[0]

        self.assertNotIn("dataset_readbacks", omitted_config)
        self.assertEqual(explicit_config["dataset_readbacks"], evidence)

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

    def test_saved_placeholder_role_rejects_string_measure(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "chartId": "wizard_1",
                "data": {
                    "visualization": {
                        "id": "column",
                        "placeholders": [
                            {"id": "x", "items": [{"guid": "category_guid"}]},
                            {"id": "y", "items": [{"guid": "value_guid"}]},
                        ],
                    },
                    "datasetsPartialFields": [
                        {"guid": "category_guid"},
                        {"guid": "value_guid"},
                    ],
                },
            },
            [
                {
                    "datasetId": "dataset_1",
                    "result_schema": [
                        {"guid": "category_guid", "type": "string"},
                        {"guid": "value_guid", "type": "string"},
                    ],
                }
            ],
            strict=False,
            enforce_role_types=True,
        )

        rules = {finding["rule"] for finding in report["findings"]}
        self.assertFalse(report["ok"])
        self.assertIn("wizard_field_role_type_mismatch", rules)

    def test_saved_role_type_mismatch_is_warning_without_explicit_semantic_policy(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "chartId": "wizard_1",
                "data": {
                    "visualization": {
                        "id": "metric",
                        "placeholders": [
                            {"id": "measures", "items": [{"guid": "label_guid"}]},
                        ],
                    },
                    "datasetsPartialFields": [{"guid": "label_guid"}],
                },
            },
            [
                {
                    "datasetId": "dataset_1",
                    "result_schema": [{"guid": "label_guid", "type": "string"}],
                }
            ],
            strict=False,
        )

        mismatches = [
            finding
            for finding in report["findings"]
            if finding["rule"] == "wizard_field_role_type_mismatch"
        ]
        self.assertTrue(report["ok"], report["findings"])
        self.assertEqual([finding["severity"] for finding in mismatches], ["warning"])

    def test_saved_placeholder_role_accepts_numeric_measure(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import validate_wizard_field_binding_against_dataset_readback

        report = validate_wizard_field_binding_against_dataset_readback(
            {
                "chartId": "wizard_1",
                "data": {
                    "visualization": {
                        "id": "column",
                        "placeholders": [
                            {"id": "x", "items": [{"guid": "category_guid"}]},
                            {"id": "y", "items": [{"guid": "value_guid"}]},
                        ],
                    },
                    "datasetsPartialFields": [
                        {"guid": "category_guid"},
                        {"guid": "value_guid"},
                    ],
                },
            },
            [
                {
                    "datasetId": "dataset_1",
                    "result_schema": [
                        {"guid": "category_guid", "type": "string"},
                        {"guid": "value_guid", "type": "float"},
                    ],
                }
            ],
            strict=False,
        )

        self.assertTrue(report["ok"], report["findings"])


if __name__ == "__main__":
    unittest.main()
