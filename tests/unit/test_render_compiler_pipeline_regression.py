import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.editor.bundle import generate_editor_bundle
from datalens_dev_mcp.editor.render_compiler import (
    RenderContractCompileError,
    compile_bundle_render_contract,
)
from datalens_dev_mcp.editor.render_contract import resolve_dashboard_render_contract
from datalens_dev_mcp.editor.standard_templates import required_source_columns
from datalens_dev_mcp.mcp.tools.pipeline import dl_generate_editor_bundle
from datalens_dev_mcp.runtime_resources import resource_json


PROFILE_V1 = "standard_editor_v1"
PROFILE_V2 = "standard_editor_v2"
TEMPLATE_SET_SHA256 = "6d35e7ae7e31ffb5677010b63e8e6d9455c8955a5b5f041e939281e0470a5da8"
FAMILY_V1_TAB_HASHES = {
    "kpi_value_only": "9fcd6b5e01d9f07ac79f1c7ceb1be7d74a5d378b8953b72fa846b96585c40020",
    "line_chart": "02f52f3c1eed2ed8bc5e084436065c729ea8bd6208ec103f607bca427a2bbb9d",
    "horizontal_bar": "19d0571d7718e59545359905f9720219a0f328bc569350d1bcc7b66ab2c6b736",
}
FAMILY_SOURCE_COLUMNS = {
    "kpi_value_only": ["current_value"],
    "line_chart": ["bucket", "value"],
    "horizontal_bar": ["label", "value"],
    "stacked_100": ["label", "value"],
    "waterfall": ["label", "value"],
}
RUNTIME_ROWS = {
    "kpi_value_only": [{"current_value": 1234}],
    "line_chart": [
        {"bucket": "2026-01", "metric": "value", "value": 10},
        {"bucket": "2026-02", "metric": "value", "value": 20},
    ],
    "horizontal_bar": [
        {"label": "Alpha category", "value": 10},
        {"label": "Beta category", "value": 5},
    ],
    "stacked_100": [
        {"label": "Alpha category", "value": 10},
        {"label": "Beta category", "value": 5},
    ],
    "waterfall": [
        {"label": "Alpha category", "value": 10},
        {"label": "Beta category", "value": -3},
    ],
}
SELECTOR_FAMILIES = {
    "single_select_dropdown",
    "multi_select_dropdown",
    "search_selector",
    "date_range_selector",
    "selector_family_static",
    "selector_family_dynamic",
}


class RenderCompilerPipelineRegressionTests(unittest.TestCase):
    def test_standard_editor_v1_tabs_remain_byte_identical_and_hash_locked(self):
        for family, expected_tabs_sha256 in FAMILY_V1_TAB_HASHES.items():
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_brief(root, family=family)
                generated = self._generate(
                    root,
                    family=family,
                    authoring_profile=PROFILE_V1,
                )
                direct = generate_editor_bundle(
                    widget_id="chart",
                    route="editor_advanced",
                    title="Synthetic chart",
                    dataset_alias="dataset",
                    columns=FAMILY_SOURCE_COLUMNS[family],
                    family=family,
                    visual_spec=generated["renderer_visual_spec"],
                    chart_decision_record=generated["chart_decision_record"],
                )

                self.assertEqual(generated["tabs"], direct["tabs"])
                self.assertEqual(_tabs_sha256(generated["tabs"]), expected_tabs_sha256)
                self.assertEqual(
                    generated["template_provenance"]["compiled_tabs_sha256"],
                    expected_tabs_sha256,
                )
                self.assertEqual(
                    generated["template_provenance"]["profile_template_set_sha256"],
                    TEMPLATE_SET_SHA256,
                )
                self.assertNotIn("render_contract", generated)
                self.assertNotIn(
                    "__dlGenerateProfileHtml",
                    generated["tabs"]["prepare.js"],
                )

    def test_standard_editor_v2_compiles_density_into_tabs_and_runtime_for_key_families(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for generated JavaScript validation")

        for family, base_tabs_sha256 in FAMILY_V1_TAB_HASHES.items():
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self._write_brief(root, family=family)
                compact = self._generate(
                    root,
                    family=family,
                    authoring_profile=PROFILE_V2,
                    render_overrides={"density": "compact"},
                )
                compact_repeat = self._generate(
                    root,
                    family=family,
                    authoring_profile=PROFILE_V2,
                    render_overrides={"density": "compact"},
                )
                comfortable = self._generate(
                    root,
                    family=family,
                    authoring_profile=PROFILE_V2,
                    render_overrides={"density": "comfortable"},
                )

                compact_hash = compact["template_provenance"]["compiled_tabs_sha256"]
                comfortable_hash = comfortable["template_provenance"]["compiled_tabs_sha256"]
                self.assertNotEqual(compact["tabs"], comfortable["tabs"])
                self.assertNotEqual(compact_hash, comfortable_hash)
                self.assertEqual(
                    compact["template_provenance"]["base_compiled_tabs_sha256"],
                    base_tabs_sha256,
                )
                self.assertEqual(
                    comfortable["template_provenance"]["base_compiled_tabs_sha256"],
                    base_tabs_sha256,
                )

                self.assertEqual(compact["tabs"], compact_repeat["tabs"])
                self.assertEqual(
                    compact["render_contract"],
                    compact_repeat["render_contract"],
                )
                self.assertEqual(
                    compact_hash,
                    compact_repeat["template_provenance"]["compiled_tabs_sha256"],
                )
                self.assertEqual(
                    compact["render_contract"]["composite_sha256"],
                    compact_repeat["render_contract"]["composite_sha256"],
                )

                self.assertEqual(
                    compact["render_contract"]["effective_tokens"]["density"]["mode"],
                    "compact",
                )
                self.assertEqual(
                    comfortable["render_contract"]["effective_tokens"]["density"]["mode"],
                    "comfortable",
                )
                self.assertNotEqual(
                    compact["render_contract"]["composite_sha256"],
                    comfortable["render_contract"]["composite_sha256"],
                )
                self.assertTrue(compact["render_contract_validation"]["ok"])
                self.assertTrue(comfortable["render_contract_validation"]["ok"])

                for generated in (compact, comfortable):
                    prepare = generated["tabs"]["prepare.js"]
                    encoded_contract = json.dumps(
                        generated["render_contract"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    self.assertIn(encoded_contract, prepare)
                    self.assertIn(
                        generated["render_contract"]["composite_sha256"],
                        prepare,
                    )
                    self.assertIn("__dlGenerateProfileHtml(options, ", prepare)
                    self.assertIn(
                        '"tooltip_comparison_mode":"single_period"',
                        prepare,
                    )
                    self.assertIn(
                        '"tooltip_period_source":"normalized"',
                        prepare,
                    )
                    self.assertEqual(
                        _tabs_sha256(generated["tabs"]),
                        generated["template_provenance"]["compiled_tabs_sha256"],
                    )
                    self._node_check(prepare, node=node, root=root)

                compact_html = self._execute_prepare(
                    compact["tabs"]["prepare.js"],
                    family=family,
                    node=node,
                    root=root,
                )
                comfortable_html = self._execute_prepare(
                    comfortable["tabs"]["prepare.js"],
                    family=family,
                    node=node,
                    root=root,
                )
                self.assertNotEqual(compact_html, comfortable_html)
                if family != "kpi_value_only":
                    self.assertIn("padding:9px 10px", compact_html)
                    self.assertIn("padding:11px 13px", comfortable_html)
                self.assert_runtime_tokens(
                    family=family,
                    compact_html=compact_html,
                    comfortable_html=comfortable_html,
                )

    def test_all_38_registered_families_compile_with_route_specific_contract_binding(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for generated JavaScript validation")
        registry = resource_json("templates/datalens/standard_chart_templates.json")
        families = registry["families"]
        self.assertEqual(len(families), 38)

        for family, family_spec in families.items():
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                route = family_spec["route"]
                self._write_brief(root, family=family, route=route)
                columns = list(required_source_columns(family))
                if family == "table_node":
                    columns = ["label", "value"]
                generated = dl_generate_editor_bundle(
                    project_root=str(root),
                    widget_id="chart",
                    authoring_profile=PROFILE_V2,
                    dataset_alias="dataset" if columns else "",
                    columns=columns or None,
                    selector_contract=(
                        self._complete_selector_contract(family)
                        if family in SELECTOR_FAMILIES
                        else None
                    ),
                )

                self.assertNotIn("error", generated, generated)
                self.assertEqual(generated["generation_status"], "ready")
                self.assertTrue(generated["render_contract_validation"]["ok"])
                marker = (
                    "resolved-render-contract:"
                    + generated["render_contract"]["composite_sha256"]
                )
                tabs = generated["tabs"]
                if route == "editor_advanced":
                    self.assertIn(marker, tabs["prepare.js"])
                    self.assertIn("__dlGenerateProfileHtml(options, ", tabs["prepare.js"])
                    self._node_check(tabs["prepare.js"], node=node, root=root)
                elif route == "editor_table":
                    self.assertIn(marker, tabs["prepare.js"])
                    self.assertIn(marker, tabs["config.js"])
                    self.assertIn(
                        "const __DL_RENDER_CONTRACT = Object.freeze(",
                        tabs["config.js"],
                    )
                    self.assertNotIn("__dlGenerateProfileHtml", tabs["prepare.js"])
                    self.assertNotIn("__dlGenerateProfileHtml", tabs["config.js"])
                    self._node_check(tabs["prepare.js"], node=node, root=root)
                    self._node_check(tabs["config.js"], node=node, root=root)
                elif route == "editor_markdown":
                    self.assertIn(marker, tabs["prepare.js"])
                    self.assertNotIn("__dlGenerateProfileHtml", tabs["prepare.js"])
                    self._node_check(tabs["prepare.js"], node=node, root=root)
                elif route == "editor_js_control":
                    controls = tabs["controls.js"]
                    self.assertIn(marker, controls)
                    self.assertIn(
                        "const __DL_RENDER_CONTRACT = Object.freeze(",
                        controls,
                    )
                    self.assertIn("labelPlacement: 'left'", controls)
                    self.assertIn("width: '94%'", controls)
                    self.assertIn("updateOnChange: true", controls)
                    self._node_check(controls, node=node, root=root)
                else:
                    self.fail(f"unexpected registered route: {route}")

    def test_time_series_legend_uses_only_active_filtered_series_and_contract_insets(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for generated JavaScript validation")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(root, family="line_chart")
            generated = self._generate(
                root,
                family="line_chart",
                authoring_profile=PROFILE_V2,
            )
            html = self._execute_prepare(
                generated["tabs"]["prepare.js"],
                family="line_chart",
                node=node,
                root=root,
                rows=[
                    {"bucket": "2026-01", "metric": "success", "value": 5},
                    {"bucket": "2026-01", "metric": "zero", "value": 0},
                    {"bucket": "2026-01", "metric": "filtered", "value": None},
                ],
            )

        self.assertIn('data-series-policy="active_series_only"', html)
        self.assertIn('data-series-id="success" data-series-role="mark"', html)
        self.assertIn('data-series-id="zero" data-series-role="mark"', html)
        self.assertIn('data-series-id="success" data-series-role="legend"', html)
        self.assertIn('data-series-id="zero" data-series-role="legend"', html)
        self.assertNotIn('data-series-id="filtered"', html)
        self.assertIn('data-plot-area-policy="contract_insets"', html)
        self.assertIn('data-plot-inset-top="22"', html)
        self.assertIn('data-plot-inset-right="10"', html)
        self.assertIn('data-plot-inset-bottom="34"', html)
        self.assertIn(
            'data-role="plot-area" data-inset-top="22" '
            'data-inset-right="10" data-inset-bottom="34"',
            html,
        )

    def test_control_contract_enforcement_and_incomplete_input_status_are_preserved(self):
        family = "single_select_dropdown"
        complete_contract = self._complete_selector_contract(family)
        raw = generate_editor_bundle(
            widget_id="chart",
            route="editor_js_control",
            title="Synthetic chart",
            family=family,
            selector_contract=complete_contract,
        )
        raw["tabs"]["controls.js"] = raw["tabs"]["controls.js"].replace(
            "width: '94%'",
            "width: '100%'",
        )
        resolved = resolve_dashboard_render_contract(
            profile_id="standard_dashboard_v1",
            family=family,
        )
        with self.assertRaises(RenderContractCompileError):
            compile_bundle_render_contract(raw, render_contract=resolved)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(
                root,
                family=family,
                route="editor_js_control",
            )
            incomplete = dl_generate_editor_bundle(
                project_root=str(root),
                widget_id="chart",
                authoring_profile=PROFILE_V2,
            )

        self.assertNotIn("error", incomplete, incomplete)
        self.assertEqual(incomplete["generation_status"], "blocked_missing_input")
        self.assertTrue(incomplete["render_contract_validation"]["ok"])
        self.assertIn(
            "const __DL_RENDER_CONTRACT = Object.freeze(",
            incomplete["tabs"]["controls.js"],
        )

    def test_horizontal_scroll_adapter_marks_the_visible_overflow_container(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for generated JavaScript validation")
        family = "horizontal_bar"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_brief(root, family=family)
            generated = dl_generate_editor_bundle(
                project_root=str(root),
                widget_id="chart",
                authoring_profile=PROFILE_V2,
                dataset_alias="dataset",
                columns=FAMILY_SOURCE_COLUMNS[family],
                render_overrides={
                    "density": "compact",
                    "horizontal_adapter": "scroll",
                },
            )
            html = self._execute_prepare(
                generated["tabs"]["prepare.js"],
                family=family,
                node=node,
                root=root,
            )

        self.assertNotIn("error", generated, generated)
        self.assertTrue(generated["render_contract_validation"]["ok"])
        self.assertIn('data-component="horizontal_rank"', html)
        self.assertIn(
            "overflow-x:hidden;overflow-y:auto;scrollbar-gutter:stable;padding-right:4px",
            html,
        )
        self.assertIn("overflow-x:hidden;overflow-y:visible", html)
        self.assertEqual(html.count("scrollbar-gutter:stable"), 1)

    def test_native_tooltip_titles_keep_values_and_ranges_but_drop_label_only_duplicates(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for generated JavaScript validation")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meaningful_html: dict[str, str] = {}
            for family in ("stacked_100", "waterfall"):
                family_root = root / family
                self._write_brief(family_root, family=family)
                generated = self._generate(
                    family_root,
                    family=family,
                    authoring_profile=PROFILE_V2,
                )
                meaningful_html[family] = self._execute_prepare(
                    generated["tabs"]["prepare.js"],
                    family=family,
                    node=node,
                    root=family_root,
                )

            family = "horizontal_bar"
            family_root = root / family
            self._write_brief(family_root, family=family)
            generated = self._generate(
                family_root,
                family=family,
                authoring_profile=PROFILE_V2,
            )
            redundant_title_source = generated["tabs"]["prepare.js"].replace(
                '<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                "${esc(row.label)}</span>",
                '<span title="${esc(row.label)}" '
                'style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                "${esc(row.label)}</span>",
            )
            self.assertNotEqual(
                redundant_title_source,
                generated["tabs"]["prepare.js"],
            )
            sanitized_html = self._execute_prepare(
                redundant_title_source,
                family=family,
                node=node,
                root=family_root,
            )

        self.assertIn('title="Alpha category 10"', meaningful_html["stacked_100"])
        self.assertIn('title="Beta category 5"', meaningful_html["stacked_100"])
        self.assertIn('title="0 → 10"', meaningful_html["waterfall"])
        self.assertIn('title="10 → 7"', meaningful_html["waterfall"])
        self.assertNotIn('title="Alpha category"', sanitized_html)
        self.assertNotIn('title="Beta category"', sanitized_html)

    def assert_runtime_tokens(
        self,
        *,
        family: str,
        compact_html: str,
        comfortable_html: str,
    ) -> None:
        if family == "kpi_value_only":
            for html in (compact_html, comfortable_html):
                self.assertIn('data-role="kpi"', html)
                self.assertIn('data-role="kpi-value"', html)
                self.assertIn(
                    'data-tooltip-comparison-mode="single_period"',
                    html,
                )
                self.assertIn(
                    'data-tooltip-period-source="normalized"',
                    html,
                )
                self.assertIn("padding:11px 11px 7px 11px", html)
                self.assertIn("border:0", html)
                self.assertIn("border-radius:0", html)
                self.assertIn("outline:none", html)
                self.assertIn("box-shadow:none", html)
                self.assertIn("background:transparent", html)
                self.assertIn(
                    "padding:0;border:0;border-radius:0;outline:none;"
                    "box-shadow:none;background:transparent",
                    html,
                )
            self.assertIn(
                "font-size:31px;line-height:34px;font-weight:750",
                compact_html,
            )
            self.assertIn(
                "font-size:34px;line-height:38px;font-weight:750",
                comfortable_html,
            )
        elif family == "line_chart":
            for html in (compact_html, comfortable_html):
                self.assertIn("font-family:Inter,Arial,sans-serif", html)
                self.assertIn("line-height:16px", html)
                self.assertIn("#2B75E2", html)
        elif family == "horizontal_bar":
            for html in (compact_html, comfortable_html):
                self.assertIn(
                    "grid-template-columns:184px minmax(0,234px) 106px",
                    html,
                )
                self.assertIn('data-component="horizontal_rank"', html)
                self.assertIn("min-height:32px", html)
                self.assertIn("border-radius:0.75px", html)
                self.assertIn("-webkit-line-clamp:2", html)
                self.assertIn("font-size:12px;line-height:16px", html)
                self.assertNotIn('title="Alpha category"', html)
                self.assertNotIn('title="Beta category"', html)

    def _generate(
        self,
        root: Path,
        *,
        family: str,
        authoring_profile: str,
        render_overrides: dict | None = None,
    ) -> dict:
        generated = dl_generate_editor_bundle(
            project_root=str(root),
            widget_id="chart",
            authoring_profile=authoring_profile,
            dataset_alias="dataset",
            columns=FAMILY_SOURCE_COLUMNS[family],
            render_overrides=render_overrides,
        )
        self.assertNotIn("error", generated, generated)
        self.assertEqual(generated["family"], family)
        self.assertEqual(generated["generation_status"], "ready")
        return generated

    def _write_brief(
        self,
        root: Path,
        *,
        family: str,
        route: str = "editor_advanced",
    ) -> None:
        artifacts = root / "artifacts"
        artifacts.mkdir(parents=True)
        brief = {
            "dashboard_name": "Synthetic dashboard",
            "dashboard_type": "operational",
            "audience": ["operator"],
            "requirements": [{"text": "Show a synthetic metric"}],
            "data_contract": {"fields": []},
            "chart_decisions": [
                {
                    "decision_id": "chart",
                    "title": "Synthetic chart",
                    "family": family,
                    "route": route,
                    "renderer_visual_spec": {},
                    "chart_decision_record": {
                        "selected_family": family,
                        "selected_route": route,
                        "renderer_visual_spec": {},
                    },
                }
            ],
        }
        (artifacts / "dashboard_brief.json").write_text(
            json.dumps(brief),
            encoding="utf-8",
        )

    def _complete_selector_contract(self, family: str) -> dict:
        if family == "date_range_selector":
            return {
                "param": "period",
                "label": "Period",
                "option_source": "none",
                "default_values": ["__interval_2026-01-01_2026-01-31"],
                "reset_behavior": "initial",
            }
        if family == "selector_family_dynamic":
            return {
                "param": "state",
                "label": "State",
                "option_source": "dataset",
                "default_values": [],
                "reset_behavior": "empty",
            }
        return {
            "param": "state",
            "label": "State",
            "option_source": "static",
            "options": [
                {"title": "All", "value": "all"},
                {"title": "Open", "value": "open"},
            ],
            "default_values": ["all"],
            "reset_behavior": "initial",
        }

    def _node_check(self, source: str, *, node: str, root: Path) -> None:
        path = root / "syntax-check.js"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(path)],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def _execute_prepare(
        self,
        source: str,
        *,
        family: str,
        node: str,
        root: Path,
        rows: list[dict] | None = None,
    ) -> str:
        path = root / f"{family}-runtime.js"
        path.write_text(source, encoding="utf-8")
        script = (
            "global.Editor = {"
            "getLoadedData: () => ({rows: JSON.parse(process.argv[2])}),"
            "getParams: () => ({}),"
            "wrapFn: (spec) => spec,"
            "generateHtml: (html) => html"
            "};"
            "const prepared = require(process.argv[1]);"
            "const output = prepared.render.fn("
            "JSON.parse(process.argv[3]), ...prepared.render.args"
            ");"
            "process.stdout.write(String(output));"
        )
        result = subprocess.run(
            [
                node,
                "-e",
                script,
                str(path),
                json.dumps(rows if rows is not None else RUNTIME_ROWS[family]),
                json.dumps({"width": 600, "height": 300}),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


def _tabs_sha256(tabs: dict) -> str:
    canonical = json.dumps(
        tabs,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
