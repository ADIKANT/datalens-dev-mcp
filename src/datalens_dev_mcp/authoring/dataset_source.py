"""Small Dataset-to-matrix binding compiler; no network or model-generated JS."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

_FILTER_OPERATIONS = frozenset({"IN", "NOT_IN", "EQ", "NE", "BETWEEN", "GT", "GTE", "LT", "LTE"})


def _field_index(bindings: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    fields = bindings.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("Dataset binding requires fields from Dataset readback")
    result: dict[str, dict[str, Any]] = {}
    for field in fields:
        if not isinstance(field, Mapping) or not isinstance(field.get("guid"), str) or not field["guid"]:
            raise ValueError("Dataset readback fields require nonempty GUIDs")
        result[field["guid"]] = dict(field)
    return result


def _dataset_query(bindings: Mapping[str, Any], guids: list[str], titles: list[str]) -> dict[str, Any]:
    limit = bindings.get("source_limit", 1000)
    if type(limit) is not int or not 1 <= limit <= 100000:
        raise ValueError("source_limit must be an integer from 1 to 100000")
    selectors = bindings.get("selectors") or []
    if not isinstance(selectors, list):
        raise TypeError("selectors must be a list")
    selector_contracts: list[dict[str, Any]] = []
    params: dict[str, list[str]] = {}
    by_guid = _field_index(bindings)
    for selector in selectors:
        if not isinstance(selector, Mapping):
            raise TypeError("selector binding must be an object")
        name = selector.get("param_name")
        guid = selector.get("field_guid")
        empty = selector.get("empty_selection")
        operation = str(selector.get("operation") or "IN").upper()
        if not isinstance(name, str) or not name or not isinstance(guid, str) or guid not in by_guid:
            raise ValueError("selector binding requires param_name and a known field_guid")
        if empty not in {"all", "none", "error"}:
            raise ValueError("selector empty_selection must be all, none or error")
        if operation not in _FILTER_OPERATIONS:
            raise ValueError(f"unsupported Dataset filter operation: {operation}")
        default = selector.get("default")
        values = default if isinstance(default, list) else ([] if default is None else [default])
        params[name] = [str(value) for value in values]
        selector_contracts.append(
            {
                "param_name": name,
                "column": str(by_guid[guid].get("title") or ""),
                "type": "title",
                "operation": operation,
                "empty_selection": empty,
            }
        )
    dataset_parameters = bindings.get("dataset_parameters") or []
    if not isinstance(dataset_parameters, list):
        raise TypeError("dataset_parameters must be a list")
    parameter_contracts: list[dict[str, str]] = []
    for parameter in dataset_parameters:
        if not isinstance(parameter, Mapping):
            raise TypeError("Dataset parameter binding must be an object")
        identifier = parameter.get("id")
        name = parameter.get("param_name")
        if not isinstance(identifier, str) or not identifier or not isinstance(name, str) or not name:
            raise ValueError("Dataset parameter binding requires id and param_name")
        default = parameter.get("default")
        values = default if isinstance(default, list) else ([] if default is None else [default])
        values = [value for value in values if value is not None and value != ""]
        if len(values) > 1:
            raise ValueError(f"Dataset parameter requires one default value: {name}")
        params[name] = [str(value).lower() if isinstance(value, bool) else str(value) for value in values]
        parameter_contracts.append({"id": identifier, "param_name": name})
    sources = "const {buildSource} = require('libs/dataset/v2');\n"
    sources += "const params = Editor.getParams();\nconst where = [];\n"
    sources += "const selectorContracts = " + json.dumps(selector_contracts, ensure_ascii=False) + ";\n"
    sources += "for (const selector of selectorContracts) {\n"
    sources += "  const rawValue = params[selector.param_name];\n"
    sources += (
        "  const rawValues = Array.isArray(rawValue) ? rawValue : [rawValue];\n"
        "  const values = rawValues.filter(value => value !== null && value !== undefined && value !== '')"
        ".map(String);\n"
    )
    sources += "  if (!values.length && selector.empty_selection === 'error') throw new Error('selector value is required: ' + selector.param_name);\n"
    sources += "  if (values.length || selector.empty_selection === 'none') where.push({column: selector.column, type: selector.type, operation: selector.operation, values});\n}\n"
    sources += "const datasetParameters = " + json.dumps(parameter_contracts, ensure_ascii=False) + ".map(item => {\n"
    sources += "  const raw = params[item.param_name];\n"
    sources += "  const values = (Array.isArray(raw) ? raw : [raw]).filter(value => value !== null && value !== undefined && value !== '');\n"
    sources += "  if (values.length > 1) throw new Error('Dataset parameter requires one value: ' + item.param_name);\n"
    sources += "  return values.length ? {id: item.id, value: String(values[0])} : null;\n}).filter(Boolean);\n"
    query = {
        "columns": titles,
        "limit": limit,
    }
    sources += "module.exports = {source: buildSource({id: Editor.getId('dataset'), columns: "
    sources += json.dumps(query["columns"], ensure_ascii=False) + ", where, parameters: datasetParameters, limit: "
    sources += str(query["limit"]) + "})};\n"
    prelude = "const loaded = Editor.getLoadedData();\n"
    prelude += "if (!loaded || !Object.prototype.hasOwnProperty.call(loaded, 'source')) throw new Error('source alias is missing: source');\n"
    prelude += "const sourceEvents = loaded.source;\n"
    prelude += "if (Array.isArray(sourceEvents) && sourceEvents.some(item => item && item.event === 'error')) throw new Error('source failed: source');\n"
    return {
        "meta": {"links": {"dataset": bindings["dataset_id"]}},
        "sources_js": sources,
        "params": params,
        "prepare_prelude": prelude,
    }


def matrix_dataset_source(bindings: Mapping[str, Any]) -> dict[str, Any]:
    by_guid = _field_index(bindings)
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
    query = _dataset_query(bindings, guids, titles)
    prepare = (
        query["prepare_prelude"]
        + "const Dataset = require('libs/dataset/v2');\nconst names = "
        + json.dumps(titles, ensure_ascii=False)
        + ";\n"
    )
    prepare += """const rows = Dataset.getDatasetRows({datasetName: 'source'});
const number = value => value === null || value === undefined || value === '' ? null :
  (Number.isFinite(Number(value)) ? Number(value) : null);
const preparedRows = rows.map(row => ({
  label: names.slice(0, -2).map(name => row[name] == null ? '—' : String(row[name])).join(' / '),
  current: number(row[names[names.length - 2]]),
  previous: number(row[names[names.length - 1]])
}));
module.exports = {rows: preparedRows, state: preparedRows.length ? 'ready' : 'no_data'};
"""
    return {"meta": query["meta"], "sources_js": query["sources_js"], "params": query["params"], "prepare_js": prepare}


def kpi_dataset_source(bindings: Mapping[str, Any]) -> dict[str, Any]:
    mode = bindings.get("value_mode")
    if mode not in {"last", "sum"}:
        raise ValueError("KPI Dataset binding requires explicit value_mode: last or sum")
    if mode == "sum" and (bindings.get("metric") or {}).get("additive") is not True:
        raise ValueError("sum requires an explicitly additive metric")
    source = matrix_dataset_source({**bindings, "rows": [bindings.get("date")]})
    transform = source["prepare_js"]
    source["prepare_js"] = (
        "const prepared = (() => { const module = {exports: {}};\n" + transform + "\nreturn module.exports; })();\n"
    )
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
  points: rows.map(row => ({date: row.label, value: row.current})),
  current_period: rows.length ? rows[rows.length - 1].label : '',
  previous_period: rows.length ? rows[rows.length - 1].label : '',
  state: rows.length ? 'ready' : 'no_data'};
"""
    return source


def weekly_dataset_source(bindings: Mapping[str, Any]) -> dict[str, Any]:
    by_guid = _field_index(bindings)
    references = [bindings.get("group"), bindings.get("date"), bindings.get("metric")]
    guids, titles = [], []
    for reference in references:
        if not isinstance(reference, Mapping) or reference.get("field_guid") not in by_guid:
            raise ValueError("weekly Dataset binding requires known group, date and metric field GUIDs")
        guid = reference["field_guid"]
        title = by_guid[guid].get("title")
        if not isinstance(title, str) or not title:
            raise ValueError("Dataset field readback must include title")
        guids.append(guid)
        titles.append(title)
    if len(set(titles)) != len(titles):
        raise ValueError("weekly Dataset binding requires distinct field titles")
    metric = bindings["metric"]
    field = by_guid[metric["field_guid"]]
    aggregations = [
        str(value).lower() for value in (field.get("aggregation"), metric.get("aggregation"))
        if value is not None
    ]
    if (
        len(set(aggregations)) != 1
        or aggregations[0] not in {"sum", "count"}
        or metric.get("additive") is False
    ):
        raise ValueError(
            "weekly Dataset auto-sum requires known sum/count aggregation across group/date rows; "
            "use explicit source or prepared_data with source-computed totals for non-additive or unknown measures"
        )
    missing = metric.get("missing_combinations", "unknown")
    if missing not in {"unknown", "zero"} or (missing == "zero" and aggregations[0] != "count"):
        raise ValueError("weekly missing_combinations must be unknown, or zero for a count measure")
    query = _dataset_query(bindings, guids, titles)
    prepare = query["prepare_prelude"] + "const Dataset = require('libs/dataset/v2');\n"
    prepare += "const missingValue = " + ("0" if missing == "zero" else "null") + ";\n"
    prepare += "const names = " + json.dumps(titles, ensure_ascii=False) + ";\n"
    prepare += """const sourceRows = Dataset.getDatasetRows({datasetName: 'source'});
const isoDate = date => date.toISOString().slice(0, 10);
const isoWeek = value => {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) throw new Error('weekly dates must be parseable dates');
  const monday = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const weekday = monday.getUTCDay() || 7;
  monday.setUTCDate(monday.getUTCDate() - weekday + 1);
  const thursday = new Date(monday);
  thursday.setUTCDate(thursday.getUTCDate() + 3);
  const firstThursday = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 4));
  const firstWeekday = firstThursday.getUTCDay() || 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstWeekday + 4);
  const number = 1 + Math.round((thursday - firstThursday) / 604800000);
  const key = thursday.getUTCFullYear() + '-W' + String(number).padStart(2, '0');
  const sunday = new Date(monday);
  sunday.setUTCDate(sunday.getUTCDate() + 6);
  return {key, label: key, date_from: isoDate(monday), date_to: isoDate(sunday)};
};
const weekByKey = new Map();
const valueByGroup = new Map();
for (const row of sourceRows) {
  const week = isoWeek(row[names[1]]);
  const group = row[names[0]] == null ? '—' : String(row[names[0]]);
  const raw = row[names[2]];
  const metric = raw == null || (typeof raw === 'string' && raw.trim() === '') ? null : Number(raw);
  if (metric !== null && !Number.isFinite(metric)) throw new Error('weekly metric must be numeric');
  weekByKey.set(week.key, week);
  if (!valueByGroup.has(group)) valueByGroup.set(group, new Map());
  const values = valueByGroup.get(group);
  const previous = values.has(week.key) ? values.get(week.key) : 0;
  values.set(week.key, previous === null || metric === null ? null : previous + metric);
}
const sum = values => values.some(value => value === null) ? null : values.reduce((total, value) => total + value, 0);
const weeks = Array.from(weekByKey.values()).sort((a, b) => a.key.localeCompare(b.key));
const rows = Array.from(valueByGroup.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([label, values]) => {
  const aligned = weeks.map(week => values.has(week.key) ? values.get(week.key) : missingValue);
  const value_states = weeks.map(week => !values.has(week.key) ? 'missing' : values.get(week.key) === null ? 'unknown' : 'value');
  return {label, values: aligned, value_states, total: sum(aligned)};
});
const total_values = weeks.map((week, index) => sum(rows.map(row => row.values[index])));
const grand_total = sum(total_values);
module.exports = {weeks, rows, total_values, grand_total, state: rows.length ? 'ready' : 'no_data'};
"""
    return {
        "meta": query["meta"],
        "sources_js": query["sources_js"],
        "params": query["params"],
        "prepare_js": prepare,
    }


def compile_direct_source(binding: Mapping[str, Any]) -> dict[str, Any]:
    kind = binding.get("kind")
    connection_id = binding.get("connection_id")
    if kind not in {"ql", "api"} or not isinstance(connection_id, str) or not connection_id:
        raise ValueError("direct_source requires kind ql/api and connection_id")
    params = binding.get("params") or {}
    if not isinstance(params, Mapping):
        raise TypeError("direct_source params must be an object")
    normalized_params: dict[str, list[str]] = {}
    for key, raw in params.items():
        if not isinstance(key, str) or not key:
            raise ValueError("direct_source parameter names must be nonempty strings")
        values = raw if isinstance(raw, list) else [raw]
        normalized_params[key] = [str(value) for value in values]
    if kind == "ql":
        query = binding.get("sql_query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("QL direct_source requires sql_query")
        source = "{qlConnectionId: Editor.getId('connection'), data: {sql_query: " + json.dumps(query) + "}}"
    else:
        path = binding.get("path")
        method = str(binding.get("method") or "GET").upper()
        if not isinstance(path, str) or not path.startswith("/") or method not in {"GET", "POST"}:
            raise ValueError("API direct_source requires absolute path and GET/POST method")
        source = "{apiConnectionId: Editor.getId('connection'), path: " + json.dumps(path)
        source += ", method: " + json.dumps(method)
        if "body" in binding:
            if not isinstance(binding["body"], Mapping):
                raise ValueError("API direct_source body must be an object")
            source += ", body: " + json.dumps(dict(binding["body"]), ensure_ascii=False)
        source += "}"
    sources_js = "module.exports = {source: " + source + "};\n"
    prelude = "const loaded = Editor.getLoadedData();\n"
    prelude += "if (!loaded || !Object.prototype.hasOwnProperty.call(loaded, 'source')) throw new Error('source alias is missing: source');\n"
    prelude += "const sourceEvents = loaded.source;\n"
    prelude += "if (!Array.isArray(sourceEvents)) throw new Error('source response is malformed: source');\n"
    prelude += (
        "if (sourceEvents.some(item => item && item.event === 'error')) throw new Error('source failed: source');\n"
    )
    transform = binding.get("prepare_js")
    if transform is not None and (not isinstance(transform, str) or not transform.strip()):
        raise ValueError("direct_source prepare_js must be nonempty source text")
    prepare_js = prelude + (
        transform or "module.exports = {state: sourceEvents.length ? 'ready' : 'no_data', events: sourceEvents};"
    )
    return {
        "meta": {"links": {"connection": connection_id}},
        "sources_js": sources_js,
        "prepare_js": prepare_js,
        "params": normalized_params,
        "source_kind": kind,
    }
