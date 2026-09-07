from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
from datalens_dev_mcp.objects.write import ObjectMutationService
from datalens_dev_mcp.operation_store import OperationStore
from datalens_dev_mcp.server import list_tools


class FakeReader:
    def __init__(self, replies: dict[tuple[str, str, str], list[dict[str, Any]]]) -> None:
        self.replies = {key: list(value) for key, value in replies.items()}
        self.calls: list[tuple[str, str, str]] = []

    def object_get(self, object_type: str, object_id: str, *, branch: str = "saved", revision_id=None):
        del revision_id
        self.calls.append((object_type, object_id, branch))
        values = self.replies[(object_type, object_id, branch)]
        return values.pop(0) if len(values) > 1 else values[0]


class FakeBackend:
    def __init__(self, outcomes: list[dict[str, Any] | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _next(self, effect: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((effect, payload))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def create(self, draft: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        return self._next("create", {"draft": draft, "destination": destination})

    def update(self, object_type: str, object_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        return self._next("update", {"object_type": object_type, "object_id": object_id, "snapshot": snapshot})

    def publish(self, object_type: str, object_id: str, saved: dict[str, Any]) -> dict[str, Any]:
        return self._next("publish", {"object_type": object_type, "object_id": object_id, "saved": saved})


def rb(kind: str, oid: str, rev: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "identity": {"object_type": kind, "object_id": oid, "branch": "saved", "revision_id": rev},
        "object": obj,
    }


def service(tmp_path: Path, reader: FakeReader, backend: FakeBackend) -> ObjectMutationService:
    return ObjectMutationService(reader=reader, backend=backend, store=OperationStore(tmp_path / "operations"))


def test_save_only_reads_saved_and_never_publishes(tmp_path: Path) -> None:
    reader = FakeReader({("editor_chart", "chart-1", "saved"): [rb("editor_chart", "chart-1", "r1", {"id": "chart-1", "data": {}})]})
    backend = FakeBackend([{"object_id": "chart-1"}])
    result = service(tmp_path, reader, backend).create_objects(
        [{"client_ref": "c1", "object_type": "editor_chart", "name": "Synthetic", "snapshot": {"data": {}}}],
        {"workbook_id": "wb-1"},
        delivery_mode="save",
        operation_id="op-save",
    )
    assert result["status"] == "completed"
    assert [effect for effect, _ in backend.calls] == ["create"]
    assert reader.calls == [("editor_chart", "chart-1", "saved")]


def test_completed_operation_is_returned_without_duplicate_create(tmp_path: Path) -> None:
    reader = FakeReader({("wizard_chart", "chart-1", "saved"): [rb("wizard_chart", "chart-1", "r1", {"id": "chart-1", "data": {}})]})
    backend = FakeBackend([{"object_id": "chart-1"}])
    writer = service(tmp_path, reader, backend)
    args = ([{"client_ref": "c1", "object_type": "wizard_chart", "name": "Synthetic", "snapshot": {"data": {}}}], {"workbook_id": "wb-1"})
    first = writer.create_objects(*args, operation_id="same-op")
    second = writer.create_objects(*args, operation_id="same-op")
    assert first == second
    assert len(backend.calls) == 1


def test_title_only_patch_uses_one_object_read_and_preserves_unknown_fields(tmp_path: Path) -> None:
    reader = FakeReader({
        ("dashboard", "dash-1", "saved"): [
            rb("dashboard", "dash-1", "r1", {"id": "dash-1", "name": "Old", "data": {"tabs": [{"id": "manual"}]}, "unknown": {"keep": True}}),
            rb("dashboard", "dash-1", "r2", {"id": "dash-1", "name": "New", "data": {"tabs": [{"id": "manual"}]}, "unknown": {"keep": True}}),
        ]
    })
    backend = FakeBackend([{"object_id": "dash-1"}])
    result = service(tmp_path, reader, backend).update_objects(
        [{"object_type": "dashboard", "object_id": "dash-1", "expected_revision": "r1", "patch": {"name": "New"}}],
        operation_id="op-title",
    )
    assert result["status"] == "completed"
    snapshot = backend.calls[0][1]["snapshot"]
    assert snapshot["name"] == "New"
    assert snapshot["data"]["tabs"][0]["id"] == "manual"
    assert snapshot["unknown"] == {"keep": True}
    assert reader.calls == [("dashboard", "dash-1", "saved"), ("dashboard", "dash-1", "saved")]


def test_revision_drift_blocks_write(tmp_path: Path) -> None:
    reader = FakeReader({("dashboard", "dash-1", "saved"): [rb("dashboard", "dash-1", "r2", {"id": "dash-1", "name": "Manual"})]})
    backend = FakeBackend([])
    result = service(tmp_path, reader, backend).update_objects(
        [{"object_type": "dashboard", "object_id": "dash-1", "expected_revision": "r1", "patch": {"name": "New"}}],
        operation_id="op-drift",
    )
    assert result["status"] == "blocked"
    assert result["results"][0]["code"] == "revision_changed"
    assert backend.calls == []


def test_partial_batch_resumes_without_repeating_first_effect(tmp_path: Path) -> None:
    reader = FakeReader({
        ("editor_chart", "one", "saved"): [rb("editor_chart", "one", "r1", {"id": "one"})],
        ("editor_chart", "two", "saved"): [rb("editor_chart", "two", "r1", {"id": "two"})],
    })
    backend = FakeBackend([{"object_id": "one"}, DataLensApiError("synthetic rejected", http_status=400, response_received=True), {"object_id": "two"}])
    writer = service(tmp_path, reader, backend)
    drafts = [
        {"client_ref": "one", "object_type": "editor_chart", "name": "One", "snapshot": {}},
        {"client_ref": "two", "object_type": "editor_chart", "name": "Two", "snapshot": {}},
    ]
    first = writer.create_objects(drafts, {"workbook_id": "wb-1"}, operation_id="op-batch")
    second = writer.create_objects(drafts, {"workbook_id": "wb-1"}, operation_id="op-batch")
    assert first["status"] == "partial"
    assert second["status"] == "completed"
    assert [payload["draft"]["client_ref"] for effect, payload in backend.calls if effect == "create"] == ["one", "two", "two"]


def test_unknown_outcome_is_persisted_and_reconcile_only_reads(tmp_path: Path) -> None:
    reader = FakeReader({("dashboard", "dash-1", "saved"): [
        rb("dashboard", "dash-1", "r1", {"id": "dash-1", "name": "Old"}),
        rb("dashboard", "dash-1", "r2", {"id": "dash-1", "name": "New"}),
    ]})
    backend = FakeBackend([UncertainWriteError("lost response", method="updateDashboard")])
    writer = service(tmp_path, reader, backend)
    result = writer.update_objects(
        [{"object_type": "dashboard", "object_id": "dash-1", "expected_revision": "r1", "patch": {"name": "New"}, "current": rb("dashboard", "dash-1", "r1", {"id": "dash-1", "name": "Old"})}],
        operation_id="op-uncertain",
    )
    assert result["status"] == "uncertain"
    reconciled = writer.reconcile("op-uncertain")
    assert reconciled["status"] == "completed"
    assert reconciled["write_replayed"] is False
    assert len(backend.calls) == 1


def test_publish_uses_fresh_saved_revision_then_published_readback(tmp_path: Path) -> None:
    saved = rb("dashboard", "dash-1", "r7", {"id": "dash-1", "revId": "r7", "data": {"tabs": []}})
    published = rb("dashboard", "dash-1", "r8", {"id": "dash-1", "revId": "r8", "data": {"tabs": []}})
    published["identity"]["branch"] = "published"
    reader = FakeReader({("dashboard", "dash-1", "saved"): [saved], ("dashboard", "dash-1", "published"): [published]})
    backend = FakeBackend([{"object_id": "dash-1"}])
    result = service(tmp_path, reader, backend).publish_objects(
        [{"object_type": "dashboard", "object_id": "dash-1", "expected_saved_revision": "r7"}], operation_id="op-publish"
    )
    assert result["status"] == "completed"
    assert backend.calls[0][1]["saved"]["identity"]["revision_id"] == "r7"
    assert reader.calls[-1] == ("dashboard", "dash-1", "published")


def test_l06_exposes_only_direct_lifecycle_tools() -> None:
    schemas = {item["name"]: item for item in list_tools()}
    assert {"dl_object_diff", "dl_object_create", "dl_object_update", "dl_object_publish", "dl_operation_get", "dl_operation_reconcile"} <= schemas.keys()
    assert schemas["dl_object_diff"]["annotations"]["readOnlyHint"] is True
    assert schemas["dl_object_create"]["annotations"]["idempotentHint"] is False
    assert "task" not in " ".join(schemas).lower()
