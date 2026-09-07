import json
import os
from pathlib import Path

import pytest
from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

from datalens_dev_mcp.authoring.artifacts import prune_recipe_artifacts, resolve_artifact
from datalens_dev_mcp.server import dl_compile_recipe, dl_editor_validate


def test_mcp_materialized_compile_returns_reference_not_renderer(tmp_path):
    result = dl_compile_recipe(
        "native_detail_table",
        {
            "dataset_id": "synthetic-dataset",
            "object_name": "Synthetic",
            "columns": [{"field_guid": "synthetic-field"}],
        },
        output_dir=str(tmp_path),
    )
    assert "draft" not in result
    draft = resolve_artifact(result["draft_reference"])
    assert draft["wizard"]["roles"]["columns"] == ["synthetic-field"]


def test_mcp_compile_materializes_to_external_state_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    result = dl_compile_recipe(
        "native_detail_table",
        {
            "dataset_id": "synthetic-dataset",
            "object_name": "Synthetic",
            "columns": [{"field_guid": "synthetic-field"}],
        },
    )

    assert "draft" not in result
    artifact = Path(result["draft_reference"]["artifact_path"])
    assert artifact.is_relative_to(tmp_path / "datalens-dev-mcp" / "recipe-artifacts")
    assert resolve_artifact(result["draft_reference"])["wizard"]["roles"]["columns"] == ["synthetic-field"]


def test_mcp_compile_response_is_a_compact_handle(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    result = dl_compile_recipe(
        "comparison_matrix",
        {
            "rows": [],
            "metric": {"label": "Synthetic"},
            "source": {
                "meta": {},
                "sources_js": "module.exports = {};",
                "prepare_js": "module.exports = {rows: []};",
            },
        },
    )

    assert set(result) == {"ok", "recipe_id", "summary", "draft_reference"}
    assert set(result["summary"]) == {
        "technology",
        "object_type",
        "renderer_reused",
        "network_calls",
        "datalens_writes",
    }
    assert len(json.dumps(result)) < 1_000
    assert len(json.dumps(resolve_artifact(result["draft_reference"]))) > len(json.dumps(result)) * 5


def test_single_editor_validation_resolves_compiled_artifact_reference(tmp_path):
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps(
            {
                "object_type": "advanced-chart_node",
                "variant": "advanced-chart_node",
                "source_aliases": [],
                "tabs": {
                    "meta.json": "{}",
                    "params.js": "module.exports = {};",
                    "sources.js": "module.exports = {};",
                    "prepare.js": "module.exports = {};",
                    "controls.js": "module.exports = {};",
                },
            }
        )
    )

    result = dl_editor_validate(draft={"artifact_path": str(path)})

    assert result["ok"] is True


def test_recipe_artifact_cache_prunes_old_completed_directories(tmp_path):
    root = tmp_path / "recipe-artifacts"
    old = root / "old"
    recent = root / "recent"
    keep = root / "keep"
    for directory in (old, recent, keep):
        directory.mkdir(parents=True)
        (directory / "draft.json").write_text("{}")
    os.utime(old, (100, 100))
    os.utime(recent, (200, 200))
    os.utime(keep, (300, 300))

    prune_recipe_artifacts(keep, max_directories=2, max_bytes=1_000, max_age_seconds=10**12)

    assert not old.exists()
    assert recent.exists()
    assert keep.exists()


def test_failed_default_compile_does_not_leave_an_empty_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    with pytest.raises(ValueError, match="unknown recipe_id"):
        dl_compile_recipe("unknown-recipe", {})

    root = tmp_path / "datalens-dev-mcp" / "recipe-artifacts"
    assert list(root.iterdir()) == []


def test_create_resolves_artifact_before_recording_and_writing(tmp_path):
    path = tmp_path / "draft.json"
    path.write_text(json.dumps({"object_type": "wizard_chart", "name": "Synthetic", "snapshot": {"data": {}}}))
    reader = FakeReader({("wizard_chart", "synthetic", "saved"): [rb("wizard_chart", "synthetic", "r1", {"data": {}})]})
    backend = FakeBackend([{"object_id": "synthetic"}])
    result = service(tmp_path, reader, backend).create_objects(
        [{"artifact_path": str(path), "client_ref": "table"}], {"workbook_id": "synthetic"}
    )
    assert result["status"] == "completed"
    assert "artifact_path" not in backend.calls[0][1]["draft"]
    assert backend.calls[0][1]["draft"]["name"] == "Synthetic"


def test_update_maps_compiled_editor_artifact_to_saved_data_without_echoing_renderer(tmp_path):
    path = tmp_path / "selector.json"
    path.write_text(
        json.dumps(
            {
                "object_type": "control_node",
                "client_ref": "selector",
                "name": "Updated selector",
                "tabs": {
                    "meta.json": '{"links": {}}',
                    "params.js": "module.exports = {priority_filter: []};",
                    "controls.js": "module.exports = {consumers: ['matrix', 'kpi']};",
                },
                "bindings": {"private": "not-provider-data"},
            }
        )
    )
    current = {
        "entryId": "selector-id",
        "name": "Old selector",
        "revId": "r1",
        "data": {"meta": "old", "params": "old", "controls": "old", "manual": "preserve"},
        "unknown": {"preserve": True},
    }
    updated = {
        **current,
        "name": "Updated selector",
        "revId": "r2",
        "data": {
            **current["data"],
            "meta": '{"links": {}}',
            "params": "module.exports = {priority_filter: []};",
            "controls": "module.exports = {consumers: ['matrix', 'kpi']};",
        },
    }
    reader = FakeReader(
        {
            ("control_node", "selector-id", "saved"): [
                rb("control_node", "selector-id", "r1", current),
                rb("control_node", "selector-id", "r2", updated),
            ]
        }
    )
    backend = FakeBackend([{"object_id": "selector-id"}])

    result = service(tmp_path, reader, backend).update_objects(
        [
            {
                "artifact_path": str(path),
                "object_type": "control_node",
                "object_id": "selector-id",
                "expected_revision": "r1",
            }
        ]
    )

    assert result["status"] == "completed"
    snapshot = backend.calls[0][1]["snapshot"]
    assert snapshot["name"] == "Updated selector"
    assert snapshot["data"] == updated["data"]
    assert snapshot["unknown"] == {"preserve": True}
    assert "tabs" not in snapshot
    assert "bindings" not in snapshot


def test_artifact_reference_cannot_silently_override_content(tmp_path):
    with pytest.raises(ValueError, match="only"):
        resolve_artifact({"artifact_path": str(tmp_path / "draft.json"), "snapshot": {}})


def test_artifact_reference_rejects_recursive_reference(tmp_path):
    path = tmp_path / "draft.json"
    path.write_text(json.dumps({"artifact_path": str(path)}))
    with pytest.raises(ValueError, match="concrete JSON object"):
        resolve_artifact({"artifact_path": str(path)})
