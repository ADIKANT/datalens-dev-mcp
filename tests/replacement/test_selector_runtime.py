import json
import subprocess

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.editor.validation import validate_editor_draft


def test_static_selector_exports_documented_controls_and_string_defaults(tmp_path):
    draft = compile_recipe(
        "selector",
        {
            "parameter": {"name": "region", "default": 7},
            "options": [{"title": "Synthetic region", "value": 7}],
            "consumers": ["synthetic-chart"],
        },
        user_config_path=tmp_path / "absent.json",
    )["draft"]
    assert validate_editor_draft(draft)["ok"]
    assert "config.json" not in draft["tabs"]
    js = draft["tabs"]["controls.js"] + "\nconsole.log(JSON.stringify(module.exports));"
    output = subprocess.check_output(["node", "-e", js], text=True)
    controls = json.loads(output)["controls"]
    assert controls[0]["type"] == "select"
    assert controls[0]["param"] == "region"
    assert controls[0]["content"] == [{"title": "Synthetic region", "value": "7"}]
    assert "updateParams" not in js
    params = subprocess.check_output(
        ["node", "-e", draft["tabs"]["params.js"] + "console.log(JSON.stringify(module.exports));"], text=True
    )
    assert json.loads(params) == {"region": ["7"]}
