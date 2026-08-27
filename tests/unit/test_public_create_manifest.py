from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest


def _write_manifest(root: Path, *, dependency: bool = False) -> Path:
    (root / "payloads").mkdir(parents=True, exist_ok=True)
    dataset = {
        "workbookId": "workbook_1",
        "dataset": {"sources": []},
        "name": "Synthetic dataset",
    }
    (root / "payloads" / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    objects = [
        {
            "key": "dataset_main",
            "object_type": "dataset",
            "route": "dataset",
            "name": "Synthetic dataset",
            "payload_path": "payloads/dataset.json",
            "dependencies": [],
        }
    ]
    if dependency:
        editor = {
            "entry": {
                "workbookId": "workbook_1",
                "name": "Synthetic chart",
                "type": "advanced-chart_node",
                "data": {
                    "meta": "{}",
                    "params": "{}",
                    "sources": 'module.exports = {datasetId: "${object:dataset_main}"};',
                    "prepare": "module.exports = {};",
                },
            }
        }
        (root / "payloads" / "chart.json").write_text(json.dumps(editor), encoding="utf-8")
        objects.append(
            {
                "key": "chart_main",
                "object_type": "editor_chart",
                "route": "editor_advanced",
                "name": "Synthetic chart",
                "payload_path": "payloads/chart.json",
                "dependencies": ["dataset_main"],
            }
        )
    manifest = {
        "schema_id": "datalens_public_create_manifest",
        "manifest_version": 1,
        "workbook_id": "workbook_1",
        "objects": objects,
    }
    path = root / "create-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_bundle_is_hash_bound_and_dependency_order_is_deterministic() -> None:
    from datalens_dev_mcp.pipeline.create_manifest import (
        create_template_actions,
        load_create_bundle,
        resolve_object_placeholders,
        validate_create_bundle,
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_manifest(root, dependency=True)
        bundle = load_create_bundle(root, "create-manifest.json", workbook_id="workbook_1")

    assert validate_create_bundle(bundle) == ()
    assert [item["key"] for item in bundle["objects"]] == ["dataset_main", "chart_main"]
    actions = create_template_actions(bundle, baseline_artifact="discovery.json")
    assert [item["object_key"] for item in actions] == ["dataset_main", "chart_main"]
    resolved = resolve_object_placeholders(actions[1]["payload"], {"dataset_main": "dataset_created_1"})
    assert "dataset_created_1" in resolved["entry"]["data"]["sources"]
    assert "${object:" not in json.dumps(resolved)


def test_bundle_persists_writable_projection_instead_of_read_model() -> None:
    from datalens_dev_mcp.pipeline.create_manifest import load_create_bundle

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_manifest(root)
        payload_path = root / "payloads" / "dataset.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        payload["dataset"]["source_avatars"] = [
            {
                "id": "avatar_1",
                "managed_by": "user",
                "source_id": "source_1",
                "is_root": True,
                "valid": True,
                "virtual": False,
            }
        ]
        payload_path.write_text(json.dumps(payload), encoding="utf-8")

        bundle = load_create_bundle(root, "create-manifest.json", workbook_id="workbook_1")

    avatar = bundle["objects"][0]["payload"]["dataset"]["source_avatars"][0]
    assert avatar == {
        "id": "avatar_1",
        "managed_by": "user",
        "source_id": "source_1",
        "is_root": True,
    }


def test_manifest_path_escape_and_forward_dependency_fail_closed() -> None:
    from datalens_dev_mcp.pipeline.create_manifest import CreateManifestError, load_create_bundle

    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
        root = Path(tmp)
        _write_manifest(root)
        outside_manifest = Path(outside) / "manifest.json"
        outside_manifest.write_text("{}", encoding="utf-8")
        with pytest.raises(CreateManifestError, match="relative"):
            load_create_bundle(root, str(outside_manifest), workbook_id="workbook_1")

        manifest = json.loads((root / "create-manifest.json").read_text(encoding="utf-8"))
        manifest["objects"][0]["dependencies"] = ["later"]
        (root / "create-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(CreateManifestError, match="dependencies"):
            load_create_bundle(root, "create-manifest.json", workbook_id="workbook_1")
