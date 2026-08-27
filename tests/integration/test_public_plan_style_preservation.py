from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.public_plan_builder import PublicPlanBuilder
from datalens_dev_mcp.pipeline.semantic_change_planner import SemanticChangePlanner
from tests.integration.test_public_plan_materialization import build_public_plan_fixture


def test_style_binding_drift_invalidates_immutable_plan() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, plan = build_public_plan_fixture(Path(tmp))
        style = read_json(journal.style_binding_path, {})
        style["binding_hash"] = "9" * 64
        write_json(journal.style_binding_path, style)
        issues = PublicPlanBuilder(journal, contract).validate_current()
    assert plan["style_binding_hash"] == "d" * 64
    assert "plan binding is stale: style_binding_hash" in issues


@pytest.mark.parametrize(
    ("family", "object_type", "tabs"),
    [
        ("kpi_strip", "editor_chart", ["meta", "sources", "prepare"]),
        ("trend_chart", "editor_chart", ["params", "sources", "prepare"]),
        ("advanced_table", "editor_table", ["sources", "controls", "prepare"]),
        ("selector_control", "control", ["params", "controls", "prepare"]),
        ("multi_tab_widget", "editor_chart", ["meta", "params", "sources", "controls", "prepare", "config"]),
        ("shared_large_runtime", "editor_chart", ["sources", "prepare", "config"]),
    ],
)
def test_sanitized_style_families_preserve_runtime_tabs_and_aliases(
    family: str,
    object_type: str,
    tabs: list[str],
) -> None:
    data = {name: _tab_source(name, family) for name in tabs}
    before_order = list(data)
    before_alias_source = data.get("sources")
    baseline = {
        "result": {
            "chart": {
                "entry": {"entryId": "chart_demo", "revId": "r3", "unknownStyle": {"family": family}},
                "data": data,
            }
        }
    }
    graph = {
        "nodes": [
            {
                "object_type": object_type,
                "object_id": "chart_demo",
                "saved_revision": "r3",
                "technology": "editor_advanced",
            }
        ],
        "edges": [],
    }
    contract = {
        "task_id": f"task_{family}",
        "scope": {
            "allowed_objects": ["chart_demo"],
            "allowed_tabs": ["prepare.js"],
            "allowed_semantic_slots": ["series_label"],
        },
        "acceptance": [],
    }
    result = SemanticChangePlanner().plan(
        contract,
        target_graph=graph,
        baselines={"baseline-chart-chart_demo-saved.json": baseline},
        changes=[{"target_id": "chart_demo", "slot_id": "series_label", "value": "Revenue"}],
        binding_hashes={"style_binding_hash": "a" * 64},
    )
    assert result["ok"] is True
    materialized = result["materialized_payloads"]["chart_demo"]
    assert list(materialized["data"]) == before_order
    assert materialized["data"].get("sources") == before_alias_source
    assert materialized["unknownStyle"] == {"family": family}
    assert "function protectedRuntime" in materialized["data"]["prepare"]
    assert "Revenue" in materialized["data"]["prepare"]
    assert result["semantic_patch_plan"]["bindings"]["style_binding_hash"] == "a" * 64


def _tab_source(name: str, family: str) -> str:
    if name == "prepare":
        padding = "\n".join(f"const helper{i}={i};" for i in range(120)) if family == "shared_large_runtime" else ""
        return (
            "/* datalens-protected:runtime:start */"
            f"function protectedRuntime(){{return '{family}';}}{padding}"
            "/* datalens-protected:runtime:end */\n"
            "const title='/* datalens-slot:series_label:text:start */Old"
            "/* datalens-slot:series_label:end */';"
        )
    if name == "sources":
        return "module.exports={revenueAlias:{data:[]},dateAlias:{data:[]}};"
    if name == "meta":
        return '{"family":"synthetic"}'
    return f"module.exports={{family:'{family}',tab:'{name}'}};"
