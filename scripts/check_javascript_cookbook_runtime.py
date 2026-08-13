#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_javascript_cookbook as cookbook  # noqa: E402


NODE_PROBE = r"""
const crypto = require('crypto');
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const issues = [];
const evidence = [];
const semantics = [];

function issue(scope, rule, detail) { issues.push({scope, rule, detail: String(detail || '')}); }
function sourceEvents(fields, rows) {
  const names = fields.map((field) => field.alias);
  return [{event: 'metadata', data: {names}}, ...(rows || []).map((row) => ({
    event: 'row',
    data: names.map((name) => Object.prototype.hasOwnProperty.call(row, name) ? row[name] : null),
  }))];
}
function editor(fields, rows, params, theme) {
  const values = {...(params || {}), theme: [theme]};
  return {
    getId: (name) => `synthetic_${name}`,
    getLoadedData: () => ({rows: sourceEvents(fields, rows)}),
    getParams: () => values,
    getParam: (name) => values[name] || [],
    updateParams: (patch) => Object.assign(values, patch || {}),
    generateHtml: (value) => String(value == null ? '' : value),
    wrapFn: (value) => value,
  };
}
function execute(source, Editor) {
  const moduleObject = {exports: {}};
  new Function('module', 'exports', 'Editor', 'require', source)(moduleObject, moduleObject.exports, Editor, (name) => {
    if (name === 'libs/dataset/v2') return {buildSource: (config) => ({kind: 'dataset', ...config})};
    throw new Error(`unsupported require: ${name}`);
  });
  return moduleObject.exports;
}
function hash(value) { return crypto.createHash('sha256').update(String(value)).digest('hex'); }
function targets(value) { return [...String(value).matchAll(/data-id="([^"]+)"/g)].map((item) => item[1]); }

function validateSource(scope, tabs, fields, Editor, mode) {
  const source = execute(tabs['sources.js'], Editor);
  const aliases = fields.map((field) => field.alias);
  if (!aliases.length) return;
  if (!source || !source.rows) throw new Error('Sources.rows is missing');
  if (mode === 'dataset') {
    if (JSON.stringify(source.rows.columns) !== JSON.stringify(aliases)) {
      throw new Error(`dataset aliases differ: ${JSON.stringify(source.rows.columns)} != ${JSON.stringify(aliases)}`);
    }
  } else {
    const sql = String(source.rows.data && source.rows.data.sql_query || '');
    if (!sql.includes('__TABLE__') || !sql.includes('WHERE event_date BETWEEN')) {
      throw new Error('ClickHouse template lacks table/filter placeholders');
    }
    aliases.forEach((alias) => {
      if (!new RegExp(`\\bAS\\s+${alias}\\b`, 'i').test(sql)) throw new Error(`ClickHouse alias missing: ${alias}`);
    });
    if (!source.rows.qlConnectionId) throw new Error('ClickHouse connection binding is missing');
  }
}

function probeRoute(scope, record, viewport, theme, mode = 'dataset', paramsOverride = null) {
  const params = {...record.params, ...(paramsOverride || {})};
  const Editor = editor(record.source_contract, record.fixture_rows, params, theme);
  validateSource(scope, record.tabs, record.source_contract, Editor, mode);
  const paramsModel = execute(record.tabs['params.js'], Editor);
  if (!paramsModel || typeof paramsModel !== 'object' || Array.isArray(paramsModel)) throw new Error('Params is not an object');
  let output = '';
  let tooltipBytes = 0;
  let targetCount = 0;
  let prepared = null;
  let config = null;
  if (record.route === 'editor_advanced') {
    prepared = execute(record.tabs['prepare.js'], Editor);
    if (!prepared.render || typeof prepared.render.fn !== 'function' || !Array.isArray(prepared.render.args)) {
      throw new Error('Prepare has no render wrapFn contract');
    }
    output = prepared.render.fn({width: viewport.width, height: viewport.height}, ...prepared.render.args);
    if (typeof output !== 'string' || !output.trim() || !/<(?:div|svg)\b/i.test(output)) throw new Error('renderer returned empty output');
    const ids = targets(output); targetCount = ids.length;
    if (record.tooltip === 'native') {
      if (!ids.length) throw new Error('native tooltip recipe has no data targets');
      const renderer = prepared.tooltip && prepared.tooltip.renderer;
      if (!renderer || typeof renderer.fn !== 'function') throw new Error('native tooltip renderer is missing');
      for (const id of ids) {
        const rendered = renderer.fn({target: {getAttribute: (name) => name === 'data-id' ? id : null}}, ...renderer.args);
        if (typeof rendered === 'string' && rendered.trim()) { tooltipBytes = Buffer.byteLength(rendered); break; }
      }
      if (!tooltipBytes) throw new Error('native tooltip targets returned no content');
    } else if (record.tooltip === 'inline' && !ids.length && !/<title\b|\btitle="/i.test(output)) {
      throw new Error('inline tooltip recipe has no interactive target');
    }
  } else if (record.route === 'editor_table') {
    prepared = execute(record.tabs['prepare.js'], Editor);
    config = execute(record.tabs['config.js'], Editor);
    if (!Array.isArray(prepared.head) || !prepared.head.length || !Array.isArray(prepared.rows) || !prepared.rows.length) {
      throw new Error('native table is empty');
    }
    if (!config.paginator || !Number.isInteger(config.paginator.limit)) throw new Error('native table paginator is invalid');
    output = `<table data-variant="${prepared.tableVariant || ''}">${prepared.rows.length}</table>`;
    targetCount = prepared.rows.length;
  } else if (record.route === 'editor_js_control') {
    prepared = execute(record.tabs['controls.js'], Editor);
    if (!prepared || !Array.isArray(prepared.controls) || !prepared.controls.length) throw new Error('Controls returned no controls');
    output = `<div>${prepared.controls.length}</div>`; targetCount = prepared.controls.length;
  } else throw new Error(`unknown route: ${record.route}`);
  return {output, prepared, config, targetCount, tooltipBytes};
}

function semanticChecks(record, result) {
  const output = result.output;
  if (record.slug === 'area-chart') {
    const ok = /data-role="area-fill"/.test(output) && /<path\b/.test(output);
    semantics.push({rule: 'area_fill_path', ok}); if (!ok) throw new Error('area chart has no fill path');
  }
  if (record.slug === 'cumulative-line') {
    const series = result.prepared.render.args[0] && result.prepared.render.args[0].series || [];
    const values = series[0] && series[0].values || [];
    const nonDecreasing = values.every((value, index) => index === 0 || value >= values[index - 1]);
    const ok = !/data-role="area-fill"/.test(output) && values.length > 1 && nonDecreasing;
    semantics.push({rule: 'cumulative_line_monotonic_no_fill', ok}); if (!ok) throw new Error('cumulative line semantic contract failed');
  }
  if (record.slug === 'matrix-heatmap') {
    const xs = new Set([...output.matchAll(/data-x="([^"]+)"/g)].map((item) => item[1]));
    const ys = new Set([...output.matchAll(/data-y="([^"]+)"/g)].map((item) => item[1]));
    const ok = xs.size >= 2 && ys.size >= 2 && /data-role="heatmap-matrix"/.test(output);
    semantics.push({rule: 'heatmap_two_coordinates', ok});
    if (!ok) throw new Error('heatmap does not expose two coordinates');
  }
  if (record.slug === 'sankey') {
    const ok = (output.match(/data-role="sankey-node"/g) || []).length >= 2
      && (output.match(/data-role="sankey-link"/g) || []).length >= 1;
    semantics.push({rule: 'sankey_nodes_links', ok});
    if (!ok) throw new Error('Sankey nodes/links are missing');
  }
  if (record.route === 'editor_table') {
    const text = JSON.stringify(result.prepared.head);
    let ok = true;
    if (record.variant === 'detail') {
      ok = /"pinned":true/.test(text)
        && result.config.horizontalScroll === true
        && result.config.pinnedColumnCount === 2;
    }
    if (record.variant === 'status') ok = /"type":"status"/.test(text) && /"type":"link"/.test(text);
    if (record.variant === 'grouped_summary') ok = /"sub":\[/.test(text) && /"type":"progress"/.test(text);
    semantics.push({rule: `table_${record.variant}`, ok});
    if (!ok) throw new Error(`table ${record.variant} semantic contract failed`);
  }
}

for (const record of payload.recipes) {
  for (const [viewportName, viewport] of Object.entries(payload.viewports)) {
    for (const theme of ['light', 'dark']) {
      const scope = `${record.slug}/${record.lang}/${viewportName}/${theme}`;
      try {
        const result = probeRoute(scope, record, viewport, theme);
        if (viewportName === 'dashboard' && theme === 'light') semanticChecks(record, result);
        evidence.push({
          kind: 'recipe', slug: record.slug, variant: record.variant, lang: record.lang,
          viewport: viewportName, theme, output_bytes: Buffer.byteLength(result.output),
          output_sha256: hash(result.output), target_count: result.targetCount,
          tooltip_bytes: result.tooltipBytes,
        });
      } catch (error) { issue(scope, 'runtime_probe_failed', error && error.stack || error); }
    }
  }
}

function alternateParams(caseRecord) {
  const values = {...caseRecord.defaults};
  if (values.timeStep) values.timeStep = ['month'];
  if (values.comparisonMethod) values.comparisonMethod = ['previous_year'];
  if (values.category) values.category = ['a'];
  if (values.status) values.status = ['ready'];
  return values;
}

for (const caseRecord of payload.cases) {
  const states = [
    {name: 'default', params: caseRecord.defaults},
    {name: 'alternate', params: alternateParams(caseRecord)},
  ];
  for (const lang of ['ru', 'en']) {
    for (const [viewportName, viewport] of Object.entries(payload.viewports)) {
      for (const theme of ['light', 'dark']) {
        for (const mode of ['dataset', 'clickhouse']) {
          for (const state of states) {
    const scope = `${caseRecord.slug}/${lang}/${viewportName}/${theme}/${mode}/${state.name}`;
    try {
      let bytes = 0; let objectCount = 0;
      for (const object of caseRecord.objects) {
        const localized = object.localized[lang];
        const tabs = localized.modes[mode];
        const record = {
          slug: `${caseRecord.slug}:${object.id}`, variant: object.role,
          route: object.route, tooltip: object.tooltip, tabs, params: state.params,
          source_contract: localized.source_contract,
          fixture_rows: object.fixture_rows[lang] || [],
        };
        const result = probeRoute(scope, record, viewport, theme, mode, state.params);
        bytes += Buffer.byteLength(result.output); objectCount += 1;
      }
      if (!objectCount || !bytes) throw new Error('case rendered no objects');
      evidence.push({
        kind: 'case', slug: caseRecord.slug, lang, viewport: viewportName, theme,
        source_mode: mode, selector_state: state.name, object_count: objectCount,
        output_bytes: bytes,
      });
    } catch (error) { issue(scope, 'case_runtime_probe_failed', error && error.stack || error); }
          }
        }
      }
    }
  }
}

process.stdout.write(JSON.stringify({issues, evidence, semantics}));
"""


def resolve_node() -> str | None:
    explicit = os.environ.get("DATALENS_MCP_NODE", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return str(path) if path.is_file() else None
    return shutil.which("node")


def build_payload() -> dict[str, Any]:
    catalog = cookbook.load_catalog()
    compiled_map: dict[tuple[str, str], dict[str, Any]] = {}
    recipes: list[dict[str, Any]] = []
    for source in catalog["recipes"]:
        for lang in cookbook.LOCALES:
            compiled = cookbook.compile_recipe(catalog, source, lang)
            compiled_map[(source["slug"], lang)] = compiled
            recipes.append(compiled)
    cases: list[dict[str, Any]] = []
    source_by_slug = {item["slug"]: item for item in catalog["recipes"]}
    for source_case in catalog["cases"]:
        compiled_case = cookbook.compile_case(catalog, source_case, compiled_map)
        objects: list[dict[str, Any]] = []
        for item in compiled_case["objects"]:
            recipe_slug = item.get("recipe") or ""
            fixture_rows = {lang: compiled_map[(recipe_slug, lang)]["fixture_rows"] if recipe_slug else [] for lang in cookbook.LOCALES}
            tooltip = source_by_slug[recipe_slug]["tooltip"] if recipe_slug else "none"
            objects.append({**item, "fixture_rows": fixture_rows, "tooltip": tooltip})
        cases.append(
            {
                "slug": compiled_case["slug"],
                "kind": compiled_case["kind"],
                "defaults": cookbook._case_defaults(source_case),
                "objects": objects,
            }
        )
    return {"viewports": catalog["viewports"], "recipes": recipes, "cases": cases}


def run_sweep(*, require_node: bool = False) -> dict[str, Any]:
    node = resolve_node()
    if not node:
        return {
            "ok": not require_node,
            "status": "unavailable",
            "recipe_count": 0,
            "case_count": 0,
            "probe_count": 0,
            "issues": ["Node.js is required"] if require_node else [],
        }
    payload = build_payload()
    completed = subprocess.run(
        [node, "-e", NODE_PROBE],
        cwd=ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "ok": False,
            "status": "failed",
            "recipe_count": len(payload["recipes"]),
            "case_count": len(payload["cases"]),
            "probe_count": 0,
            "issues": [completed.stderr.strip() or f"Node exited with {completed.returncode}"],
        }
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "status": "failed",
            "recipe_count": len(payload["recipes"]),
            "case_count": len(payload["cases"]),
            "probe_count": 0,
            "issues": [f"Node returned invalid JSON: {exc}"],
        }
    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    issues = result.get("issues") if isinstance(result.get("issues"), list) else []
    semantics = result.get("semantics") if isinstance(result.get("semantics"), list) else []
    expected_recipe_probes = 34 * 2 * 3 * 2
    expected_case_probes = 3 * 2 * 3 * 2 * 2 * 2
    recipe_probes = sum(item.get("kind") == "recipe" for item in evidence)
    case_probes = sum(item.get("kind") == "case" for item in evidence)
    if recipe_probes != expected_recipe_probes:
        issues.append({"rule": "recipe_matrix_incomplete", "detail": f"{recipe_probes}/{expected_recipe_probes}"})
    if case_probes != expected_case_probes:
        issues.append({"rule": "case_matrix_incomplete", "detail": f"{case_probes}/{expected_case_probes}"})
    if not semantics or any(item.get("ok") is not True for item in semantics):
        issues.append({"rule": "semantic_matrix_failed", "detail": semantics})
    return {
        "ok": not issues,
        "status": "passed" if not issues else "failed",
        "recipe_count": 34,
        "localized_recipe_count": len(payload["recipes"]),
        "case_count": len(payload["cases"]),
        "probe_count": len(evidence),
        "recipe_probe_count": recipe_probes,
        "case_probe_count": case_probes,
        "tooltip_probe_count": sum(int(item.get("tooltip_bytes") or 0) > 0 for item in evidence),
        "semantic_probe_count": len(semantics),
        "issues": issues,
        "evidence": evidence,
        "semantics": semantics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the JavaScript Cookbook Node runtime matrix.")
    parser.add_argument("--strict", action="store_true", help="Require Node.js and fail on any probe issue.")
    parser.add_argument("--details", action="store_true", help="Include per-probe evidence.")
    args = parser.parse_args(argv)
    try:
        report = run_sweep(require_node=args.strict)
    except (KeyError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        report = {"ok": False, "status": "failed", "issues": [str(exc)]}
    if not args.details:
        report.pop("evidence", None)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
