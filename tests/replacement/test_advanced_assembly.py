import json
import subprocess

import pytest

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.editor.formatting import format_editor_source
from datalens_dev_mcp.editor.validation import validate_editor_draft


@pytest.mark.parametrize("source", [
    'const rows=[{name:"First",amount:42},{name:"Second",amount:0}];module.exports={rows:rows.map(r=>({...r,total:r.amount*2})),count:rows.length};',
    r'const sql=`SELECT \'a  b\'\nFROM sample WHERE x=${2}`;const raw=String.raw`\n\t`;module.exports={sql,raw,regex:/a{1,2}\/b/g.source,unicode:"\u0041"};',
    'const row={nested:{amount:0}};/* keep context */module.exports={value:row?.nested?.amount??42,ratio:6/2/3};',
])
def test_editor_formatting_preserves_javascript_results(source):
    formatted = format_editor_source(source)
    assert format_editor_source(formatted) == formatted
    program = ('const vm=require("node:vm");const inputs=' + json.dumps([source, formatted]) + ';'
               'console.log(JSON.stringify(inputs.map(s=>{const c={module:{exports:{}}};'
               'vm.runInNewContext(s,c);return c.module.exports})));')
    before, after = json.loads(subprocess.check_output(["node", "-e", program], text=True))
    assert before == after


def test_editor_formatting_rejects_changed_automatic_semicolon_insertion():
    with pytest.raises(ValueError, match="would change JavaScript syntax"):
        format_editor_source('function value(){return\n{amount:42}}module.exports=value();')


def test_assembled_prepare_calls_renderer_without_unsupported_config_tab(tmp_path):
    draft = compile_recipe(
        "comparison_matrix",
        {
            "rows": [],
            "metric": {"label": "Synthetic"},
            "source": {
                "meta": {},
                "sources_js": "module.exports = {};",
                "prepare_js": "module.exports = {rows: [{label: 'Synthetic row', current: 2, previous: 1}]};",
            },
        },
        user_config_path=tmp_path / "absent.json",
    )["draft"]
    assert validate_editor_draft(draft)["ok"]
    assert "config.json" not in draft["tabs"]
    script = "const Editor = {wrapFn: x => x, generateHtml: x => x};\n" + draft["tabs"]["prepare.js"]
    script += "\nconsole.log(module.exports.render.fn({height:200}, ...module.exports.render.args));"
    html = subprocess.check_output(["node", "-e", script], text=True)
    assert "Synthetic row" in html and "100.00%" in html


def test_advanced_compile_does_not_invent_source(tmp_path):
    with pytest.raises(ValueError, match="explicit source"):
        compile_recipe(
            "comparison_matrix",
            {"rows": [], "metric": {"label": "Synthetic"}},
            user_config_path=tmp_path / "absent.json",
        )
