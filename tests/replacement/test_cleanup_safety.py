import pytest

from datalens_dev_mcp.api.errors import DataLensApiError, DataLensSafetyError, UncertainWriteError
from datalens_dev_mcp.objects.cleanup import CleanupService


def obj(kind, identity):
    return {"object_type": kind, "object_id": identity}


class Provider:
    def __init__(self):
        self.edges = {"board": ["chart"], "chart": ["data"], "data": [], "protected": []}
        self.types = {"board": "dashboard", "chart": "widget", "data": "dataset", "protected": "dashboard"}
        self.absent = set()
        self.calls = []
        self.failure = None

    def object_relations(self, identity, *, direction="to"):
        ids = self.edges.get(identity, []) if direction == "from" else [k for k, v in self.edges.items() if identity in v]
        return {"complete": True, "relations": [{"id": k, "type": self.types[k]} for k in ids]}

    def object_get(self, kind, identity, **kwargs):
        if identity in self.absent:
            raise DataLensApiError("absent", http_status=404, response_received=True)
        return {"identity": obj(kind, identity), "object": {"id": identity}}

    def delete(self, kind, identity):
        self.calls.append(identity)
        if self.failure:
            raise self.failure
        self.absent.add(identity)


def setup():
    provider = Provider()
    return provider, CleanupService(reader=provider, deleter=provider)


def test_separately_authorized_repeat_keeps_original_unknown_and_never_replays():
    from datalens_dev_mcp.operation_store import compact_operation

    p, service = setup()
    p.edges = {"data": []}
    first = service.preview([obj("dataset", "data")], preserve_roots=[])
    p.failure = UncertainWriteError("synthetic lost response")
    unknown = service.apply(first, confirmed_delete=first["delete"])
    assert unknown["status"] == "uncertain"
    fresh = service.preview(first["candidates"], preserve_roots=[])
    with pytest.raises(DataLensSafetyError):
        service.apply(fresh, confirmed_delete=fresh["delete"])
    assert p.calls == ["data"]
    repeat_of = [{"operation_id": unknown["operation_id"], "object_id": "data",
                  "receipt_version": unknown["store_version"]}]
    p.failure = None
    result = service.apply(fresh, confirmed_delete=fresh["delete"], repeat_of=repeat_of)
    assert result["ok"] and result["results"][0]["absence_verified"]
    assert p.calls == ["data", "data"]
    assert service.store.get(unknown["operation_id"]) == unknown
    assert compact_operation(result)["repeat_of"] == repeat_of
    assert compact_operation(unknown)["store_version"] == unknown["store_version"]
    assert service.apply(fresh, confirmed_delete=fresh["delete"], repeat_of=repeat_of)["ok"]
    assert p.calls == ["data", "data"]
    # Even after compaction and an object reappears, the same grant is spent.
    service.store._compact_receipt(result)
    p.absent.clear()
    newer = service.preview(first["candidates"], preserve_roots=[])
    with pytest.raises(DataLensSafetyError):
        service.apply(newer, confirmed_delete=newer["delete"], repeat_of=repeat_of)
    assert p.calls == ["data", "data"]


@pytest.mark.parametrize("conflict", ["version", "scope", "pending", "missing", "wrong_target", "drift"])
def test_repeat_permission_does_not_override_receipt_or_preview_conflicts(conflict):
    p, service = setup()
    p.edges = {"data": []}
    first = service.preview([obj("dataset", "data")], preserve_roots=[obj("dashboard", "protected")])
    p.failure = UncertainWriteError("synthetic lost response")
    unknown = service.apply(first, confirmed_delete=first["delete"])
    refs = [{"operation_id": unknown["operation_id"], "object_id": "data",
             "receipt_version": unknown["store_version"]}]
    fresh = service.preview(first["candidates"], preserve_roots=first["preserve_roots"])
    if conflict == "version":
        service.reconcile(unknown["operation_id"])
    elif conflict in {"scope", "pending"}:
        unknown["auth_scope" if conflict == "scope" else "status"] = "other" if conflict == "scope" else "pending"
        service.store.put(unknown)
        refs[0]["receipt_version"] = unknown["store_version"]
    elif conflict == "missing":
        refs[0]["operation_id"] = "nonexistent"
    elif conflict == "wrong_target":
        refs[0]["object_id"] = "unrelated"
    elif conflict == "drift":
        p.edges["protected"] = ["data"]
    p.failure = None
    if conflict == "drift":
        result = service.apply(fresh, confirmed_delete=fresh["delete"], repeat_of=refs)
        assert result["status"] == "preview_changed"
        # A preview_changed reservation must recheck the grant on resumption.
        p.edges["protected"] = []
        service.reconcile(unknown["operation_id"])
    with pytest.raises(DataLensSafetyError):
        service.apply(fresh, confirmed_delete=fresh["delete"], repeat_of=refs)
    assert p.calls == ["data"]


@pytest.mark.parametrize("second_outcome", ["not_applied", "unknown"])
def test_new_repeat_attempt_requires_every_unknown_and_keeps_known_failures_recoverable(second_outcome):
    p, service = setup()
    p.edges = {"data": []}
    first = service.preview([obj("dataset", "data")], preserve_roots=[])
    p.failure = UncertainWriteError("synthetic lost response")
    unknown = service.apply(first, confirmed_delete=first["delete"])
    refs = [{"operation_id": unknown["operation_id"], "object_id": "data",
             "receipt_version": unknown["store_version"]}]
    fresh = service.preview(first["candidates"], preserve_roots=[])
    if second_outcome == "not_applied":
        p.failure = DataLensApiError("connection failed", dispatch_state="not_dispatched", response_received=False)
    second = service.apply(fresh, confirmed_delete=fresh["delete"], repeat_of=refs)
    assert second["results"][0]["effect_outcome"] == second_outcome
    newer = service.preview(first["candidates"], preserve_roots=[])
    p.failure = None
    if second_outcome == "unknown":
        with pytest.raises(DataLensSafetyError):
            service.apply(newer, confirmed_delete=newer["delete"], repeat_of=refs)
        # This represents a new informed authorization covering the latest risk.
        refs.append({"operation_id": second["operation_id"], "object_id": "data",
                     "receipt_version": second["store_version"]})
    assert service.apply(newer, confirmed_delete=newer["delete"], repeat_of=refs)["ok"]
    assert p.calls == ["data", "data", "data"]


def test_alias_preserve_identity_and_its_dependencies():
    _p, service = setup()
    preview = service.preview(
        [obj("widget", "chart"), obj("dataset", "data")], preserve_roots=[obj("editor_chart", "chart")]
    )
    assert preview["delete"] == []
    assert {x["object_id"] for x in preview["preserve"]} == {"chart", "data"}


def test_consumer_first_even_with_reversed_inventory():
    p, service = setup()
    get = p.object_get
    reads = 0
    ordered_fields = ["first", "second"]

    def read(kind, identity, **kwargs):
        nonlocal reads
        snapshot = get(kind, identity, **kwargs)
        if kind == "dataset":
            reads += 1
            choices = ["first", "second"] if reads % 2 else ["second", "first"]
            snapshot["object"].update({
                "dataset": {"result_schema": list(ordered_fields), "result_schema_aux": {
                    "inter_dependencies": {"deps": [{"ref_field_ids": choices}]},
                }},
                "options": {
                    "sources": {"compatible_types": [{"source_type": value} for value in choices]},
                    "join": {"types": choices},
                    "connections": {"items": [{"replacement_types": [{"conn_type": value} for value in choices]}]},
                },
            })
        return snapshot

    p.object_get = read
    preview = service.preview([obj("dataset", "data"), obj("widget", "chart"), obj("dash", "board")], preserve_roots=[])
    assert [x["object_id"] for x in preview["delete"]] == ["board", "chart", "data"]
    fresh = service.preview(preview["candidates"], preserve_roots=[])
    assert fresh["dependency_fingerprint"] == preview["dependency_fingerprint"]
    ordered_fields.reverse()
    assert service.apply(preview, confirmed_delete=preview["delete"])["status"] == "preview_changed"
    assert p.calls == []
    ordered_fields.reverse()
    assert service.apply(preview, confirmed_delete=preview["delete"])["ok"]
    assert p.calls == ["board", "chart", "data"]


@pytest.mark.parametrize(
    "failure", [DataLensApiError("failed", http_status=500, response_received=True), UncertainWriteError("timeout")]
)
def test_failure_stops_dependencies_and_reports_skips(failure):
    p, service = setup()
    preview = service.preview([obj("dash", "board"), obj("widget", "chart"), obj("dataset", "data")], preserve_roots=[])
    p.failure = failure
    result = service.apply(preview, confirmed_delete=preview["delete"])
    assert not result["ok"]
    assert p.calls == ["board"]
    assert [x["status"] for x in result["results"]][1:] == ["skipped", "skipped"]
    assert result["results"][0]["status"] == result["status"] == "uncertain"
    assert "not replay" in result["next_action"]


def test_fresh_preserve_closure_invalidates_old_preview_without_writes():
    p, service = setup()
    preview = service.preview(
        [obj("dash", "board"), obj("widget", "chart"), obj("dataset", "data")],
        preserve_roots=[obj("dashboard", "protected")],
    )
    p.edges["protected"] = ["chart"]
    result = service.apply(preview, confirmed_delete=preview["delete"])
    assert not result["ok"]
    assert result["status"] == "preview_changed"
    assert p.calls == []
    assert "chart" not in [x["object_id"] for x in result["preview"]["delete"]]


def test_new_external_consumer_invalidates_preview():
    p, service = setup()
    preview = service.preview([obj("dash", "board"), obj("widget", "chart"), obj("dataset", "data")], preserve_roots=[])
    p.edges["protected"] = ["data"]
    result = service.apply(preview, confirmed_delete=preview["delete"])
    assert not result["ok"] and p.calls == []


@pytest.mark.parametrize("candidate", [obj("unsupported", "bad"), obj("dataset", ""), obj("dataset", "board")])
def test_invalid_candidate_rejected_before_first_mutation(candidate):
    p, service = setup()
    try:
        preview = service.preview([obj("dash", "board"), candidate], preserve_roots=[])
        if preview["complete"]:
            service.apply(preview, confirmed_delete=preview["delete"])
    except ValueError:
        pass
    assert p.calls == []


def test_cycle_fails_closed():
    p, service = setup()
    p.edges["data"] = ["board"]
    preview = service.preview([obj("dash", "board"), obj("widget", "chart"), obj("dataset", "data")], preserve_roots=[])
    assert not preview["complete"]
    assert p.calls == []


def test_relation_404_is_not_object_absence():
    p, service = setup()

    def missing_relation(*args, **kwargs):
        raise DataLensApiError("relations missing", http_status=404, response_received=True)

    p.object_relations = missing_relation
    preview = service.preview([obj("dataset", "data")], preserve_roots=[])
    assert not preview["complete"]
    assert p.calls == []


def test_inverse_preserved_consumer_evidence_fails_closed():
    p, service = setup()
    p.edges = {"board": [], "data": []}
    p.object_relations = lambda identity, direction="to": {
        "complete": True,
        "relations": [{"id": "board", "type": "dashboard"}] if identity == "data" and direction == "to" else [],
    }
    preview = service.preview(
        [obj("dashboard", "board"), obj("dataset", "data")], preserve_roots=[obj("dash", "board")]
    )
    assert not preview["complete"] or not any(x["object_id"] == "data" for x in preview["delete"])


def test_successful_mutation_with_failed_readback_is_uncertain():
    p, service = setup()
    p.edges = {"data": []}
    get = p.object_get

    def read(*args, **kwargs):
        if p.calls:
            raise DataLensApiError("readback failed", http_status=503, response_received=True)
        return get(*args, **kwargs)

    p.object_get = read
    preview = service.preview([obj("dataset", "data")], preserve_roots=[])
    result = service.apply(preview, confirmed_delete=preview["delete"])
    assert result["results"][0]["status"] == "uncertain"


def test_delete_404_needs_actual_absence_before_dependencies():
    p, service = setup()
    p.edges = {"board": ["data"], "data": []}

    def missing_delete(kind, identity):
        p.calls.append(identity)
        raise DataLensApiError("delete route missing", http_status=404, response_received=True)

    p.delete = missing_delete
    preview = service.preview([obj("dashboard", "board"), obj("dataset", "data")], preserve_roots=[])
    result = service.apply(preview, confirmed_delete=preview["delete"])
    assert not result["ok"]
    assert p.calls == ["board"]
    assert result["results"][0]["status"] == "uncertain"
    assert result["results"][1]["status"] == "skipped"


@pytest.fixture(autouse=True)
def isolated_cleanup_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
