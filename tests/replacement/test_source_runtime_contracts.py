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

    assert selected["id"] == "dataset-synthetic"
    assert selected["columns"] == ["Region", "Current", "Previous"]
    assert selected["where"] == [{"column": "Region", "operation": "IN", "values": ["north"]}]
    assert selected["limit"] == 25
    assert cleared["where"] == []
    assert source["params"] == {"region_filter": []}
    assert "updateParams" not in source["sources_js"]


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
