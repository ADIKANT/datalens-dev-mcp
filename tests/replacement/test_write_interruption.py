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


def test_legacy_ack_reconcile_releases_only_verified_target_with_fresh_cas(tmp_path, monkeypatch):
    from datalens_dev_mcp.api.errors import DataLensSafetyError
    from datalens_dev_mcp.server import call_tool

    current = rb("dashboard", "d", "manual", {"entry": {"entryId": "d", "tenantId": "tenant",
                 "workbookId": "wb", "data": {"tabs": [{"id": "manual"}]}}})
    reader = FakeReader({("dashboard", "d", "saved"): [current]})
    backend = FakeBackend([])
    writer = service(tmp_path, reader, backend)
    writer.provider_scope = "scope"
    writer.store.put({"operation_id": "legacy", "effect": "update", "status": "uncertain",
        "request_digest": "historical", "results": [{"key": "dashboard:d", "status": "uncertain",
        "target": {"object_type": "dashboard", "object_id": "d"}, "write_returned": True,
        "effect_outcome": "unknown", "expected_revision": "before", "returned_revision": None,
        "desired": {"entry": {"data": {"tabs": [{"id": "old"}]}}}, "readback": current,
        "error": "old timeout", "code": "readback_mismatch"}]})
    monkeypatch.setattr("datalens_dev_mcp.server.default_mutation_service", lambda: writer)
    result = call_tool("dl_operation_reconcile", {"operation_id": "legacy"})["structuredContent"]
    assert result["write_replayed"] is False
    assert result["status"] == "resolved"
    item = result["results"][0]
    assert item["effect_outcome"] == "applied"
    assert item["verification_status"] == "historical_content_unverified"
    assert item["write_verified"] is False
    assert "error" not in item
    assert backend.calls == []
    with pytest.raises(DataLensSafetyError):
        writer.update_objects([{"object_type": "dashboard", "object_id": "d", "patch": {"name": "Next"}}],
                              operation_id="no-cas")
    saved = writer.store.get("legacy")
    assert saved["results"][0]["history"][0]["error"] == "old timeout"
    assert writer.reconcile("legacy")["store_version"] == saved["store_version"]
    writer.update_objects([{"object_type": "dashboard", "object_id": "d", "expected_revision": "stale",
                           "patch": {"name": "Next"}}], operation_id="stale-cas")
    assert backend.calls == []
    from copy import deepcopy
    after = deepcopy(current)
    after["identity"]["revision_id"] = "new"
    after["object"]["entry"]["data"]["note"] = "Intentional new change"
    reader.replies[("dashboard", "d", "saved")] = [current, after]
    backend.outcomes.append({"object_id": "d", "object": {"entry": {"revId": "new"}}})
    updated = call_tool("dl_object_update", {"changes": [{"object_type": "dashboard", "object_id": "d",
        "expected_revision": "manual", "patch": {"entry": {"data": {"note": "Intentional new change"}}}}],
        "operation_id": "fresh-change"})["structuredContent"]
    assert updated["status"] == "completed"
    assert backend.calls[0][1]["snapshot"]["entry"]["data"]["tabs"] == [{"id": "manual"}]
    published = deepcopy(after)
    published["identity"]["branch"] = "published"
    reader.replies[("dashboard", "d", "published")] = [published]
    backend.outcomes.append({"object_id": "d"})
    result = call_tool("dl_object_publish", {"targets": [{"object_type": "dashboard", "object_id": "d",
                         "expected_saved_revision": "new"}], "operation_id": "fresh-publish"})["structuredContent"]
    assert result["status"] == "completed"
    assert [kind for kind, _ in backend.calls] == ["update", "publish"]


def test_manual_input_field_type_is_rejected_before_dispatch_and_legacy_normalized():
    from copy import deepcopy

    from datalens_dev_mcp.api.errors import InputContractError
    from datalens_dev_mcp.api.sdk_adapter import _validate_dashboard_snapshot
    from datalens_dev_mcp.objects.write import _readback_contains, _readback_intent

    snapshot = {"entry": {"version": 2, "data": {"tabs": [{"id": "t", "items": [{"id": "rates",
        "type": "group_control", "data": {"group": [{"sourceType": "manual", "source": {
            "elementType": "input", "fieldName": "rate_" + str(i), "fieldType": "string",
            "defaultValue": str(i), "required": True}} for i in range(3)]}}]}]}}}
    with pytest.raises(InputContractError, match="fieldType"):
        _validate_dashboard_snapshot(snapshot)
    actual = deepcopy(snapshot)
    controls = actual["entry"]["data"]["tabs"][0]["items"][0]["data"]["group"]
    for control in controls:
        control["source"].pop("fieldType")
    expected = _readback_intent("dashboard", snapshot)
    assert _readback_contains(_readback_intent("dashboard", actual), expected)
    controls[0]["source"].pop("required")
    assert not _readback_contains(_readback_intent("dashboard", actual), expected)
    controls[0]["source"]["required"] = True
    controls.reverse()
    assert not _readback_contains(_readback_intent("dashboard", actual), expected)
    controls.reverse()
    controls[0]["source"]["defaultValue"] = "different"
    assert not _readback_contains(_readback_intent("dashboard", actual), expected)


@pytest.mark.parametrize("case", ["unknown", "incomplete", "wrong_identity", "wrong_branch", "wrong_tenant", "provisioning"])
def test_reconcile_does_not_release_unproven_history(tmp_path, case):
    from copy import deepcopy
    current = rb("dashboard", "d", "r3", {"entry": {"entryId": "d", "tenantId": "tenant",
                 "workbookId": "wb", "data": {"tabs": [{"id": "manual"}]}}})
    old = deepcopy(current)
    if case == "incomplete":
        current["complete"] = False
    if case == "wrong_identity":
        current["identity"]["object_id"] = "other"
    if case == "wrong_branch":
        current["identity"]["branch"] = "published"
    if case == "wrong_tenant":
        current["object"]["entry"]["tenantId"] = "different"
    writer = service(tmp_path, FakeReader({("dashboard", "d", "saved"): [current]}), FakeBackend([]))
    writer.store.put({"operation_id": "held", "effect": "update", "status": "uncertain", "results": [{
        "status": "uncertain", "target": {"object_type": "dashboard", "object_id": "d"},
        "write_returned": case != "unknown", "readback": old, "expected_revision": "r1",
        "desired": {"entry": {"data": {"tabs": [{"id": "old"}]}}},
        **({"connection_operation": {"id": "provisioning"}} if case == "provisioning" else {})}]})
    for _ in range(2):
        result = writer.reconcile("held")
        assert result["status"] == "uncertain"
        assert result["write_replayed"] is False
    assert writer.backend.calls == []


@pytest.mark.parametrize("response, expected, role", [
    ({"entry": {"revId": "r2"}}, "r2", "result"), ({"rev_id": "r2"}, "r2", "result"),
    ({"entry": {"revId": "r1"}}, None, "precondition"), ({}, None, "not_returned")])
def test_returned_revision_keeps_nested_result_and_precondition_separate(tmp_path, response, expected, role):
    writer = service(tmp_path, FakeReader({}), FakeBackend([]))
    record = {"operation_id": "revision", "effect": "update", "results": []}
    item = {"status": "uncertain", "expected_revision": "r1"}
    record["results"].append(item)
    writer._returned(record, item, {"object": response})
    assert item["returned_revision"] == expected
    assert item["response_revision_role"] == role


def test_partial_claim_preserves_completed_targets_and_provider_scope(tmp_path):
    from datalens_dev_mcp.api.errors import DataLensSafetyError
    from datalens_dev_mcp.operation_store import OperationStore
    store = OperationStore(tmp_path)
    store.put({"operation_id": "batch", "effect": "update", "status": "pending", "provider_scope": "a",
               "write_targets": ["done", "unknown"], "results": [
                   {"status": "completed", "target": {"object_id": "done"}},
                   {"status": "uncertain", "target": {"object_id": "unknown"}}]})
    def claim(oid, target, scope):
        return store.claim({"operation_id": oid, "effect": "update", "request_digest": oid,
                            "provider_scope": scope, "write_targets": [target], "status": "pending"})
    assert claim("independent", "done", "a")[0]
    assert claim("other-scope", "unknown", "b")[0]
    with pytest.raises(DataLensSafetyError):
        claim("held-target", "unknown", "a")


def test_concurrent_receipt_reconciliation_cannot_overwrite_newer_result(tmp_path):
    from datalens_dev_mcp.operation_store import OperationStore
    store = OperationStore(tmp_path)
    original = store.put({"operation_id": "shared", "status": "uncertain", "results": []})
    competing = store.get("shared")
    original["status"] = "resolved"
    store.put(original)
    with pytest.raises(UncertainWriteError, match="concurrently"):
        store.put(competing)
    assert store.get("shared")["status"] == "resolved"


def test_retry_rejected_batch_cannot_bypass_another_unknown_target(tmp_path):
    from datalens_dev_mcp.api.errors import DataLensSafetyError
    from datalens_dev_mcp.operation_store import OperationStore
    store = OperationStore(tmp_path)
    retry = {"operation_id": "rejected", "effect": "update", "request_digest": "one", "provider_scope": "a",
             "write_targets": ["d"], "status": "failed", "results": [
                 {"status": "failed", "target": {"object_id": "d"}, "effect_outcome": "not_applied"}]}
    store.put(retry)
    store.put({"operation_id": "unknown", "effect": "update", "request_digest": "two", "provider_scope": "a",
               "write_targets": ["d"], "status": "uncertain", "results": [
                   {"status": "uncertain", "target": {"object_id": "d"}, "effect_outcome": "unknown"}]})
    with pytest.raises(DataLensSafetyError):
        store.claim(retry)


def test_resumed_claim_is_reserved_before_a_second_caller(tmp_path):
    from datalens_dev_mcp.operation_store import OperationStore
    store = OperationStore(tmp_path)
    record = {"operation_id": "retry", "effect": "update", "request_digest": "same", "status": "failed",
              "write_targets": ["d"], "results": [{"status": "failed", "target": {"object_id": "d"}}]}
    store.put(record)
    assert store.claim(record)[0] is True
    assert store.claim(record)[0] is False


@pytest.mark.parametrize("count,complete", [(0, True), (1, True), (2, True), (0, False)])
def test_unknown_create_investigation_never_attributes_by_name(tmp_path, count, complete):
    class Reader(FakeReader):
        def workbook_entries(self, workbook_id, **kwargs):
            assert workbook_id == "w"
            return {"ok": True, "complete": complete, "page_count": 1,
                    "objects": [{"id": f"candidate-{i}", "object_type": "editor_chart", "name": "Synthetic",
                                 "workbook_id": "w"} for i in range(count)]}
    reader = Reader({("editor_chart", f"candidate-{i}", "saved"):
                     [rb("editor_chart", f"candidate-{i}", "r1", {"name": "Synthetic", "workbookId": "w"})]
                     for i in range(count)})
    writer = service(tmp_path, reader, FakeBackend([UncertainWriteError("lost")]))
    writer.create_objects(draft(), {"workbook_id": "w"}, operation_id="unknown")
    before = writer.store.get("unknown")
    result = writer.reconcile("unknown", investigate_create=True)
    item = result["results"][0]
    assert item["effect_outcome"] == "unknown" and "target" not in item
    assert item["investigation"]["candidate_count"] == count
    assert item["investigation"]["inventory_complete"] == complete
    assert item["investigation"]["attribution"] == "unavailable"
    assert result["write_replayed"] is False and len(writer.backend.calls) == 1
    assert item["intent"] == before["results"][0]["intent"]
    assert result["request_digest"] == before["request_digest"]
