from __future__ import annotations

import tempfile
from pathlib import Path

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.pipeline.target_discovery import TargetDiscoveryService, parse_target_url
from datalens_dev_mcp.pipeline.task_contract import TargetContract, WorkspaceContract, create_task_contract


class DiscoveryClient:
    def __init__(
        self,
        *,
        ambiguous: bool = False,
        missing_dashboard: bool = False,
        chart_scope: str = "editor_chart",
        chart_type: str = "",
        unavailable_chart: bool = False,
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.ambiguous = ambiguous
        self.missing_dashboard = missing_dashboard
        self.chart_scope = chart_scope
        self.chart_type = chart_type
        self.unavailable_chart = unavailable_chart

    def rpc_readonly(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == "getDashboard":
            if self.missing_dashboard:
                return {"result": {}}
            return {
                "result": {
                    "dashboard": {
                        "entry": {"entryId": "dash_demo", "workbookId": "book_demo", "revId": "dash-r7"},
                        "data": {"tabs": [{"id": "main", "items": [{"chartId": "chart_demo"}]}]},
                    }
                }
            }
        if method == "getWorkbookEntries":
            dashboards = [
                {"entryId": "dash_demo", "scope": "dashboard", "displayKey": "Demo dashboard"},
            ]
            if self.ambiguous:
                dashboards.append({"entryId": "dash_other", "scope": "dashboard", "displayKey": "Other dashboard"})
            return {
                "total": len(dashboards) + 3,
                "entries": [
                    *dashboards,
                    {
                        "entryId": "chart_demo",
                        "scope": self.chart_scope,
                        "type": self.chart_type,
                        "displayKey": "Trend",
                    },
                    {"entryId": "dataset_demo", "scope": "dataset", "displayKey": "Dataset"},
                    {"entryId": "connection_demo", "scope": "connection", "displayKey": "Connection"},
                ],
            }
        if method in {"getEditorChart", "getWizardChart"}:
            if self.unavailable_chart:
                raise DataLensApiError("chart was not found", http_status=404)
            return {
                "result": {
                    "chart": {
                        "entry": {"entryId": "chart_demo", "revId": "chart-r3"},
                        "data": {
                            "datasetId": "dataset_demo",
                            "visualization": {"measures": [{"guid": "guid_value"}]},
                            "meta": "{}",
                            "sources": "module.exports = {main: {data: []}};",
                            "prepare": "module.exports = function(data) { return data; };",
                        },
                    }
                }
            }
        if method == "getDataset":
            return {
                "result": {
                    "dataset": {
                        "datasetId": "dataset_demo",
                        "revId": "dataset-r2",
                        "fields": [
                            {"guid": "guid_date", "name": "event_date", "type": "date"},
                            {"guid": "guid_value", "name": "value", "type": "float"},
                        ],
                        "sources": [{"connectionId": "connection_demo"}],
                    }
                }
            }
        if method == "getConnection":
            return {"result": {"connection": {"connectionId": "connection_demo", "type": "clickhouse"}}}
        raise AssertionError(method)


def _contract(root: Path, *, dashboard_id: str = "dash_demo", workbook_id: str = "") -> dict:
    return create_task_contract(
        raw_request="Update the synthetic dashboard",
        mode="update",
        route="unresolved",
        workspace=WorkspaceContract(project_root=str(root)),
        target=TargetContract(
            dashboard_id=dashboard_id,
            workbook_id=workbook_id,
            object_ids=(dashboard_id,) if dashboard_id else (),
            object_types=("dashboard",) if dashboard_id else (),
        ),
    ).to_dict()


def test_dashboard_discovery_builds_bounded_graph_and_dataset_field_catalog() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient()
        result = TargetDiscoveryService(client).discover(_contract(Path(tmp)))
    assert result["status"] == "success"
    assert result["target_binding"]["source"] == "live_discovery"
    assert result["target_binding"]["saved_revision"] == "dash-r7"
    assert result["target_binding"]["technology"] == "editor_advanced"
    dataset = next(item for item in result["target_graph"]["nodes"] if item["object_type"] == "dataset")
    chart = next(item for item in result["target_graph"]["nodes"] if item["object_type"] == "editor_chart")
    assert [item["guid"] for item in dataset["field_catalog"]] == ["guid_date", "guid_value"]
    assert chart["field_guids"] == ["guid_value"]
    assert [method for method, _ in client.calls] == [
        "getDashboard", "getWorkbookEntries", "getEditorChart", "getDataset", "getConnection"
    ]


def test_workbook_ambiguity_is_reported_only_after_inventory_read() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient(ambiguous=True)
        result = TargetDiscoveryService(client).discover(
            _contract(Path(tmp), dashboard_id="", workbook_id="book_demo"),
            request_text="Update a dashboard",
        )
    assert result["status"] == "blocked"
    assert result["candidate_count"] == 2
    assert client.calls == [("getWorkbookEntries", {"workbookId": "book_demo"})]


def test_target_url_parses_the_stable_id_before_a_slug() -> None:
    assert parse_target_url("https://datalens.example/abc123456789-demo-dashboard") == "abc123456789"


def test_dashboard_not_found_returns_typed_discovery_blocker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = TargetDiscoveryService(DiscoveryClient(missing_dashboard=True)).discover(_contract(Path(tmp)))
    assert result["status"] == "blocked"
    assert result["missing_facts"] == ["fresh_saved_target"]
    assert "no dashboard payload" in result["reason"]


def test_explicit_non_chart_object_type_is_rejected_after_inventory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        contract = _contract(Path(tmp))
        contract["target"]["object_ids"] = ["dash_demo", "connection_demo"]
        result = TargetDiscoveryService(DiscoveryClient()).discover(contract)
    assert result["status"] == "blocked"
    assert "unsupported target type connection" in result["reason"]


def test_discovery_is_api_only_even_when_request_forbids_browser_use() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient()
        result = TargetDiscoveryService(client).discover(
            _contract(Path(tmp)),
            request_text="Do not use a browser; inspect the saved dashboard through the API",
        )
    assert result["status"] == "success"
    assert all(method.startswith("get") for method, _ in client.calls)


def test_wizard_target_preserves_wizard_technology() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient(chart_scope="wizard_chart")
        result = TargetDiscoveryService(client).discover(_contract(Path(tmp)))
    assert result["status"] == "success"
    assert result["target_binding"]["technology"] == "wizard_native"
    assert any(method == "getWizardChart" for method, _ in client.calls)


def test_widget_scope_uses_concrete_wizard_node_type_for_read_route() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        client = DiscoveryClient(chart_scope="widget", chart_type="graph_wizard_node")
        result = TargetDiscoveryService(client).discover(_contract(Path(tmp)))
    assert result["status"] == "success"
    assert result["target_binding"]["technology"] == "wizard_native"
    assert any(method == "getWizardChart" for method, _ in client.calls)


def test_graph_object_budget_is_global_and_records_truncation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = TargetDiscoveryService(DiscoveryClient(), max_objects=2).discover(_contract(Path(tmp)))
    assert result["status"] == "success"
    assert len(result["target_graph"]["nodes"]) == 2
    assert result["target_graph"]["limitations"] == ["target graph reached the configured object limit"]


def test_unrequested_unavailable_chart_is_recorded_as_bounded_limitation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = TargetDiscoveryService(DiscoveryClient(unavailable_chart=True)).discover(_contract(Path(tmp)))
    assert result["status"] == "success"
    assert result["target_binding"]["technology"] == "dashboard"
    assert result["target_graph"]["limitations"] == ["dashboard references an unavailable chart"]
