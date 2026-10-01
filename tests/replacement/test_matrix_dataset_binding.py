import json
import subprocess

from datalens_dev_mcp.authoring.recipes import compile_recipe


def test_matrix_dataset_binding_uses_guid_query_and_maps_rows_without_null_coercion(tmp_path):
    draft = compile_recipe(
        "comparison_matrix",
        {
            "dataset_id": "synthetic-dataset",
            "object_name": "Synthetic matrix",
            "rows": [{"field_guid": "region"}],
            "metric": {"field_guid": "current"},
            "comparison": {"field_guid": "previous"},
            "fields": [
                {"guid": "region", "title": "Region"},
                {"guid": "current", "title": "Current"},
                {"guid": "previous", "title": "Previous"},
            ],
        },
        user_config_path=tmp_path / "absent.json",
    )["draft"]
    assert json.loads(draft["tabs"]["meta.json"])["links"]["dataset"] == "synthetic-dataset"
    sources = "const Editor={getId:()=> 'synthetic-dataset',getParams:()=>({})};\n"
    sources += "const require=()=>({buildSource:x=>x});\n" + draft["tabs"]["sources.js"]
    sources += "console.log(JSON.stringify(module.exports));"
    request = json.loads(subprocess.check_output(["node", "-e", sources], text=True))["source"]
    assert request["columns"] == ["Region", "Current", "Previous"]
    prepare = "const Editor={wrapFn:x=>x,getLoadedData:()=>({source:[{event:'metadata'}]})}; "
    prepare += "const require=()=>({getDatasetRows:()=>[{Region:'Synthetic',Current:null,Previous:'2'}]});\n"
    prepare += draft["tabs"]["prepare.js"] + "\nconsole.log(JSON.stringify(module.exports.render.args[0]));"
    result = json.loads(subprocess.check_output(["node", "-e", prepare], text=True))
    assert result["rows"] == [{"label": "Synthetic", "current": None, "previous": 2}]


def test_named_dataset_queries_keep_denominator_independent_and_order_before_limit():
    from datalens_dev_mcp.authoring.validation import validate_drafts

    fields = [{"guid": name, "title": name} for name in ("team", "day", "id", "count", "unused")]
    binding = {"dataset_id": "synthetic", "fields": fields, "metric": "Count", "dataset_source": {
        "queries": [
            {"alias": "numerator", "role": "selected team detail", "field_guids": ["day", "id", "count"],
             "selectors": [{"field_guid": "team", "param_name": "team", "default": [False], "empty_selection": "all"}],
             "filters": [{"field_guid": "id", "operation": "NOT_IN", "values": ["excluded"]}],
             "sort": [{"field_guid": "day", "direction": "desc"}, {"field_guid": "id", "direction": "desc"}], "limit": 100},
            {"alias": "denominator", "role": "global daily denominator", "field_guids": ["day", "count"],
             "filters": [{"field_guid": "day", "operation": "BETWEEN", "values": ["2026-01-01", "2026-01-02"]}]},
            {"alias": "prior", "role": "previous rolling window", "field_guids": ["count"],
             "selectors": [{"field_guid": "day", "param_name": "range", "operation": "BETWEEN", "empty_selection": "error",
                            "default": ["2026-01-01", "2026-01-21"], "window": {"days": 7, "offset_days": -7}}]},
        ], "prepare_js": "module.exports = {value: 0};"}}
    draft = compile_recipe("kpi_sparkline", binding,
                           presentation={"comparison": {"enabled": False}, "kpi": {"sparkline": False}})["draft"]
    assert validate_drafts([draft])["ok"]
    script = "const Editor={getId:()=> 'synthetic', getParams:()=>({team:[false],range:['2026-02-01','2026-02-21']})}; const require=()=>({buildSource:x=>x});\n"
    script += draft["tabs"]["sources.js"] + "\nconsole.log(JSON.stringify(module.exports));"
    queries = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    assert queries["numerator"]["columns"] == ["day", "id", "count"]
    assert queries["numerator"]["where"][0] == {"column": "id", "type": "title", "operation": "NIN", "values": ["excluded"]}
    assert queries["numerator"]["where"][1]["values"] == ["false"]
    assert queries["numerator"]["order_by"] == [{"column": "day", "direction": "DESC"}, {"column": "id", "direction": "DESC"}]
    assert queries["numerator"]["limit"] == 100
    assert queries["denominator"]["where"] == [{"column": "day", "type": "title", "operation": "BETWEEN", "values": ["2026-01-01", "2026-01-02"]}]
    assert queries["prior"]["where"][0]["values"] == ["2026-02-08", "2026-02-14"]
    invalid = subprocess.run(["node", "-e", script.replace("2026-02-21", "2026-02-31")], text=True, capture_output=True)
    assert invalid.returncode != 0 and "two ordered ISO dates" in invalid.stderr
