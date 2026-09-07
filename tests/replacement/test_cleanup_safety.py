import pytest

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
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
        ids = self.edges.get(identity, []) if direction == "to" else [k for k, v in self.edges.items() if identity in v]
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


def test_alias_preserve_identity_and_its_dependencies():
    _p, service = setup()
    preview = service.preview(
        [obj("widget", "chart"), obj("dataset", "data")], preserve_roots=[obj("editor_chart", "chart")]
    )
    assert preview["delete"] == []
    assert {x["object_id"] for x in preview["preserve"]} == {"chart", "data"}


def test_consumer_first_even_with_reversed_inventory():
    p, service = setup()
    preview = service.preview([obj("dataset", "data"), obj("widget", "chart"), obj("dash", "board")], preserve_roots=[])
    assert [x["object_id"] for x in preview["delete"]] == ["board", "chart", "data"]
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
    assert result["results"][0]["status"] == ("uncertain" if isinstance(failure, UncertainWriteError) else "failed")


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
        "relations": [{"id": "board", "type": "dashboard"}] if identity == "data" and direction == "from" else [],
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
