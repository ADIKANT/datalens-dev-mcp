from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.maintenance import validate_html_content
from datalens_dev_mcp.objects.backup import BackupService
from datalens_dev_mcp.objects.cleanup import CleanupService


class Reader:
    def __init__(self) -> None:
        self.objects = {
            ("dashboard", "dash", "saved"): {
                "ok": True,
                "identity": {"object_type": "dashboard", "object_id": "dash", "branch": "saved", "revision_id": "r1"},
                "object": {"id": "dash", "data": {}},
            },
            ("dataset", "shared", "saved"): {
                "ok": True,
                "identity": {
                    "object_type": "dataset",
                    "object_id": "shared",
                    "branch": "unbranched",
                    "revision_id": "r2",
                },
                "object": {"id": "shared"},
            },
        }
        self.relations = {"dash": [{"id": "shared", "type": "dataset"}], "shared": []}

    def object_get(self, object_type: str, object_id: str, *, branch="saved", revision_id=None):
        del revision_id
        if object_id in {"missing", "orphan"}:
            raise DataLensApiError("synthetic missing", http_status=404, response_received=True)
        return self.objects[(object_type, object_id, branch)]

    def object_relations(self, object_id: str, **kwargs):
        del kwargs
        return {"ok": True, "complete": True, "relations": self.relations.get(object_id, [])}


class Deleter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def delete(self, object_type: str, object_id: str) -> dict[str, Any]:
        self.calls.append((object_type, object_id))
        if object_id == "gone":
            raise DataLensApiError("not found", http_status=404, response_received=True)
        return {"deleted": True}


def test_backup_exports_objects_and_marks_missing_entry_partial(tmp_path: Path) -> None:
    result = BackupService(Reader()).export(
        [{"object_type": "dashboard", "object_id": "dash"}, {"object_type": "dataset", "object_id": "missing"}],
        tmp_path / "backup",
    )
    assert result["complete"] is False
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["artifact_kind"] == "snapshot_not_full_restore"
    assert [item["status"] for item in manifest["objects"]] == ["exported", "failed"]


def test_cleanup_preserves_shared_dependency_and_deletes_only_exact_preview() -> None:
    deleter = Deleter()
    service = CleanupService(reader=Reader(), deleter=deleter)
    candidates = [
        {"object_type": "dashboard", "object_id": "dash"},
        {"object_type": "dataset", "object_id": "shared"},
        {"object_type": "editor_chart", "object_id": "orphan"},
        {"object_type": "editor_chart", "object_id": "gone"},
    ]
    preview = service.preview(candidates, preserve_roots=[{"object_type": "dashboard", "object_id": "dash"}])
    assert {item["object_id"] for item in preview["preserve"]} == {"dash", "shared"}
    assert {item["object_id"] for item in preview["delete"]} == {"orphan", "gone"}
    applied = service.apply(preview, confirmed_delete=preview["delete"])
    assert applied["status"] == "completed_with_absent"
    assert [item["status"] for item in applied["results"]] == ["deleted", "already_absent"]


def test_cleanup_refuses_changed_confirmation() -> None:
    preview = CleanupService(reader=Reader(), deleter=Deleter()).preview(
        [{"object_type": "editor_chart", "object_id": "orphan"}], preserve_roots=[]
    )
    try:
        CleanupService(reader=Reader(), deleter=Deleter()).apply(preview, confirmed_delete=[])
    except ValueError as exc:
        assert "exactly match" in str(exc)
    else:
        raise AssertionError("changed deletion set was accepted")


def test_html_contract_requires_string_and_documented_size_limit() -> None:
    assert validate_html_content("<p>Synthetic</p>")["ok"] is True
    assert validate_html_content({"html": "<p>x</p>"})["ok"] is False
    assert validate_html_content("x" * (5 * 1024 * 1024 + 1))["issues"][0]["code"] == "html_too_large"


def test_admin_boundary_does_not_claim_license_revoke() -> None:
    from datalens_dev_mcp.maintenance import admin_capabilities

    result = admin_capabilities()
    assert result["license_assignment"] is True
    assert result["license_revoke"] is False
    assert result["html_page"]["browser_fallback"] is False
