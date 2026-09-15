from __future__ import annotations

from collections.abc import Mapping

import pytest

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
from datalens_dev_mcp.api.schemas import OperationRegistry
from datalens_dev_mcp.api.sdk_adapter import SDK_VERSION, SdkAdapter
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.server import call_tool, list_tools


class SequenceTransport:
    def __init__(self, outcomes: list[dict | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, dict, dict[str, str]]] = []

    def call(self, method: str, payload: dict, headers: Mapping[str, str]) -> dict:
        self.calls.append((method, dict(payload), dict(headers)))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return dict(outcome)


def _config() -> DataLensConfig:
    return DataLensConfig(
        base_url="https://api.datalens.test",
        org_id="synthetic-org",
        iam_token="synthetic-token",
        read_retries=1,
    )


def test_config_report_never_contains_credentials() -> None:
    report = _config().credential_report()
    assert report == {
        "installation": "yacloud",
        "api_version": "3",
        "base_url": "https://api.datalens.test",
        "org_id_set": True,
        "credential_source": "explicit",
        "token_present": True,
        "refresh_available": False,
    }
    assert "synthetic-token" not in repr(report)
    assert "synthetic-token" not in repr(_config())


def test_read_retries_transient_failure_once() -> None:
    transport = SequenceTransport([TimeoutError("synthetic timeout"), {"entries": []}])
    client = DataLensApiClient(_config(), transport=transport)

    assert client.read("getWorkbooksList", {"pageSize": 10}) == {"entries": []}
    assert [call[0] for call in transport.calls] == ["getWorkbooksList", "getWorkbooksList"]


def test_read_uses_documented_api_version_per_method() -> None:
    transport = SequenceTransport([{"entries": []}, {"data": {"rows": []}}])
    client = DataLensApiClient(_config(), transport=transport)

    client.read("getWorkbooksList", {"pageSize": 10})
    client.read("getDatasetData", {"datasetId": "dataset-synthetic"})

    assert transport.calls[0][2]["x-dl-api-version"] == "3"
    assert transport.calls[1][2]["x-dl-api-version"] == "3"


def test_write_transport_failure_is_uncertain_and_never_replayed() -> None:
    transport = SequenceTransport([TimeoutError("synthetic timeout")])
    client = DataLensApiClient(_config(), transport=transport)

    with pytest.raises(UncertainWriteError) as error:
        client.write("updateDashboard", {"dashboardId": "dash-synthetic"})

    assert error.value.method == "updateDashboard"
    assert error.value.response_received is False
    assert len(transport.calls) == 1


def test_read_auth_refresh_has_one_owner_and_one_retry() -> None:
    transport = SequenceTransport(
        [DataLensApiError("unauthenticated", http_status=401, response_received=True), {"id": "wb-synthetic"}]
    )
    refreshes: list[str] = []

    def refresh() -> str:
        refreshes.append("once")
        return "refreshed-synthetic-token"

    client = DataLensApiClient(_config(), transport=transport, token_refresher=refresh)
    assert client.read("getWorkbook", {"workbookId": "wb-synthetic"}) == {"id": "wb-synthetic"}
    assert refreshes == ["once"]
    assert transport.calls[1][2]["authorization"] == "Bearer refreshed-synthetic-token"


def test_operation_registry_records_real_sdk_coverage() -> None:
    registry = OperationRegistry.load()
    assert SDK_VERSION == "3.0.0"
    assert registry.get("createWizardChart")["backend"] == "official_sdk"
    assert registry.get("createEditorChart")["backend"] == "official_sdk"
    assert registry.get("createDashboard")["backend"] == "official_sdk"
    assert registry.get("getDatasetData")["backend"] == "public_api_adapter"
    assert registry.get("getDatasetData")["api_version"] == "3"
    assert registry.get("updateDashboard")["backend"] == "official_sdk"


def test_sdk_adapter_exposes_versioned_factories_without_executing_them() -> None:
    adapter = SdkAdapter()
    assert adapter.describe_factory("wizard", "flat_table") == {
        "sdk_version": "3.0.0",
        "resource": "wizard",
        "variant": "flat_table",
        "supported": True,
        "effect": "mutation_on_build",
    }
    assert adapter.describe_factory("editor", "table")["supported"] is True
    assert adapter.describe_factory("editor", "unknown")["supported"] is False


def test_l02_tools_expose_auth_and_versioned_schema_without_generic_rpc() -> None:
    names = {item["name"] for item in list_tools()}
    assert {"dl_auth_check", "dl_auth_refresh", "dl_method_schema"} <= names
    assert "dl_rpc_expert" not in names
    result = call_tool("dl_method_schema", {"method": "createWizardChart"})["structuredContent"]
    assert result["operation"]["backend"] == "official_sdk"
    assert result["operation"]["verified"] == "sdk_3.0.0"


def test_create_tool_describes_nested_typed_dataset_contract() -> None:
    create_tool = next(item for item in list_tools() if item["name"] == "dl_object_create")

    assert "dataset.connection_id/source/fields" in create_tool["description"]
    assert "top-level object_type/name/client_ref" in create_tool["description"]


@pytest.mark.parametrize("body,code", [(b"x" * 1025, "response_too_large"), (b"<html>private login</html>", "invalid_json"),
                                      (b"\xff", "invalid_json"), (b"[]", "invalid_response")])
def test_http_response_is_bounded_closed_and_not_echoed(monkeypatch, body, code):
    from io import BytesIO

    from datalens_dev_mcp.api.client import HttpJsonTransport

    response = BytesIO(body)
    monkeypatch.setattr("datalens_dev_mcp.api.client.request.urlopen", lambda *a, **k: response)
    with pytest.raises(DataLensApiError) as caught:
        HttpJsonTransport("https://example.invalid", max_response_bytes=1024).call("getDataset", {}, {})
    assert response.closed
    assert caught.value.remote_code == code
    assert "private login" not in str(caught.value)


def test_http_error_body_is_not_read_and_retry_after_is_bounded(monkeypatch):
    from io import BytesIO
    from urllib.error import HTTPError

    from datalens_dev_mcp.api.client import HttpJsonTransport

    class UnreadBody(BytesIO):
        def read(self, *args):
            raise AssertionError("error body must not be read")

    body = UnreadBody(b"private" * 1000)
    failure = HTTPError("https://example.invalid", 429, "private", {"Retry-After": "120"}, body)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("datalens_dev_mcp.api.client.request.urlopen", fail)
    client = DataLensApiClient(_config(), transport=HttpJsonTransport("https://example.invalid"))
    with pytest.raises(DataLensApiError) as caught:
        client.read("getWorkbooksList")
    assert body.closed and caught.value.retry_after_sec == 120
    assert "private" not in str(caught.value)


def test_safe_read_backoff_and_budget_do_not_retry_local_os_errors(monkeypatch):
    delays = []
    monkeypatch.setattr("datalens_dev_mcp.api.client.time.sleep", delays.append)
    transport = SequenceTransport([DataLensApiError("busy", http_status=429, retry_after_sec=1), {"workbooks": []}])
    assert DataLensApiClient(_config(), transport=transport).read("getWorkbooksList") == {"workbooks": []}
    assert delays == [1]
    transport = SequenceTransport([PermissionError("local permission")])
    with pytest.raises(PermissionError):
        DataLensApiClient(_config(), transport=transport).read("getWorkbooksList")
    assert len(transport.calls) == 1
