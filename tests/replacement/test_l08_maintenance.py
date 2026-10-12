from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
                    "branch": "saved",
                    "revision_id": "r2",
                },
                "object": {"id": "shared"},
            },
        }
        self.relations = {"dash": [{"id": "shared", "type": "dataset"}], "shared": []}

    def object_get(self, object_type: str, object_id: str, *, branch="saved", revision_id=None):
        del revision_id
        if object_id in {"missing", "orphan", "gone"}:
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
    assert [item["status"] for item in applied["results"]] == ["already_absent", "already_absent"]


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


@pytest.mark.parametrize("branch,revision", [("saved", None), ("published", None), ("saved", "historical")])
def test_backup_checks_exact_target_and_private_files(tmp_path, branch, revision):
    class ExactReader:
        def object_get(self, kind, oid, **kwargs):
            assert kwargs == {"branch": branch, "revision_id": revision}
            return {"ok": True, "complete": True, "full_state": True,
                    "identity": {"object_type": kind, "object_id": oid, "branch": branch,
                                 "revision_id": revision or branch + "-revision"},
                    "object": {"name": "Synthetic"}}
    result = BackupService(ExactReader()).export([
        {"object_type": "dataset", "object_id": "synthetic", "branch": branch, "revision_id": revision}
    ], tmp_path)
    assert result["complete"] is True
    for path in tmp_path.glob("*.json"):
        assert path.stat().st_mode & 0o777 == 0o600
    assert result["objects"][0]["requested_revision"] == revision


@pytest.mark.parametrize("kind,content,full", [
    ("html_page", {"name": "Metadata only"}, False),
    ("connection", {"password": "synthetic-password"}, True),
    ("dataset", {"name": "Partial"}, False),
])
def test_backup_written_file_does_not_prove_complete_content(tmp_path, kind, content, full):
    class PartialReader:
        def object_get(self, object_type, oid, **kwargs):
            return {"ok": True, "complete": full, "full_state": full,
                    "identity": {"object_type": object_type, "object_id": oid,
                                 "branch": "unbranched" if kind == "connection" else "saved", "revision_id": "r1"},
                    "object": content}
    result = BackupService(PartialReader()).export([{"object_type": kind, "object_id": "synthetic"}], tmp_path)
    assert result["complete"] is False
    assert result["objects"][0]["file_written"] is True
    assert result["objects"][0]["target_verified"] is True
    assert result["objects"][0]["content_complete"] is False
    assert "synthetic-password" not in (tmp_path / result["objects"][0]["file"]).read_text()


@pytest.mark.parametrize("status,mime,body", [
    (403, "text/html", b"expired"), (302, "text/html", b"redirect"),
    (200, "application/json", b"{}"), (200, "text/html; charset=latin1", b"bad"),
    (200, "text/html", b"\xff"), (200, "text/html", b"x" * 101),
])
def test_html_storage_errors_are_bounded_and_do_not_expose_signed_url(monkeypatch, status, mime, body):
    import httpx

    from datalens_dev_mcp import maintenance
    real_client = httpx.Client
    def factory(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        def handle(request):
            assert not any(key in request.headers for key in ("authorization", "cookie", "x-yc-org-id"))
            return httpx.Response(status, headers={"content-type": mime}, content=body)
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(maintenance.httpx, "Client", factory)
    monkeypatch.setattr(maintenance, "HTML_MAX_BYTES", 100)
    with pytest.raises(DataLensApiError) as raised:
        maintenance.read_html_preview("https://storage.invalid/preview?signature=synthetic-private")
    assert "synthetic-private" not in str(raised.value)


def test_admin_boundary_does_not_claim_license_revoke() -> None:
    from datalens_dev_mcp.maintenance import admin_capabilities

    result = admin_capabilities()
    assert result["license_assignment"] is True
    assert result["license_revoke"] is False
    assert result["html_page"]["browser_fallback"] is False


@pytest.fixture(autouse=True)
def isolated_cleanup_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
