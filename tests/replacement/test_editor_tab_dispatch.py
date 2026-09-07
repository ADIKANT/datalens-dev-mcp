from types import SimpleNamespace

import pytest

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


@pytest.mark.parametrize("filename", ["config.json", "build.js", "description.js", "unknown.js"])
def test_editor_unsupported_tab_prevents_write(filename):
    writes = []
    builder = SimpleNamespace(build=lambda *args: writes.append(args), meta=lambda _: None, description=lambda _: None)
    client = SimpleNamespace(create=SimpleNamespace(editor_chart=SimpleNamespace(advanced_chart=lambda **_: builder)))
    with pytest.raises(ValueError, match="unsupported tab"):
        SdkAdapter(client=client).create(
            {
                "name": "Synthetic",
                "object_type": "editor_chart",
                "variant": "advanced-chart_node",
                "tabs": {"meta.json": "{}", filename: "{}"},
            },
            {"workbook_id": "synthetic"},
        )
    assert writes == []


def test_supported_editor_tabs_are_forwarded_verbatim():
    received, writes = {}, []
    builder = SimpleNamespace(
        **{
            name: lambda text, name=name: received.update({name: text})
            for name in ("meta", "params", "sources", "prepare", "controls")
        }
    )

    def build():
        writes.append(True)
        return {"id": "synthetic-chart"}

    builder.build = build
    client = SimpleNamespace(create=SimpleNamespace(editor_chart=SimpleNamespace(advanced_chart=lambda **_: builder)))
    tabs = {
        "meta.json": "{}",
        "params.js": "module.exports = {};",
        "sources.js": "module.exports = {};",
        "prepare.js": "module.exports = {};",
        "controls.js": "module.exports = [];",
    }
    result = SdkAdapter(client=client).create(
        {"name": "Synthetic", "object_type": "editor_chart", "variant": "advanced-chart_node", "tabs": tabs},
        {"workbook_id": "synthetic"},
    )
    assert received == {filename.split(".")[0]: content for filename, content in tabs.items()}
    assert writes == [True]
    assert result["expected_readback"] == {"data": received}


def test_static_validation_does_not_approve_unhandled_config_tab():
    from datalens_dev_mcp.editor.validation import validate_editor_draft

    result = validate_editor_draft(
        {
            "variant": "advanced-chart_node",
            "tabs": {
                "meta.json": "{}",
                "params.js": "",
                "sources.js": "",
                "prepare.js": "",
                "controls.js": "",
                "config.json": "{}",
            },
        }
    )
    assert not result["ok"]
    assert any(issue["code"] == "editor_tabs_unsupported" for issue in result["issues"])
