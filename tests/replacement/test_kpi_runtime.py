import json
import subprocess
from importlib.resources import files

from datalens_dev_mcp.authoring.recipes import list_recipes


def render(data):
    source = files("datalens_dev_mcp.assets.recipes").joinpath("kpi_sparkline_renderer.js").read_text()
    config = list_recipes()["kpi_sparkline"]["visual_contract"]
    script = "const vm = require('node:vm'); const Editor = {generateHtml: x => x, wrapFn: x => x};\n" + source
    script += "\nconst result = module.exports(" + json.dumps(data) + "," + json.dumps(config) + ");"
    script += "const fn = vm.runInNewContext('(' + result.render.fn.toString() + ')', {Editor});"
    script += "console.log(fn({width:300,height:180}, ...result.render.args));"
    return subprocess.check_output(["node", "-e", script], text=True)


def test_kpi_zero_is_not_no_data_and_missing_points_break_line():
    html = render({"value": 0, "previous": 0, "points": [0, 1, None, 2, 0]})
    assert "No data" not in html
    assert "Undefined: previous = 0" in html
    assert html.count('data-id="sparkline-area"') == 2
    assert "NaN" not in html and "Infinity" not in html


def test_kpi_missing_value_is_not_rendered_as_zero():
    html = render({"value": None, "points": []})
    assert "No data" in html
    assert "<svg" not in html
