from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from datalens_dev_mcp import server
from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.config import DataLensConfig


class PreviewTransport:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def call(self, method, payload, headers):
        self.calls.append((method, payload))
        if self.error:
            raise self.error
        return {"schema": [{"guid": "synthetic-guid", "name": "Value", "type": "integer"}], "rows": [[7]]}


def runtime(monkeypatch, error=None):
    transport = PreviewTransport(error)
    api = DataLensApiClient(DataLensConfig(org_id="synthetic-org", iam_token="synthetic-token", read_retries=0),
                            transport=transport)
    monkeypatch.setattr(server, "get_runtime", lambda: SimpleNamespace(api=api, sdk=SimpleNamespace(get_dataset_data=lambda payload: api.read("getDatasetData", payload))))
    return transport


def preview(**overrides):
    return {"dataset_id": "synthetic-dataset", "columns": ["synthetic-guid"],
            "fields": [{"guid": "synthetic-guid", "title": "Value", "data_type": "integer"}], **overrides}


@pytest.mark.parametrize("invalid", [
    {"columns": [{"guid": "synthetic-guid"}]}, {"columns": []}, {"fields": [{}]},
    {"filters": [{"guid": "synthetic-guid", "operation": {}}]},
    {"sort": [{"guid": "synthetic-guid", "direction": "sideways"}]},
    {"params": ["bad"]}, {"fields": []},
])
def test_bad_nested_preview_is_actionable_before_provider(monkeypatch, invalid):
    transport = runtime(monkeypatch)
    result = server.call_tool("dl_dataset_preview", preview(**invalid))
    assert result["isError"]
    assert result["structuredContent"]["status"] == "input_error"
    assert result["structuredContent"]["next_action"]
    assert result["structuredContent"]["argument_path"]
    assert result["structuredContent"]["expected"]
    assert "inputSchema" not in result["structuredContent"]["next_action"]
    assert transport.calls == []


def test_documented_guid_example_uses_real_preview_and_transport(monkeypatch):
    transport = runtime(monkeypatch)
    result = server.call_tool("dl_dataset_preview", preview())
    assert not result["isError"]
    assert transport.calls[0][1]["columns"] == ["synthetic-guid"]
    assert result["structuredContent"]["rows"] == [[7]]
    assert result["structuredContent"]["columns"] == ["synthetic-guid"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


@pytest.mark.parametrize(("http_status", "expected"), [(404, "not_found"), (403, "permission_denied"),
                                                       (409, "revision_conflict"), (400, "provider_rejected")])
def test_provider_errors_are_tool_results_not_protocol_errors(monkeypatch, http_status, expected):
    runtime(monkeypatch, DataLensApiError("synthetic rejection", http_status=http_status, response_received=True))
    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "dl_dataset_preview", "arguments": preview()}})
    assert "error" not in response
    assert response["result"]["isError"]
    assert response["result"]["structuredContent"]["status"] == expected


def test_post_dispatch_value_error_is_unknown(monkeypatch):
    transport = runtime(monkeypatch, ValueError("bad provider decode"))
    result = server.call_tool("dl_admin_assign_licenses", {"assignments": [{"subjectId": "synthetic-user"}]})
    assert len(transport.calls) == 1
    assert result["isError"]
    assert result["structuredContent"]["status"] == "write_outcome_unknown"
    assert "reconcil" in result["structuredContent"]["next_action"]


def test_schema_labels_and_replacement_annotations():
    result = server.call_tool("dl_method_schema", {"method": "updateDataset"})["structuredContent"]
    assert result["schema_kind"] == "reference_contract"
    assert result["full_payload_schema"] is False
    schemas = {item["name"]: item for item in server.list_tools()}
    assert schemas["dl_object_update"]["annotations"]["destructiveHint"] is True
    assert schemas["dl_object_publish"]["annotations"]["destructiveHint"] is True


@pytest.mark.parametrize("repeat_of", [[{}], [{"operation_id": "old", "object_id": "entry", "receipt_version": 0}],
                                        [{"operation_id": "old", "object_id": "entry", "receipt_version": True}]])
def test_cleanup_repeat_schema_rejects_invalid_references_before_provider(monkeypatch, repeat_of):
    def unexpected():
        pytest.fail("provider service must not be reached")

    monkeypatch.setattr(server, "_cleanup_service", unexpected)
    result = server.call_tool("dl_cleanup_apply", {"preview": {}, "confirmed_delete": [], "repeat_of": repeat_of})
    assert result["isError"]
    assert result["structuredContent"]["status"] == "input_error"


def test_cleanup_repeat_public_tool_passes_exact_references(monkeypatch):
    refs = [{"operation_id": "old", "object_id": "entry", "receipt_version": 5}]

    def apply(preview, **kwargs):
        assert kwargs["repeat_of"] == refs
        assert kwargs["operation_id"] == "new"
        return {"ok": True, "effect": "cleanup", "status": "completed", "repeat_of": refs, "results": []}

    monkeypatch.setattr(server, "_cleanup_service", lambda: SimpleNamespace(apply=apply))
    result = server.call_tool("dl_cleanup_apply", {"preview": {}, "confirmed_delete": [],
                                                  "operation_id": "new", "repeat_of": refs})
    assert not result["isError"]
    assert result["structuredContent"]["repeat_of"] == refs


def test_runtime_fingerprint_reports_active_identity_without_cwd_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = server.dl_server_info()
    second = server.dl_server_info()
    assert first["runtime"] == second["runtime"]
    assert first["runtime"]["instance_id"]
    assert first["runtime"]["package_version"] == first["version"]
    assert first["capability_revision"]
    assert first["build"]["source_commit"] is None
    assert first["build"]["commit_status"] == "unknown"


def test_method_lookup_distinguishes_tool_input_from_provider_metadata():
    result = server.dl_method_schema("dl_object_update")
    assert result["status"] == "wrong_contract_level"
    assert result["tool_contract"]["fields"] == ["changes", "delivery_mode", "operation_id"]
    assert result["tool_contract"]["required"] == ["changes"]
    assert "available_methods" not in result
    result = server.call_tool("dl_object_diff", {"object_type": "dashboard", "object_id": "synthetic",
                                                "patch": {"name": "x"}, "expected_revision": "r1"})
    assert result["structuredContent"]["code"] == "input_error"
    assert "changes[].expected_revision" in result["structuredContent"]["message"]
    provider = server.dl_method_schema("updateDashboard")
    assert provider["ok"] and provider["operation"]["authorization_scope"] == "write"


def test_new_distribution_does_not_masquerade_as_active_process(monkeypatch):
    from importlib import import_module

    identity = import_module("datalens_dev_mcp.runtime_identity")
    before = server.dl_server_info()
    monkeypatch.setattr(identity.metadata, "version", lambda name: "99.0.0")
    after = server.dl_server_info()
    assert after["runtime"] == before["runtime"]
    assert after["build"] == before["build"]
    assert after["installed_distribution_version"] == "99.0.0"
    assert after["active_version_matches_installed"] is False


@pytest.mark.parametrize("failed", [False, True])
def test_owned_wrapper_prints_wire_payload_once(failed):
    payload = {"ok": not failed, "message": "synthetic-single-copy"}
    wire = {"structuredContent": payload, "content": [{"type": "text", "text": json.dumps(payload)}],
            "isError": failed}
    script = Path(__file__).resolve().parents[2] / "scripts" / "print_tool_result.py"
    result = subprocess.run([sys.executable, str(script)], input=json.dumps(wire), capture_output=True, text=True, check=False)
    assert result.returncode == int(failed)
    assert result.stdout.count("synthetic-single-copy") == 1
    assert json.loads(result.stdout) == payload


def test_malformed_rpc_params_stays_a_protocol_error():
    result = server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": ["invalid"]})
    assert result["error"]["code"] == -32602


def test_non_object_rpc_does_not_kill_stdio(tmp_path):
    request = {"jsonrpc": "2.0", "id": 6, "method": "ping"}
    result = subprocess.run([sys.executable, "-m", "datalens_dev_mcp.cli", "stdio"], cwd=tmp_path,
                            input='[]\n' + json.dumps(request) + '\n', capture_output=True, text=True, check=True)
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert responses[0]["error"]["code"] == -32600
    assert responses[1]["id"] == 6


def test_destination_schema_preserves_path_and_rejects_multiple_locations():
    from jsonschema import Draft202012Validator

    schema = next(x["inputSchema"] for x in server.list_tools() if x["name"] == "dl_object_create")
    validator = Draft202012Validator(schema)
    args = {"drafts": [{"object_type": "dataset", "name": "Synthetic"}], "destination": {"path": "synthetic/path"}}
    assert list(validator.iter_errors(args)) == []
    args["destination"]["workbook_id"] = "synthetic-workbook"
    assert list(validator.iter_errors(args))


def test_preview_resolves_fields_from_nested_full_dataset_before_query(monkeypatch):
    from datalens_dev_mcp.objects.read import ObjectReadService

    transport = runtime(monkeypatch)

    class DatasetReader:
        def get_object(self, object_type, object_id, **kwargs):
            return {"id": object_id, "revId": "r1", "data": {"dataset": {
                "result_schema": [{"guid": "synthetic-guid", "title": "Value"}]}}}

    reader = ObjectReadService(api=None, sdk=DatasetReader())
    monkeypatch.setattr(server, "_read_service", lambda: reader)
    result = server.call_tool("dl_dataset_preview", {"dataset_id": "synthetic-dataset", "columns": ["synthetic-guid"]})
    assert not result["isError"]
    assert result["structuredContent"]["rows"] == [[7]]
    assert result["structuredContent"]["columns"] == ["synthetic-guid"]
    assert len(transport.calls) == 1


@pytest.mark.parametrize(("name", "readonly", "cancelled"), [
    ("dl_cleanup_preview", True, False),
    ("dl_cleanup_apply", True, False),
    ("dl_cleanup_apply", False, False),
    ("dl_cleanup_apply", False, True),
])
def test_cleanup_response_deadline_does_not_release_worker_or_replay(monkeypatch, name, readonly, cancelled):
    from threading import Event, Thread

    from datalens_dev_mcp.api.budget import check_dispatch, current_budget

    entered, release, sent, cancellation = Event(), Event(), Event(), Event()
    responses, barriers = [], []

    def blocked_handler(**kwargs):
        budget = current_budget.get()
        budget.phase = "delete" if not readonly else "dependencies"
        budget.read_progress = {"completed_read_count": 1, "remaining_read_count": 2,
                                "remaining_count_kind": "known; undiscovered dependencies may add reads"}
        check_dispatch(readonly=readonly)
        entered.set()
        assert release.wait(2)
        try:
            check_dispatch(readonly=False)
        except DataLensApiError as exc:
            barriers.append(exc.remote_code)
        return {"ok": True, "late_result": True}

    monkeypatch.setitem(server.TOOLS, name, blocked_handler)
    args = {"budget_sec": 0.2, "candidates": [], "preserve_roots": []} if name.endswith("preview") else {
        "budget_sec": 0.2, "preview": {"operation_id": "synthetic-cleanup"}, "confirmed_delete": [],
    }
    request = {"id": 17, "method": "tools/call", "params": {"name": name, "arguments": args}}

    def emit(response):
        responses.append(response)
        sent.set()

    worker = Thread(target=server._run_domain_request, args=(request, cancellation, emit))
    worker.start()
    try:
        assert entered.wait(1)
        if cancelled:
            cancellation.set()
        assert server.handle_request({"id": 18, "method": "ping"})["result"] == {}
        assert sent.wait(1)
        assert worker.is_alive()  # Still owns the SDK until the call unwinds.
        result = responses[0]["result"]["structuredContent"]
        assert result["complete"] is False and result["worker_active"] is True
        assert result["status"] == ("operation_cancelled" if cancelled else "operation_budget_exhausted")
        assert result["progress"]["provider_calls"] == 1
        assert result["progress"]["remaining_read_count"] == 2
        if name.endswith("apply"):
            assert result["operation_id"] == "synthetic-cleanup"
            assert result["effect_outcome"] == "unknown"
            assert result["new_provider_effects_admitted"] is (not readonly)
        else:
            assert "effect_outcome" not in result
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert len(responses) == 1  # Late completion never emits a second response.
    assert barriers == ["operation_cancelled" if cancelled else "operation_budget_exhausted"]


def test_cleanup_invalid_budget_rejects_before_deadline_thread(monkeypatch):
    from threading import Event

    def forbidden_timer(*args, **kwargs):
        raise AssertionError("invalid input must not start a timer")

    monkeypatch.setattr(server, "Timer", forbidden_timer)
    responses = []
    server._run_domain_request({"id": 19, "method": "tools/call", "params": {
        "name": "dl_cleanup_preview", "arguments": {"budget_sec": -1, "candidates": [], "preserve_roots": []},
    }}, Event(), responses.append)
    assert responses[0]["result"]["structuredContent"]["status"] == "input_error"


def test_packaged_provenance_validates_content_and_sdk(tmp_path):
    from datalens_dev_mcp.runtime_identity import _load_provenance
    payload = {"format": 1, "source_commit": "a" * 40, "source_tree": "b" * 40,
               "commit_status": "clean", "package_version": server.__version__, "sdk_pin": "3.2.0",
               "package_content_sha256": "c" * 64, "schema_sha256": "d" * 64,
               "assets_sha256": "e" * 64, "skills_sha256": "f" * 64}
    path = tmp_path / "_build_provenance.json"
    assert _load_provenance(path, "c" * 64)["commit_status"] == "unknown"
    path.write_text(json.dumps(payload))
    assert _load_provenance(path, "c" * 64)["source_commit"] == "a" * 40
    assert _load_provenance(path, "0" * 64)["commit_status"] == "mismatch"
    payload["sdk_pin"] = "0.0.0"
    path.write_text(json.dumps(payload))
    assert _load_provenance(path, "c" * 64)["commit_status"] == "mismatch"
    path.write_text('{bad')
    assert _load_provenance(path, "c" * 64)["commit_status"] == "invalid"


def test_provenance_digest_covers_assets_and_external_skills(tmp_path):
    from datalens_dev_mcp.provenance import content_digest
    (tmp_path / "renderer.js").write_text("const value = 1;")
    before = content_digest(tmp_path)
    (tmp_path / "renderer.js").write_text("const value = 2;")
    assert content_digest(tmp_path) != before
    before = content_digest(tmp_path)
    (tmp_path / "SKILL.md").write_text("Synthetic skill")
    assert content_digest(tmp_path) != before
    before = content_digest(tmp_path)
    (tmp_path / "_build_provenance.json").write_text("{}")
    assert content_digest(tmp_path) == before


@pytest.mark.parametrize("name,args", [
    ("dl_object_create", {"drafts": [{"object_type": "dashboard", "name": "Synthetic", "client_ref": "d",
                                      "dashboard": {"tabs": []}}], "destination": {"workbook_id": "synthetic"}}),
    ("dl_object_update", {"changes": [{"object_type": "dashboard", "object_id": "synthetic",
                                      "expected_revision": "r1", "patch": {"name": "New"}}]}),
    ("dl_object_publish", {"targets": [{"object_type": "dashboard", "object_id": "synthetic",
                                      "expected_saved_revision": "r1"}]}),
])
def test_mutation_response_deadline_blocks_later_dispatch(monkeypatch, tmp_path, name, args):
    from threading import Event, Thread

    from datalens_dev_mcp.api.budget import check_dispatch
    monkeypatch.setenv("DATALENS_OPERATION_BUDGET_SEC", "0.1")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    entered, release, sent = Event(), Event(), Event()
    responses, errors = [], []
    def handler(**kwargs):
        check_dispatch(readonly=False)
        entered.set()
        release.wait(2)
        try:
            check_dispatch(readonly=False)
        except DataLensApiError as exc:
            errors.append(exc.remote_code)
        return {"ok": True}
    monkeypatch.setitem(server.TOOLS, name, handler)
    def emit(response):
        responses.append(response)
        sent.set()
    worker = Thread(target=server._run_domain_request, args=(
        {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}, Event(), emit))
    worker.start()
    try:
        assert entered.wait(1)
        assert sent.wait(0.5)
        assert worker.is_alive()
        result = responses[0]["result"]["structuredContent"]
        assert result["operation_id"]
        assert result["effect_outcome"] == "unknown"
    finally:
        release.set()
        worker.join(3)
    assert len(responses) == 1
    assert errors == ["operation_budget_exhausted"]


def test_stdio_busy_keeps_control_available_without_dispatch(monkeypatch):
    import io
    from threading import Event
    entered, release = Event(), Event()
    calls = []
    def slow(**kwargs):
        calls.append(kwargs)
        entered.set()
        assert release.wait(2)
        return {"ok": True}
    monkeypatch.setitem(server.TOOLS, "dl_object_get", slow)
    def request(oid, name):
        args = {"object_type": "dashboard", "object_id": "synthetic"} if name == "dl_object_get" else {}
        return json.dumps({"id": oid, "method": "tools/call", "params": {"name": name, "arguments": args}}) + "\n"
    def input_lines():
        yield request(1, "dl_object_get")
        assert entered.wait(1)
        yield request(2, "dl_object_get")
        yield request(3, "dl_server_info")
        release.set()
    output = io.StringIO()
    monkeypatch.setattr(server.sys, "stdin", input_lines())
    monkeypatch.setattr(server.sys, "stdout", output)
    server.serve_stdio()
    replies = {value["id"]: value for value in map(json.loads, output.getvalue().splitlines())}
    busy = replies[2]["error"]["data"]
    assert busy["code"] == "domain_busy" and busy["request_sent"] is False
    assert busy["worker_active"] is True and busy["active_request_id"] == 1
    assert replies[3]["result"]["structuredContent"]["domain"]["available"] is False
    assert len(calls) == 1


def test_build_stamp_binds_checkout_and_survives_source_archive(tmp_path, monkeypatch):
    from datalens_dev_mcp.provenance import build_provenance, content_digest
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    value = build_provenance(root)
    assert value["source_commit"] == subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).strip()
    assert value["commit_status"] == ("dirty" if dirty else "clean")
    package = tmp_path / "src/datalens_dev_mcp"
    package.mkdir(parents=True)
    (package / "module.py").write_text("value = 1")
    value["package_content_sha256"] = content_digest(package)
    (package / "_build_provenance.json").write_text(json.dumps(value))
    assert build_provenance(tmp_path) == value
    (package / "module.py").write_text("value = 2")
    with pytest.raises(ValueError, match="does not match"):
        build_provenance(tmp_path)
