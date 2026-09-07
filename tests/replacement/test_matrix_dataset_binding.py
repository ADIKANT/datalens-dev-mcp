import json
import subprocess

from datalens_dev_mcp.authoring.recipes import compile_recipe


def test_matrix_dataset_binding_uses_guid_query_and_maps_rows_without_null_coercion(tmp_path):
    draft = compile_recipe("comparison_matrix", {
        "dataset_id": "synthetic-dataset", "object_name": "Synthetic matrix",
        "rows": [{"field_guid": "region"}], "metric": {"field_guid": "current"},
        "comparison": {"field_guid": "previous"},
        "fields": [{"guid": "region", "title": "Region"}, {"guid": "current", "title": "Current"},
                   {"guid": "previous", "title": "Previous"}],
    }, user_config_path=tmp_path / "absent.json")["draft"]
    assert json.loads(draft["tabs"]["meta.json"])["links"]["dataset"] == "synthetic-dataset"
    sources = "const Editor={getId:()=> 'synthetic-dataset'};\n" + draft["tabs"]["sources.js"]
    sources += "console.log(JSON.stringify(module.exports));"
    request = json.loads(subprocess.check_output(["node", "-e", sources], text=True))["source"]
    assert request["data"]["fields"][1]["ref"] == {"type": "id", "title": "current"}
    prepare = "const Editor={wrapFn:x=>x}; const require=()=>({getDatasetRows:()=>[{Region:'Synthetic',Current:null,Previous:'2'}]});\n"
    prepare += draft["tabs"]["prepare.js"] + "\nconsole.log(JSON.stringify(module.exports.render.args[0]));"
    result = json.loads(subprocess.check_output(["node", "-e", prepare], text=True))
    assert result["rows"] == [{"label": "Synthetic", "current": None, "previous": 2}]
