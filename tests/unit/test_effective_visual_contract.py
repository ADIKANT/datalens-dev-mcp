from __future__ import annotations

import pytest

from datalens_dev_mcp.pipeline.effective_visual_contract import (
    constraints_for_action,
    resolve_effective_visual_contract,
)
from datalens_dev_mcp.pipeline.visual_decisions import VisualDecisionEngine


def _graph(workbook_id: str = "book_alpha") -> dict:
    return {
        "graph_hash": "g" * 64,
        "nodes": [
            {
                "object_id": "chart_alpha",
                "object_type": "editor_chart",
                "workbook_id": workbook_id,
                "technology": "editor_advanced",
                "saved_revision": "r7",
                "tab_id": "main",
            }
        ],
        "edges": [],
    }


def _contract(workbook_id: str = "book_alpha") -> dict:
    return {
        "task_id": "task_alpha",
        "contract_revision": 2,
        "mode": "update",
        "route": "editor_advanced",
        "target": {"workbook_id": workbook_id, "object_ids": ["chart_alpha"]},
        "scope": {"allowed_objects": ["chart_alpha"], "allowed_tabs": ["prepare.js"]},
        "acceptance": [],
    }


@pytest.mark.parametrize(
    ("changes", "expected_show"),
    [
        ([], False),
        ([{"target_id": "chart_alpha", "category": "legend", "typed_value": {"show": True}}], True),
    ],
)
def test_effective_contract_precedence_operationalizes_project_legend(
    changes: list[dict],
    expected_show: bool,
) -> None:
    context = {
        "context_hash": "c" * 64,
        "project_profile_hash": "p" * 64,
        "accepted_exemplar_hash": "e" * 64,
        "typed_profile": {"legend": {"show": False}},
        "typed_decisions": [],
        "task_corrections": [],
    }
    resolved = resolve_effective_visual_contract(
        _contract(),
        target_graph=_graph(),
        baselines={"chart-alpha": {}},
        style_binding={"technology": "editor_advanced"},
        decision_context=context,
        changes=changes,
    )

    assert resolved["status"] == "success"
    assert resolved["required"]["legend"]["show"] is expected_show
    applied = constraints_for_action(
        resolved,
        {"target_id": "chart_alpha", "slot_id": "legend_visibility", "value": expected_show},
        target_id="chart_alpha",
        tab_id="prepare.js",
    )
    assert applied["required"]["legend"]["show"] is expected_show
    assert applied["contract_hash"] == resolved["contract_hash"]

    decision = VisualDecisionEngine().decide(
        chart_id="chart_alpha",
        business_question="Show the monthly revenue trend from the declared dataset",
        data_shape={"has_date": True, "measure_count": 1},
        effective_visual_contract=resolved,
    )
    assert decision.legend_spec["show"] is expected_show
    assert decision.effective_visual_contract_hash == resolved["contract_hash"]


def test_effective_contract_without_project_context_has_no_project_legend_rule() -> None:
    resolved = resolve_effective_visual_contract(
        _contract("book_beta"),
        target_graph=_graph("book_beta"),
        baselines={},
        style_binding={"technology": "editor_advanced"},
        decision_context={},
    )

    assert resolved["status"] == "success"
    assert "legend" not in resolved["required"]
    assert all(item["assertion_id"] != "legend_visibility_contract" for item in resolved["assertions"])
