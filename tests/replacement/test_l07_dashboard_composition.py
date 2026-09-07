from __future__ import annotations

import pytest

from datalens_dev_mcp.dashboard.composition import (
    RESERVED_PARAMETERS,
    compose_dashboard_patch,
    dependency_order,
    validate_dashboard_contract,
)


def test_narrow_dashboard_patch_preserves_manual_geometry_and_unknown_widgets() -> None:
    current = {
        "data": {
            "tabs": [
                {
                    "id": "overview",
                    "items": [{"id": "chart-a", "layout": {"x": 0, "y": 0, "w": 12, "h": 19}, "manual": True}],
                }
            ],
            "unknown": {"keep": True},
        },
        "name": "Old",
    }
    proposed = compose_dashboard_patch(current, {"name": "New"})
    assert proposed["data"] == current["data"]
    assert proposed["name"] == "New"


def test_range_selector_requires_every_consumer_and_no_stale_override() -> None:
    contract = {
        "parameters": [{"name": "period", "type": "date_range", "default": []}],
        "widgets": {
            "chart-a": {"params": {}},
            "chart-b": {"params": {"period": "stale-static"}},
        },
        "selectors": [
            {
                "id": "period-control",
                "param_name": "period",
                "mode": "range",
                "clear": True,
                "empty_selection": "all",
                "consumers": ["chart-a", "chart-b"],
            }
        ],
    }
    result = validate_dashboard_contract(contract)
    assert {item["code"] for item in result["issues"]} == {"stale_consumer_override"}
    contract["widgets"]["chart-b"]["params"] = {}
    assert validate_dashboard_contract(contract)["ok"] is True


def test_reserved_parameters_are_rejected_but_custom_parameter_is_allowed() -> None:
    for name in RESERVED_PARAMETERS:
        result = validate_dashboard_contract({"parameters": [{"name": name}]})
        assert result["ok"] is False
    assert validate_dashboard_contract({"parameters": [{"name": "business_period"}]})["ok"] is True


def test_fixed_matrix_legend_and_cumulative_comparison_are_not_invalidated() -> None:
    result = validate_dashboard_contract(
        {
            "visuals": [
                {"family": "comparison_matrix", "legend": {"mode": "fixed_semantic", "visible": True}},
                {"family": "time_comparison", "comparison": {"method": "cumulative", "periods_overlap": True}},
            ]
        }
    )
    assert result["ok"] is True


def test_dependency_order_supports_more_than_25_objects_and_is_stable() -> None:
    drafts = [{"client_ref": f"chart-{index}", "depends_on": ["dataset"]} for index in range(30)] + [
        {"client_ref": "dataset", "depends_on": ["connection"]},
        {"client_ref": "connection"},
    ]
    ordered = dependency_order(drafts)
    refs = [item["client_ref"] for item in ordered]
    assert len(refs) == 32
    assert refs.index("connection") < refs.index("dataset") < refs.index("chart-29")


def test_dependency_order_rejects_missing_and_cyclic_references() -> None:
    with pytest.raises(ValueError, match="unknown dependency"):
        dependency_order([{"client_ref": "chart", "depends_on": ["missing"]}])
    with pytest.raises(ValueError, match="cycle"):
        dependency_order([{"client_ref": "a", "depends_on": ["b"]}, {"client_ref": "b", "depends_on": ["a"]}])
