from __future__ import annotations

from datalens_dev_mcp.pipeline.dataset_data_contract import validate_dataset_data_query


def test_experimental_query_has_no_revision_parameter_and_does_not_invent_branch_semantics() -> None:
    result = validate_dataset_data_query(
        {
            "datasetId": "dataset_demo",
            "columns": ["value_guid"],
            "limit": 20,
        },
        field_catalog=[{"guid": "value_guid", "name": "value", "type": "float"}],
    )
    assert result["ok"] is True
    assert "revId" not in result["contract"]["payload"]
    assert "revision" not in result["contract"]["payload"]
    assert result["contract"]["dataset_data_semantics"] == "unknown_experimental"
