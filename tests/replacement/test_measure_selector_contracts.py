from __future__ import annotations

from datalens_dev_mcp.dashboard.composition import validate_dashboard_contract
from datalens_dev_mcp.dataset.contracts import validate_dataset_fields, validate_visualization_fields


def test_visualization_rejects_unknown_guid_instead_of_silently_skipping_it() -> None:
    fields = [{"guid": "amount", "title": "Amount", "type": "MEASURE", "aggregation": "sum"}]

    result = validate_visualization_fields(fields, ["amount", "missing-guid"])

    assert result["ok"] is False
    assert result["issues"] == [
        {
            "code": "visualization_field_guid_unknown",
            "path": "visualization.fields",
            "message": "field GUID is absent from Dataset readback: missing-guid",
        }
    ]


def test_dataset_validation_preserves_existing_measure_semantics_without_inventing_sum() -> None:
    direct = {"guid": "amount", "title": "Amount", "type": "MEASURE", "aggregation": "sum"}
    aggregate_formula = {
        "guid": "orders", "title": "Orders", "type": "MEASURE",
        "formula": "COUNTD([order_id])", "aggregation": "none",
    }

    result = validate_dataset_fields([direct, aggregate_formula])

    assert result["ok"] is True
    assert result["fields"][0]["aggregation"] == "sum"
    assert "formula" not in result["fields"][0]
    assert result["fields"][1]["formula"] == "COUNTD([order_id])"
    assert result["fields"][1]["aggregation"] == "none"


def test_selector_requires_one_declared_parameter_and_explicit_clear_semantics() -> None:
    base = {
        "parameters": [{"name": "region", "type": "string", "default": []}],
        "widgets": {"chart-a": {"params": {}}},
        "selectors": [
            {
                "id": "region-control", "param_name": "region", "mode": "multi",
                "clear": True, "select_all": True, "empty_selection": "all",
                "consumers": ["chart-a"],
            }
        ],
    }
    assert validate_dashboard_contract(base)["ok"] is True

    duplicate = {**base, "parameters": [*base["parameters"], {"name": "region", "type": "string"}]}
    assert {issue["code"] for issue in validate_dashboard_contract(duplicate)["issues"]} == {
        "parameter_duplicate"
    }

    missing_semantics = {**base, "selectors": [{**base["selectors"][0], "empty_selection": None}]}
    assert {issue["code"] for issue in validate_dashboard_contract(missing_semantics)["issues"]} == {
        "selector_empty_semantics_missing"
    }


def test_selector_cannot_target_an_undeclared_parameter() -> None:
    result = validate_dashboard_contract(
        {
            "parameters": [],
            "widgets": {"chart-a": {"params": {}}},
            "selectors": [
                {
                    "id": "region-control", "param_name": "region", "mode": "single",
                    "clear": False, "empty_selection": "error", "consumers": ["chart-a"],
                }
            ],
        }
    )

    assert {issue["code"] for issue in result["issues"]} == {"selector_parameter_undeclared"}
