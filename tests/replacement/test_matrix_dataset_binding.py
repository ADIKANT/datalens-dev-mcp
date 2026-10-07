import json
import subprocess

import pytest
from jsonschema import Draft202012Validator

from datalens_dev_mcp.authoring.profiles import get_authoring_defaults
from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.authoring.validation import validate_drafts


def test_matrix_dataset_binding_uses_guid_query_and_maps_rows_without_null_coercion(tmp_path):
    bundle = compile_recipe(
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
    )
    draft = bundle["draft"]
    schema = get_authoring_defaults(family="comparison_matrix")["recipe_contract"]["bindings_schema"]
    assert "rows" in schema["properties"]
    Draft202012Validator(schema).validate(draft["bindings"])
    plan = bundle["summary"]["source_plan"]
    assert plan["kind"] == "dataset" and plan["upstream_cost"] == "unverified"
    assert [field["field_guid"] for field in plan["queries"][0]["fields"]] == ["region", "current", "previous"]
    assert "source" not in draft["bindings"]
    assert validate_drafts([draft])["ok"]
    restyled = compile_recipe("comparison_matrix", draft["bindings"], {"geometry": {"width": 18}})
    assert restyled["summary"]["source_plan"] == plan
    assert validate_drafts([restyled["draft"]])["ok"]
    with pytest.raises(ValueError, match=r"/bindings/rows/0/field_guid"):
        compile_recipe("comparison_matrix", {**draft["bindings"], "rows": [{}]})
    with pytest.raises(ValueError, match=r"/bindings/comparison"):
        compile_recipe("comparison_matrix", {k: v for k, v in draft["bindings"].items() if k != "comparison"})
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


@pytest.mark.parametrize("route", ["source", "direct_source", "prepared_data"])
def test_matrix_alternative_routes_do_not_require_dataset_fields(route, tmp_path):
    alternatives = {
        "source": {"meta": {}, "sources_js": "module.exports = {};", "prepare_js": "module.exports = {rows: []};"},
        "direct_source": {"kind": "api", "connection_id": "synthetic", "path": "/rows",
                          "prepare_js": "module.exports = {rows: []};"},
        "prepared_data": {"rows": []},
    }
    bindings = {"rows": [], "metric": "Count", route: alternatives[route]}
    schema = get_authoring_defaults(family="comparison_matrix")["recipe_contract"]["bindings_schema"]
    Draft202012Validator(schema).validate(bindings)
    result = compile_recipe("comparison_matrix", bindings, user_config_path=tmp_path / "absent.json")
    assert result["summary"]["source_plan"]["kind"] == {"source": "custom", "direct_source": "api", "prepared_data": "prepared"}[route]
    assert validate_drafts([result["draft"]])["ok"]
    # An unused Dataset ID must not turn prepared values into an implicit query.
    if route == "prepared_data":
        with_id = compile_recipe("comparison_matrix", {**bindings, "dataset_id": "synthetic"})
        assert with_id["draft"]["tabs"] == result["draft"]["tabs"]


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
    bundle = compile_recipe("kpi_sparkline", binding,
                            presentation={"comparison": {"enabled": False}, "kpi": {"sparkline": False}})
    draft = bundle["draft"]
    plan = bundle["summary"]["source_plan"]
    assert plan["kind"] == "dataset" and plan["prepare_dependencies"] == "explicit_custom"
    assert [item["alias"] for item in plan["queries"]] == ["numerator", "denominator", "prior"]
    assert plan["queries"][0]["selectors"][0]["field_guid"] == "team"
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
    invalid = subprocess.run(["node", "-e", script.replace("2026-02-21", "2026-02-31")], text=True, capture_output=True, check=False)
    assert invalid.returncode != 0 and "two ordered ISO dates" in invalid.stderr
