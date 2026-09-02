import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WizardFieldBindingLiveReadbackTests(unittest.TestCase):
    def test_saved_visualization_null_icon_ref_is_not_a_field_reference(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import (
            validate_wizard_field_binding_against_dataset_readback,
        )

        payload = {
            "data": {
                "datasetsIds": ["dataset_1"],
                "datasetsPartialFields": [[{"guid": "value_guid", "data_type": "float"}]],
                "visualization": {
                    "id": "metric",
                    "icon": {"ref": None},
                    "placeholders": [
                        {
                            "id": "measures",
                            "icon": {"ref": None},
                            "items": [{"guid": "value_guid", "data_type": "float"}],
                        }
                    ],
                },
            }
        }
        readback = {
            "datasetId": "dataset_1",
            "dataset": {"result_schema": [{"guid": "value_guid", "data_type": "float"}]},
        }

        result = validate_wizard_field_binding_against_dataset_readback(
            payload,
            [readback],
            strict=True,
            enforce_role_types=True,
        )

        self.assertTrue(result["ok"], result["findings"])

    def test_nested_per_dataset_partial_fields_are_flattened(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import (
            validate_wizard_field_binding_against_dataset_readback,
            validate_wizard_visual_dataset_contract,
        )

        payload = {
            "data": {
                "datasetsIds": ["dataset_1"],
                "datasetsPartialFields": [
                    [
                        {"guid": "category_guid", "title": "Category", "calc_mode": "direct"},
                        {"guid": "value_guid", "title": "Value", "calc_mode": "formula"},
                    ]
                ],
                "visualization": {
                    "id": "column",
                    "placeholders": [
                        {"items": [{"guid": "category_guid"}]},
                        {"items": [{"guid": "value_guid"}]},
                    ],
                },
            }
        }
        readback = {
            "datasetId": "dataset_1",
            "dataset": {
                "result_schema": [
                    {"guid": "category_guid", "data_type": "string"},
                    {"guid": "value_guid", "data_type": "integer"},
                ]
            },
        }

        contract = validate_wizard_visual_dataset_contract(payload)
        live = validate_wizard_field_binding_against_dataset_readback(
            payload,
            [readback],
            strict=True,
            enforce_role_types=False,
        )

        self.assertTrue(contract.ok, contract.findings)
        self.assertTrue(live["ok"], live["findings"])

    def test_nested_partial_field_can_be_proven_chart_local_elsewhere_in_payload(self):
        from datalens_dev_mcp.pipeline.wizard_contracts import (
            validate_wizard_field_binding_against_dataset_readback,
        )

        payload = {
            "data": {
                "datasetsIds": ["dataset_1"],
                "datasetsPartialFields": [
                    [{"guid": "local_measure", "title": "Local measure", "calc_mode": "direct"}]
                ],
                "visualization": {
                    "id": "column",
                    "placeholders": [
                        {
                            "items": [
                                {
                                    "guid": "local_measure",
                                    "calc_mode": "direct",
                                    "local": True,
                                    "quickFormula": True,
                                }
                            ]
                        }
                    ],
                },
            }
        }
        readback = {"datasetId": "dataset_1", "dataset": {"result_schema": []}}

        result = validate_wizard_field_binding_against_dataset_readback(
            payload,
            [readback],
            strict=True,
            enforce_role_types=False,
        )

        self.assertTrue(result["ok"], result["findings"])

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

    def test_public_generator_binds_all_explicit_funnel_fields_to_native_placeholder(self):
        from datalens_dev_mcp.mcp.tools.pipeline import (
            dl_generate_editor_bundle,
            dl_start_pipeline,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dl_start_pipeline(str(root), dashboard_name="Native funnel")
            Path(root, "artifacts", "dashboard_brief.json").write_text(
                json.dumps(
                    {
                        "dashboard_name": "Native funnel",
                        "dashboard_type": "overview",
                        "data_contract": {
                            "contract_id": "DATA-001",
                            "dataset_id": "dataset_1",
                            "fields": [],
                        },
                        "chart_decisions": [
                            {
                                "decision_id": "CD-001",
                                "widget_id": "funnel",
                                "route": "wizard_native",
                                "family": "funnel_snapshot",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "datalens_dev_mcp.mcp.tools.pipeline.build_wizard_payload_plan",
                return_value={"ok": False, "validation": {"errors": ["stub"]}},
            ) as build:
                dl_generate_editor_bundle(
                    str(root),
                    widget_id="funnel",
                    dataset_alias="dataset_1",
                    columns=["stage_guid", "value_guid"],
                )
            config = build.call_args.args[0]

        self.assertEqual(config["visualization_id"], "funnel")
        self.assertEqual(
            config["field_bindings"]["measures"],
            [
                {"guid": "stage_guid", "title": "stage_guid"},
                {"guid": "value_guid", "title": "value_guid"},
            ],
        )

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
