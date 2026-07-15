import json
import re
import unittest
from pathlib import Path


class StandardChartTemplateTests(unittest.TestCase):
    def setUp(self):
        self.registry_path = Path("templates/datalens/standard_chart_templates.json")

    def test_registry_covers_approved_families_and_excludes_removed(self):
        from datalens_dev_mcp.pipeline.chart_taxonomy import APPROVED_CHARTS, REMOVED_CHARTS

        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        families = registry["families"]

        self.assertEqual(set(APPROVED_CHARTS), set(families))
        self.assertFalse(set(REMOVED_CHARTS).intersection(families))

    def test_registered_templates_have_required_artifacts(self):
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))

        for family, spec in registry["families"].items():
            template_dir = Path(spec["template_dir"])
            with self.subTest(family=family):
                self.assertTrue(template_dir.is_dir(), f"{template_dir} missing")
                self.assertTrue((template_dir / "README.md").is_file())
                self.assertTrue((template_dir / "schema.json").is_file())
                self.assertTrue((template_dir / "example_input.json").is_file())
                for file_name in spec["required_files"]:
                    self.assertTrue((template_dir / file_name).is_file(), f"{family}: {file_name} missing")

    def test_registry_declares_truthful_status_and_inputs(self):
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))

        for family, spec in registry["families"].items():
            with self.subTest(family=family):
                self.assertIn(spec["status"], {"IMPLEMENTED", "ROUTE_ONLY", "BLOCKED_NEEDS_TEMPLATE", "REMOVED"})
                self.assertIsInstance(spec["implemented_behavior"], str)
                self.assertIsInstance(spec["required_inputs"], list)
                if spec["status"] != "IMPLEMENTED":
                    self.assertTrue(spec["fallback_family"])

    def test_called_out_variants_are_injected_and_branch_backed(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        markers = {
            "heatmap": "renderHeatmap",
            "waterfall": "renderWaterfall",
            "grouped_bar": "renderGroupedBar",
            "stacked_100": "renderStacked100",
            "bullet_assignees": "renderBulletAssignees",
            "combo_time_series_combo": "buildVerticalBars(true)",
            "area_completion": "buildLineSeries(true)",
            "funnel_snapshot": "buildFunnel",
            "pie": "renderPieLike(data.variant === 'donut')",
            "donut": "renderPieLike(data.variant === 'donut')",
            "treemap": "renderTreemap",
            "histogram": "renderHistogram",
            "box_plot": "renderBoxPlot",
            "scatter": "renderScatter(false)",
            "bubble": "renderScatter(true)",
        }

        for family, marker in markers.items():
            bundle = generate_editor_bundle(widget_id=f"{family}_widget", route="editor_advanced", title=family, family=family)
            prepare = bundle["tabs"]["prepare.js"]
            params = bundle["tabs"]["params.js"]
            with self.subTest(family=family):
                self.assertIn(f"const TEMPLATE_VARIANT = '{family}';", prepare)
                self.assertIn(marker, prepare)
                self.assertIn(f'"chart_variant": "{family}"', params)

    def test_kpi_variants_are_injected_and_branch_backed(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        for family in ("kpi_value_only", "kpi_value_delta", "kpi_value_sparkline", "kpi_value_delta_sparkline"):
            bundle = generate_editor_bundle(widget_id=f"{family}_widget", route="editor_advanced", title=family, family=family)
            prepare = bundle["tabs"]["prepare.js"]
            with self.subTest(family=family):
                self.assertIn(f"const TEMPLATE_VARIANT = '{family}';", prepare)
                self.assertIn("showDelta", prepare)
                self.assertIn("showSparkline", prepare)

    def test_advanced_js_templates_are_commented_and_safe(self):
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))

        for family, spec in registry["families"].items():
            if spec["route"] != "editor_advanced":
                continue
            prepare_path = Path(spec["template_dir"]) / "prepare.js"
            text = prepare_path.read_text(encoding="utf-8")
            with self.subTest(family=family):
                self.assertIn("Editor.wrapFn", text)
                self.assertIn("Editor.generateHtml", text)
                self.assertIn("HOUSE_STYLE", text)
                self.assertIn("//", text)
                self.assertNotIn("d3_node", text)
                self.assertNotIn("ql_chart", text)

    def test_templates_do_not_embed_private_paths_or_ids(self):
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in Path("templates/datalens").rglob("*")
            if path.is_file()
        )

        private_root = "/" + "Users" + "/alexandr"
        self.assertNotIn(private_root, text)
        datalens_shaped_ids = re.findall(r"\b(?=[a-z0-9]{0,12}\d)[a-z0-9]{13}\b", text)
        self.assertEqual(datalens_shaped_ids, [])

    def test_editor_bundle_prefers_standard_templates_for_family_generation(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="trend_widget",
            route="editor_advanced",
            title="Trend Widget",
            family="line_chart",
        )

        self.assertEqual(bundle["source_template"], "templates/datalens/advanced_editor/time_series")
        self.assertIn("params.js", bundle["tabs"])
        self.assertIn("Editor.wrapFn", bundle["tabs"]["prepare.js"])
        self.assertIn("// Render/layout", bundle["tabs"]["prepare.js"])

    def test_production_standard_bundles_fail_closed_without_source_binding(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        demo_markers = ("UNION ALL SELECT", "2026-W01", "128 AS current_value", "42 AS value")
        for family in (
            "kpi_value_only",
            "line_chart",
            "horizontal_bar",
            "scatter",
            "pie",
            "sankey_status_flow",
        ):
            bundle = generate_editor_bundle(
                widget_id=f"{family}_production",
                route="editor_advanced",
                title=family,
                family=family,
            )
            sources = bundle["tabs"]["sources.js"]
            with self.subTest(family=family):
                self.assertEqual(bundle["generation_status"], "blocked_missing_source")
                self.assertEqual(bundle["source_contract"]["binding"], "empty")
                self.assertIn("Provide dataset_alias", sources)
                self.assertTrue(bundle["blocking_issues"])
                for marker in demo_markers:
                    self.assertNotIn(marker, sources)

    def test_production_standard_bundle_uses_caller_dataset_and_columns(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="orders_trend",
            route="editor_advanced",
            title="Orders Trend",
            family="line_chart",
            dataset_alias="orders_dataset",
            columns=["bucket", "metric", "value"],
        )

        self.assertEqual(bundle["generation_status"], "ready")
        self.assertTrue(bundle["source_contract"]["production_ready"])
        self.assertEqual(bundle["source_contract"]["dataset_alias"], "orders_dataset")
        self.assertIn('"dataset": "orders_dataset"', bundle["tabs"]["meta.json"])
        self.assertIn('columns: ["bucket", "metric", "value"]', bundle["tabs"]["sources.js"])
        self.assertNotIn("UNION ALL SELECT", bundle["tabs"]["sources.js"])
        self.assertNotIn("2026-W01", bundle["tabs"]["sources.js"])

    def test_production_standard_bundle_blocks_ignored_column_aliases(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="orders_trend",
            route="editor_advanced",
            title="Orders Trend",
            family="line_chart",
            dataset_alias="orders_dataset",
            columns=["event_date", "amount"],
        )

        self.assertEqual(bundle["generation_status"], "blocked_missing_source")
        self.assertEqual(bundle["source_contract"]["missing_output_columns"], ["bucket", "value"])
        messages = "\n".join(issue["message"] for issue in bundle["blocking_issues"])
        self.assertIn("bucket, value", messages)
        self.assertEqual(bundle["tabs"]["sources.js"].strip().splitlines()[-1], "module.exports = {};")

    def test_distribution_and_target_templates_require_real_statistics(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        box_blocked = generate_editor_bundle(
            widget_id="age_box",
            route="editor_advanced",
            title="Age distribution",
            family="box_plot",
            dataset_alias="age_dataset",
            columns=["label", "value"],
        )
        bullet_blocked = generate_editor_bundle(
            widget_id="assignee_target",
            route="editor_advanced",
            title="Assignee target",
            family="bullet_assignees",
            dataset_alias="assignee_dataset",
            columns=["label", "value"],
        )
        box_ready = generate_editor_bundle(
            widget_id="age_box_ready",
            route="editor_advanced",
            title="Age distribution",
            family="box_plot",
            dataset_alias="age_dataset",
            columns=["label", "min", "q1", "median", "q3", "max"],
        )

        self.assertEqual(
            box_blocked["source_contract"]["missing_output_columns"],
            ["min", "q1", "median", "q3", "max"],
        )
        self.assertEqual(bullet_blocked["source_contract"]["missing_output_columns"], ["target"])
        self.assertEqual(box_ready["generation_status"], "ready")
        self.assertNotIn("row.value * 0.35", box_ready["tabs"]["prepare.js"])

    def test_templates_do_not_fabricate_sparklines_or_missing_series_values(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        kpi = generate_editor_bundle(
            widget_id="real_sparkline",
            route="editor_advanced",
            title="Real sparkline",
            family="kpi_value_sparkline",
            dataset_alias="metric_dataset",
            columns=["current_value", "sparkline"],
        )
        line = generate_editor_bundle(
            widget_id="real_series",
            route="editor_advanced",
            title="Real series",
            family="line_chart",
            dataset_alias="metric_dataset",
            columns=["bucket", "value"],
        )

        self.assertNotIn("4,6,5,8,7,9,11", kpi["tabs"]["prepare.js"])
        self.assertNotIn("found ? found.value : 0", line["tabs"]["prepare.js"])
        self.assertIn("return found ?", line["tabs"]["prepare.js"])

    def test_source_free_standard_routes_remain_ready_without_placeholder_connection(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        for route, family in (
            ("editor_markdown", "md_methodology_block"),
            ("editor_js_control", "multi_select_dropdown"),
        ):
            bundle = generate_editor_bundle(
                widget_id=f"{family}_production",
                route=route,
                title=family,
                family=family,
            )
            with self.subTest(route=route, family=family):
                self.assertEqual(bundle["generation_status"], "ready")
                self.assertEqual(bundle["source_contract"]["status"], "not_required")
                self.assertEqual(bundle["tabs"]["sources.js"], "module.exports = {};\n")
                self.assertNotIn("defaultConnection", bundle["tabs"]["meta.json"])


if __name__ == "__main__":
    unittest.main()
