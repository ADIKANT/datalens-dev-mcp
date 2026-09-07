"""Small Dataset-to-matrix binding compiler; no network or model-generated JS."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def matrix_dataset_source(bindings: Mapping[str, Any]) -> dict[str, Any]:
    fields = bindings.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("Dataset binding requires fields from Dataset readback")
    by_guid = {field["guid"]: field for field in fields}
    rows = bindings.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("matrix Dataset binding requires row fields")
    metric, comparison = bindings.get("metric"), bindings.get("comparison")
    references = [*rows, metric, comparison]
    guids, titles = [], []
    for reference in references:
        if not isinstance(reference, Mapping) or reference.get("field_guid") not in by_guid:
            raise ValueError("matrix binding must reference known Dataset field GUIDs, including comparison")
        guid = reference["field_guid"]
        title = by_guid[guid].get("title")
        if not isinstance(title, str) or not title:
            raise ValueError("Dataset field readback must include title")
        guids.append(guid)
        titles.append(title)
    if len(set(titles)) != len(titles):
        raise ValueError("matrix Dataset binding requires distinct field titles")
    spec = {"data": {"fields": [{"ref": {"type": "id", "title": guid}} for guid in guids]}}
    sources = "const source = " + json.dumps(spec) + ";\nsource.datasetId = Editor.getId('dataset');\nmodule.exports = {source};\n"
    prepare = "const Dataset = require('libs/dataset/v2');\nconst names = " + json.dumps(titles, ensure_ascii=False) + ";\n"
    prepare += """const rows = Dataset.getDatasetRows({datasetName: 'source'});
const number = value => value === null || value === undefined || value === '' ? null :
  (Number.isFinite(Number(value)) ? Number(value) : null);
module.exports = {rows: rows.map(row => ({
  label: names.slice(0, -2).map(name => row[name] == null ? '—' : String(row[name])).join(' / '),
  current: number(row[names[names.length - 2]]),
  previous: number(row[names[names.length - 1]])
}))};
"""
    return {"meta": {"links": {"dataset": bindings["dataset_id"]}}, "sources_js": sources, "prepare_js": prepare}


def kpi_dataset_source(bindings: Mapping[str, Any]) -> dict[str, Any]:
    mode = bindings.get("value_mode")
    if mode not in {"last", "sum"}:
        raise ValueError("KPI Dataset binding requires explicit value_mode: last or sum")
    if mode == "sum" and (bindings.get("metric") or {}).get("additive") is not True:
        raise ValueError("sum requires an explicitly additive metric")
    source = matrix_dataset_source({**bindings, "rows": [bindings.get("date")]})
    transform = source["prepare_js"]
    source["prepare_js"] = "const prepared = (() => { const module = {exports: {}};\n" + transform + "\nreturn module.exports; })();\n"
    source["prepare_js"] += "const mode = " + json.dumps(mode) + ";\n"
    source["prepare_js"] += """const rows = prepared.rows.map(row => ({...row, timestamp: Date.parse(row.label)}));
if (rows.some(row => !Number.isFinite(row.timestamp))) throw new Error('KPI dates must be parseable dates');
rows.sort((a, b) => a.timestamp - b.timestamp);
if (new Set(rows.map(row => row.timestamp)).size !== rows.length) throw new Error('KPI requires one row per date');
const summary = key => {
  if (!rows.length) return null;
  if (mode === 'last') return rows[rows.length - 1][key];
  if (rows.some(row => row[key] === null)) return null;
  return rows.reduce((total, row) => total + row[key], 0);
};
module.exports = {value: summary('current'), previous: summary('previous'),
  points: rows.map(row => ({date: row.label, value: row.current}))};
"""
    return source
