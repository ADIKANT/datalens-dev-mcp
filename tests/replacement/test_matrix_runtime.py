import json
import subprocess
from importlib.resources import files

from datalens_dev_mcp.authoring.recipes import list_recipes


def test_matrix_wrapfn_has_no_outer_closure_and_handles_missing_zero_and_escaping():
    source = files("datalens_dev_mcp.assets.recipes").joinpath("version_matrix_renderer.js").read_text()
    contract = list_recipes()["comparison_matrix"]["visual_contract"]
    data = {"rows": [{"label": "<script>synthetic</script>", "current": 0, "previous": 0},
                     {"label": "Missing", "current": None, "previous": 2},
                     {"label": "Growth", "current": 12, "previous": 10}]}
    script = "const vm = require('node:vm'); const Editor = {generateHtml: x => x, wrapFn: x => x};\n" + source
    script += "\nconst exported = module.exports(" + json.dumps(data) + "," + json.dumps(contract) + ");"
    script += "const handler = vm.runInNewContext('(' + exported.render.fn.toString() + ')', {Editor});"
    script += "console.log(handler({width:320,height:180}, ...exported.render.args));"
    html = subprocess.check_output(["node", "-e", script], text=True)
    assert 'role="table"' in html
    assert "&lt;script&gt;synthetic&lt;/script&gt;" in html
    assert "Undefined: previous = 0" in html
    assert "Missing comparison" in html
    assert "20.00%" in html
    assert "NaN" not in html and "Infinity" not in html
