import subprocess

import pytest

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.editor.validation import validate_editor_draft


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
