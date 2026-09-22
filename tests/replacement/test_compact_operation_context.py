from __future__ import annotations

import json
import os
import time

from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

from datalens_dev_mcp import server
from datalens_dev_mcp.operation_store import OperationStore, compact_operation


def test_compact_operation_keeps_actionable_result_without_payload_or_javascript() -> None:
    large_js = "module.exports = " + "x" * 20_000
    full = {
        "ok": True,
        "operation_id": "op-1",
        "effect": "create",
        "status": "completed",
        "next_action": "Inspect the existing receipt; an active or interrupted claim must not be replayed.",
        "results": [
            {
                "key": "chart",
                "status": "completed",
                "code": "readback_verified",
                "target": {"object_type": "editor_chart", "object_id": "chart-id"},
                "observed_revision": "r1",
                "desired": {"data": {"prepare": large_js}},
                "readback": {"object": {"data": {"prepare": large_js}}},
                "changes": [{"path": "/data/prepare", "before": "", "after": large_js}],
                "evidence": "saved_readback",
            }
        ],
    }

    compact = compact_operation(full)

    assert "next_action" not in compact
    assert "next_action" in full  # Historical storage remains unchanged.
    assert compact["results"][0]["target"]["object_id"] == "chart-id"
    assert compact["detail_reference"] == {"operation_id": "op-1", "include_detail": True}
    assert "desired" not in compact["results"][0]
    assert "readback" not in compact["results"][0]
    assert compact["results"][0]["changed_fields"] == ["/data/prepare"]
    assert compact_operation(compact) == compact
    assert len(json.dumps(compact)) < 800


def test_public_write_wrappers_are_compact_and_full_record_is_explicit(monkeypatch) -> None:
    full = {
        "ok": True,
        "operation_id": "op-1",
        "effect": "create",
        "status": "completed",
        "results": [{"key": "chart", "status": "completed", "desired": {"secret": "large"}}],
    }

    class FakeService:
        def create_objects(self, *args, **kwargs):
            return full

        def get_operation(self, operation_id):
            assert operation_id == "op-1"
            return full

    monkeypatch.setattr(server, "default_mutation_service", FakeService)
    class ReceiptStore:
        def get(self, operation_id):
            assert operation_id == "op-1"
            return full

    monkeypatch.setattr(server, "OperationStore", ReceiptStore)

    created = server.dl_object_create([{"client_ref": "chart"}], {"workbook_id": "workbook"})
    assert "desired" not in created["results"][0]
    assert "desired" not in server.dl_operation_get("op-1")["results"][0]
    assert server.dl_operation_get("op-1", include_detail=True) == full
    wire = server.call_tool("dl_operation_get", {"operation_id": "op-1", "include_detail": True})
    assert wire["structuredContent"] == full
    assert "large" not in wire["content"][0]["text"]


def test_operation_records_redact_credentials_before_persistence(tmp_path) -> None:
    reader = FakeReader(
        {
            ("connection", "connection-id", "saved"): [
                {
                    **rb("connection", "connection-id", "r1", {"name": "Synthetic", "password": "not-returned"}),
                    "identity": {
                        "object_type": "connection",
                        "object_id": "connection-id",
                        "branch": "unbranched",
                        "revision_id": "r1",
                    },
                }
            ]
        }
    )
    writer = service(tmp_path, reader, FakeBackend([{"object_id": "connection-id"}]))
    result = writer.create_objects(
        [
            {
                "client_ref": "connection",
                "object_type": "connection",
                "name": "Synthetic",
                "snapshot": {"name": "Synthetic", "password": "private-value", "iam_token": "private-token"},
            }
        ],
        {"workbook_id": "workbook"},
        operation_id="credential-redaction",
    )

    persisted = (tmp_path / "operations" / "credential-redaction.json").read_text(encoding="utf-8")
    assert result["status"] == "completed"
    assert "private-value" not in persisted
    assert "private-token" not in persisted
    assert '"password"' not in persisted
    assert '"iam_token"' not in persisted


def test_store_prunes_old_completed_records_but_preserves_uncertain_recovery(tmp_path) -> None:
    store = OperationStore(tmp_path, max_records=1, max_bytes=10_000, max_age_seconds=1)
    store.put({"operation_id": "old-complete", "status": "completed"})
    store.put({"operation_id": "old-uncertain", "status": "uncertain"})
    old = time.time() - 60
    os.utime(tmp_path / "old-complete.json", (old, old))
    os.utime(tmp_path / "old-uncertain.json", (old, old))

    store.put({"operation_id": "new-complete", "status": "completed"})

    assert store.get("old-complete")["detail_pruned"] is True
    assert store.get("old-complete")["status"] == "completed"
    assert (tmp_path / "old-uncertain.json").exists()
    assert (tmp_path / "new-complete.json").exists()


def test_diff_compares_full_source_but_bounds_values_and_paths(tmp_path):
    before = {"data": {"prepare": "before" * 10000}, **{f"field-{i}": i for i in range(60)}}
    patch = {"data": {"prepare": "after" * 10000}, **{f"field-{i}": i + 1 for i in range(60)}}
    reader = FakeReader({("editor_chart", "synthetic", "saved"): [rb("editor_chart", "synthetic", "r1", before)]})
    writer = service(tmp_path, reader, FakeBackend([]))
    result = writer.diff("editor_chart", "synthetic", patch)
    assert result["changed_field_count"] == 61 and result["diff_complete"] is False
    assert len(result["changes"]) == 50
    source = next(row for row in result["changes"] if row["path"] == "/data/prepare")
    assert source["before"]["value_omitted"] and source["after"]["value_omitted"]
    assert source["before"]["sha256"] != source["after"]["sha256"]
    assert "beforebefore" not in json.dumps(result)
    assert writer.backend.calls == []
