from __future__ import annotations

import json
import subprocess

import pytest

from datalens_dev_mcp.authoring.dataset_source import compile_direct_source, matrix_dataset_source
from datalens_dev_mcp.authoring.recipes import compile_recipe


def _dataset_bindings() -> dict:
    return {
        "dataset_id": "dataset-synthetic",
        "rows": [{"field_guid": "region"}],
        "metric": {"field_guid": "current"},
        "comparison": {"field_guid": "previous"},
        "fields": [
            {"guid": "region", "title": "Region", "type": "DIMENSION"},
            {"guid": "current", "title": "Current", "type": "MEASURE"},
            {"guid": "previous", "title": "Previous", "type": "MEASURE"},
        ],
        "selectors": [
            {
                "param_name": "region_filter",
                "field_guid": "region",
                "default": [],
                "empty_selection": "all",
                "operation": "IN",
            }
        ],
        "source_limit": 25,
    }


def _run_sources(source: dict, params: dict) -> dict:
    script = "const Editor={getId:()=> 'dataset-synthetic',getParams:()=> (" + json.dumps(params) + ")};\n"
    script += "const require=()=>({buildSource:x=>x});\n" + source["sources_js"]
    script += "console.log(JSON.stringify(module.exports));"
    return json.loads(subprocess.check_output(["node", "-e", script], text=True))["source"]


def test_dataset_source_uses_documented_builder_and_selector_without_static_restore() -> None:
    source = matrix_dataset_source(_dataset_bindings())

    selected = _run_sources(source, {"region_filter": ["north"]})
    cleared = _run_sources(source, {"region_filter": []})
    cleared_from_dashboard_default = _run_sources(source, {"region_filter": [""]})

    assert selected["id"] == "dataset-synthetic"
    assert selected["columns"] == ["Region", "Current", "Previous"]
    assert selected["where"] == [{"column": "Region", "type": "title", "operation": "IN", "values": ["north"]}]
    assert selected["limit"] == 25
    assert cleared["where"] == []
    assert cleared_from_dashboard_default["where"] == []
    assert source["params"] == {"region_filter": []}
    assert "updateParams" not in source["sources_js"]


def test_dataset_source_accepts_scalar_selector_value_from_dashboard_runtime() -> None:
    source = matrix_dataset_source(_dataset_bindings())

    selected = _run_sources(source, {"region_filter": "north"})

    assert selected["where"] == [{"column": "Region", "type": "title", "operation": "IN", "values": ["north"]}]


@pytest.mark.parametrize(
    ("loaded", "message"),
    [
        ({}, "source alias is missing"),
        ({"source": [{"event": "error", "data": {"message": "synthetic upstream"}}]}, "source failed"),
    ],
)
def test_dataset_prepare_distinguishes_missing_alias_and_upstream_error(loaded: dict, message: str) -> None:
    source = matrix_dataset_source(_dataset_bindings())
    script = "const Editor={getLoadedData:()=> (" + json.dumps(loaded) + ")};\n"
    script += "const require=()=>({getDatasetRows:()=>[]});\n" + source["prepare_js"]
    result = subprocess.run(["node", "-e", script], text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert message in result.stderr


def test_dataset_prepare_keeps_valid_empty_result_distinct() -> None:
    source = matrix_dataset_source(_dataset_bindings())
    loaded = {"source": [{"event": "metadata", "data": {"names": ["Region", "Current", "Previous"]}}]}
    script = "const Editor={getLoadedData:()=> (" + json.dumps(loaded) + ")};\n"
    script += "const require=()=>({getDatasetRows:()=>[]});\n" + source["prepare_js"]
    script += "console.log(JSON.stringify(module.exports));"
    result = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    assert result == {"rows": [], "state": "no_data"}


def test_dataset_prepare_delegates_non_array_loaded_source_to_dataset_runtime() -> None:
    """The provider may expose an opaque loaded-source handle consumed by libs/dataset/v2."""
    source = matrix_dataset_source(_dataset_bindings())
    loaded = {"source": {"status": "loaded"}}
    script = "const Editor={getLoadedData:()=> (" + json.dumps(loaded) + ")};\n"
    script += (
        "const require=()=>({getDatasetRows:()=>[{Region:'north',Current:3,Previous:2}]});\n" + source["prepare_js"]
    )
    script += "console.log(JSON.stringify(module.exports));"

    result = json.loads(subprocess.check_output(["node", "-e", script], text=True))

    assert result == {
        "rows": [{"label": "north", "current": 3, "previous": 2}],
        "state": "ready",
    }


def test_weekly_recipe_compiles_dataset_rows_to_iso_week_totals(tmp_path) -> None:
    result = compile_recipe(
        "weekly_totals_table",
        {
            "dataset_id": "dataset-synthetic",
            "fields": [
                {"guid": "day", "title": "Day", "type": "DIMENSION"},
                {"guid": "priority", "title": "Priority", "type": "DIMENSION"},
                {"guid": "current", "title": "Current issues", "type": "MEASURE", "aggregation": "sum"},
            ],
            "group": {"field_guid": "priority", "label": "Priority"},
            "date": {"field_guid": "day", "label": "ISO week"},
            "metric": {"field_guid": "current", "label": "Current issues"},
        },
        user_config_path=tmp_path / "absent.json",
    )
    source = result["draft"]["bindings"]["source"]
    loaded = {"source": {"status": "loaded"}}
    rows = [
        {"Day": "2026-09-01", "Priority": "High", "Current issues": 12},
        {"Day": "2026-09-02", "Priority": "Medium", "Current issues": 8},
        {"Day": "2026-09-03", "Priority": "Low", "Current issues": 5},
    ]
    script = "const Editor={getLoadedData:()=> (" + json.dumps(loaded) + ")};\n"
    script += "const require=()=>({getDatasetRows:()=>" + json.dumps(rows) + "});\n" + source["prepare_js"]
    script += "console.log(JSON.stringify(module.exports));"

    prepared = json.loads(subprocess.check_output(["node", "-e", script], text=True))

    assert prepared == {
        "weeks": [
            {
                "key": "2026-W36",
                "label": "2026-W36",
                "date_from": "2026-08-31",
                "date_to": "2026-09-06",
            }
        ],
        "rows": [
            {"label": "High", "values": [12], "value_states": ["value"], "total": 12},
            {"label": "Low", "values": [5], "value_states": ["value"], "total": 5},
            {"label": "Medium", "values": [8], "value_states": ["value"], "total": 8},
        ],
        "total_values": [25],
        "grand_total": 25,
        "state": "ready",
    }


def test_direct_ql_and_api_sources_compile_only_documented_shapes() -> None:
    ql = compile_direct_source(
        {
            "kind": "ql",
            "connection_id": "connection-synthetic",
            "sql_query": "select 1 as synthetic_value",
        }
    )
    api = compile_direct_source(
        {
            "kind": "api",
            "connection_id": "api-connection-synthetic",
            "path": "/synthetic",
            "method": "POST",
            "body": {"limit": 1},
        }
    )

    assert ql["meta"] == {"links": {"connection": "connection-synthetic"}}
    assert "qlConnectionId: Editor.getId('connection')" in ql["sources_js"]
    assert "sql_query" in ql["sources_js"]
    assert "apiConnectionId: Editor.getId('connection')" in api["sources_js"]
    assert 'method: "POST"' in api["sources_js"]
    assert "fetch(" not in api["sources_js"]


def test_recipe_accepts_short_direct_source_binding_and_declares_params(tmp_path) -> None:
    result = compile_recipe(
        "kpi_sparkline",
        {
            "direct_source": {
                "kind": "ql",
                "connection_id": "connection-synthetic",
                "sql_query": "select 1 as current_value, 1 as previous_value",
                "prepare_js": "module.exports = {value: 1, previous: 1, points: []};",
                "params": {"region_filter": []},
            },
            "metric": {"field_guid": "current", "label": "Synthetic KPI"},
            "date": {"field_guid": "date"},
            "comparison": {"method": "previous_period", "label": "Previous"},
        },
        user_config_path=tmp_path / "absent.json",
    )

    tabs = result["draft"]["tabs"]
    assert json.loads(tabs["meta.json"])["links"]["connection"] == "connection-synthetic"
    assert "region_filter" in tabs["params.js"]
    assert "qlConnectionId" in tabs["sources.js"]


def _weekly_binding(aggregation="sum"):
    return {
        "dataset_id": "dataset-synthetic",
        "fields": [
            {"guid": "group", "title": "Group"},
            {"guid": "date", "title": "Day"},
            {"guid": "value", "title": "Value", "aggregation": aggregation},
        ],
        "group": {"field_guid": "group"},
        "date": {"field_guid": "date"},
        "metric": {"field_guid": "value"},
    }


def _compiled_weekly(tmp_path, binding):
    return compile_recipe("weekly_totals_table", binding, user_config_path=tmp_path / "absent.json")["draft"]


def _weekly_prepared(tmp_path, rows, binding=None):
    draft = _compiled_weekly(tmp_path, binding or _weekly_binding())
    script = "const Editor={getLoadedData:()=>({source:{status:'loaded'}}),wrapFn:x=>x};\n"
    script += "const require=()=>({getDatasetRows:()=>" + json.dumps(rows) + "});\n"
    # Execute the public emitted tab, capture the actual prepared argument passed to the renderer.
    script += draft["tabs"]["prepare.js"]
    script += "console.log(JSON.stringify(module.exports.render.args));"
    return json.loads(subprocess.check_output(["node", "-e", script], text=True))[0]


def test_weekly_additive_sum_uses_readback_semantics(tmp_path):
    prepared = _weekly_prepared(tmp_path, [
        {"Group": "A", "Day": "2026-09-01", "Value": 10},
        {"Group": "A", "Day": "2026-09-02", "Value": 20},
    ])
    assert prepared["rows"][0]["values"] == [30]
    assert prepared["grand_total"] == 30


@pytest.mark.parametrize("aggregation", ["avg", "ratio", "count_distinct", "none", None])
def test_weekly_dataset_refuses_unproven_additive_totals(tmp_path, aggregation):
    with pytest.raises(ValueError, match="source-computed totals"):
        _compiled_weekly(tmp_path, _weekly_binding(aggregation))


@pytest.mark.parametrize("unknown", [None, "", "   "])
def test_weekly_unknown_does_not_become_zero_or_partial_total(tmp_path, unknown):
    prepared = _weekly_prepared(tmp_path, [
        {"Group": "A", "Day": "2026-09-01", "Value": unknown},
        {"Group": "A", "Day": "2026-09-02", "Value": 10},
        {"Group": "B", "Day": "2026-09-08", "Value": 0},
    ])
    assert prepared["rows"][0]["values"] == [None, None]
    assert prepared["rows"][0]["value_states"] == ["unknown", "missing"]
    assert prepared["rows"][1]["values"] == [None, 0]
    assert prepared["rows"][1]["value_states"] == ["missing", "value"]
    assert prepared["rows"][0]["total"] is None
    assert prepared["total_values"] == [None, None]
    assert prepared["grand_total"] is None


def test_weekly_declared_count_missing_combinations_zero_keeps_explicit_unknown(tmp_path):
    binding = _weekly_binding("count")
    binding["metric"]["missing_combinations"] = "zero"
    prepared = _weekly_prepared(tmp_path, [
        {"Group": "A", "Day": "2026-09-01", "Value": None},
        {"Group": "B", "Day": "2026-09-08", "Value": 0},
    ], binding)
    assert prepared["rows"][0]["values"] == [None, 0]
    assert prepared["rows"][1]["values"] == [0, 0]
    assert prepared["total_values"] == [None, 0]
    assert prepared["grand_total"] is None


@pytest.mark.parametrize("value,expected", [("High", "High"), (0, "0"), (False, "false")])
def test_dataset_parameter_scalar_and_singleton_preserve_value(tmp_path, value, expected):
    binding = _weekly_binding()
    binding["dataset_parameters"] = [{"id": "parameter-id", "param_name": "priority"}]
    source = _compiled_weekly(tmp_path, binding)["bindings"]["source"]
    for raw in (value, [value]):
        query = _run_sources(source, {"priority": raw})
        assert query["parameters"] == [{"id": "parameter-id", "value": expected}]
        assert query["where"] == []


@pytest.mark.parametrize("params", [{}, {"priority": None}, {"priority": ""}, {"priority": []}, {"priority": [""]}, {"priority": [None]}])
def test_dataset_parameter_clear_is_omitted(tmp_path, params):
    binding = _weekly_binding()
    binding["dataset_parameters"] = [{"id": "parameter-id", "param_name": "priority"}]
    source = _compiled_weekly(tmp_path, binding)["bindings"]["source"]
    assert _run_sources(source, params)["parameters"] == []


def test_dataset_parameter_rejects_multiple_values(tmp_path):
    binding = _weekly_binding()
    binding["dataset_parameters"] = [{"id": "parameter-id", "param_name": "priority"}]
    source = _compiled_weekly(tmp_path, binding)["bindings"]["source"]
    with pytest.raises(subprocess.CalledProcessError):
        _run_sources(source, {"priority": ["High", "Low"]})


@pytest.mark.parametrize("route", ["prepared_data", "source"])
def test_weekly_ratio_preserves_source_computed_totals(tmp_path, route):
    binding = _weekly_binding("avg")
    binding["metric"]["aggregation"] = "ratio"
    prepared = {
        "weeks": [{"key": "2026-W36", "label": "2026-W36"}],
        "rows": [
            {"label": "A", "values": [0.8], "total": 0.8},
            {"label": "B", "values": [0.9], "total": 0.9},
        ],
        "total_values": [26 / 30], "grand_total": 26 / 30,
    }
    if route == "prepared_data":
        binding[route] = prepared
    else:
        binding[route] = {"meta": {}, "sources_js": "module.exports = {};",
                          "prepare_js": "module.exports = " + json.dumps(prepared) + ";"}
    draft = _compiled_weekly(tmp_path, binding)
    script = "const Editor={wrapFn:x=>x};\n" + draft["tabs"]["prepare.js"]
    script += "console.log(JSON.stringify(module.exports.render.args[0]));"
    actual = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    assert actual == prepared
    assert actual["grand_total"] == pytest.approx(0.8666666666666667)


def test_dataset_parameter_default_false_has_runtime_spelling(tmp_path):
    binding = _weekly_binding()
    binding["dataset_parameters"] = [{"id": "parameter-id", "param_name": "priority", "default": False}]
    source = _compiled_weekly(tmp_path, binding)["bindings"]["source"]
    assert _run_sources(source, source["params"])["parameters"] == [{"id": "parameter-id", "value": "false"}]


def test_weekly_binding_cannot_override_nonadditive_field(tmp_path):
    binding = _weekly_binding("avg")
    binding["metric"].update(aggregation="sum", additive=True)
    with pytest.raises(ValueError, match="source-computed totals"):
        _compiled_weekly(tmp_path, binding)


def test_dataset_parameter_multiple_defaults_are_rejected(tmp_path):
    binding = _weekly_binding()
    binding["dataset_parameters"] = [{"id": "parameter-id", "param_name": "priority", "default": [0, False]}]
    with pytest.raises(ValueError, match="one default value"):
        _compiled_weekly(tmp_path, binding)
