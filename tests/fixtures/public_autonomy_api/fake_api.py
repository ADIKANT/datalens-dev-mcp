from __future__ import annotations

from copy import deepcopy
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError


class PublicAutonomyApi:
    """Stateful DataLens transport double; orchestration remains production code."""

    def __init__(
        self,
        *,
        dataset_behavior: str = "normal",
        missing_dashboard: bool = False,
        ambiguous_inventory: bool = False,
        initial_label: str = "Old",
        stale_chart_after_reads: int = 0,
        fail_read_method: str = "",
        failure_kind: str = "",
        fail_write_number: int = 0,
        write_failure_kind: str = "",
        variant: int = 1,
        second_chart: bool = False,
    ) -> None:
        self.dataset_behavior = dataset_behavior
        self.missing_dashboard = missing_dashboard
        self.ambiguous_inventory = ambiguous_inventory
        self.stale_chart_after_reads = max(0, int(stale_chart_after_reads))
        self.fail_read_method = fail_read_method
        self.failure_kind = failure_kind
        self.fail_write_number = max(0, int(fail_write_number))
        self.write_failure_kind = write_failure_kind
        self.variant = variant
        self.second_chart = second_chart
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.write_calls: list[tuple[str, dict[str, Any]]] = []
        self.saved_charts = {"chart_demo": _chart_entry(initial_label, object_id="chart_demo")}
        if second_chart:
            self.saved_charts["chart_demo_2"] = _chart_entry("Old secondary", object_id="chart_demo_2")
        self.published_charts = deepcopy(self.saved_charts)
        self._chart_read_count = 0
        self._write_attempt_count = 0

    @property
    def write_count(self) -> int:
        return len(self.write_calls)

    @property
    def saved_chart(self) -> dict[str, Any]:
        return self.saved_charts["chart_demo"]

    @saved_chart.setter
    def saved_chart(self, value: dict[str, Any]) -> None:
        self.saved_charts["chart_demo"] = value

    def rpc_readonly(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, deepcopy(payload)))
        if method == self.fail_read_method:
            raise _provider_failure(self.failure_kind, phase="read")
        if method == "getDashboard":
            if self.missing_dashboard:
                return {"result": {}}
            return {
                "result": {
                    "dashboard": {
                        "entry": {"entryId": "dash_demo", "workbookId": "book_demo", "revId": "dash-r7"},
                        "data": {
                            "tabs": [
                                {
                                    "id": "main",
                                    "items": [
                                        {"chartId": chart_id}
                                        for chart_id in self.saved_charts
                                    ],
                                }
                            ]
                        },
                    }
                }
            }
        if method == "getWorkbookEntries":
            dashboards = [{"entryId": "dash_demo", "scope": "dashboard", "displayKey": "Synthetic dashboard"}]
            if self.ambiguous_inventory:
                dashboards.append(
                    {"entryId": "dash_other", "scope": "dashboard", "displayKey": "Synthetic alternate"}
                )
            entries = [
                *dashboards,
                *[
                    {
                        "entryId": chart_id,
                        "scope": "editor_chart",
                        "displayKey": f"Synthetic trend {index + 1}",
                    }
                    for index, chart_id in enumerate(self.saved_charts)
                ],
                {"entryId": "dataset_demo", "scope": "dataset", "displayKey": "Synthetic dataset"},
                {"entryId": "connection_demo", "scope": "connection", "displayKey": "Synthetic connection"},
            ]
            return {"total": len(entries), "entries": entries}
        if method == "getEditorChart":
            self._chart_read_count += 1
            chart_id = str(payload.get("chartId") or "chart_demo")
            entries = self.published_charts if payload.get("branch") == "published" else self.saved_charts
            entry = entries[chart_id]
            if self.stale_chart_after_reads and self._chart_read_count > self.stale_chart_after_reads:
                entry = _chart_entry("Concurrent change", object_id=chart_id)
                entry["revId"] = "chart-stale-r9"
            return _chart_response(entry)
        if method == "getDataset":
            return {
                "result": {
                    "dataset": {
                        "datasetId": "dataset_demo",
                        "revId": "dataset-r2",
                        "fields": _dataset_schema(),
                        "sources": [{"connectionId": "connection_demo"}],
                    }
                }
            }
        if method == "getConnection":
            return {"result": {"connection": {"connectionId": "connection_demo", "type": "clickhouse"}}}
        if method == "getDatasetData":
            if self.dataset_behavior == "unavailable":
                raise ConnectionError("synthetic getDatasetData unavailable")
            columns = [str(item) for item in payload.get("columns") or []]
            schema_by_guid = {item["guid"]: item for item in _dataset_schema()}
            schema = [deepcopy(schema_by_guid[item]) for item in columns]
            rows = [] if self.dataset_behavior == "empty" else [[_dataset_values()[item] for item in columns]]
            return {"schema": schema, "rows": rows}
        if method == "validateDataset":
            return {
                "result": {
                    "dataset": {
                        "datasetId": str(payload.get("datasetId") or "dataset_demo"),
                        "component_errors": [],
                    }
                }
            }
        raise AssertionError(f"unexpected read method: {method}")

    def rpc_exclusive_read(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.rpc_readonly(method, payload)

    def rpc(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, deepcopy(payload)))
        if method != "updateEditorChart":
            return self.rpc_readonly(method, payload)
        self._write_attempt_count += 1
        if self.fail_write_number and self._write_attempt_count == self.fail_write_number:
            raise _provider_failure(self.write_failure_kind or "timeout", phase="write")
        self.write_calls.append((method, deepcopy(payload)))
        entry = deepcopy(payload.get("entry") or {})
        chart_id = str(entry.get("entryId") or "chart_demo")
        entry["entryId"] = chart_id
        entry["revId"] = "chart-r4"
        entry["savedId"] = "saved-chart-r4"
        if payload.get("mode") == "publish":
            self.published_charts[chart_id] = deepcopy(entry)
        else:
            self.saved_charts[chart_id] = deepcopy(entry)
        return _chart_response(entry)


def _chart_entry(label: str, *, object_id: str) -> dict[str, Any]:
    return {
        "entryId": object_id,
        "revId": "chart-r3",
        "data": {
            "datasetId": "dataset_demo",
            "visualization": {"measures": [{"guid": "guid_value"}]},
            "meta": "{}",
            "sources": "module.exports = {main: {data: []}};",
            "prepare": (
                "const title='/* datalens-slot:series_label:text:start */"
                f"{label}/* datalens-slot:series_label:end */'; module.exports={{title}};"
            ),
        },
    }


def _chart_response(entry: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(entry)
    data = value.pop("data", {})
    return {"result": {"chart": {"entry": value, "data": data}}}


def _dataset_schema() -> list[dict[str, Any]]:
    return [
        {"guid": "guid_date", "name": "event_date", "type": "date"},
        {"guid": "guid_value", "name": "value", "type": "float"},
        {"guid": "guid_category", "name": "category", "type": "string"},
    ]


def _dataset_values() -> dict[str, Any]:
    return {"guid_date": "2026-08-27", "guid_value": 42.0, "guid_category": "Synthetic"}


def _provider_failure(kind: str, *, phase: str) -> DataLensApiError:
    if kind == "401":
        return DataLensApiError("synthetic authorization failure", http_status=401, request_phase=phase)
    if kind == "403":
        return DataLensApiError("synthetic permission failure", http_status=403, request_phase=phase)
    if kind == "429":
        return DataLensApiError(
            "synthetic rate limit",
            http_status=429,
            request_phase=phase,
            retry_after_sec=0,
            retry_exhausted=True,
        )
    return DataLensApiError(
        "synthetic transport timeout",
        request_phase=phase,
        response_received=False,
        transport_category="timeout",
        retry_exhausted=True,
    )
