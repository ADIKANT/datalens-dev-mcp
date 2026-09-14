from types import SimpleNamespace

import pytest

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
from datalens_dev_mcp.objects.read import ObjectReadService


@pytest.mark.parametrize(
    "kind", ["advanced-chart_node", "advanced_chart", "d3_node", "table_node", "control_node", "markdown_node"]
)
@pytest.mark.parametrize("branch", ["saved", "published"])
def test_editor_create_aliases_have_matching_readback_route(kind, branch):
    calls = []
    wire_type = "advanced-chart_node" if kind == "advanced_chart" else kind

    def get_editor(**kwargs):
        calls.append(kwargs)
        return {"id": "synthetic-chart", "revId": "synthetic-revision", "scope": "widget", "type": wire_type}

    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(editor_chart=get_editor)))
    reader = ObjectReadService(api=None, sdk=adapter)
    result = reader.object_get(kind, "synthetic-chart", branch=branch)
    assert result["object"]["id"] == "synthetic-chart"
    assert result["identity"]["object_type"] == kind
    assert result["identity"]["branch"] == branch
    assert calls == [{"by_id": "synthetic-chart", "branch": branch}]
    wire_type = "table_node" if wire_type != "table_node" else "control_node"
    with pytest.raises(ValueError, match="subtype mismatch"):
        reader.object_get(kind, "synthetic-chart", branch=branch)


def test_chart_entry_envelope_does_not_hide_revision_or_tabs():
    snapshot = {"entry": {"id": "synthetic-chart", "revId": "r1", "data": {"prepare": "synthetic"}}}
    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(editor_chart=lambda **_: snapshot)))
    assert adapter.get_object("editor_chart", "synthetic-chart") == snapshot["entry"]


def test_chart_entry_derives_readback_name_from_provider_key() -> None:
    snapshot = {
        "entry": {
            "entryId": "synthetic-chart",
            "key": "workbook-id/Synthetic KPI - Updated",
            "revId": "r2",
            "data": {"prepare": "synthetic"},
        }
    }
    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(editor_chart=lambda **_: snapshot)))

    result = adapter.get_object("editor_chart", "synthetic-chart")

    assert result["name"] == "Synthetic KPI - Updated"


def test_chart_entry_derives_readback_name_from_top_level_provider_key() -> None:
    snapshot = {
        "entryId": "synthetic-chart",
        "key": "workbook-id/Synthetic generic chart",
        "revId": "r2",
        "data": {"prepare": "synthetic"},
    }
    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(chart=lambda **_: snapshot)))

    result = adapter.get_object("widget", "synthetic-chart")

    assert result["name"] == "Synthetic generic chart"


def test_cleanup_inventory_widget_alias_routes_generic_chart_read_and_delete() -> None:
    calls: list[dict[str, str]] = []
    deleted: list[bool] = []
    target = SimpleNamespace(
        response_snapshot={"entry": {"entryId": "synthetic-chart", "key": "folder/Synthetic chart"}},
        delete=lambda: deleted.append(True),
    )

    def get_chart(**kwargs):
        calls.append(kwargs)
        return target

    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(chart=get_chart)))

    assert adapter.get_object("widget", "synthetic-chart")["name"] == "Synthetic chart"
    assert adapter.delete("widget", "synthetic-chart")["deleted"] is True
    assert calls == [
        {"by_id": "synthetic-chart", "branch": "saved"},
        {"by_id": "synthetic-chart", "branch": "saved"},
    ]
    assert deleted == [True]


def test_cleanup_inventory_dash_alias_routes_dashboard_delete() -> None:
    calls: list[dict[str, str]] = []
    deleted: list[bool] = []
    target = SimpleNamespace(delete=lambda: deleted.append(True))

    def get_dashboard(**kwargs):
        calls.append(kwargs)
        return target

    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(dashboard=get_dashboard)))

    assert adapter.delete("dash", "synthetic-dashboard")["deleted"] is True
    assert calls == [{"by_id": "synthetic-dashboard", "branch": "saved"}]
    assert deleted == [True]
