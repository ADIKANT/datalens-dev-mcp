import copy
import json
import multiprocessing
from io import BytesIO
from unittest.mock import patch

import datalens_sdk
import httpx
import pytest
from test_dataset_update_wire import snapshot

from datalens_dev_mcp.api.errors import InputContractError
from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.objects.read import ObjectReadService
from datalens_dev_mcp.objects.write import ObjectMutationService
from datalens_dev_mcp.operation_store import OperationStore
from datalens_dev_mcp.server import dl_object_create, dl_object_update


@pytest.mark.parametrize(
    "mode",
    [
        "full",
        "narrow",
        "stale_outer",
        "stale_inner",
        "wrong_business",
        "wrong_id",
        "third_revision",
        "lost_response",
        "readback_unavailable",
        "rejected",
        "array_order",
        "partial_after",
    ],
)
def test_full_dataset_public_update_advancing_revisions(tmp_path, mode):
    state = snapshot()
    state["dataset"]["avatar_relations"] = [{"id": "first"}, {"id": "second"}]
    wanted = copy.deepcopy(state)
    wanted["dataset"]["description"] = "after"
    writes = []
    if mode == "stale_outer":
        state["revId"] = "outer-manual"
    if mode == "stale_inner":
        state["dataset"]["revision_id"] = "inner-manual"

    def handle(request):
        if writes and mode == "readback_unavailable":
            raise httpx.ReadTimeout("readback unavailable", request=request)
        return httpx.Response(200, json=state)

    def direct(request, **kwargs):
        payload = json.loads(request.data)
        writes.append(payload)
        if mode == "rejected":
            from urllib.error import HTTPError

            raise HTTPError(request.full_url, 409, "revision conflict", {}, BytesIO(b"{}"))
        state["dataset"] = payload["data"]["dataset"]
        state["dataset"]["revision_id"] = "inner-r8"
        state["revId"] = "outer-r2"
        if mode == "partial_after":
            state["complete"] = False
        returned = copy.deepcopy(state)
        if mode == "wrong_business":
            state["dataset"]["description"] = "wrong"
        if mode == "wrong_id":
            state["id"] = "other-object"
        if mode == "third_revision":
            state["revId"] = "outer-r3"
        if mode == "array_order":
            state["dataset"]["avatar_relations"].reverse()
        if mode == "lost_response":
            raise TimeoutError("applied but response lost")
        return BytesIO(json.dumps(returned).encode())

    config = DataLensConfig(base_url="https://synthetic.invalid", org_id="synthetic", iam_token="synthetic")
    client = datalens_sdk.DataLensClientYC(auth=None, base_url=config.base_url, transport=httpx.MockTransport(handle))
    sdk = SdkAdapter(config, client=client)
    writer = ObjectMutationService(
        reader=ObjectReadService(api=None, sdk=sdk), backend=sdk, store=OperationStore(tmp_path)
    )
    if mode == "narrow":
        wanted = {"dataset": {"description": "after"}}
    args = [
        {"object_type": "dataset", "object_id": "synthetic-dataset", "expected_revision": "outer-r1", "patch": wanted}
    ]
    with (
        patch("datalens_dev_mcp.server.default_mutation_service", return_value=writer),
        patch("datalens_dev_mcp.api.client.request.urlopen", direct),
    ):
        result = dl_object_update(args, operation_id="dataset-full")
        expected = (
            "completed"
            if mode in {"full", "narrow"}
            else (
                "blocked" if mode == "stale_outer" else "failed" if mode in {"stale_inner", "rejected"} else "uncertain"
            )
        )
        assert result["status"] == expected
        if expected in {"failed", "blocked"}:
            assert "active or interrupted" not in result["next_action"]
            assert "new operation_id" in result["next_action"]
        if expected == "uncertain":
            assert "must not be replayed" in result["next_action"]
        if expected != "failed":
            assert dl_object_update(args, operation_id="dataset-full")["status"] == expected
        reconciled = writer.reconcile("dataset-full")
        assert reconciled["status"] == ("completed" if mode == "lost_response" else expected)
        if mode == "partial_after":
            state["complete"] = True
            assert writer.reconcile("dataset-full")["status"] == "completed"
    assert len(writes) == (0 if mode in {"stale_inner", "stale_outer"} else 1)
    if mode == "full":
        assert {k: v for k, v in state["dataset"].items() if k != "revision_id"} == {
            k: v for k, v in wanted["dataset"].items() if k != "revision_id"
        }


def create_draft():
    return [
        {
            "client_ref": "synthetic",
            "object_type": "editor_chart",
            "variant": "control_node",
            "name": "Synthetic selector",
            "tabs": {
                "meta.json": "{}",
                "params.js": "module.exports={};",
                "controls.js": "module.exports={controls:[]};",
            },
        }
    ]


def process_create(root, oid, effects, entered, release, results, pause_claim=False):
    def handle(request):
        with effects.get_lock():
            effects.value += 1
        entered.set()
        assert release.wait(10)
        raise httpx.ReadTimeout("synthetic lost response", request=request)

    client = datalens_sdk.DataLensClientYC(
        auth=None, base_url="https://synthetic.invalid", transport=httpx.MockTransport(handle)
    )
    sdk = SdkAdapter(client=client)
    writer = ObjectMutationService(reader=ObjectReadService(api=None, sdk=sdk), backend=sdk, store=OperationStore(root))
    original_record = writer._record

    def record(*args):
        result = original_record(*args)
        if pause_claim:
            entered.set()
            assert release.wait(10)
        return result

    writer._record = record
    with patch("datalens_dev_mcp.server.default_mutation_service", return_value=writer):
        results.put(dl_object_create(create_draft(), {"workbook_id": "synthetic-workbook"}, operation_id=oid))


@pytest.mark.parametrize("same_id", [True, False])
def test_public_multiprocess_admission(tmp_path, same_id):
    ctx = multiprocessing.get_context("spawn")
    effects, entered, release, results = ctx.Value("i", 0), ctx.Event(), ctx.Event(), ctx.Queue()
    first = ctx.Process(
        target=process_create, args=(str(tmp_path), "op-a", effects, entered, release, results, same_id)
    )
    second = ctx.Process(
        target=process_create, args=(str(tmp_path), "op-a" if same_id else "op-b", effects, entered, release, results)
    )
    first.start()
    assert entered.wait(10)
    entered.clear()
    second.start()
    try:
        if same_id:
            second.join(3)
            assert not second.is_alive(), "same-ID caller must return in-flight without waiting for network"
            assert effects.value == 0
        else:
            assert entered.wait(3), "independent ID was blocked on another network call"
            assert effects.value == 2
    finally:
        release.set()
        first.join(10)
        second.join(10)
    assert first.exitcode == second.exitcode == 0
    assert effects.value == (1 if same_id else 2)


@pytest.mark.parametrize("failure", [ValueError("bad response"), TypeError("bad response")])
def test_post_effect_decode_error_is_unknown(tmp_path, failure):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, service

    backend = FakeBackend([failure])
    writer = service(tmp_path, FakeReader({}), backend)
    result = writer.create_objects(create_draft(), {"workbook_id": "synthetic"}, operation_id="decode")
    assert result["status"] == "uncertain"
    assert result["results"][0]["code"] == "write_outcome_unknown"
    assert "reconcile" in result["results"][0]["next_action"]
    writer.create_objects(create_draft(), {"workbook_id": "synthetic"}, operation_id="decode")
    assert len(backend.calls) == 1


def test_receipt_pruning_retains_claims_and_recovery_state(tmp_path):
    store = OperationStore(tmp_path, max_records=1, max_bytes=1, max_age_seconds=0)
    for oid, status in [("old", "completed"), ("recovery", "uncertain"), ("latest", "completed")]:
        store.put(
            {
                "operation_id": oid,
                "request_digest": oid,
                "effect": "create",
                "status": status,
                "results": [],
                "heavy": "x" * 100,
            }
        )
    assert store.get("old")["detail_pruned"] is True
    assert store.get("recovery")["status"] == "uncertain"
    admitted, previous = store.claim({"operation_id": "old", "request_digest": "old", "effect": "create"})
    assert admitted is False
    assert previous["status"] == "completed"


@pytest.mark.parametrize("limit", ["max_records", "max_bytes", "max_age_seconds"])
def test_pruning_does_not_rewrite_existing_tombstones(tmp_path, monkeypatch, limit):
    store = OperationStore(tmp_path)
    for index in range(4):
        store._compact_receipt({
            "operation_id": f"old-{index}", "request_digest": f"digest-{index}",
            "effect": "create", "status": "completed", "results": [],
        })
    before = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}
    setattr(store, limit, 0)
    compacted = []
    original = store._compact_receipt

    def track_compaction(record):
        compacted.append(record["operation_id"])
        original(record)

    monkeypatch.setattr(store, "_compact_receipt", track_compaction)
    pending = store.put({"operation_id": "active", "status": "pending", "results": []})
    store.put(pending)
    assert compacted == []
    assert all((tmp_path / name).read_bytes() == contents for name, contents in before.items())
    admitted, previous = store.claim({
        "operation_id": "old-0", "request_digest": "digest-0", "effect": "create",
    })
    assert admitted is False and previous["status"] == "completed"
    with pytest.raises(InputContractError, match="different request"):
        store.claim({"operation_id": "old-0", "request_digest": "changed", "effect": "create"})


def test_resumed_compact_failure_can_prune_new_detail(tmp_path):
    store = OperationStore(tmp_path, max_bytes=1)
    identity = {"operation_id": "retry", "request_digest": "same", "effect": "create"}
    store._compact_receipt({**identity, "status": "failed", "results": []})
    admitted, resumed = store.claim(identity)
    assert admitted is True
    assert not resumed.get("detail_pruned")
    resumed.update({"status": "completed", "results": [{
        "key": "chart", "status": "completed", "desired": {"data": "x" * 10000},
    }]})
    store.put(resumed)
    store.put({"operation_id": "next", "status": "pending", "results": []})
    compact = store.get("retry")
    assert compact["detail_pruned"] is True
    assert "desired" not in compact["results"][0]
    assert store.claim(identity)[0] is False


def test_claim_crash_and_conflicting_request_never_replay(tmp_path):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, service

    writer = service(tmp_path, FakeReader({}), FakeBackend([]))
    original = writer._items

    def interrupt(*args):
        raise KeyboardInterrupt()

    writer._items = interrupt
    with pytest.raises(KeyboardInterrupt):
        writer.create_objects(create_draft(), {"workbook_id": "synthetic"}, operation_id="claim-crash")
    writer._items = original
    assert (
        writer.create_objects(create_draft(), {"workbook_id": "synthetic"}, operation_id="claim-crash")["status"]
        == "pending"
    )
    with pytest.raises(ValueError, match="different request"):
        writer.create_objects(create_draft(), {"workbook_id": "different"}, operation_id="claim-crash")
    assert writer.backend.calls == []


def test_store_cas_prevents_stale_reconcile_overwrite(tmp_path):
    store = OperationStore(tmp_path)
    _, original = store.claim({"operation_id": "cas", "request_digest": "x", "effect": "create", "status": "pending"})
    stale = copy.deepcopy(original)
    original["status"] = "uncertain"
    store.put(original)
    stale["status"] = "completed"
    with pytest.raises(RuntimeError, match="concurrently"):
        OperationStore(tmp_path).put(stale)
    assert store.get("cas")["status"] == "uncertain"


@pytest.mark.parametrize("marker", [{"read_view": "summary"}, {"full_state": False}])
def test_projection_is_not_replacement_state(tmp_path, marker):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, service

    writer = service(tmp_path, FakeReader({}), FakeBackend([]))
    with pytest.raises(ValueError, match="full"):
        writer.update_objects([{"object_type": "dataset", "object_id": "synthetic", "patch": marker}])
    assert writer.backend.calls == []


@pytest.mark.parametrize("after_effect", [False, True])
def test_process_crash_keeps_durable_claim(tmp_path, after_effect):
    ctx = multiprocessing.get_context("spawn")
    effects, entered, release, results = ctx.Value("i", 0), ctx.Event(), ctx.Event(), ctx.Queue()
    args = (str(tmp_path), "crashed", effects, entered, release, results)
    first = ctx.Process(target=process_create, args=(*args, not after_effect))
    first.start()
    assert entered.wait(10)
    first.terminate()
    first.join(10)
    restarted = ctx.Process(target=process_create, args=args)
    restarted.start()
    restarted.join(10)
    assert restarted.exitcode == 0
    assert effects.value == (1 if after_effect else 0)
    recovered = results.get(timeout=2)
    assert recovered["status"] == ("uncertain" if after_effect else "pending")
    assert "replayed" in recovered["next_action"]


def test_store_failure_before_transport_blocks_effect(tmp_path):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, service

    writer = service(tmp_path, FakeReader({}), FakeBackend([]))
    with (
        patch.object(writer.store, "_write", side_effect=OSError("synthetic disk unavailable")),
        pytest.raises(OSError),
    ):
        writer.create_objects(create_draft(), {"workbook_id": "synthetic"}, operation_id="disk")
    assert writer.backend.calls == []


@pytest.mark.parametrize("change", ["payload", "effect", "target"])
def test_same_id_conflict_is_bound_before_effect(tmp_path, change):
    store = OperationStore(tmp_path)
    candidate = {"operation_id": "bound", "request_digest": "original", "effect": "create", "status": "pending"}
    store.claim(candidate)
    conflicting = copy.deepcopy(candidate)
    if change == "effect":
        conflicting["effect"] = "update"
    else:
        conflicting["request_digest"] = change
    with pytest.raises(ValueError, match="different request"):
        OperationStore(tmp_path).claim(conflicting)


@pytest.mark.parametrize("destination", [{"workbook_id": "synthetic"}, {"path": "synthetic/"}])
def test_public_conflicting_id_is_input_error_without_second_effect(tmp_path, destination):
    from datalens_dev_mcp.server import call_tool

    effects = []

    def handle(request):
        effects.append(request)
        raise httpx.ReadTimeout("synthetic lost response", request=request)

    client = datalens_sdk.DataLensClientYC(
        auth=None, base_url="https://synthetic.invalid", transport=httpx.MockTransport(handle)
    )
    sdk = SdkAdapter(client=client)
    writer = ObjectMutationService(
        reader=ObjectReadService(api=None, sdk=sdk), backend=sdk, store=OperationStore(tmp_path)
    )
    args = {"drafts": create_draft(), "destination": destination, "operation_id": "bound-public"}
    with patch("datalens_dev_mcp.server.default_mutation_service", return_value=writer):
        assert call_tool("dl_object_create", args)["structuredContent"]["status"] == "uncertain"
        args["drafts"][0]["name"] = "Changed request"
        result = call_tool("dl_object_create", args)
    assert result["structuredContent"]["status"] == "input_error"
    assert result["isError"] is True
    assert len(effects) == 1


@pytest.mark.parametrize("effect", ["update", "publish"])
@pytest.mark.parametrize(
    "marker", [{"complete": False}, {"full_state": False}, {"read_view": "summary"}, {"ok": False}]
)
def test_public_mutation_requires_complete_current_read(tmp_path, effect, marker):
    from datalens_dev_mcp.server import call_tool

    writes = []
    state = {"entry": {"entryId": "synthetic-dashboard", "savedId": "r1", "data": {"tabs": []}}, **marker}

    def handle(request):
        if not request.url.path.endswith("getDashboard"):
            writes.append(request)
        return httpx.Response(200, json=state)

    client = datalens_sdk.DataLensClientYC(
        auth=None, base_url="https://synthetic.invalid", transport=httpx.MockTransport(handle)
    )
    sdk = SdkAdapter(client=client)
    writer = ObjectMutationService(
        reader=ObjectReadService(api=None, sdk=sdk), backend=sdk, store=OperationStore(tmp_path)
    )
    target = {"object_type": "dashboard", "object_id": "synthetic-dashboard"}
    arguments = (
        {"changes": [{**target, "patch": {"data": {"title": "after"}}}]}
        if effect == "update"
        else {"targets": [target]}
    )
    with patch("datalens_dev_mcp.server.default_mutation_service", return_value=writer):
        result = call_tool("dl_object_" + effect, arguments)
    assert writes == []
    assert result["structuredContent"]["status"] == "blocked"
    assert result["structuredContent"]["results"][0]["code"] == "full_read_required"


@pytest.mark.parametrize("invalid", ["unsupported", "no_name", "typed_config"])
def test_public_sdk_validation_is_definite_input_failure(tmp_path, invalid):
    from datalens_dev_mcp.server import call_tool

    requests = []

    def handle(request):
        requests.append(request)
        raise AssertionError("invalid input reached provider")

    client = datalens_sdk.DataLensClientYC(
        auth=None, base_url="https://synthetic.invalid", transport=httpx.MockTransport(handle)
    )
    sdk = SdkAdapter(client=client)
    writer = ObjectMutationService(
        reader=ObjectReadService(api=None, sdk=sdk), backend=sdk, store=OperationStore(tmp_path)
    )
    drafts = create_draft()
    if invalid == "unsupported":
        drafts[0]["object_type"] = "unsupported"
    elif invalid == "no_name":
        del drafts[0]["name"]
    else:
        drafts[0]["tabs"]["meta.json"] = 42
    with patch("datalens_dev_mcp.server.default_mutation_service", return_value=writer):
        result = call_tool("dl_object_create", {"drafts": drafts, "destination": {"workbook_id": "synthetic"}})[
            "structuredContent"
        ]
    assert result["status"] == "failed"
    assert result["results"][0]["code"] == "input_error"
    assert requests == []


def test_create_preflight_receipt_retains_intent_and_safe_failure(tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        raise httpx.ReadTimeout("synthetic read timeout", request=request)

    client = datalens_sdk.DataLensClientYC(auth=None, base_url="https://synthetic.invalid",
                                          transport=httpx.MockTransport(handle))
    sdk = SdkAdapter(client=client)
    store = OperationStore(tmp_path)
    writer = ObjectMutationService(reader=ObjectReadService(api=None, sdk=sdk), backend=sdk, store=store)
    draft = {"object_type": "dataset", "name": "Synthetic", "client_ref": "source",
             "dataset": {"connection_id": "synthetic-connection"}}
    result = writer.create_objects([draft], {"workbook_id": "synthetic"}, operation_id="prepared")
    assert result["status"] == "failed"
    item = result["results"][0]
    assert item["dispatch_state"] == "not_dispatched" and item["effect_outcome"] == "not_applied"
    assert item["desired"] == {"name": "Synthetic"}
    assert item["intent"]["destination"] == {"workbook_id": "synthetic"}
    assert item["intent"]["bindings"] == {"connection_id": "synthetic-connection"}
    assert len(item["intent"]["content_sha256"]) == 64
    assert requests and all(request.url.path.endswith("/getConnection") for request in requests)
    assert "reconcile" not in result["next_action"].lower()
    client.close()


def test_named_dashboard_parameter_removal_preserves_neighbors_and_verifies_absence(tmp_path):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

    before = {"entry": {"data": {"settings": {"globalParams": {"remove": [], "keep": ["value"]},
                                             "unrelated": True}, "tabs": [{"id": "tab"}]}}}
    after = copy.deepcopy(before)
    del after["entry"]["data"]["settings"]["globalParams"]["remove"]
    for mode in ("applied", "still_present", "stale"):
        reader = FakeReader({("dashboard", "synthetic", "saved"): [
            rb("dashboard", "synthetic", "r1", before),
            rb("dashboard", "synthetic", "r2", after if mode == "applied" else before),
        ]})
        backend = FakeBackend([{"object_id": "synthetic", "object": {"revId": "r2"}}])
        writer = service(tmp_path / mode, reader, backend)
        result = writer.update_objects([{"object_type": "dashboard", "object_id": "synthetic",
                                         "expected_revision": "old" if mode == "stale" else "r1",
                                         "remove_global_params": ["remove"]}])
        assert result["status"] == {"applied": "completed", "still_present": "uncertain", "stale": "blocked"}[mode]
        if mode != "stale":
            assert result["results"][0]["changes"] == [
                {"path": "/entry/data/settings/globalParams/remove", "before": [], "after": None}]
        else:
            assert backend.calls == []


def compact_dashboard_case():
    before = {"entry": {"data": {"settings": {"keep": True}, "tabs": [
        {"id": "overview", "title": "Overview", "aliases": {"default": [["period"]]},
         "items": [{"id": "manual", "type": "future_widget", "data": {"body": "x" * 210_000}},
                   {"id": "remove", "type": "text", "data": {"text": "temporary"}}],
         "layout": [{"i": "manual", "x": 1, "y": 4, "w": 10, "h": 8, "parent": "fixed"},
                    {"i": "remove", "x": 1, "y": 12, "w": 10, "h": 2}],
         "connections": [{"from": "selector", "to": "remove", "kind": "ignore"}],
         "unknown": {"preserve": [True, 1]}},
        {"id": "neighbor", "title": "Untouched", "items": [{"id": "other", "data": {"keep": True}}]},
    ]}}}
    new_item = {"id": "new", "type": "widget", "data": {"chartId": "synthetic-chart"}}
    new_layout = {"i": "new", "x": 1, "y": 20, "w": 10, "h": 8}
    new_connection = {"from": "selector", "to": "new", "kind": "ignore"}
    delta = {"tabs": [{"id": "overview", "patch": {"aliases": {"default": [["period", "new_period"]]}},
                      "items": {"add": [new_item], "remove": ["remove"]},
                      "layout": {"add": [new_layout], "update": [{"i": "manual", "patch": {"y": 6}}],
                                 "remove": ["remove"]},
                      "connections": {"add": [new_connection], "remove": [{"from": "selector", "to": "remove"}]}}]}
    after = copy.deepcopy(before)
    tab = after["entry"]["data"]["tabs"][0]
    tab["aliases"]["default"][0].append("new_period")
    tab["items"] = [tab["items"][0], new_item]
    tab["layout"] = [{**tab["layout"][0], "y": 6}, new_layout]
    tab["connections"] = [new_connection]
    change = {"object_type": "dashboard", "object_id": "synthetic", "expected_revision": "r1",
              "dashboard_patch": delta}
    return before, after, change


@pytest.mark.parametrize("mode", ["applied", "stale", "missing_neighbor", "wrong_type", "partial", "lost_response"])
def test_compact_dashboard_update_preserves_complete_tabs_and_existing_lifecycle(tmp_path, mode):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

    from datalens_dev_mcp.api.errors import UncertainWriteError
    from datalens_dev_mcp.server import call_tool

    before, wanted, change = compact_dashboard_case()
    observed = copy.deepcopy(wanted)
    if mode == "stale":
        change["expected_revision"] = "stale"
    elif mode == "missing_neighbor":
        observed["entry"]["data"]["tabs"].pop()
    elif mode == "wrong_type":
        observed["entry"]["data"]["tabs"][0]["unknown"]["preserve"][0] = 1
    readback = rb("dashboard", "synthetic", "r2", observed)
    if mode == "partial":
        readback["full_state"] = False
    reader = FakeReader({("dashboard", "synthetic", "saved"): [
        rb("dashboard", "synthetic", "r1", before), readback]})
    backend = FakeBackend([UncertainWriteError("lost response") if mode == "lost_response"
                           else {"object_id": "synthetic", "object": {"revId": "r2"}}])
    writer = service(tmp_path, reader, backend)
    with patch("datalens_dev_mcp.server.default_mutation_service", return_value=writer):
        result = call_tool("dl_object_update", {"changes": [change], "operation_id": "compact"})["structuredContent"]
    assert result["status"] == {"applied": "completed", "stale": "blocked"}.get(mode, "uncertain")
    assert len(json.dumps(change).encode()) < 2000
    assert len(json.dumps(before).encode()) > 200_000
    if mode == "stale":
        assert backend.calls == []
    else:
        assert len(backend.calls) == 1
        assert backend.calls[0][1]["snapshot"] == wanted
        # Receipt replay, including unknown writes, never dispatches again.
        assert writer.update_objects([change], operation_id="compact")["status"] == result["status"]
        assert len(backend.calls) == 1


@pytest.mark.parametrize("invalid", ["no_revision", "wrong_object", "mixed_modes", "mixed_no_revision",
                                     "mixed_wrong_object", "tab_array", "empty_delta", "identity_patch"])
def test_compact_dashboard_update_schema_rejects_ambiguous_requests_before_reads(invalid):
    from datalens_dev_mcp.server import call_tool

    _, _, change = compact_dashboard_case()
    if invalid == "no_revision":
        del change["expected_revision"]
    elif invalid == "wrong_object":
        change["object_type"] = "editor_chart"
    elif invalid.startswith("mixed_"):
        change["patch"] = {"name": "not allowed"}
        if invalid == "mixed_no_revision":
            del change["expected_revision"]
        elif invalid == "mixed_wrong_object":
            change["object_type"] = "editor_chart"
    elif invalid == "tab_array":
        change["dashboard_patch"]["tabs"][0]["patch"]["items"] = []
    elif invalid == "identity_patch":
        change["dashboard_patch"]["tabs"][0]["layout"]["update"][0]["patch"]["i"] = "other"
    else:
        change["dashboard_patch"]["tabs"][0] = {"id": "overview"}
    with patch("datalens_dev_mcp.server.default_mutation_service") as service_mock:
        result = call_tool("dl_object_update", {"changes": [change]})["structuredContent"]
    assert result["code"] == "input_error"
    service_mock.assert_not_called()


@pytest.mark.parametrize("invalid", ["missing_tab", "duplicate_tab", "missing_item", "duplicate_item", "mixed_identity"])
def test_compact_dashboard_addresses_fail_before_dispatch(tmp_path, invalid):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

    from datalens_dev_mcp.server import call_tool

    before, _, change = compact_dashboard_case()
    tab = change["dashboard_patch"]["tabs"][0]
    if invalid == "missing_tab":
        tab["id"] = "missing"
    elif invalid == "duplicate_tab":
        before["entry"]["data"]["tabs"].append(copy.deepcopy(before["entry"]["data"]["tabs"][0]))
    elif invalid == "missing_item":
        tab["items"]["remove"] = ["missing"]
    elif invalid == "duplicate_item":
        tab["items"]["add"][0]["id"] = "manual"
    else:
        tab["layout"]["remove"].append("manual")
    reader = FakeReader({("dashboard", "synthetic", "saved"): [rb("dashboard", "synthetic", "r1", before)]})
    backend = FakeBackend([])
    with patch("datalens_dev_mcp.server.default_mutation_service", return_value=service(tmp_path, reader, backend)):
        result = call_tool("dl_object_update", {"changes": [change]})["structuredContent"]
    assert result["results"][0]["code"] == "input_error"
    assert result["results"][0]["effect_outcome"] == "not_applied"
    assert backend.calls == []


def test_compact_dashboard_diff_and_no_change_do_not_write(tmp_path):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

    from datalens_dev_mcp.server import call_tool

    before, wanted, change = compact_dashboard_case()
    reader = FakeReader({("dashboard", "synthetic", "saved"): [rb("dashboard", "synthetic", "r1", before)]})
    backend = FakeBackend([])
    writer = service(tmp_path, reader, backend)
    with patch("datalens_dev_mcp.server.default_mutation_service", return_value=writer):
        result = call_tool("dl_object_diff", {"object_type": "dashboard", "object_id": "synthetic",
                           "dashboard_patch": change["dashboard_patch"]})["structuredContent"]
        assert result["ok"] and result["changes"][0]["after"]["value_omitted"]
        assert len(json.dumps(result)) < 1500
        full = call_tool("dl_object_diff", {"object_type": "dashboard", "object_id": "synthetic",
                         "dashboard_patch": change["dashboard_patch"], "include_proposed": True})["structuredContent"]
        assert full["proposed"] == wanted
        change["dashboard_patch"] = {"tabs": [{"id": "overview", "patch": {"title": "Overview"}}]}
        result = call_tool("dl_object_update", {"changes": [change]})["structuredContent"]
    assert result["results"][0]["code"] == "no_change"
    assert backend.calls == []
