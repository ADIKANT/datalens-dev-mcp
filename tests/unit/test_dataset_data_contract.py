from __future__ import annotations

from datalens_dev_mcp.pipeline.dataset_data_contract import (
    build_field_catalog,
    resolve_field_guids,
    validate_dataset_data_query,
)
from datalens_dev_mcp.pipeline.dataset_preview import extract_dataset_fields


def _catalog() -> list[dict]:
    return build_field_catalog(
        [
            {"guid": "date_guid", "name": "event_date", "type": "date"},
            {"guid": "key_guid", "name": "id", "type": "string", "unique": True},
            {"guid": "left_value", "name": "value", "type": "float"},
            {"guid": "right_value", "name": "value", "type": "float"},
        ]
    )


def test_duplicate_names_require_chart_binding_or_business_clarification() -> None:
    unresolved = resolve_field_guids(["value"], _catalog())
    resolved = resolve_field_guids(["value"], _catalog(), chart_bound_guids=["right_value"])
    assert unresolved["ok"] is False
    assert unresolved["ambiguous"][0]["candidate_guids"] == ["left_value", "right_value"]
    assert resolved["guids"] == ["right_value"]


def test_offset_and_multi_page_require_total_order_contract() -> None:
    result = validate_dataset_data_query(
        {
            "datasetId": "dataset_demo",
            "columns": ["date_guid", "key_guid"],
            "limit": 100,
            "offset": 100,
            "max_pages": 2,
        },
        field_catalog=_catalog(),
    )
    assert result["ok"] is False
    assert any("offset" in item for item in result["issues"])
    assert any("multi-page" in item for item in result["issues"])


def test_query_contract_keeps_experimental_branch_semantics_explicit() -> None:
    result = validate_dataset_data_query(
        {
            "datasetId": "dataset_demo",
            "columns": ["key_guid"],
            "sort": [{"guid": "key_guid", "direction": "asc"}],
            "tie_breaker_fields": ["key_guid"],
        },
        field_catalog=_catalog(),
    )
    assert result["ok"] is True
    assert result["contract"]["dataset_data_semantics"] == "unknown_experimental"
    assert result["contract"]["query_hash"]


def test_provider_semantic_type_does_not_replace_physical_data_type() -> None:
    catalog = build_field_catalog(
        [
            {
                "guid": "metric_guid",
                "name": "Metric",
                "type": "MEASURE",
                "data_type": "float",
                "cast": "float",
                "aggregation": "sum",
            },
            {
                "guid": "date_guid",
                "name": "Date",
                "type": "DIMENSION",
                "dataType": "date",
            },
        ]
    )
    assert catalog[0]["type"] == "date"
    assert catalog[0]["semantic_role"] == "dimension"
    assert catalog[1]["type"] == "float"
    assert catalog[1]["semantic_role"] == "measure"


def test_richer_duplicate_guid_enriches_early_reference_projection() -> None:
    fields = extract_dataset_fields(
        {
            "result_schema": [{"guid": "metric_guid", "name": "Metric"}],
            "fields": [
                {
                    "guid": "metric_guid",
                    "name": "Metric",
                    "type": "MEASURE",
                    "data_type": "float",
                    "aggregation": "sum",
                }
            ],
        }
    )
    assert fields == [
        {
            "guid": "metric_guid",
            "name": "Metric",
            "type": "float",
            "semantic_role": "measure",
            "aggregation": "sum",
            "formula": "",
            "source": "",
            "hidden": False,
            "unique": False,
            "sensitive": False,
        }
    ]


def test_physical_array_type_keeps_its_declared_underscore() -> None:
    catalog = build_field_catalog(
        [{"guid": "items_guid", "name": "Items", "type": "DIMENSION", "data_type": "ARRAY_INT"}]
    )
    assert catalog[0]["type"] == "array_int"
