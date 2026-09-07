from types import SimpleNamespace

import pytest

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


@pytest.mark.parametrize(
    "kind", ["advanced-chart_node", "advanced_chart", "d3_node", "table_node", "control_node", "markdown_node"]
)
@pytest.mark.parametrize("branch", ["saved", "published"])
def test_editor_create_aliases_have_matching_readback_route(kind, branch):
    calls = []

    def get_editor(**kwargs):
        calls.append(kwargs)
        return {"id": "synthetic-chart", "revId": "synthetic-revision"}

    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(editor_chart=get_editor)))
    result = adapter.get_object(kind, "synthetic-chart", branch=branch)
    assert result["id"] == "synthetic-chart"
    assert calls == [{"by_id": "synthetic-chart", "branch": branch}]


def test_chart_entry_envelope_does_not_hide_revision_or_tabs():
    snapshot = {"entry": {"id": "synthetic-chart", "revId": "r1", "data": {"prepare": "synthetic"}}}
    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(editor_chart=lambda **_: snapshot)))
    assert adapter.get_object("editor_chart", "synthetic-chart") == snapshot["entry"]
