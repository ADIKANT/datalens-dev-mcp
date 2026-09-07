from __future__ import annotations

from types import SimpleNamespace

from datalens_sdk import Connection, DataLensClientYC, EntryLocation
from datalens_sdk.converter.dashboard import DashboardConverter
from datalens_sdk.converter.dataset import DatasetConverter
from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
from datalens_dev_mcp.authoring.typed_graph import dashboard_builder, dataset_builder

DATASET_SPEC = {
    "connection_id": "connection-existing",
    "source": {
        "alias": "Synthetic events",
        "source_type": "CH_TABLE",
        "parameters": {"db_name": "synthetic", "table_name": "events"},
    },
    "fields": [
        {
            "guid": "region",
            "title": "Region",
            "source": "region",
            "kind": "dimension",
            "cast": "string",
        },
        {
            "guid": "amount",
            "title": "Amount",
            "source": "amount",
            "kind": "measure",
            "cast": "float",
            "aggregation": "sum",
        },
        {
            "guid": "order_count",
            "title": "Orders",
            "formula": "COUNTD([order_id])",
            "kind": "measure",
            "aggregation": "none",
        },
    ],
}


DASHBOARD_SPEC = {
    "tabs": [
        {
            "title": "Overview",
            "tab_id": "overview",
            "items": [
                {
                    "kind": "external_selector",
                    "chart_id": "selector-id",
                    "title": "Region",
                    "item_id": "selector",
                    "at": [0, 0, 36, 2],
                },
                {"kind": "chart", "chart_id": "kpi-id", "title": "KPI", "item_id": "kpi", "at": [0, 2, 12, 8]},
                {"kind": "chart", "chart_id": "trend-id", "title": "Trend", "item_id": "trend", "at": [12, 2, 12, 8]},
                {"kind": "chart", "chart_id": "table-id", "title": "Table", "item_id": "table", "at": [24, 2, 12, 8]},
            ],
        }
    ],
    "settings": {"dependent_selectors": True, "hide_dash_title": False},
}


def test_dataset_builder_uses_official_source_and_field_actions_without_snapshot() -> None:
    with DataLensClientYC(auth=None) as client:
        connection = Connection(id="connection-existing", type="clickhouse", installation="yacloud")
        builder = dataset_builder(
            client,
            connection,
            DATASET_SPEC,
            name="Synthetic dataset",
            location=EntryLocation.workbook("workbook"),
        )
        create_payload = DatasetConverter.from_domain_create(builder.to_spec()).to_payload()
        validation_payload = DatasetConverter.from_domain_create_validate_step(
            sources=builder.to_spec().sources,
            relations=builder.to_spec().relations,
            actions=builder.to_spec().actions,
        )

    assert create_payload["dataset"]["sources"][0]["connection_id"] == "connection-existing"
    updates = validation_payload["data"]["updates"]
    fields = [update for update in updates if update["action"] == "add_field"]
    calculations = [
        update
        for update in updates
        if update["action"] == "add_field" and update["field"].get("calc_mode") == "formula"
    ]
    assert {update["field"]["guid"] for update in fields} >= {"region", "amount", "order_count"}
    assert calculations[0]["field"]["formula"] == "COUNTD([order_id])"


def test_dashboard_builder_places_three_distinct_charts_and_external_selector() -> None:
    with DataLensClientYC(auth=None) as client:
        builder = dashboard_builder(
            client,
            DASHBOARD_SPEC,
            name="Synthetic dashboard",
            location=EntryLocation.workbook("workbook"),
        )
        payload = DashboardConverter.from_domain_create(builder.to_spec()).to_payload()

    items = payload["entry"]["data"]["tabs"][0]["items"]
    assert [item["type"] for item in items] == ["control", "widget", "widget", "widget"]
    assert items[0]["data"]["source"]["chartId"] == "selector-id"
    assert [item["data"]["tabs"][0]["chartId"] for item in items[1:]] == ["kpi-id", "trend-id", "table-id"]


def test_sdk_adapter_typed_dataset_and_dashboard_create_call_build_once() -> None:
    built: list[str] = []
    with DataLensClientYC(auth=None) as official:

        def dataset_factory(**kwargs):
            builder = official.create.dataset(**kwargs)
            builder.build = lambda: built.append("dataset") or {"id": "dataset-id"}
            return builder

        def dashboard_factory(**kwargs):
            builder = official.create.dashboard(**kwargs)
            builder.build = lambda: built.append("dashboard") or {"id": "dashboard-id", "entry": {"data": {}}}
            return builder

        connection = Connection(id="connection-existing", type="clickhouse", installation="yacloud")
        client = SimpleNamespace(
            get=SimpleNamespace(connection=lambda **_: connection),
            create=SimpleNamespace(
                source=official.create.source,
                dataset=dataset_factory,
                dashboard=dashboard_factory,
            ),
        )
        adapter = SdkAdapter(client=client)
        dataset = adapter.create(
            {"object_type": "dataset", "name": "Synthetic dataset", "dataset": DATASET_SPEC},
            {"workbook_id": "workbook"},
        )
        dashboard = adapter.create(
            {"object_type": "dashboard", "name": "Synthetic dashboard", "dashboard": DASHBOARD_SPEC},
            {"workbook_id": "workbook"},
        )

    assert built == ["dataset", "dashboard"]
    assert dataset["object_id"] == "dataset-id"
    assert dashboard["object_id"] == "dashboard-id"
    assert "expected_readback" in dashboard


def test_dependency_batch_binds_dataset_three_charts_selector_and_dashboard_ids(tmp_path) -> None:
    identities = [
        ("dataset", "dataset-id"),
        ("wizard_chart", "kpi-id"),
        ("wizard_chart", "trend-id"),
        ("editor_chart", "table-id"),
        ("editor_chart", "selector-id"),
        ("dashboard", "dashboard-id"),
    ]
    replies = {(kind, object_id, "saved"): [rb(kind, object_id, "r1", {})] for kind, object_id in identities}
    replies[("dataset", "dataset-id", "saved")][0]["identity"]["branch"] = "unbranched"
    reader = FakeReader(replies)
    id_by_ref = {
        "dataset": "dataset-id",
        "kpi": "kpi-id",
        "trend": "trend-id",
        "table": "table-id",
        "selector": "selector-id",
        "dashboard": "dashboard-id",
    }

    class GraphBackend(FakeBackend):
        def __init__(self) -> None:
            super().__init__([])

        def create(self, draft, destination):
            self.calls.append(("create", {"draft": draft, "destination": destination}))
            return {"object_id": id_by_ref[draft["client_ref"]]}

    backend = GraphBackend()
    dataset_ref = {"$object_ref": "dataset"}
    drafts = [
        {"client_ref": "dataset", "object_type": "dataset", "name": "Synthetic", "dataset": DATASET_SPEC},
        {"client_ref": "kpi", "object_type": "wizard_chart", "name": "KPI", "wizard": {"dataset_id": dataset_ref}},
        {"client_ref": "trend", "object_type": "wizard_chart", "name": "Trend", "wizard": {"dataset_id": dataset_ref}},
        {
            "client_ref": "table",
            "object_type": "editor_chart",
            "name": "Table",
            "tabs": {
                "meta.json": "{}",
                "params.js": "module.exports={};",
                "sources.js": "",
                "prepare.js": "",
                "controls.js": "",
            },
            "dataset_id": dataset_ref,
        },
        {
            "client_ref": "selector",
            "object_type": "editor_chart",
            "name": "Selector",
            "tabs": {"meta.json": "{}", "params.js": "module.exports={};", "controls.js": ""},
        },
        {
            "client_ref": "dashboard",
            "object_type": "dashboard",
            "name": "Dashboard",
            "dashboard": {
                "tabs": [
                    {
                        "title": "Overview",
                        "items": [
                            {
                                "kind": "external_selector",
                                "chart_id": {"$object_ref": "selector"},
                                "title": "Region",
                                "at": [0, 0, 36, 2],
                            },
                            {"kind": "chart", "chart_id": {"$object_ref": "kpi"}, "title": "KPI", "at": [0, 2, 12, 8]},
                            {
                                "kind": "chart",
                                "chart_id": {"$object_ref": "trend"},
                                "title": "Trend",
                                "at": [12, 2, 12, 8],
                            },
                            {
                                "kind": "chart",
                                "chart_id": {"$object_ref": "table"},
                                "title": "Table",
                                "at": [24, 2, 12, 8],
                            },
                        ],
                    }
                ]
            },
        },
    ]

    result = service(tmp_path, reader, backend).create_objects(drafts, {"workbook_id": "workbook"})

    assert result["status"] == "completed", result
    calls = {call[1]["draft"]["client_ref"]: call[1]["draft"] for call in backend.calls}
    assert calls["kpi"]["wizard"]["dataset_id"] == "dataset-id"
    assert calls["trend"]["wizard"]["dataset_id"] == "dataset-id"
    items = calls["dashboard"]["dashboard"]["tabs"][0]["items"]
    assert [item["chart_id"] for item in items] == ["selector-id", "kpi-id", "trend-id", "table-id"]
