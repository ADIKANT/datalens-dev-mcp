from __future__ import annotations

import json

import pytest

from datalens_dev_mcp import server
from datalens_dev_mcp.objects.read import ObjectReadService


class Transport:
    def __init__(self):
        self.calls = []
        self.rev = "r1"
        self.pages = {
            "": {"entries": [{"entryId": "a", "scope": "dataset"}], "nextPageToken": "p2"},
            "p2": {
                "entries": [
                    {"entryId": "a", "scope": "dataset"},
                    {"entryId": "d", "scope": "dash"},
                    {"entryId": "b", "scope": "dataset"},
                ]
            },
        }

    def read(self, method, payload):
        self.calls.append((method, payload))
        return self.pages[payload.get("pageToken", "")]

    def get_object(self, kind, identity, **kwargs):
        self.calls.append((kind, identity))
        if identity == "broken":
            raise TimeoutError("synthetic failure")
        return {"id": identity, "revId": self.rev, "data": {"large": "x" * 10000, "name": "Synthetic"}}


@pytest.fixture
def transport(monkeypatch):
    transport = Transport()
    service = ObjectReadService(api=transport, sdk=transport)
    monkeypatch.setattr(server, "_read_service", lambda: service)
    return transport


def test_partial_is_not_lost_through_public_snapshot(transport):
    # Existing handler supports defaults: exercise actual 100-page bound before adding arguments.
    transport.pages = {
        str(i) if i else "": {"entries": [{"entryId": "a", "scope": "dataset"}], "nextPageToken": str(i + 1)}
        for i in range(101)
    }
    result = server.dl_dashboard_snapshot("d")
    assert result["complete"] is False
    assert result["continuation"]


def test_public_continuation_deduplicates_and_binds_scope(transport):
    first = server.dl_dashboard_snapshot("d", max_pages=1)
    assert first["partial_reason"] == "page_limit_reached"
    second = server.dl_dashboard_snapshot("d", max_pages=1, continuation=first["continuation"])
    assert second["complete"] is True
    assert [x["identity"]["object_id"] for x in second["dependencies"]] == ["b"]
    assert transport.calls.count(("dataset", "a")) == 1
    assert second["graph_consistency"] == "unverified"
    with pytest.raises(ValueError, match="continuation"):
        server.dl_dashboard_snapshot("other", continuation=first["continuation"])


def test_unknown_and_failed_dependencies_survive_continuation(transport):
    transport.pages[""]["entries"] += [{"entryId": "u", "scope": "unknown"}, {"entryId": "broken", "scope": "dataset"}]
    first = server.dl_dashboard_snapshot("d", max_pages=1)
    second = server.dl_dashboard_snapshot("d", continuation=first["continuation"])
    assert second["complete"] is False
    assert {x["reason"] for x in second["unresolved_relations"]} == {"unknown_type", "dependency_read_failed"}


def test_target_revision_drift_stays_partial(transport):
    first = server.dl_dashboard_snapshot("d", max_pages=1)
    transport.rev = "r2"
    second = server.dl_dashboard_snapshot("d", continuation=first["continuation"])
    assert second["complete"] is False
    assert second["graph_consistency"] == "drift_detected"
    assert "target_revision_drift" in second["partial_reasons"]


def test_full_summary_and_exact_fields_share_identity(transport):
    full = server.dl_object_get("dataset", "a")
    summary = server.dl_object_get("dataset", "a", view="summary")
    projection = server.dl_object_get("dataset", "a", view="projection", fields=["/data/name"])
    assert summary["identity"] == projection["identity"] == full["identity"]
    assert summary["complete"] and summary["full_state"] is False
    assert summary["full_read"]["tool"] == "dl_object_get"
    assert projection["object"] == {"/data/name": "Synthetic"}
    assert len(json.dumps(summary)) < len(json.dumps(full)) / 4
    assert full["object"]["data"]["large"] == "x" * 10000


def test_exact_limit_and_provider_partial(transport):
    transport.pages[""].pop("nextPageToken")
    assert server.dl_dashboard_snapshot("d", max_pages=1)["complete"] is True
    transport.pages[""]["complete"] = False
    result = server.dl_dashboard_snapshot("d", max_pages=1)
    assert result["complete"] is False
    assert result["partial_reason"] == "provider_relations_partial"


def test_relation_cursor_cycle_is_partial_without_false_progress(transport):
    transport.pages["p2"]["nextPageToken"] = "p2"
    result = server.dl_dashboard_snapshot("d")
    assert result["complete"] is False
    assert result["partial_reason"] == "pagination_cursor_cycle"
    assert result["continuation"] is None


def test_projection_missing_pointer_and_invalid_view_before_provider(transport):
    before = len(transport.calls)
    with pytest.raises(ValueError, match="projection"):
        server.dl_object_get("dataset", "a", view="projection", fields=["name"])
    assert len(transport.calls) == before
    result = server.dl_object_get("dataset", "a", view="projection", fields=["/missing"])
    assert result["missing_fields"] == ["/missing"]
    assert result["full_state"] is False


@pytest.mark.parametrize(
    "changes",
    [{"branch": "published"}, {"revision_id": "other"}, {"view": "summary"}, {"reference_dashboard_id": "other"}],
)
def test_continuation_rejects_changed_read_scope_before_read(transport, changes):
    first = server.dl_dashboard_snapshot("d", max_pages=1)
    before = len(transport.calls)
    with pytest.raises(ValueError, match="continuation"):
        server.dl_dashboard_snapshot("d", continuation=first["continuation"], **changes)
    assert len(transport.calls) == before


def test_relation_failure_keeps_earlier_pages(transport):
    del transport.pages["p2"]
    result = server.dl_dashboard_snapshot("d")
    assert not result["complete"]
    assert result["partial_reason"] == "relation_read_failed"
    assert [x["identity"]["object_id"] for x in result["dependencies"]] == ["a"]
    assert result["continuation"]


def test_summary_dependencies_are_marked_and_have_full_address(transport):
    result = server.dl_dashboard_snapshot("d", view="summary")
    assert result["complete"]
    assert all(x["full_state"] is False and x["full_read"] for x in result["dependencies"])


@pytest.mark.parametrize(
    "payload", [{"id": "wrong"}, {"id": "d", "scope": "dataset"}, {"id": "d", "branch": "published"}]
)
def test_provider_identity_mismatch_is_not_echoed_as_requested_identity(transport, monkeypatch, payload):
    monkeypatch.setattr(transport, "get_object", lambda *args, **kwargs: payload)
    with pytest.raises(ValueError, match="mismatch"):
        server.dl_object_get("dashboard", "d")


def test_provider_partial_remains_partial_after_terminal_continuation(transport):
    transport.pages[""]["complete"] = False
    first = server.dl_dashboard_snapshot("d", max_pages=1)
    assert first["partial_reason"] == "provider_relations_partial"
    second = server.dl_dashboard_snapshot("d", continuation=first["continuation"])
    assert second["complete"] is False
    assert "provider_relations_partial" in second["partial_reasons"]


@pytest.mark.parametrize("view", ["full", "summary", "projection"])
@pytest.mark.parametrize("failed", [False, True])
def test_reference_partial_or_failure_preserves_target_in_all_views(transport, monkeypatch, view, failed):
    original = transport.get_object

    def get_object(kind, identity, **kwargs):
        if identity == "reference":
            if failed:
                raise TimeoutError("synthetic reference failure")
            return {"id": identity, "revId": "ref1", "complete": False}
        return original(kind, identity, **kwargs)

    monkeypatch.setattr(transport, "get_object", get_object)
    fields = ["/id"] if view == "projection" else None
    result = server.dl_dashboard_snapshot("d", reference_dashboard_id="reference", view=view, fields=fields)
    assert result["complete"] is False
    assert result["target"]["identity"]["object_id"] == "d"
    assert result["partial_reason"] == ("reference_read_failed" if failed else "reference_partial")
    assert result["reference"]["complete"] is False


def test_provider_partial_survives_a_later_page_read_failure(transport):
    transport.pages[""]["complete"] = False
    terminal = transport.pages.pop("p2")
    first = server.dl_dashboard_snapshot("d")
    assert "provider_relations_partial" in first["partial_reasons"]
    transport.pages["p2"] = terminal
    second = server.dl_dashboard_snapshot("d", continuation=first["continuation"])
    assert second["complete"] is False
    assert "provider_relations_partial" in second["partial_reasons"]
