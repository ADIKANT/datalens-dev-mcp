#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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
    checks = [
        ("unresolved_local_shared_require", UNRESOLVED_IMPORT_RE),
        ("decorative_css_token", DECORATIVE_CSS_RE),
        ("stale_implicit_kpi_comparator", STALE_KPI_RE),
        ("forbidden_advanced_editor_markup", FORBIDDEN_HTML_RE),
    ]
    for rule, pattern in checks:
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
            widget_id="kpi_value",
            route="editor_advanced",
            title="KPI Value",
            family="kpi_value_only",
            source_mode="golden_fixture",
        ),
        generate_editor_bundle(
            widget_id="kpi_comparator",
            route="editor_advanced",
            title="KPI Comparator",
            family="kpi_value_delta",
            source_mode="golden_fixture",
        ),
        generate_editor_bundle(
            widget_id="native_table",
            route="editor_table",
            title="Native Table",
            family="table_node",
            columns=["name", "value"],
            source_mode="golden_fixture",
        ),
        generate_editor_bundle(
            widget_id="line_chart",
            route="editor_advanced",
            title="Line Chart",
            family="line_chart",
            source_mode="golden_fixture",
        ),
        generate_editor_bundle(
            widget_id="bar_chart",
            route="editor_advanced",
            title="Bar Chart",
            family="horizontal_bar",
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
        build_wizard_payload_plan(),
    ]
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

    generated_path = ARTIFACT_DIR / "generated_bundles.json"
    generated_path.write_text(json.dumps(bundles, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    issues = template_issues + generated_all_issues
    summary = {
        "ok": not issues,
        "checked_template_files": len(checked_templates),
        "generated_bundle_count": len(bundles),
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
