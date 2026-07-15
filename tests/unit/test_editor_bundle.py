import json
import tempfile
import unittest
from pathlib import Path


class EditorBundleTests(unittest.TestCase):
    def test_generates_route_specific_tabs_as_strings(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        table = generate_editor_bundle(
            widget_id="synthetic_table",
            route="editor_table",
            title="Synthetic Table",
            dataset_alias="synthetic_dataset",
            columns=["period", "value"],
        )
        markdown = generate_editor_bundle(
            widget_id="synthetic_notes",
            route="editor_markdown",
            title="Synthetic Notes",
            markdown="Synthetic methodology note.",
        )
        selector = generate_editor_bundle(
            widget_id="synthetic_selector",
            route="editor_js_control",
            title="Synthetic Selector",
            param="segment",
            options=["all", "new"],
        )

        self.assertEqual(table["entry_type"], "table_node")
        self.assertIn("config.js", table["tabs"])
        self.assertIn("module.exports = {head, rows", table["tabs"]["prepare.js"])
        self.assertEqual(markdown["entry_type"], "markdown_node")
        self.assertNotIn("config.js", markdown["tabs"])
        self.assertIn("module.exports = {markdown}", markdown["tabs"]["prepare.js"])
        self.assertEqual(selector["entry_type"], "control_node")
        self.assertIn("controls", selector["tabs"]["controls.js"])
        for bundle in (table, markdown, selector):
            self.assertTrue(all(isinstance(value, str) for value in bundle["tabs"].values()))

    def test_advanced_fallback_does_not_copy_gallery_demo_data(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle

        bundle = generate_editor_bundle(
            widget_id="synthetic_diagnostics",
            route="editor_advanced",
            title="Synthetic Diagnostics",
        )

        self.assertEqual(bundle["generation_status"], "blocked_missing_source_or_family")
        self.assertNotIn("source_example", bundle)
        self.assertNotIn("UNION ALL SELECT", bundle["tabs"]["sources.js"])
        self.assertNotIn("Static demo data", bundle["tabs"]["sources.js"])
        self.assertNotIn("source_plugin", bundle)
        self.assertNotIn("private-corpus", str(bundle))

    def test_payload_compiler_rejects_blocked_generated_source(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle
        from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload

        bundle = generate_editor_bundle(
            widget_id="orders_trend",
            route="editor_advanced",
            title="Orders Trend",
            family="line_chart",
        )

        with self.assertRaisesRegex(ValueError, "Provide dataset_alias"):
            compile_editor_payload(bundle, workbook_id="workbook_local_001")

    def test_payload_plan_reports_blocked_bundle_instead_of_compiling_it(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle
        from datalens_dev_mcp.mcp.tools.pipeline import dl_build_payload_plan

        bundle = generate_editor_bundle(
            widget_id="orders_trend",
            route="editor_advanced",
            title="Orders Trend",
            family="line_chart",
        )
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "dashboard" / "orders_trend"
            bundle_dir.mkdir(parents=True)
            (bundle_dir / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

            plan = dl_build_payload_plan(tmp, workbook_id="workbook_local_001")

            self.assertEqual(plan["status"], "blocked")
            self.assertEqual(plan["payloads"], [])
            self.assertEqual(plan["blocking_issues"][0]["widget_id"], "orders_trend")
            self.assertIn("dataset_alias", plan["blocking_issues"][0]["action"])
            self.assertFalse((Path(tmp) / "artifacts" / "payloads" / "orders_trend.payload.json").exists())

    def test_cyrillic_display_titles_get_distinct_ascii_internal_names(self):
        from datalens_dev_mcp.editor.bundle import generate_editor_bundle
        from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload

        names = []
        for widget_id, title in (
            ("sales_widget", "Продажи по регионам"),
            ("revenue_widget", "Выручка по регионам"),
        ):
            bundle = generate_editor_bundle(
                widget_id=widget_id,
                route="editor_advanced",
                title=title,
                family="line_chart",
                dataset_alias="metrics_dataset",
                columns=["bucket", "value"],
            )
            payload = compile_editor_payload(bundle, workbook_id="workbook_local_001")
            self.assertEqual(bundle["display_title"], title)
            self.assertRegex(payload["entry"]["name"], r"^[a-z0-9_-]+$")
            names.append(payload["entry"]["name"])

        self.assertNotEqual(names[0], names[1])
        self.assertIn("prodazhi_po_regionam", names[0])
        self.assertIn("vyruchka_po_regionam", names[1])

    def test_payload_compiler_preserves_editor_entry_subtree(self):
        from datalens_dev_mcp.editor.payload_compiler import compile_editor_payload

        bundle = {
            "widget_id": "synthetic_kpi",
            "route": "editor_advanced",
            "entry_type": "advanced-chart_node",
            "name": "js - kpi synthetic value",
            "tabs": {
                "meta.json": '{"links":{}}',
                "params.js": "module.exports = {};",
                "sources.js": "module.exports = {};",
                "controls.js": "module.exports = {};",
                "prepare.js": "module.exports = {render: () => ''};",
            },
        }

        payload = compile_editor_payload(bundle, workbook_id="workbook_local_001")

        self.assertEqual(payload["entry"]["type"], "advanced-chart_node")
        self.assertEqual(payload["entry"]["data"]["prepare"], "module.exports = {render: () => ''};")
        self.assertEqual(payload["mode"], "save")


if __name__ == "__main__":
    unittest.main()
