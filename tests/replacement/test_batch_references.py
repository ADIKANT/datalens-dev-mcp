import pytest
from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

from datalens_dev_mcp.dashboard.composition import dependency_order


def test_created_chart_id_is_bound_into_dependent_dashboard(tmp_path):
    reader = FakeReader(
        {
            ("editor_chart", "synthetic-chart", "saved"): [rb("editor_chart", "synthetic-chart", "r1", {"data": {}})],
            ("dashboard", "synthetic-dashboard", "saved"): [
                rb("dashboard", "synthetic-dashboard", "r1", {"data": {"chartId": "synthetic-chart"}})
            ],
        }
    )
    backend = FakeBackend([{"object_id": "synthetic-chart"}, {"object_id": "synthetic-dashboard"}])
    drafts = [
        {
            "client_ref": "dashboard",
            "object_type": "dashboard",
            "name": "Synthetic dashboard",
            "snapshot": {"data": {"chartId": {"$object_ref": "chart"}}},
        },
        {"client_ref": "chart", "object_type": "editor_chart", "name": "Synthetic chart", "snapshot": {"data": {}}},
    ]
    writer = service(tmp_path, reader, backend)
    result = writer.create_objects(drafts, {"workbook_id": "synthetic"}, operation_id="synthetic-batch")
    assert result["status"] == "completed"
    assert backend.calls[1][1]["draft"]["snapshot"]["data"]["chartId"] == "synthetic-chart"
    writer.create_objects(drafts, {"workbook_id": "synthetic"}, operation_id="synthetic-batch")
    assert len(backend.calls) == 2
    assert drafts[0]["snapshot"]["data"]["chartId"] == {"$object_ref": "chart"}


def test_unknown_object_reference_is_rejected_before_execution():
    with pytest.raises(ValueError, match="unknown dependency"):
        dependency_order([{"client_ref": "dashboard", "snapshot": {"chartId": {"$object_ref": "missing"}}}])
