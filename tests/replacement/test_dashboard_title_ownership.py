"""Recipe presentation must survive placement into the actual SDK payload."""

import subprocess
from copy import deepcopy

import pytest
from datalens_sdk import DataLensClientYC, EntryLocation
from datalens_sdk.converter.dashboard import DashboardConverter

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.authoring.typed_graph import dashboard_builder


def compile_kpi(tmp_path, presentation=None):
    return compile_recipe(
        "kpi_sparkline",
        {
            "object_name": "Synthetic orders KPI",
            "metric": {"field_guid": "orders", "label": "Orders", "unit": "count"},
            "date": {"field_guid": "order_day"},
            "comparison": {"field_guid": "previous_orders", "method": "previous_period", "label": "Previous period"},
            "prepared_data": {
                "value": 12,
                "previous": 10,
                "points": [
                    {"date": "2026-01-01", "value": 10},
                    {"date": "2026-01-02", "value": 12},
                ],
            },
        },
        presentation=presentation,
        user_config_path=tmp_path / "absent.json",
        project_root=tmp_path,
    )["draft"]


def render_body(draft):
    script = "const Editor={wrapFn:x=>x,generateHtml:x=>x};\n" + draft["tabs"]["prepare.js"]
    script += "\nconsole.log(module.exports.render.fn({width:480,height:260},...module.exports.render.args));"
    return subprocess.check_output(["node", "-e", script], text=True)


def assemble(item):
    with DataLensClientYC(auth=None) as client:
        builder = dashboard_builder(
            client,
            {"tabs": [{"title": "Overview", "items": [item]}]},
            name="Synthetic overview",
            location=EntryLocation.workbook("workbook"),
        )
        return DashboardConverter.from_domain_create(builder.to_spec()).to_payload()["entry"]["data"]["tabs"][0]


@pytest.mark.parametrize(
    ("owner", "visible", "body_count", "native_count"),
    [
        ("body", True, 1, 0),
        ("widget", True, 0, 1),
        ("hidden", True, 0, 0),
        ("widget", False, 0, 0),
    ],
)
def test_selected_title_owner_has_one_heading_in_assembled_dashboard(
    tmp_path, owner, visible, body_count, native_count
):
    draft = compile_kpi(tmp_path, {"visible_title": {"owner": owner, "visible": visible, "text": "Orders"}})
    item = {
        "kind": "chart",
        "chart_id": "kpi-id",
        "title": "Orders",
        "at": [0, 0, 12, 8],
        "presentation": draft["visual_contract"],
    }
    tab = assemble(item)
    widget = tab["items"][0]["data"]
    html = render_body(draft)
    assert html.count(">Orders</div>") == body_count
    assert int(not widget["hideTitle"]) == native_count
    assert body_count + native_count == (1 if visible and owner != "hidden" else 0)
    assert ">12<" in html and ">10<" in html and "sparkline-area" in html
    assert tab["layout"] == [{"i": "el_1", "x": 0, "y": 0, "w": 12, "h": 8}]


@pytest.mark.parametrize(
    ("owner", "enabled", "body_count", "native_count"),
    [
        ("body", True, 1, 0),
        ("widget", True, 0, 1),
        ("hidden", True, 0, 0),
        ("widget", False, 0, 0),
    ],
)
def test_selected_hint_owner_has_one_target(tmp_path, owner, enabled, body_count, native_count):
    draft = compile_kpi(tmp_path, {"hint": {"owner": owner, "enabled": enabled, "text": "Completed orders"}})
    tab = assemble(
        {
            "kind": "chart",
            "chart_id": "kpi-id",
            "title": "Orders",
            "at": [0, 0, 12, 8],
            "presentation": draft["visual_contract"],
        }
    )
    native = tab["items"][0]["data"]["tabs"][0]
    assert render_body(draft).count('data-id="kpi-hint"') == body_count
    assert int(native.get("enableHint", False)) == native_count
    if native_count:
        assert native["hint"] == "Completed orders"
    assert draft["visual_contract"]["hint"]["owner"] == owner
    assert draft["visual_contract"]["hint"]["enabled"] == enabled


def test_standalone_kpi_retains_body_hint_and_default_title(tmp_path):
    draft = compile_kpi(tmp_path)
    html = render_body(draft)
    assert html.count(">Orders</div>") == 0
    assert html.count('data-id="kpi-hint"') == 1


def test_plain_chart_keeps_native_default_and_explicit_placement_wins(tmp_path):
    item = {"kind": "chart", "chart_id": "wizard-id", "title": "Native orders", "at": [0, 0, 12, 8]}
    assert assemble(item)["items"][0]["data"]["hideTitle"] is False
    draft = compile_kpi(tmp_path)
    item.update(presentation=draft["visual_contract"], show_title=True, hint="Explicit help")
    before = deepcopy(item)
    native = assemble(item)["items"][0]["data"]
    assert native["hideTitle"] is False
    assert native["tabs"][0]["title"] == "Native orders"
    assert native["tabs"][0]["hint"] == "Explicit help"
    assert item == before
    item["show_title"] = False
    item["hint"] = None
    native = assemble(item)["items"][0]["data"]
    assert native["hideTitle"] is True
    assert native["tabs"][0].get("enableHint", False) is False


@pytest.mark.parametrize("text", [None, ["business_meaning"], {"calculation": "sum"}])
def test_widget_hint_does_not_publish_generic_content_keys(tmp_path, text):
    draft = compile_kpi(tmp_path, {"hint": {"owner": "widget", "text": text}})
    tab = assemble(
        {
            "kind": "chart",
            "chart_id": "kpi-id",
            "title": "Orders",
            "at": [0, 0, 12, 8],
            "presentation": draft["visual_contract"],
        }
    )
    assert tab["items"][0]["data"]["tabs"][0].get("enableHint", False) is False
