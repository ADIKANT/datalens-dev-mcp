from pathlib import Path

import pytest
from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError


def draft():
    return [
        {"client_ref": "a", "object_type": "editor_chart", "name": "Synthetic", "snapshot": {"data": {"title": "New"}}}
    ]


def test_create_interrupted_inside_transport_is_not_replayed(tmp_path: Path):
    class Interrupted(FakeBackend):
        def create(self, draft, destination):
            self.calls.append(("create", draft))
            raise KeyboardInterrupt()

    backend = Interrupted([])
    writer = service(tmp_path, FakeReader({}), backend)
    with pytest.raises(KeyboardInterrupt):
        writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="crash")
    record = writer.store.get("crash")
    assert record is not None and record["status"] == "uncertain"
    restarted = service(tmp_path, FakeReader({}), backend)
    assert restarted.create_objects(draft(), {"workbook_id": "w"}, operation_id="crash")["status"] == "uncertain"
    assert len(backend.calls) == 1


def test_returned_create_id_survives_interrupted_readback(tmp_path: Path):
    class InterruptedReader:
        def object_get(self, *args, **kwargs):
            raise KeyboardInterrupt()

    backend = FakeBackend([{"object_id": "created"}])
    writer = service(tmp_path, InterruptedReader(), backend)
    with pytest.raises(KeyboardInterrupt):
        writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="returned-id")
    record = writer.store.get("returned-id")
    assert record["results"][0]["target"]["object_id"] == "created"
    reader = FakeReader(
        {("editor_chart", "created", "saved"): [rb("editor_chart", "created", "r1", {"data": {"title": "New"}})]}
    )
    result = service(tmp_path, reader, backend).reconcile("returned-id")
    assert result["status"] == "completed"
    assert len(backend.calls) == 1


def test_readback_failure_after_create_does_not_repeat_create(tmp_path: Path):
    class BrokenReader:
        def object_get(self, *args, **kwargs):
            raise DataLensApiError("read unavailable", http_status=503)

    backend = FakeBackend([{"object_id": "created"}])
    writer = service(tmp_path, BrokenReader(), backend)
    first = writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="read-failed")
    assert first["status"] == "uncertain"
    writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="read-failed")
    assert len(backend.calls) == 1


def test_supplied_current_cannot_bypass_fresh_revision_check(tmp_path: Path):
    reader = FakeReader({("dashboard", "d", "saved"): [rb("dashboard", "d", "manual", {"name": "Manual"})]})
    backend = FakeBackend([])
    result = service(tmp_path, reader, backend).update_objects(
        [
            {
                "object_type": "dashboard",
                "object_id": "d",
                "expected_revision": "old",
                "patch": {"name": "New"},
                "current": rb("dashboard", "d", "old", {"name": "Old"}),
            }
        ]
    )
    assert result["status"] == "blocked"
    assert backend.calls == []


def test_update_readback_mismatch_is_not_completed_or_replayed(tmp_path: Path):
    reader = FakeReader({("dashboard", "d", "saved"): [rb("dashboard", "d", "r1", {"name": "Old"})]})
    backend = FakeBackend([{"object_id": "d"}])
    writer = service(tmp_path, reader, backend)
    change = [{"object_type": "dashboard", "object_id": "d", "expected_revision": "r1", "patch": {"name": "New"}}]
    result = writer.update_objects(change, operation_id="mismatch")
    assert result["status"] == "uncertain"
    writer.update_objects(change, operation_id="mismatch")
    assert len(backend.calls) == 1


def test_publish_reconcile_does_not_accept_older_published_content(tmp_path: Path):
    saved = rb("dashboard", "d", "r2", {"data": {"tabs": [{"id": "new"}]}})
    old = rb("dashboard", "d", "r1", {"data": {"tabs": [{"id": "old"}]}})
    old["identity"]["branch"] = "published"
    reader = FakeReader({("dashboard", "d", "saved"): [saved], ("dashboard", "d", "published"): [old]})
    backend = FakeBackend([UncertainWriteError("lost")])
    writer = service(tmp_path, reader, backend)
    writer.publish_objects(
        [{"object_type": "dashboard", "object_id": "d", "expected_saved_revision": "r2"}], operation_id="publish"
    )
    assert writer.reconcile("publish")["status"] == "uncertain"
    assert len(backend.calls) == 1


def test_dependent_create_waits_for_uncertain_parent(tmp_path: Path):
    backend = FakeBackend([UncertainWriteError("lost")])
    writer = service(tmp_path, FakeReader({}), backend)
    drafts = draft() + [
        {
            "client_ref": "child",
            "object_type": "dashboard",
            "name": "Synthetic child",
            "snapshot": {},
            "depends_on": ["a"],
        }
    ]
    result = writer.create_objects(drafts, {"workbook_id": "w"})
    assert result["status"] == "uncertain"
    assert len(backend.calls) == 1


def test_unknown_create_new_operation_id_cannot_replay(tmp_path):
    from datalens_dev_mcp.api.errors import DataLensSafetyError
    backend = FakeBackend([UncertainWriteError("lost"), {"object_id": "duplicate"}])
    writer = service(tmp_path, FakeReader({}), backend)
    writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="original")
    with pytest.raises(DataLensSafetyError):
        writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="new-id")
    assert len(backend.calls) == 1


def test_ack_remains_applied_when_readback_fails(tmp_path):
    class BrokenReader:
        def object_get(self, *args, **kwargs):
            raise DataLensApiError("readback rate limited", http_status=429, response_received=True)
    writer = service(tmp_path, BrokenReader(), FakeBackend([{"object_id": "created"}]))
    result = writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="ack")
    assert result["status"] == "uncertain"
    assert result["results"][0]["write_returned"] is True
    assert result["results"][0]["effect_outcome"] == "applied"


def test_ack_and_id_survive_receipt_storage_failure(tmp_path, monkeypatch):
    from datalens_dev_mcp.api.errors import error_response
    backend = FakeBackend([{"object_id": "created"}])
    writer = service(tmp_path, FakeReader({}), backend)
    put = writer.store.put
    def fail_after_ack(record):
        if any(item.get("write_returned") for item in record["results"]):
            raise OSError("synthetic disk full")
        return put(record)
    monkeypatch.setattr(writer.store, "put", fail_after_ack)
    with pytest.raises(UncertainWriteError) as caught:
        writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="disk-failure")
    result = error_response(caught.value, effect_possible=True)
    assert result["operation_id"] == "disk-failure"
    assert result["receipt_persisted"] is False
    assert result["results"][0]["target"]["object_id"] == "created"
    assert result["results"][0]["effect_outcome"] == "applied"
    assert len(backend.calls) == 1


def test_dataset_batch_title_conflict_has_zero_effects(tmp_path):
    backend = FakeBackend([])
    writer = service(tmp_path, FakeReader({("dataset", "s", "saved"): [
        rb("dataset", "s", "r1", {"dataset": {"result_schema": []}})]}), backend)
    changes = [{"object_type": "dashboard", "object_id": "d", "patch": {"name": "Independent"}},
               {"object_type": "dataset", "object_id": "s", "patch": {"dataset": {"result_schema": [
                   {"guid": "one", "title": "Same"}, {"guid": "two", "title": "Same"}]}}}]
    result = writer.update_objects(changes, operation_id="titles")
    assert not result["ok"]
    assert backend.calls == []
    assert result["results"][0]["status"] == "pending"


def test_invalid_dataset_metadata_save_retains_separate_validation(tmp_path):
    state = {"dataset": {"description": "New", "sources": [{"id": "s", "valid": True}],
                         "result_schema": [{"guid": "g", "valid": False}],
                         "component_errors": {"items": [{"errors": [{"code": "TITLE_CONFLICT"}]}]}}}
    before = {"dataset": {**state["dataset"], "description": "Old"}}
    saved = rb("dataset", "s", "r2", state)
    saved["identity"]["branch"] = "unbranched"
    reader = FakeReader({("dataset", "s", "saved"): [rb("dataset", "s", "r1", before), saved]})
    backend = FakeBackend([{"object_id": "s"}])
    result = service(tmp_path, reader, backend).update_objects(
        [{"object_type": "dataset", "object_id": "s", "patch": {"dataset": {"description": "New"}}}])
    assert result["status"] == "completed" and result["ok"] is False
    item = result["results"][0]
    assert item["write_verified"] is True
    assert item["dataset_validation"]["status"] == "invalid"
    assert result["task_complete"] is False
    assert backend.calls[0][1]["snapshot"]["dataset"]["result_schema"] == before["dataset"]["result_schema"]
