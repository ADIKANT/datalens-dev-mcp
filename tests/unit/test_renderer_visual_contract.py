import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from datalens_dev_mcp.editor.bundle import generate_editor_bundle
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from scripts.run_visual_runtime_contract_sweep import rendered_geometry_issues


ROOT = Path(__file__).resolve().parents[2]
NODE_RENDER_SCRIPT = r"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
global.Editor = {
  getLoadedData: () => ({rows: payload.rows}),
  getParams: () => ({}),
  wrapFn: (value) => value,
  generateHtml: (value) => value,
};
const moduleObject = {exports: {}};
new Function('module', 'exports', 'Editor', payload.source)(
  moduleObject,
  moduleObject.exports,
  global.Editor,
);
const renderer = moduleObject.exports.render;
process.stdout.write(renderer.fn(
  {width: payload.width, height: payload.height},
  ...renderer.args,
));
"""


def render_advanced_family(family, rows, *, width=560, height=320):
    bundle = generate_editor_bundle(
        widget_id=f"visual_regression_{family}",
        route="editor_advanced",
        title=family,
        family=family,
        source_mode="golden_fixture",
    )
    return subprocess.run(
        [shutil.which("node"), "-e", NODE_RENDER_SCRIPT],
        input=json.dumps(
            {
                "source": bundle["tabs"]["prepare.js"],
                "rows": rows,
                "width": width,
                "height": height,
            }
        ),
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )


class RendererVisualContractTests(unittest.TestCase):
    def test_generated_bundles_do_not_emit_decorative_css_or_duplicate_title_hints(self):
        for family in ("kpi_value_only", "line_chart", "horizontal_bar"):
            with self.subTest(family=family):
                bundle = generate_editor_bundle(
                    widget_id=family,
                    route="editor_advanced",
                    title=family,
                    family=family,
                )
                joined = "\n".join(str(value) for value in bundle["tabs"].values())

                self.assertNotIn("box-shadow", joined)
                self.assertNotIn("drop-shadow", joined)
                self.assertNotIn('data-id="hint"', joined)
                self.assertNotIn("data.title", joined)
                result = validate_editor_runtime_contract({"tabs": bundle["tabs"]}, source=family, allow_unknown_warnings=True)
                self.assertTrue(result["ok"], json.dumps(result["findings"], indent=2))

    def test_table_bundle_uses_native_bar_contract(self):
        bundle = generate_editor_bundle(
            widget_id="table",
            route="editor_table",
            title="Table",
            family="table_node",
            columns=["name", "value"],
        )
        prepare = bundle["tabs"]["prepare.js"]

        self.assertIn("type: 'bar'", prepare)
        self.assertIn("barColor", prepare)
        self.assertNotRegex(prepare, r"<div[^>]+width\s*:")

    def test_visual_runtime_contract_sweep_passes(self):
        completed = subprocess.run(
            [sys.executable, "scripts/run_visual_runtime_contract_sweep.py", "--strict"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary["responsive_static_bundle_count"], 25)
        if shutil.which("node"):
            expected_pairs = {
                (width, height)
                for width in (236, 360, 530, 560, 700, 900)
                for height in (220, 320, 420)
            }
            self.assertEqual(summary["responsive_probe_count"], 25 * len(expected_pairs))
            self.assertTrue(
                all(item["status"] == "passed" for item in summary["responsive_probe_results"]),
                summary["responsive_probe_results"],
            )
            for item in summary["responsive_probe_results"]:
                actual_pairs = {
                    (probe["width"], probe["height"])
                    for probe in item["probes"]
                }
                self.assertEqual(actual_pairs, expected_pairs, item["family"])

    def test_time_series_preserves_internal_null_gap_and_trims_future_null_bucket(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        bundle = generate_editor_bundle(
            widget_id="null_gap",
            route="editor_advanced",
            title="Null gap",
            family="line_chart",
            source_mode="golden_fixture",
        )
        script = r"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
global.Editor = {
  getLoadedData: () => ({rows: payload.rows}),
  getParams: () => ({}),
  wrapFn: (value) => value,
  generateHtml: (value) => value,
};
const moduleObject = {exports: {}};
new Function('module', 'exports', 'Editor', payload.source)(
  moduleObject,
  moduleObject.exports,
  global.Editor,
);
const renderer = moduleObject.exports.render;
process.stdout.write(renderer.fn({width: 560, height: 320}, ...renderer.args));
"""
        completed = subprocess.run(
            [node, "-e", script],
            input=json.dumps(
                {
                    "source": bundle["tabs"]["prepare.js"],
                    "rows": [
                        {"bucket": "2026-01", "metric": "Value", "value": 1},
                        {"bucket": "2026-02", "metric": "Value", "value": None},
                        {"bucket": "2026-03", "metric": "Value", "value": 3},
                        {"bucket": "2026-04", "metric": "Value", "value": None},
                    ],
                }
            ),
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        paths = re.findall(r'<path d="([^"]+)" fill="none"', completed.stdout)
        self.assertEqual(len(paths), 2, completed.stdout)
        self.assertTrue(all(" L" not in path for path in paths), paths)
        self.assertNotIn("04.26", completed.stdout)

    def test_signed_numeric_domains_render_inside_the_viewport(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = r"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
global.Editor = {
  getLoadedData: () => ({rows: payload.rows}),
  getParams: () => ({}),
  wrapFn: (value) => value,
  generateHtml: (value) => value,
};
const moduleObject = {exports: {}};
new Function('module', 'exports', 'Editor', payload.source)(
  moduleObject,
  moduleObject.exports,
  global.Editor,
);
const renderer = moduleObject.exports.render;
process.stdout.write(renderer.fn({width: 560, height: 320}, ...renderer.args));
"""

        def render(family, rows):
            bundle = generate_editor_bundle(
                widget_id=f"signed_{family}",
                route="editor_advanced",
                title=family,
                family=family,
                source_mode="golden_fixture",
            )
            return subprocess.run(
                [node, "-e", script],
                input=json.dumps({"source": bundle["tabs"]["prepare.js"], "rows": rows}),
                cwd=ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

        time_chart = render(
            "vertical_bar_time_bucket",
            [
                {"bucket": "2026-01", "metric": "Value", "value": -5},
                {"bucket": "2026-02", "metric": "Value", "value": 10},
            ],
        )
        comparison = render(
            "horizontal_bar",
            [
                {"label": "Negative", "group": "All", "value": -8, "target": -4},
                {"label": "Positive", "group": "All", "value": 12, "target": 10},
            ],
        )
        scatter = render(
            "scatter",
            [
                {"label": "A", "x": -10, "y": -4},
                {"label": "B", "x": 20, "y": 8},
            ],
        )

        for completed in (time_chart, comparison, scatter):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotRegex(completed.stdout, r'(?:height|width|cx|cy)="-[0-9]')
        circles = re.findall(r'<circle cx="([0-9.]+)" cy="([0-9.]+)"', scatter.stdout)
        self.assertEqual(len(circles), 2, scatter.stdout)
        self.assertTrue(all(0 <= float(cx) <= 560 and 0 <= float(cy) <= 320 for cx, cy in circles), circles)

    def test_signed_time_bucket_totals_define_bar_domain(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        rows = [
            {"bucket": "A", "metric": "m1", "value": 10},
            {"bucket": "A", "metric": "m2", "value": 10},
            {"bucket": "B", "metric": "m1", "value": -10},
            {"bucket": "B", "metric": "m2", "value": -10},
        ]
        for family in ("vertical_bar_time_bucket", "combo_time_series_combo"):
            with self.subTest(family=family):
                completed = render_advanced_family(family, rows)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                view_box = re.search(
                    r'<svg[^>]*viewBox="0 0 ([0-9.]+) ([0-9.]+)"',
                    completed.stdout,
                )
                self.assertIsNotNone(view_box, completed.stdout)
                view_width, view_height = map(float, view_box.groups())
                rectangles = [
                    tuple(map(float, values))
                    for values in re.findall(
                        r'<rect x="([0-9.-]+)" y="([0-9.-]+)" '
                        r'width="([0-9.-]+)" height="([0-9.-]+)"',
                        completed.stdout,
                    )
                ]
                self.assertEqual(len(rectangles), 2, completed.stdout)
                for x, y, width, height in rectangles:
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + width, view_width + 1e-6)
                    self.assertLessEqual(y + height, view_height + 1e-6)

    def test_bubble_extrema_reserve_their_radius_inside_viewport(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        rows = [
            {"label": "min", "x": -10, "y": -4, "size": 1},
            {"label": "max", "x": 20, "y": 8, "size": 100},
        ]
        for width, height in ((236, 220), (560, 320)):
            with self.subTest(width=width, height=height):
                completed = render_advanced_family(
                    "bubble",
                    rows,
                    width=width,
                    height=height,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                circles = [
                    tuple(map(float, values))
                    for values in re.findall(
                        r'<circle cx="([0-9.-]+)" cy="([0-9.-]+)" r="([0-9.-]+)"',
                        completed.stdout,
                    )
                ]
                self.assertEqual(len(circles), 2, completed.stdout)
                for cx, cy, radius in circles:
                    self.assertGreaterEqual(cx - radius, 0)
                    self.assertGreaterEqual(cy - radius, 0)
                    self.assertLessEqual(cx + radius, width + 1e-6)
                    self.assertLessEqual(cy + radius, height + 1e-6)

    def test_part_whole_dasharrays_use_normalized_path_length(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        rows = [{"label": "A", "value": 50}, {"label": "B", "value": 50}]
        for family in ("pie", "donut"):
            with self.subTest(family=family):
                completed = render_advanced_family(family, rows)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                slice_circles = [
                    attributes
                    for attributes in re.findall(r"<circle\b([^>]*)>", completed.stdout)
                    if "stroke-dasharray=" in attributes
                ]
                self.assertEqual(len(slice_circles), 2, completed.stdout)
                for attributes in slice_circles:
                    self.assertIn('pathLength="100"', attributes)
                    dasharray = re.search(r'stroke-dasharray="([0-9.]+) ([0-9.]+)"', attributes)
                    self.assertIsNotNone(dasharray, attributes)
                    self.assertAlmostEqual(sum(map(float, dasharray.groups())), 100)

    def test_waterfall_preserves_step_order_and_uses_cumulative_geometry(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        completed = render_advanced_family(
            "waterfall",
            [
                {"label": "step-1", "value": 10},
                {"label": "step-2", "value": -100},
                {"label": "step-3", "value": 20},
            ],
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertLess(completed.stdout.index("step-1"), completed.stdout.index("step-2"))
        self.assertLess(completed.stdout.index("step-2"), completed.stdout.index("step-3"))
        bars = [
            tuple(map(float, values))
            for values in re.findall(
                r'<i title="[^"]+" style="position:absolute;display:block;'
                r'left:([0-9.]+)%;height:12px;width:([0-9.]+)%',
                completed.stdout,
            )
        ]
        self.assertEqual(bars, [(90.0, 10.0), (0.0, 100.0), (0.0, 20.0)])
        self.assertTrue(all(left >= 0 and width >= 0 and left + width <= 100 for left, width in bars))
        cumulative_labels = re.findall(
            r'<b style="text-align:right;">([^<]+)</b>',
            completed.stdout,
        )
        self.assertEqual(cumulative_labels, ["10", "-90", "-70"])

    def test_rendered_geometry_gate_detects_static_overflow_classes(self):
        html = (
            '<div style="left:35%;width:70%;">NaN</div>'
            '<svg viewBox="0 0 100 100">'
            '<rect x="90" y="0" width="20" height="10"/>'
            '<circle cx="95" cy="5" r="10"></circle>'
            '<circle cx="50" cy="50" r="10" stroke-dasharray="50 50"></circle>'
            "</svg>"
        )
        issues = rendered_geometry_issues(
            family="pie",
            html=html,
            path="synthetic",
            probe="100x100",
        )
        self.assertEqual(
            {issue["rule"] for issue in issues},
            {
                "responsive_render_nonfinite_geometry",
                "responsive_percent_geometry_out_of_bounds",
                "responsive_svg_rect_out_of_bounds",
                "responsive_svg_circle_out_of_bounds",
                "responsive_part_whole_path_length_missing",
            },
        )


if __name__ == "__main__":
    unittest.main()
