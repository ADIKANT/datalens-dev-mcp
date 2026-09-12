from __future__ import annotations

from typing import Any

from datalens_dev_mcp.dataset.contracts import validate_dataset_fields, validate_visualization_fields
from datalens_dev_mcp.dataset.preview import DatasetPreviewService, compile_preview_request
from datalens_dev_mcp.server import list_tools
from datalens_dev_mcp.wizard.authoring import compile_wizard_create, inspect_wizard_shape

FIELDS = [
    {
        "guid": "date-guid",
        "title": "Day",
        "name": "day",
        "calc_mode": "direct",
        "type": "DIMENSION",
        "data_type": "date",
        "source": "day",
        "unique": True,
    },
    {
        "guid": "revenue-guid",
        "title": "Revenue",
        "name": "revenue",
        "calc_mode": "formula",
        "type": "MEASURE",
        "data_type": "float",
        "aggregation": "sum",
        "formula": "SUM([revenue])",
    },
    {
        "guid": "orders-guid",
        "title": "Orders",
        "name": "orders",
        "calc_mode": "formula",
        "type": "MEASURE",
        "data_type": "integer",
        "aggregation": "sum",
        "formula": "SUM([orders])",
    },
]


class FakeApi:
    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, dict(payload)))
        return self.replies.pop(0)


def test_dataset_validation_preserves_guids_and_measure_levels() -> None:
    result = validate_dataset_fields(FIELDS)
    assert result["ok"] is True
    assert [field["guid"] for field in result["fields"]] == ["date-guid", "revenue-guid", "orders-guid"]
    assert {field["guid"]: field["calculation_level"] for field in result["fields"]} == {
        "date-guid": "row",
        "orders-guid": "aggregate",
        "revenue-guid": "aggregate",
    }


def test_lod_and_time_intelligence_are_rejected_across_fields() -> None:
    fields = [
        {"guid": "lod", "title": "LOD", "type": "MEASURE", "formula": "SUM([x] FIXED [region])"},
        {"guid": "ago", "title": "Previous", "type": "MEASURE", "formula": "AGO([lod], 'year')"},
    ]
    assert validate_dataset_fields(fields)["ok"] is True
    result = validate_visualization_fields(fields, ["lod", "ago"])
    assert result["ok"] is False
    assert any(issue["code"] == "lod_with_time_intelligence" for issue in result["issues"])


def test_preview_requires_real_guids_and_deterministic_multipage_sort() -> None:
    invalid = compile_preview_request(
        dataset_id="dataset-1",
        fields=FIELDS,
        columns=["Revenue"],
        sort=[],
        max_pages=2,
    )
    assert invalid["ok"] is False
    assert "Revenue" not in invalid["request"]["columns"]

    valid = compile_preview_request(
        dataset_id="dataset-1",
        fields=FIELDS,
        columns=["date-guid", "revenue-guid"],
        sort=[{"guid": "date-guid", "direction": "asc"}],
        tie_breaker_guids=["date-guid"],
        max_pages=2,
        limit=2,
    )
    assert valid["ok"] is True
    assert valid["request"]["columns"] == ["date-guid", "revenue-guid"]


def test_preview_executes_bounded_pages_with_stable_offsets() -> None:
    api = FakeApi([{"rows": [["2026-01-01", 10], ["2026-01-02", 20]]}, {"rows": []}])
    result = DatasetPreviewService(api).preview(
        dataset_id="dataset-1",
        fields=FIELDS,
        columns=["date-guid", "revenue-guid"],
        sort=[{"guid": "date-guid", "direction": "asc"}],
        tie_breaker_guids=["date-guid"],
        max_pages=2,
        limit=2,
    )
    assert result["ok"] is True
    assert result["rows"] == [["2026-01-01", 10], ["2026-01-02", 20]]
    assert [payload["offset"] for _, payload in api.calls] == [0, 2]


def test_technical_measure_fields_cannot_be_columns_filters_or_dataset_guids() -> None:
    for technical in ("Measure Names", "Measure Values"):
        result = compile_preview_request(
            dataset_id="dataset-1",
            fields=FIELDS,
            columns=["date-guid"],
            filters=[{"guid": technical, "operation": "EQ", "values": ["Revenue"]}],
        )
        assert result["ok"] is False
        assert any("technical" in issue["code"] for issue in result["issues"])


def test_official_sdk_compiles_current_multi_measure_wizard_shape() -> None:
    result = compile_wizard_create(
        visualization="line",
        name="Synthetic revenue and orders",
        workbook_id="workbook-1",
        dataset_id="dataset-1",
        fields=FIELDS,
        roles={"x": ["date-guid"], "y": ["revenue-guid", "orders-guid"]},
        title="Revenue and orders by day",
    )
    assert result["ok"] is True
    assert result["sdk_version"] == "3.0.0"
    assert result["payload"]["data"]["sources"]["datasetsIds"] == ["dataset-1"]
    slots = result["payload"]["data"]["visualization"]
    assert [item["guid"] for item in slots["y"]["items"]] == ["revenue-guid", "orders-guid"]
    assert all(item["datasetId"] == "dataset-1" for item in slots["y"]["items"])
    assert "placeholders" not in slots
    assert "datasetsPartialFields" not in result["payload"]["data"]



def test_chart_local_field_stays_out_of_dataset_contract() -> None:
    result = compile_wizard_create(
        visualization="line",
        name="Synthetic average check",
        workbook_id="workbook-1",
        dataset_id="dataset-1",
        fields=FIELDS,
        roles={"x": ["date-guid"], "y": ["revenue-guid"]},
        local_fields=[
            {
                "guid": "avg-check-local",
                "title": "Average check",
                "formula": "SUM([revenue]) / SUM([orders])",
                "measure": True,
            }
        ],
    )
    assert result["ok"] is True
    assert all(field["guid"] != "avg-check-local" for field in result["dataset_fields"])
    assert any(update["field"]["guid"] == "avg-check-local" for update in result["payload"]["data"]["sources"]["updates"])


def test_existing_wizard_shape_is_detected_not_reinvented() -> None:
    assert inspect_wizard_shape({"datasetsPartialFields": [[{"guid": "a"}]]})["partial_fields_shape"] == "nested"
    assert inspect_wizard_shape({"datasetsPartialFields": [{"guid": "a"}]})["partial_fields_shape"] == "flat"
    assert inspect_wizard_shape({})["update_safe"] is False


def test_l04_public_tools_are_dataset_specific() -> None:
    schemas = {tool["name"]: tool for tool in list_tools()}
    assert schemas["dl_dataset_validate"]["annotations"]["readOnlyHint"] is True
    assert schemas["dl_dataset_preview"]["inputSchema"]["required"] == ["dataset_id", "columns"]
