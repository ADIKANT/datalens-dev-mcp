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

    assert transport.calls[0][2]["x-dl-api-version"] == "1"
    assert transport.calls[1][2]["x-dl-api-version"] == "2"


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
    assert SDK_VERSION == "0.9.0"
    assert registry.get("createWizardChart")["backend"] == "official_sdk"
    assert registry.get("createEditorChart")["backend"] == "official_sdk"
    assert registry.get("createDashboard")["backend"] == "official_sdk"
    assert registry.get("getDatasetData")["backend"] == "public_api_adapter"
    assert registry.get("getDatasetData")["api_version"] == "2"
    assert registry.get("publishDashboard")["readback_required"] is True


def test_sdk_adapter_exposes_versioned_factories_without_executing_them() -> None:
    adapter = SdkAdapter()
    assert adapter.describe_factory("wizard", "flat_table") == {
        "sdk_version": "0.9.0",
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
    assert result["operation"]["verified"] == "sdk_0.9.0"


def test_create_tool_describes_nested_typed_dataset_contract() -> None:
    create_tool = next(item for item in list_tools() if item["name"] == "dl_object_create")

    assert "dataset.connection_id/source/fields" in create_tool["description"]
    assert "top-level object_type/name/client_ref" in create_tool["description"]
