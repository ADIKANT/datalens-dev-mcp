from __future__ import annotations

import json

import pytest

from datalens_dev_mcp.pipeline.create_manifest import CreateManifestError, load_create_bundle


def test_temporary_ql_in_persistent_anchor_fails_before_create_without_cleanup_route(tmp_path) -> None:
    (tmp_path / "ql.json").write_text(
        json.dumps(
            {
                "route": "ql_explicit",
                "workbookId": "persistent_anchor_1",
                "name": "Temporary QL",
                "template": "ql",
                "data": {"query": "SELECT 1"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "create-manifest.json").write_text(
        json.dumps(
            {
                "schema_id": "datalens_public_create_manifest",
                "manifest_version": 1,
                "run_id": "controlled_run_1",
                "workbook_id": "persistent_anchor_1",
                "workbook_lifecycle": "persistent_anchor",
                "objects": [
                    {
                        "key": "temporary_ql",
                        "object_type": "ql_chart",
                        "route": "ql_explicit",
                        "name": "Temporary QL",
                        "payload_path": "ql.json",
                        "dependencies": [],
                        "lifecycle": "temporary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CreateManifestError, match="cleanup_route is required before temporary create"):
        load_create_bundle(
            tmp_path,
            "create-manifest.json",
            workbook_id="persistent_anchor_1",
            direct_ql_requested=True,
        )


def test_temporary_ql_uses_whole_disposable_workbook_cleanup_route(tmp_path) -> None:
    (tmp_path / "ql.json").write_text(
        json.dumps(
            {
                "route": "ql_explicit",
                "workbookId": "disposable_workbook_1",
                "name": "Temporary QL",
                "template": "ql",
                "data": {"query": "SELECT 1"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "create-manifest.json").write_text(
        json.dumps(
            {
                "schema_id": "datalens_public_create_manifest",
                "manifest_version": 1,
                "run_id": "controlled_run_1",
                "workbook_id": "disposable_workbook_1",
                "workbook_lifecycle": "disposable_sibling",
                "objects": [
                    {
                        "key": "temporary_ql",
                        "object_type": "ql_chart",
                        "route": "ql_explicit",
                        "name": "Temporary QL",
                        "payload_path": "ql.json",
                        "dependencies": [],
                        "lifecycle": "temporary",
                        "cleanup_route": "whole_disposable_workbook_delete",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    bundle = load_create_bundle(
        tmp_path,
        "create-manifest.json",
        workbook_id="disposable_workbook_1",
        direct_ql_requested=True,
    )

    assert bundle["objects"][0]["inverse_or_recreate_plan"] == {
        "strategy": "delete_workbook_and_verify_absent",
        "workbook_id": "disposable_workbook_1",
    }
