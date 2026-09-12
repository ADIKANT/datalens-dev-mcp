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
