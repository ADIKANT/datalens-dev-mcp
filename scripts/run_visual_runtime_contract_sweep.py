#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
ARTIFACT_DIR = ROOT / "artifacts" / "visual_runtime_contract"

UNRESOLVED_IMPORT_RE = re.compile(r"require\(['\"]\.\./_shared/")
DECORATIVE_CSS_RE = re.compile(r"(box-shadow|text-shadow|filter\s*:\s*drop-shadow|linear-gradient|radial-gradient)", re.I)
STALE_KPI_RE = re.compile(r"(previous_value|previous_period|previousPeriod|period_bucket|delta_pct)")
FORBIDDEN_HTML_RE = re.compile(r"<\s*/?\s*(section|script|iframe|object|embed)\b|\son[a-z]+\s*=|\ssrcdoc\s*=", re.I)
LOCKED_TEMPLATE_RULE_EXCEPTIONS = {
    "templates/datalens/authoring_profiles/charging_v2_exact/advanced_editor_runtime.js": {
        "sha256": "5f37bbd6a7012e90d0567787f006629019a852623b833eb112debe5f8f50ebf3",
        # The immutable runtime exposes an explicit previous-period selector;
        # this is not an inferred KPI comparator. Every other sweep rule still
        # applies, and a byte change is itself a blocking issue.
        "rules": {"stale_implicit_kpi_comparator"},
    },
}
FIXED_RESPONSIVE_MIN_PATTERNS = (
    re.compile(r"min-width\s*:\s*[1-9]\d*(?:\.\d+)?px", re.I),
    re.compile(r"grid-template-columns\s*:[^;\"']*minmax\(\s*[1-9]\d*(?:\.\d+)?px", re.I),
    re.compile(
        r"Math\.max\(\s*[1-9]\d*(?:\.\d+)?\s*,\s*Number\(options\s*&&\s*options\.(?:width|height)\)",
        re.I,
    ),
)
RESPONSIVE_ADVANCED_FAMILIES = (
    "kpi_value_only",
    "kpi_value_delta",
    "kpi_value_sparkline",
    "kpi_value_delta_sparkline",
    "line_chart",
    "multiline_chart",
    "area_completion",
    "vertical_bar_time_bucket",
    "combo_time_series_combo",
    "horizontal_bar",
    "grouped_bar",
    "stacked_100",
    "bullet_assignees",
    "heatmap",
    "waterfall",
    "funnel_snapshot",
    "pie",
    "donut",
    "treemap",
    "sankey_status_flow",
    "histogram",
    "box_plot",
    "scatter",
    "bubble",
    "resource_schedule_exception",
)
RESPONSIVE_PROBE_WIDTHS = (236, 360, 530, 560, 700, 900)
RESPONSIVE_PROBE_HEIGHTS = (220, 320, 420)
HTML_ATTRIBUTE_RE = re.compile(r"\b([A-Za-z_:][\w:.-]*)\s*=\s*\"([^\"]*)\"")
STYLE_ATTRIBUTE_RE = re.compile(r"\bstyle\s*=\s*\"([^\"]*)\"", re.I)
SVG_RE = re.compile(r"<svg\b([^>]*)>(.*?)</svg>", re.I | re.S)
RECT_RE = re.compile(r"<rect\b([^>]*)/?>", re.I)
CIRCLE_RE = re.compile(r"<circle\b([^>]*)/?>", re.I)
NONFINITE_RENDER_RE = re.compile(r"(?<![\w.])(?:NaN|[+-]?Infinity)(?![\w.])")
NODE_RESPONSIVE_PROBE = r"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
global.Editor = {
  getLoadedData: () => ({rows: payload.rows}),
  getParams: () => payload.params,
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
if (!renderer || typeof renderer.fn !== 'function' || !Array.isArray(renderer.args)) {
  throw new Error('generated renderer does not expose the expected wrapFn contract');
}
const outputs = payload.probes.map((probe) => ({
  width: probe.width,
  height: probe.height,
  html: renderer.fn({width: probe.width, height: probe.height}, ...renderer.args),
}));
process.stdout.write(JSON.stringify(outputs));
"""


def _html_attributes(fragment: str) -> dict[str, str]:
    return {
        name.lower(): value
        for name, value in HTML_ATTRIBUTE_RE.findall(fragment)
    }


def _finite_number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percent(value: str | None) -> float | None:
    if value is None or not value.strip().endswith("%"):
        return None
    return _finite_number(value.strip()[:-1])


def rendered_geometry_issues(
    *,
    family: str,
    html: str,
    path: str,
    probe: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def add(rule: str, token: str) -> None:
        issues.append({"rule": rule, "path": path, "line": 1, "token": f"{probe}: {token}"})

    nonfinite = NONFINITE_RENDER_RE.search(html)
    if nonfinite:
        add("responsive_render_nonfinite_geometry", nonfinite.group(0))

    for style_text in STYLE_ATTRIBUTE_RE.findall(html):
        properties: dict[str, str] = {}
        for declaration in style_text.split(";"):
            key, separator, value = declaration.partition(":")
            if separator:
                properties[key.strip().lower()] = value.strip()
        left = _percent(properties.get("left"))
        if left is None:
            left = _percent(properties.get("margin-left"))
        width = _percent(properties.get("width"))
        if left is not None and width is not None:
            if left < -1e-6 or width < -1e-6 or left + width > 100 + 1e-6:
                add(
                    "responsive_percent_geometry_out_of_bounds",
                    f"left={left:g}% width={width:g}%",
                )

    for svg_index, svg_match in enumerate(SVG_RE.finditer(html), start=1):
        svg_attributes = _html_attributes(svg_match.group(1))
        view_box = [
            _finite_number(value)
            for value in (svg_attributes.get("viewbox") or "").replace(",", " ").split()
        ]
        if len(view_box) != 4 or any(value is None for value in view_box):
            continue
        view_x, view_y, view_width, view_height = (float(value) for value in view_box)
        if view_width <= 0 or view_height <= 0:
            add(
                "responsive_svg_invalid_viewbox",
                f"svg={svg_index} viewBox={svg_attributes.get('viewbox')}",
            )
            continue
        view_right = view_x + view_width
        view_bottom = view_y + view_height
        body = svg_match.group(2)

        for rect_index, rect_match in enumerate(RECT_RE.finditer(body), start=1):
            attributes = _html_attributes(rect_match.group(1))
            values = {
                name: _finite_number(attributes.get(name))
                for name in ("x", "y", "width", "height")
            }
            if any(value is None for value in values.values()):
                continue
            x = float(values["x"])
            y = float(values["y"])
            width = float(values["width"])
            height = float(values["height"])
            if (
                width < -1e-6
                or height < -1e-6
                or x < view_x - 1e-6
                or y < view_y - 1e-6
                or x + width > view_right + 1e-6
                or y + height > view_bottom + 1e-6
            ):
                add(
                    "responsive_svg_rect_out_of_bounds",
                    (
                        f"svg={svg_index} rect={rect_index} "
                        f"x={x:g} y={y:g} width={width:g} height={height:g} "
                        f"viewBox={view_x:g} {view_y:g} {view_width:g} {view_height:g}"
                    ),
                )

        for circle_index, circle_match in enumerate(CIRCLE_RE.finditer(body), start=1):
            attributes = _html_attributes(circle_match.group(1))
            cx = _finite_number(attributes.get("cx"))
            cy = _finite_number(attributes.get("cy"))
            radius = _finite_number(attributes.get("r"))
            if cx is None or cy is None or radius is None:
                continue
            stroke_width = _finite_number(attributes.get("stroke-width")) or 0
            effective_radius = radius + max(0, stroke_width) / 2
            if (
                radius < -1e-6
                or cx - effective_radius < view_x - 1e-6
                or cy - effective_radius < view_y - 1e-6
                or cx + effective_radius > view_right + 1e-6
                or cy + effective_radius > view_bottom + 1e-6
            ):
                add(
                    "responsive_svg_circle_out_of_bounds",
                    (
                        f"svg={svg_index} circle={circle_index} "
                        f"cx={cx:g} cy={cy:g} r={radius:g} stroke_width={stroke_width:g} "
                        f"viewBox={view_x:g} {view_y:g} {view_width:g} {view_height:g}"
                    ),
                )
            if family in {"pie", "donut"} and "stroke-dasharray" in attributes:
                path_length = _finite_number(attributes.get("pathlength"))
                if path_length is None or not math.isclose(path_length, 100, rel_tol=0, abs_tol=1e-6):
                    add(
                        "responsive_part_whole_path_length_missing",
                        f"svg={svg_index} circle={circle_index} pathLength={attributes.get('pathlength')}",
                    )

    return issues


def iter_template_files() -> list[Path]:
    roots = [
        ROOT / "templates",
        ROOT / "src" / "datalens_dev_mcp" / "assets" / "templates",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".js", ".json", ".md"}
            )
    return sorted(files)


def text_issues(path: Path, text: str) -> list[dict[str, Any]]:
    issues = []
    rel = path.relative_to(ROOT).as_posix() if path.is_absolute() else path.as_posix()
    locked_exception = next(
        (
            value
            for suffix, value in LOCKED_TEMPLATE_RULE_EXCEPTIONS.items()
            if rel.endswith(suffix)
        ),
        None,
    )
    excepted_rules: set[str] = set()
    if locked_exception:
        actual_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual_sha256 != locked_exception["sha256"]:
            issues.append(
                {
                    "rule": "locked_authoring_profile_asset_hash_mismatch",
                    "path": rel,
                    "line": 1,
                    "token": actual_sha256,
                }
            )
        else:
            excepted_rules = set(locked_exception["rules"])
    checks = [
        ("unresolved_local_shared_require", UNRESOLVED_IMPORT_RE),
        ("decorative_css_token", DECORATIVE_CSS_RE),
        ("stale_implicit_kpi_comparator", STALE_KPI_RE),
        ("forbidden_advanced_editor_markup", FORBIDDEN_HTML_RE),
    ]
    for rule, pattern in checks:
        if rule in excepted_rules:
            continue
        for match in pattern.finditer(text):
            issues.append(
                {
                    "rule": rule,
                    "path": rel,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "token": match.group(0),
                }
            )
    return issues


def build_generated_bundles() -> list[dict[str, Any]]:
    from datalens_dev_mcp.editor.bundle import generate_editor_bundle
    from datalens_dev_mcp.pipeline.wizard_templates import build_wizard_payload_plan

    bundles = [
        generate_editor_bundle(
            widget_id="native_table",
            route="editor_table",
            title="Native Table",
            family="table_node",
            columns=["name", "value"],
            source_mode="golden_fixture",
        ),
        generate_editor_bundle(
            widget_id="markdown",
            route="editor_markdown",
            title="Notes",
            family="md_methodology_block",
            source_mode="golden_fixture",
        ),
        generate_editor_bundle(
            widget_id="control",
            route="editor_js_control",
            title="Selector",
            family="single_select_dropdown",
            param="segment",
            options=["all", "core"],
            source_mode="golden_fixture",
        ),
    ]
    bundles.extend(
        generate_editor_bundle(
            widget_id=f"responsive_{family}",
            route="editor_advanced",
            title=family,
            family=family,
            source_mode="golden_fixture",
        )
        for family in RESPONSIVE_ADVANCED_FAMILIES
    )
    bundles.append(build_wizard_payload_plan())
    return bundles


def generated_issues(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract

    issues = []
    name = str(bundle.get("widget_id") or bundle.get("template_name") or "generated")
    tabs = bundle.get("tabs") if isinstance(bundle.get("tabs"), dict) else {}
    for tab_name, text in tabs.items():
        if isinstance(text, str):
            issues.extend(text_issues(Path(f"generated/{name}/{tab_name}"), text))
    if bundle.get("route") == "editor_table":
        prepare = str(tabs.get("prepare.js") or "")
        if "type: 'bar'" not in prepare and '"type": "bar"' not in prepare:
            issues.append({"rule": "native_table_bar_missing", "path": f"generated/{name}/prepare.js", "line": 1, "token": ""})
        if re.search(r"<div[^>]+width\s*:", prepare):
            issues.append({"rule": "custom_html_table_bar", "path": f"generated/{name}/prepare.js", "line": 1, "token": "<div width>"})
    if bundle.get("route") == "editor_advanced":
        prepare = str(tabs.get("prepare.js") or "")
        if "Editor.wrapFn" not in prepare or "Editor.generateHtml" not in prepare:
            issues.append({"rule": "missing_editor_runtime_wrapper", "path": f"generated/{name}/prepare.js", "line": 1, "token": ""})
        if bundle.get("family") in RESPONSIVE_ADVANCED_FAMILIES:
            for dimension in ("width", "height"):
                if f"options && options.{dimension}" not in prepare:
                    issues.append(
                        {
                            "rule": "responsive_options_dimension_missing",
                            "path": f"generated/{name}/prepare.js",
                            "line": 1,
                            "token": dimension,
                        }
                    )
            for pattern in FIXED_RESPONSIVE_MIN_PATTERNS:
                match = pattern.search(prepare)
                if match:
                    issues.append(
                        {
                            "rule": "fixed_responsive_minimum",
                            "path": f"generated/{name}/prepare.js",
                            "line": prepare.count("\n", 0, match.start()) + 1,
                            "token": match.group(0),
                        }
                    )
            probes = (
                (bundle.get("renderer_visual_spec") or {})
                .get("responsive_layout", {})
                .get("widget_width_probes_px", [])
            )
            if list(probes) != list(RESPONSIVE_PROBE_WIDTHS):
                issues.append(
                    {
                        "rule": "responsive_visual_spec_probe_mismatch",
                        "path": f"generated/{name}/params.js",
                        "line": 1,
                        "token": json.dumps(probes),
                    }
                )
    runtime = validate_editor_runtime_contract({"tabs": tabs}, source=f"generated/{name}", allow_unknown_warnings=True)
    for finding in runtime.get("findings") or []:
        if finding.get("severity") == "error":
            issues.append(
                {
                    "rule": f"editor_runtime_{finding.get('rule')}",
                    "path": finding.get("path"),
                    "line": finding.get("line"),
                    "token": finding.get("message"),
                }
            )
    return issues


def responsive_probe_result(bundle: dict[str, Any]) -> dict[str, Any]:
    family = str(bundle.get("family") or "")
    if family not in RESPONSIVE_ADVANCED_FAMILIES:
        return {"family": family, "status": "not_applicable", "probes": [], "issues": []}
    node = shutil.which("node")
    if not node:
        return {"family": family, "status": "unavailable", "probes": [], "issues": []}
    source_template = ROOT / str(bundle.get("source_template") or "")
    fixture = json.loads((source_template / "example_input.json").read_text(encoding="utf-8"))
    params = json.loads((source_template / "params.json").read_text(encoding="utf-8"))
    rows = fixture.get("rows")
    if not isinstance(rows, list):
        rows = fixture.get("links")
    if not isinstance(rows, list):
        rows = []
    probes = [
        {"width": width, "height": height}
        for width in RESPONSIVE_PROBE_WIDTHS
        for height in RESPONSIVE_PROBE_HEIGHTS
    ]
    completed = subprocess.run(
        [node, "-e", NODE_RESPONSIVE_PROBE],
        input=json.dumps(
            {
                "source": str((bundle.get("tabs") or {}).get("prepare.js") or ""),
                "rows": rows,
                "params": params,
                "probes": probes,
            }
        ),
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    if completed.returncode != 0:
        return {
            "family": family,
            "status": "failed",
            "probes": [],
            "issues": [
                {
                    "rule": "responsive_runtime_probe_failed",
                    "path": f"generated/{bundle.get('widget_id')}/prepare.js",
                    "line": 1,
                    "token": completed.stderr.strip()[:1000],
                }
            ],
        }
    try:
        outputs = json.loads(completed.stdout)
    except json.JSONDecodeError:
        outputs = []
    issues: list[dict[str, Any]] = []
    probe_evidence: list[dict[str, Any]] = []
    generated_path = f"generated/{bundle.get('widget_id')}/prepare.js"
    for output in outputs if isinstance(outputs, list) else []:
        html = output.get("html") if isinstance(output, dict) else None
        width = output.get("width") if isinstance(output, dict) else None
        height = output.get("height") if isinstance(output, dict) else None
        if not isinstance(html, str) or not html.strip():
            issues.append(
                {
                    "rule": "responsive_runtime_probe_empty",
                    "path": generated_path,
                    "line": 1,
                    "token": f"{width}x{height}",
                }
            )
            continue
        for pattern in FIXED_RESPONSIVE_MIN_PATTERNS[:2]:
            match = pattern.search(html)
            if match:
                issues.append(
                    {
                        "rule": "rendered_fixed_responsive_minimum",
                        "path": generated_path,
                        "line": 1,
                        "token": f"{width}x{height}: {match.group(0)}",
                    }
                )
        issues.extend(
            rendered_geometry_issues(
                family=family,
                html=html,
                path=generated_path,
                probe=f"{width}x{height}",
            )
        )
        encoded = html.encode("utf-8")
        probe_evidence.append(
            {
                "width": width,
                "height": height,
                "serialized_bytes": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
    expected_pairs = {
        (width, height)
        for width in RESPONSIVE_PROBE_WIDTHS
        for height in RESPONSIVE_PROBE_HEIGHTS
    }
    actual_pairs = {
        (item["width"], item["height"])
        for item in probe_evidence
    }
    if len(probe_evidence) != len(expected_pairs) or actual_pairs != expected_pairs:
        issues.append(
            {
                "rule": "responsive_runtime_probe_matrix_coverage",
                "path": generated_path,
                "line": 1,
                "token": f"{len(actual_pairs)}/{len(expected_pairs)} width-height pairs",
            }
        )
    if len({item["sha256"] for item in probe_evidence}) < 2:
        issues.append(
            {
                "rule": "responsive_runtime_probe_no_layout_change",
                "path": generated_path,
                "line": 1,
                "token": "compact and wide probes rendered identical HTML",
            }
        )
    return {
        "family": family,
        "status": "passed" if not issues else "failed",
        "probes": probe_evidence,
        "issues": issues,
    }


def run_sweep() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    template_issues: list[dict[str, Any]] = []
    checked_templates = iter_template_files()
    for path in checked_templates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        template_issues.extend(text_issues(path, text))

    bundles = build_generated_bundles()
    generated_all_issues = []
    for bundle in bundles:
        generated_all_issues.extend(generated_issues(bundle))
    responsive_results = [
        responsive_probe_result(bundle)
        for bundle in bundles
        if bundle.get("family") in RESPONSIVE_ADVANCED_FAMILIES
    ]
    for result in responsive_results:
        generated_all_issues.extend(result["issues"])

    generated_path = ARTIFACT_DIR / "generated_bundles.json"
    generated_path.write_text(json.dumps(bundles, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    issues = template_issues + generated_all_issues
    summary = {
        "ok": not issues,
        "checked_template_files": len(checked_templates),
        "generated_bundle_count": len(bundles),
        "responsive_static_bundle_count": len(responsive_results),
        "responsive_probe_count": sum(len(item["probes"]) for item in responsive_results),
        "responsive_probe_results": responsive_results,
        "issues": issues,
        "artifacts": {
            "generated_bundles": str(generated_path.relative_to(ROOT)),
        },
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run visual runtime contract sweep over templates and generated bundles.")
    parser.add_argument("--strict", action="store_true", help="Fail on any issue.")
    args = parser.parse_args(argv)
    try:
        summary = run_sweep()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
