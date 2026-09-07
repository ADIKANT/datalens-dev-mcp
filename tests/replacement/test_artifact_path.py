import json

import pytest

from datalens_dev_mcp.authoring.artifacts import resolve_artifact
from datalens_dev_mcp.server import dl_compile_recipe
from test_l06_object_lifecycle import FakeReader, FakeBackend, rb, service


def test_mcp_materialized_compile_returns_reference_not_renderer(tmp_path):
    result = dl_compile_recipe("native_detail_table", {
        "dataset_id": "synthetic-dataset", "object_name": "Synthetic",
        "columns": [{"field_guid": "synthetic-field"}],
    }, output_dir=str(tmp_path))
    assert "draft" not in result
    draft = resolve_artifact(result["draft_reference"])
    assert draft["wizard"]["roles"]["columns"] == ["synthetic-field"]


def test_create_resolves_artifact_before_recording_and_writing(tmp_path):
    path = tmp_path / "draft.json"
    path.write_text(json.dumps({"object_type": "wizard_chart", "name": "Synthetic", "snapshot": {"data": {}}}))
    reader = FakeReader({("wizard_chart", "synthetic", "saved"): [rb("wizard_chart", "synthetic", "r1", {"data": {}})]})
    backend = FakeBackend([{"object_id": "synthetic"}])
    result = service(tmp_path, reader, backend).create_objects(
        [{"artifact_path": str(path), "client_ref": "table"}], {"workbook_id": "synthetic"})
    assert result["status"] == "completed"
    assert "artifact_path" not in backend.calls[0][1]["draft"]
    assert backend.calls[0][1]["draft"]["name"] == "Synthetic"


def test_artifact_reference_cannot_silently_override_content(tmp_path):
    with pytest.raises(ValueError, match="only"):
        resolve_artifact({"artifact_path": str(tmp_path / "draft.json"), "snapshot": {}})


def test_artifact_reference_rejects_recursive_reference(tmp_path):
    path = tmp_path / "draft.json"
    path.write_text(json.dumps({"artifact_path": str(path)}))
    with pytest.raises(ValueError, match="concrete JSON object"):
        resolve_artifact({"artifact_path": str(path)})
