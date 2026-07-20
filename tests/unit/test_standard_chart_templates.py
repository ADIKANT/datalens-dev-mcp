import json
import re
import shutil
import subprocess
import tempfile
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
                params_payload = json.loads(params.removeprefix("module.exports = ").removesuffix(";\n"))
                self.assertTrue(
                    all(
                        isinstance(values, list)
                        and all(isinstance(value, str) for value in values)
                        for values in params_payload.values()
                    ),
                    params_payload,
                )
                self.assertNotIn("chart_variant", params_payload)
                self.assertNotIn("renderer_visual_spec", params_payload)

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
        self.assertIn("return found && Number.isFinite(found.value)", line["tabs"]["prepare.js"])

    def test_source_free_standard_routes_are_ready_with_explicit_content(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        for route, family, extra in (
            ("editor_markdown", "md_methodology_block", {"markdown": "## Metric definition\n\nExplicit content."}),
            (
                "editor_js_control",
                "multi_select_dropdown",
                {
                    "selector_contract": {
                        "param": "state",
                        "label": "State",
                        "option_source": "static",
                        "options": ["open", "closed"],
                        "default_values": [],
                        "reset_behavior": "empty",
                    }
                },
            ),
        ):
            bundle = generate_editor_bundle(
                widget_id=f"{family}_production",
                route=route,
                title=family,
                family=family,
                **extra,
            )
            with self.subTest(route=route, family=family):
                self.assertEqual(bundle["generation_status"], "ready")
                self.assertEqual(bundle["source_contract"]["status"], "not_required")
                self.assertEqual(bundle["tabs"]["sources.js"], "module.exports = {};\n")
                self.assertNotIn("defaultConnection", bundle["tabs"]["meta.json"])

    def test_selector_family_matrix_uses_structured_contract(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        expectations = {
            "single_select_dropdown": ("select", "multiselect: false", "searchable: false"),
            "multi_select_dropdown": ("select", "multiselect: true", "searchable: true"),
            "search_selector": ("select", "multiselect: false", "searchable: true"),
            "selector_family_static": ("select", "multiselect: false", "searchable: false"),
        }
        for family, (control_type, multiselect, searchable) in expectations.items():
            bundle = generate_editor_bundle(
                widget_id=f"{family}_widget",
                route="editor_js_control",
                title="Lifecycle state",
                family=family,
                selector_contract={
                    "param": "lifecycle_state",
                    "label": "Lifecycle state",
                    "option_source": "static",
                    "options": [
                        {"title": "Draft", "value": "draft"},
                        {"title": "Published", "value": "published"},
                    ],
                    "default_values": ["draft"],
                    "reset_behavior": "initial",
                },
            )
            controls = bundle["tabs"]["controls.js"]
            params = bundle["tabs"]["params.js"]
            with self.subTest(family=family):
                self.assertEqual(bundle["generation_status"], "ready")
                self.assertIn(f"type: '{control_type}'", controls)
                self.assertIn("param: \"lifecycle_state\"", controls)
                self.assertIn(multiselect, controls)
                self.assertIn(searchable, controls)
                self.assertIn('"value": "draft"', controls)
                self.assertIn('"value": "published"', controls)
                self.assertIn('"lifecycle_state": [', params)
                self.assertIn('"draft"', params)
                self.assertNotIn("segment", controls)
                self.assertNotIn('"all"', controls)

    def test_date_range_selector_uses_official_control_and_interval_default(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="date_range_widget",
            route="editor_js_control",
            title="Reporting interval",
            family="date_range_selector",
            selector_contract={
                "param": "reporting_interval",
                "label": "Reporting interval",
                "option_source": "none",
                "default_values": ["__interval_2026-01-01_2026-01-31"],
                "reset_behavior": "initial",
            },
        )

        self.assertEqual(bundle["generation_status"], "ready")
        self.assertIn("type: 'range-datepicker'", bundle["tabs"]["controls.js"])
        self.assertIn('param: "reporting_interval"', bundle["tabs"]["controls.js"])
        self.assertNotIn("content:", bundle["tabs"]["controls.js"])
        self.assertIn(
            '"__interval_2026-01-01_2026-01-31"',
            bundle["tabs"]["params.js"],
        )

    def test_date_range_selector_supports_paired_params_and_string_array_defaults(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="paired_date_range_widget",
            route="editor_js_control",
            title="Reporting interval",
            family="date_range_selector",
            selector_contract={
                "param_from": "reporting_from",
                "param_to": "reporting_to",
                "label": "Reporting interval",
                "option_source": "none",
                "default_from": "2026-01-01",
                "default_to": "__relative_0d",
                "reset_behavior": "initial",
            },
        )

        controls = bundle["tabs"]["controls.js"]
        params = json.loads(
            bundle["tabs"]["params.js"].removeprefix("module.exports = ").removesuffix(";\n")
        )
        self.assertEqual(bundle["generation_status"], "ready")
        self.assertIn('paramFrom: "reporting_from"', controls)
        self.assertIn('paramTo: "reporting_to"', controls)
        self.assertNotIn("\n      param:", controls)
        self.assertEqual(
            params,
            {
                "reporting_from": ["2026-01-01"],
                "reporting_to": ["__relative_0d"],
            },
        )
        self.assertTrue(
            all(
                isinstance(values, list) and all(isinstance(value, str) for value in values)
                for values in params.values()
            )
        )

    def test_dynamic_selector_requires_and_consumes_dataset_source(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        selector_contract = {
            "param": "state",
            "label": "State",
            "option_source": "dataset",
            "default_values": [],
            "reset_behavior": "empty",
        }
        blocked = generate_editor_bundle(
            widget_id="dynamic_blocked",
            route="editor_js_control",
            title="Dynamic state",
            family="selector_family_dynamic",
            selector_contract=selector_contract,
        )
        ready = generate_editor_bundle(
            widget_id="dynamic_ready",
            route="editor_js_control",
            title="Dynamic state",
            family="selector_family_dynamic",
            selector_contract=selector_contract,
            dataset_alias="state_dataset",
            columns=["value", "title"],
        )

        self.assertEqual(blocked["generation_status"], "blocked_missing_source")
        self.assertEqual(ready["generation_status"], "ready")
        self.assertEqual(ready["source_contract"]["binding"], "dataset")
        self.assertIn('"dataset": "state_dataset"', ready["tabs"]["meta.json"])
        self.assertIn("Editor.getLoadedData()", ready["tabs"]["controls.js"])
        self.assertIn("content: content", ready["tabs"]["controls.js"])

    def test_dynamic_selector_executes_against_editor_event_stream(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="dynamic_runtime",
            route="editor_js_control",
            title="Dynamic state",
            family="selector_family_dynamic",
            selector_contract={
                "param": "state",
                "label": "State",
                "option_source": "dataset",
                "default_values": [],
                "reset_behavior": "empty",
            },
            dataset_alias="state_dataset",
            columns=["value", "title"],
        )
        script = (
            "global.Editor={getLoadedData:()=>({rows:["
            "{event:'metadata',data:{names:['value','title']}},"
            "{event:'row',data:['open','Open']},"
            "{event:'row',data:['closed','Closed']},"
            "{event:'row',data:['open','Duplicate']}"
            "]})};"
            "process.stdout.write(JSON.stringify(require(process.argv[1])));"
        )
        with tempfile.TemporaryDirectory() as tmp:
            controls_path = Path(tmp) / "controls.cjs"
            controls_path.write_text(bundle["tabs"]["controls.js"], encoding="utf-8")
            completed = subprocess.run(
                [node, "-e", script, str(controls_path)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        control = json.loads(completed.stdout)["controls"][0]
        self.assertEqual(
            control["content"],
            [
                {"title": "Open", "value": "open"},
                {"title": "Closed", "value": "closed"},
            ],
        )

    def test_production_selectors_and_markdown_fail_closed_without_required_content(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        selector = generate_editor_bundle(
            widget_id="selector_without_options",
            route="editor_js_control",
            title="State",
            family="single_select_dropdown",
        )
        markdown = generate_editor_bundle(
            widget_id="owner_without_content",
            route="editor_markdown",
            title="Owner",
            family="md_dashboard_owner",
        )
        section = generate_editor_bundle(
            widget_id="section_title",
            route="editor_markdown",
            title="Service quality",
            family="md_section_header",
        )

        self.assertEqual(selector["generation_status"], "blocked_missing_input")
        self.assertEqual(selector["tabs"]["controls.js"], "module.exports = {controls: []};\n")
        self.assertEqual(selector["tabs"]["params.js"], "module.exports = {};\n")
        self.assertNotIn("segment", json.dumps(selector))
        self.assertNotIn('"all"', json.dumps(selector))
        self.assertEqual(markdown["generation_status"], "blocked_missing_input")
        self.assertEqual(section["generation_status"], "ready")
        self.assertIn("## Service quality", section["tabs"]["prepare.js"])

    def test_explicit_legacy_selector_arguments_remain_supported_without_invented_default(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="legacy_explicit",
            route="editor_js_control",
            title="State",
            family="single_select_dropdown",
            param="state",
            options=["open", "closed"],
        )

        params = json.loads(
            bundle["tabs"]["params.js"].removeprefix("module.exports = ").removesuffix(";\n")
        )
        self.assertEqual(bundle["generation_status"], "ready")
        self.assertEqual(params, {"state": []})
        self.assertIn('param: "state"', bundle["tabs"]["controls.js"])
        self.assertNotIn("segment", json.dumps(bundle))

    def test_golden_fixture_explicit_legacy_inputs_override_shared_example_contract(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        date_bundle = generate_editor_bundle(
            widget_id="golden_date",
            route="editor_js_control",
            title="Date",
            family="date_range_selector",
            param="period",
            options=["2026-01-01", "2026-01-31"],
            source_mode="golden_fixture",
        )
        dynamic_bundle = generate_editor_bundle(
            widget_id="golden_dynamic",
            route="editor_js_control",
            title="Dynamic",
            family="selector_family_dynamic",
            param="state",
            source_mode="golden_fixture",
        )

        self.assertEqual(date_bundle["selector_contract"]["param"], "period")
        self.assertTrue(date_bundle["selector_contract"]["ok"], date_bundle["blocking_issues"])
        self.assertTrue(dynamic_bundle["selector_contract"]["ok"], dynamic_bundle["blocking_issues"])
        self.assertEqual(dynamic_bundle["selector_contract"]["param"], "state")

    def test_markdown_variants_preserve_explicit_user_content(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        content = "## Source notes\n\n[Runbook](https://example.invalid/runbook)"
        for family in (
            "md_methodology_block",
            "md_section_header",
            "md_dashboard_owner",
            "md_contact_block",
            "md_requirements_link_block",
            "md_source_notes",
        ):
            bundle = generate_editor_bundle(
                widget_id=f"{family}_widget",
                route="editor_markdown",
                title="Metadata",
                family=family,
                markdown=content,
            )
            with self.subTest(family=family):
                self.assertEqual(bundle["generation_status"], "ready")
                self.assertIn(json.dumps(content), bundle["tabs"]["prepare.js"])
                self.assertNotIn("Short source and metric explanation.", bundle["tabs"]["prepare.js"])


if __name__ == "__main__":
    unittest.main()
