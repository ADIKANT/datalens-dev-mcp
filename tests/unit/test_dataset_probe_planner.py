from __future__ import annotations

from datalens_dev_mcp.pipeline.dataset_probe_planner import DatasetProbePlanner


def _graph(*, unique: bool = True) -> dict:
    fields = [
        {"guid": "date_guid", "name": "event_date", "type": "date"},
        {"guid": "metric_guid", "name": "revenue", "type": "float"},
        {"guid": "dimension_guid", "name": "region", "type": "string"},
        {"guid": "key_guid", "name": "row_id", "type": "string", "unique": unique},
        {"guid": "unused_guid", "name": "unused", "type": "string", "hidden": True},
    ]
    return {
        "nodes": [
            {
                "object_type": "dataset",
                "object_id": "dataset_demo",
                "saved_revision": "r2",
                "field_catalog": fields,
                "field_catalog_hash": "f" * 64,
            }
        ]
    }


def test_planner_selects_minimal_roles_and_proven_total_order() -> None:
    contract = {
        "target": {"workbook_id": "book_demo"},
        "acceptance": [{"statement": "Trend revenue by event_date and region"}],
    }
    result = DatasetProbePlanner().plan(contract, _graph())
    query = result["plan"]["queries"][0]
    assert result["ok"] is True
    assert query["payload"]["columns"] == ["date_guid", "dimension_guid", "metric_guid", "key_guid"]
    assert query["paging"]["deterministic"] is True
    assert query["payload"]["sort"][-1] == {"guid": "key_guid", "direction": "asc"}
    assert "unused_guid" not in query["payload"]["columns"]


def test_planner_marks_sample_nondeterministic_without_unique_key() -> None:
    result = DatasetProbePlanner().plan({"target": {}}, _graph(unique=False))
    assert result["ok"] is True
    assert result["plan"]["queries"][0]["payload"].get("sort") is None
    assert result["plan"]["limitations"] == ["bounded sample has no proven total order"]


def test_planner_blocks_business_ambiguous_duplicate_field_name() -> None:
    graph = _graph()
    graph["nodes"][0]["field_catalog"].append(
        {"guid": "other_metric", "name": "revenue", "type": "float"}
    )
    result = DatasetProbePlanner().plan(
        {"target": {}, "acceptance": []}, graph, requested_fields=["revenue"]
    )
    assert result["ok"] is False
    assert result["field_resolution"]["ambiguous"]


def test_planner_uses_chart_binding_to_resolve_duplicate_name() -> None:
    graph = _graph()
    graph["nodes"][0]["field_catalog"].append(
        {"guid": "other_metric", "name": "revenue", "type": "float"}
    )
    graph["nodes"].append(
        {"object_type": "editor_chart", "object_id": "chart_demo", "field_guids": ["metric_guid"]}
    )
    graph["edges"] = [
        {"source": "chart_demo", "target": "dataset_demo", "relation": "uses_dataset"}
    ]
    contract = {
        "target": {},
        "scope": {"allowed_objects": ["chart_demo"]},
        "acceptance": [],
    }
    result = DatasetProbePlanner().plan(contract, graph, requested_fields=["revenue"])
    assert result["ok"] is True
    assert "metric_guid" in result["plan"]["queries"][0]["payload"]["columns"]


def test_planner_selects_dataset_linked_to_exact_chart_target() -> None:
    graph = _graph()
    graph["nodes"][0]["object_id"] = "dataset_unrelated"
    graph["nodes"].extend(
        [
            {"object_type": "editor_chart", "object_id": "chart_demo", "field_guids": ["wanted_guid"]},
            {
                "object_type": "dataset",
                "object_id": "dataset_wanted",
                "saved_revision": "r4",
                "field_catalog": [{"guid": "wanted_guid", "name": "value", "type": "float"}],
                "field_catalog_hash": "e" * 64,
            },
        ]
    )
    graph["edges"] = [
        {"source": "chart_demo", "target": "dataset_wanted", "relation": "uses_dataset"}
    ]
    contract = {"target": {}, "scope": {"allowed_objects": ["chart_demo"]}, "acceptance": []}
    result = DatasetProbePlanner().plan(contract, graph)
    assert result["ok"] is True
    assert result["plan"]["dataset_id"] == "dataset_wanted"
