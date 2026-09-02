from __future__ import annotations

from datalens_dev_mcp.pipeline.semantic_change_planner import SemanticChangePlanner


def _chart_payload(value: str = "Old label") -> dict:
    return {
        "result": {
            "chart": {
                "entry": {"entryId": "chart_demo", "revId": "r3"},
                "data": {
                    "meta": "{}",
                    "sources": "module.exports={main:{data:[]}};",
                    "prepare": (
                        "/* datalens-protected:runtime:start */function ratio(a,b){return b?a/b:null;}"
                        "/* datalens-protected:runtime:end */\n"
                        "const title='/* datalens-slot:series_label:text:start */"
                        f"{value}"
                        "/* datalens-slot:series_label:end */';"
                    ),
                },
            }
        }
    }


def _dataset_payload() -> dict:
    return {"result": {"dataset": {"datasetId": "dataset_demo", "revId": "r2", "fields": []}}}


def _graph() -> dict:
    return {
        "nodes": [
            {"object_type": "editor_chart", "object_id": "chart_demo", "saved_revision": "r3"},
            {"object_type": "dataset", "object_id": "dataset_demo", "saved_revision": "r2"},
        ],
        "edges": [{"source": "chart_demo", "target": "dataset_demo", "relation": "uses_dataset"}],
    }


def _contract() -> dict:
    return {
        "task_id": "task_demo",
        "scope": {
            "allowed_objects": ["chart_demo"],
            "allowed_tabs": ["prepare.js"],
            "allowed_semantic_slots": ["series_label"],
        },
        "acceptance": [],
    }


def test_semantic_planner_changes_only_allowed_slot_and_binds_style_hash() -> None:
    result = SemanticChangePlanner().plan(
        _contract(),
        target_graph=_graph(),
        baselines={"chart-chart_demo-saved": _chart_payload(), "dataset-dataset_demo-saved": _dataset_payload()},
        changes=[{"target_id": "chart_demo", "slot_id": "series_label", "value": "Revenue"}],
        binding_hashes={"style_binding_hash": "a" * 64},
    )
    assert result["ok"] is True
    assert result["semantic_patch_plan"]["bindings"]["style_binding_hash"] == "a" * 64
    payload = result["materialized_payloads"]["chart_demo"]
    assert "Revenue" in payload["data"]["prepare"]
    assert "function ratio" in payload["data"]["prepare"]
    assert result["preflight"]["all_targets_preflighted"] is True


def test_semantic_planner_blocks_noop_and_unallowed_tab() -> None:
    noop = SemanticChangePlanner().plan(
        _contract(),
        target_graph=_graph(),
        baselines={"chart-chart_demo-saved": _chart_payload(), "dataset-dataset_demo-saved": _dataset_payload()},
        changes=[{"target_id": "chart_demo", "slot_id": "series_label", "value": "Old label"}],
    )
    outside = SemanticChangePlanner().plan(
        _contract(),
        target_graph=_graph(),
        baselines={"chart-chart_demo-saved": _chart_payload(), "dataset-dataset_demo-saved": _dataset_payload()},
        changes=[
            {
                "target_id": "chart_demo",
                "tab": "sources.js",
                "anchor": {"kind": "json_pointer", "pointer": "/x"},
                "value": 1,
            }
        ],
    )
    assert noop["status"] == "already_satisfied_no_write"
    assert noop["matched_assertions"] == [
        {
            "target_id": "chart_demo",
            "tab": "",
            "slot_id": "series_label",
            "expected": "Old label",
            "matched": True,
            "fresh_state": "already_applied",
        }
    ]
    assert outside["ok"] is False
    assert "outside allowed scope" in outside["issues"][0]


def test_missing_typed_actions_is_not_reported_as_noop() -> None:
    result = SemanticChangePlanner().plan(
        {**_contract(), "contract_revision": 3, "mode": "update", "operation_kind": "mutate"},
        target_graph=_graph(),
        baselines={"chart-chart_demo-saved": _chart_payload()},
    )

    assert result["state"] == "needs_semantic_actions"
    assert result["task_id"] == "task_demo"
    assert result["contract_revision"] == 3
    assert result["object_index"][0]["technology"] == ""
    assert result["missing_fields"] == ["semantic_changes"]
    assert result["required_next_call"] is None


def test_hashed_baseline_names_match_direct_object_identity_before_graph_references() -> None:
    second = _chart_payload("Old secondary")
    second["result"]["chart"]["entry"]["entryId"] = "chart_demo_2"
    graph = _graph()
    graph["nodes"].insert(
        1,
        {"object_type": "editor_chart", "object_id": "chart_demo_2", "saved_revision": "r3"},
    )
    graph["edges"].insert(0, {"source": "dash_demo", "target": "chart_demo_2", "relation": "contains"})
    dashboard = {
        "result": {
            "dashboard": {
                "entry": {"entryId": "dash_demo", "revId": "d1"},
                "data": {"items": [{"chartId": "chart_demo_2"}]},
            }
        }
    }
    contract = _contract()
    contract["scope"]["allowed_objects"].append("chart_demo_2")
    result = SemanticChangePlanner().plan(
        contract,
        target_graph=graph,
        baselines={
            "baseline-111.json": _chart_payload(),
            "baseline-222.json": dashboard,
            "baseline-333.json": second,
            "baseline-444.json": _dataset_payload(),
        },
        changes=[
            {"target_id": "chart_demo", "slot_id": "series_label", "value": "Revenue"},
            {"target_id": "chart_demo_2", "slot_id": "series_label", "value": "Margin"},
        ],
    )
    assert result["ok"] is True
    assert set(result["materialized_payloads"]) == {"chart_demo", "chart_demo_2"}
