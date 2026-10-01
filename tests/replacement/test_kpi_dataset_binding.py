import json
import subprocess

import pytest

from datalens_dev_mcp.authoring.dataset_source import kpi_dataset_source
from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.authoring.validation import validate_drafts


def bindings():
    return {
        "dataset_id": "synthetic",
        "date": {"field_guid": "date"},
        "metric": {"field_guid": "current"},
        "comparison": {"field_guid": "previous"},
        "fields": [{"guid": g, "title": g} for g in ("date", "current", "previous")],
    }


def test_kpi_latest_is_chronological_and_preserves_missing_values():
    source = kpi_dataset_source({**bindings(), "value_mode": "last"})
    rows = [{"date": "2026-02-02", "current": None, "previous": 3}, {"date": "2026-02-01", "current": 2, "previous": 1}]
    script = "const Editor={getLoadedData:()=>({source:[{event:'metadata'}]})};\n"
    script += "const require=()=>({getDatasetRows:()=>" + json.dumps(rows) + "});\n"
    script += source["prepare_js"] + "\nconsole.log(JSON.stringify(module.exports));"
    result = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    assert result["value"] is None
    assert result["previous"] == 3
    assert result["points"][0] == {"date": "2026-02-01", "value": 2}


def test_kpi_never_infers_sum_for_nonadditive_metric():
    with pytest.raises(ValueError, match="explicit value_mode"):
        kpi_dataset_source(bindings())
    with pytest.raises(ValueError, match="additive"):
        kpi_dataset_source({**bindings(), "value_mode": "sum"})


@pytest.mark.parametrize("comparison,sparkline", [(True, True), (False, True), (False, False), (True, False)])
@pytest.mark.parametrize("value", [0, None, 7.25])
def test_period_kpi_queries_follow_effective_consumers(comparison, sparkline, value):
    source_binding = {
        **bindings(), "value_mode": "aggregate", "metric": {"field_guid": "current", "label": "Total"},
        "fields": [{"guid": "date", "title": "date", "type": "DIMENSION"},
                   {"guid": "current", "title": "current", "type": "MEASURE", "aggregation": "avg"}],
        "periods": {"current": {"param_name": "now", "default": ["2026-01-01", "2026-01-02"]}},
    }
    source_binding.pop("comparison")
    if comparison:
        source_binding["periods"]["previous"] = {"param_name": "before", "default": ["2025-12-30", "2025-12-31"]}
    else:
        # An inactive prior input cannot prevent a valid current total.
        source_binding["periods"]["previous"] = {"unused": "invalid"}
    bundle = compile_recipe("kpi_sparkline", source_binding,
                            presentation={"comparison": {"enabled": comparison}, "kpi": {"sparkline": sparkline}})
    draft = bundle["draft"]
    assert validate_drafts([draft])["ok"]
    aliases = ["current_total"] + (["source"] if sparkline else []) + (["previous_total"] if comparison else [])
    data = {alias: [{"current": value}] if alias == "current_total" else [] for alias in aliases}
    script = "const vm = require('vm'); const requests = []; let result;\n"
    script += "const params = (()=>{const module={exports:{}};" + draft["tabs"]["params.js"] + "return module.exports;})();\n"
    script += "const data = " + json.dumps(data) + ";\n"
    script += "const Editor = {getParams:()=>params, getId:()=> 'synthetic', getLoadedData:()=>data, wrapFn:({fn,args})=>{result = args; return (...a)=>fn(...a,...args);}, generateHtml:x=>x};\n"
    script += "const sourceModule = {exports:{}}; vm.runInNewContext(" + json.dumps(draft["tabs"]["sources.js"]) + ", {module:sourceModule, Editor, require:()=>({buildSource:q=>{requests.push(q);return q;}})});\n"
    script += "const target = {exports:{}}; vm.runInNewContext(" + json.dumps(draft["tabs"]["prepare.js"]) + ", {module:target, Editor, require:()=>({getDatasetRows:({datasetName})=>{if(!(datasetName in data))throw Error(datasetName); return data[datasetName];}})});\n"
    script += "console.log(JSON.stringify({queries:sourceModule.exports, params, html:target.exports.render({width:320,height:200})}));"
    result = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    assert set(result["queries"]) == set(aliases)
    assert result["queries"]["current_total"]["columns"] == ["current"]
    assert result["queries"]["current_total"]["where"][0]["column"] == "date"
    assert ("before" in result["params"]) is comparison
    assert ("No data" in result["html"]) is (value is None)
    assert ("kpi-previous" in result["html"]) is (comparison and value is not None)


def test_kpi_profile_changes_regenerate_owned_sources_and_detect_drift(tmp_path):
    binding = {**bindings(), "value_mode": "aggregate", "metric": {"field_guid": "current", "label": "Total"},
               "comparison": {}, "fields": [{"guid": "date", "title": "date"},
                   {"guid": "current", "title": "current", "type": "MEASURE", "aggregation": "countd"}],
               "periods": {name: {"param_name": name, "default": ["2026-01-01", "2026-01-02"]}
                           for name in ("current", "previous")}}
    user = tmp_path / "user.json"
    user.write_text(json.dumps({"defaults": {"comparison": {"enabled": False}}}))
    project = tmp_path / "project"
    (project / ".datalens").mkdir(parents=True)
    (project / ".datalens/authoring.json").write_text(json.dumps({"defaults": {"kpi": {"sparkline": False}}}))
    compact = compile_recipe("kpi_sparkline", binding, project_root=project, user_config_path=user)
    assert len(compact["summary"]["source_plan"]["queries"]) == 1
    full = compile_recipe("kpi_sparkline", binding, project_root=project, user_config_path=user,
                          presentation={"comparison": {"enabled": True}, "kpi": {"sparkline": True}})
    assert len(full["summary"]["source_plan"]["queries"]) == 3
    compact["draft"]["visual_contract"]["kpi"]["sparkline"] = True
    report = validate_drafts([compact["draft"]])
    assert any(error["code"] == "recipe_payload_drift" for item in report["items"] for error in item["errors"])
