import json
import tempfile
import unittest
from pathlib import Path


class VisualRuntimeContractTests(unittest.TestCase):
    def test_compiled_editor_payload_blocks_section_before_save(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle
        from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload

        bundle = generate_editor_bundle(
            widget_id="bad_section",
            route="editor_advanced",
            title="Bad Section",
            family="unknown_family_to_force_fallback",
        )
        bundle["tabs"]["prepare.js"] = (
            "module.exports = {render: Editor.wrapFn({args: [{}], fn: function() {"
            "return Editor.generateHtml(`<section>Bad</section>`);}})};\n"
        )

        with self.assertRaisesRegex(ValueError, "section_tag"):
            compile_editor_payload(bundle, workbook_id="workbook_local")

    def test_runtime_contract_blocks_dashboard_composite_unless_static_reference(self):
        from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

        body = (
            "return Editor.generateHtml(`<div class='filter-control dropdown'></div>"
            "<div class='kpi-card card-grid'></div><div class='chart-container plot-area'></div>`);"
        )

        result = validate_editor_runtime_contract({"data": {"prepare": body}}, source="runtime_contract")
        static_result = validate_editor_runtime_contract(
            {"static_reference_artifact": True, "data": {"prepare": body}},
            source="runtime_contract_static",
        )

        rules = {finding["rule"] for finding in result["findings"]}
        self.assertFalse(result["ok"])
        self.assertIn("composite_dashboard_in_advanced_editor", rules)
        self.assertIn("selector_inside_advanced_editor_body", rules)
        self.assertIn("kpi_card_grid_inside_advanced_editor", rules)
        self.assertTrue(static_result["ok"], static_result["findings"])

    def test_object_granularity_static_reference_exception_is_explicit(self):
        from datalens_dev_mcp.pipeline.dashboard_object_granularity import validate_dashboard_object_granularity

        composite = {
            "expected_visual_count": 4,
            "objects": [
                {
                    "object_id": "composite",
                    "object_type": "advanced_editor_chart",
                    "visual_count": 4,
                    "prepare": (
                        "<div class='filter-control'></div><div class='kpi-card card-grid'></div>"
                        "<svg></svg><table></table>"
                    ),
                }
            ],
        }
        static_reference = {
            **composite,
            "static_reference_artifact": True,
            "objects": [{**composite["objects"][0], "static_reference_artifact": True}],
        }

        bad = validate_dashboard_object_granularity(composite)
        good = validate_dashboard_object_granularity(static_reference)

        self.assertFalse(bad.ok)
        self.assertIn("composite_dashboard_widget", {finding.rule for finding in bad.findings})
        self.assertTrue(good.ok, [finding.to_dict() for finding in good.findings])

    def test_selector_contract_blocks_width_pct_over_budget_and_non_control_node(self):
        from datalens_dev_mcp.pipeline.selector_layout_contract import validate_selector_layout_contract

        result = validate_selector_layout_contract(
            {
                "selector_rows": [
                    [
                        {
                            "id": "team",
                            "object_type": "advanced_editor_chart",
                            "kind": "single_select",
                            "width_pct": 97,
                            "target_widget_ids": ["trend"],
                            "target_field_or_parameter": "team",
                            "default_value_policy": "all",
                        }
                    ]
                ],
                "objects": [{"object_id": "trend"}],
                "fields": ["team"],
            }
        )

        rules = {finding.rule for finding in result.findings}
        self.assertFalse(result.ok)
        self.assertIn("selector_row_width_over_budget", rules)
        self.assertIn("selector_not_control_node", rules)

    def test_native_table_bar_cells_require_contrast(self):
        from datalens_dev_mcp.pipeline.native_table_contract import validate_native_table_contract

        result = validate_native_table_contract(
            {
                "route": "table_node",
                "columns": [
                    {"id": "name", "title": "Name", "type": "text", "role": "dimension"},
                    {
                        "id": "value",
                        "title": "Value",
                        "type": "bar",
                        "role": "measure",
                        "min": 0,
                        "max": 10,
                        "barColor": "#ffffff",
                        "showLabel": True,
                        "label_position": "inside",
                        "labelColor": "#ffffff",
                    },
                ],
                "rows": [{"cells": [{"value": "A"}, {"value": 4}]}],
            },
            source_rows=1,
        )

        self.assertFalse(result.ok)
        self.assertIn("low_contrast_text_on_bar", {finding.rule for finding in result.findings})

    def test_kpi_object_has_one_metric_contract(self):
        from datalens_dev_mcp.pipeline.kpi_indicator_contract import validate_kpi_indicator_contract

        result = validate_kpi_indicator_contract(
            {
                "kpis": [
                    {
                        "object_type": "indicator_node",
                        "metrics": ["orders", "revenue"],
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

        self.assertFalse(result.ok)
        self.assertIn("kpi_multiple_metrics", {finding.rule for finding in result.findings})

    def test_line_visual_contract_requires_axes_labels_or_alternative(self):
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

        result = validate_visual_quality_contract(
            {
                "family": "line_chart",
                "labels": {"direct_labels": False},
                "axes": {"show": False, "unit_label_required": False, "date_axis_ascending": False},
                "tooltip": {"include_values": False, "include_metric_definition": False},
            }
        )

        self.assertFalse(result.ok)
        self.assertIn("line_chart_axis_label_contract", {finding.rule for finding in result.findings})

    def test_line_visual_contract_allows_readable_axes_and_value_tooltip_without_direct_labels(self):
        from datalens_dev_mcp.pipeline.visual_quality import validate_visual_quality_contract

        result = validate_visual_quality_contract(
            {
                "family": "line_chart",
                "labels": {"direct_labels": False},
                "axes": {"show": True, "date_axis_ascending": True},
                "tooltip": {"include_values": True},
            }
        )

        self.assertTrue(result.ok, [finding.to_dict() for finding in result.findings])
        self.assertNotIn("delta_v6_labels_required", {finding.rule for finding in result.findings})

    def test_project_dashboard_payload_preflight_runs_visual_contracts(self):
        from datalens_dev_mcp.mcp.tools.pipeline import dl_validate_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_dir = root / "artifacts" / "dashboard_payloads"
            payload_dir.mkdir(parents=True)
            payload = {
                "dashboardId": "dashboard_synthetic",
                "tabs": [{"id": "main", "title": "Main", "items": ["composite_item"]}],
                "items": [{"id": "composite_item", "type": "chart", "chartId": "composite"}],
                "expected_visual_count": 2,
                "objects": [
                    {
                        "object_id": "composite",
                        "object_type": "advanced_editor_chart",
                        "visual_count": 2,
                        "prepare": "<div class='filter-control'></div><div class='chart-container'></div>",
                    }
                ],
            }
            (payload_dir / "bad.dashboard.payload.json").write_text(json.dumps(payload), encoding="utf-8")

            report = dl_validate_project(str(root))

        joined = "\n".join(report["issues"])
        self.assertEqual(report["status"], "fail")
        self.assertIn("dashboard_payload_preflight", report["checked"])
        self.assertIn("composite_dashboard_widget", joined)

    def test_strict_dashboard_payload_blocks_duplicate_native_title_and_hint_in_body(self):
        from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload

        result = validate_dashboard_payload(
            {
                "id": "chart_1",
                "type": "advanced_editor",
                "native_title": "Event diagnostics",
                "native_hint": "Use dashboard metadata.",
                "data": {"html": "<h1>Event diagnostics</h1><p>Use dashboard metadata.</p>"},
            }
        )

        rules = {issue.rule for issue in result.issues}
        self.assertFalse(result.ok)
        self.assertIn("duplicate_inline_title", rules)
        self.assertIn("duplicate_inline_hint", rules)

    def test_safe_apply_preflight_blocks_metaon_in_final_editor_payload(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan

        plan = create_safe_apply_plan(
            project_root="/tmp/project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {
                        "mode": "save",
                        "entry": {
                            "entryId": "chart_metaon",
                            "type": "editor_chart",
                            "data": {"metaon": "{}"},
                        },
                    },
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_metaon", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_metaon", "branch": "saved"},
                }
            ],
        )

        validation = validate_safe_apply_plan(plan)

        self.assertFalse(validation.ok)
        self.assertIn("editor_metaon_tab", "\n".join(validation.issues))

    def test_safe_apply_preflight_blocks_html_table_inside_advanced_editor(self):
        from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan, validate_safe_apply_plan

        plan = create_safe_apply_plan(
            project_root="/tmp/project",
            approved=True,
            actions=[
                {
                    "action": "update_editor_chart",
                    "method": "updateEditorChart",
                    "payload": {
                        "mode": "save",
                        "entry": {
                            "entryId": "chart_html_table",
                            "type": "editor_chart",
                            "data": {
                                "javascript": (
                                    "module.exports = {render: Editor.wrapFn({args: [], fn: function() {"
                                    "return Editor.generateHtml(`<table><tr><td>A</td></tr></table>`);"
                                    "}})};"
                                )
                            },
                        },
                    },
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": "chart_html_table", "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": "chart_html_table", "branch": "saved"},
                }
            ],
        )

        validation = validate_safe_apply_plan(plan)

        self.assertFalse(validation.ok)
        self.assertIn("table_tag", "\n".join(validation.issues))


if __name__ == "__main__":
    unittest.main()
