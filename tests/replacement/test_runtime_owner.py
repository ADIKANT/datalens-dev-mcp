from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace

import datalens_sdk
import pytest
from datalens_sdk.errors import APIErrorContext, UnauthorizedError

from datalens_dev_mcp import server
from datalens_dev_mcp.api import auth as auth_module
from datalens_dev_mcp.api import runtime as runtime_module
from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.api.runtime import DataLensRuntime, RuntimeRegistry
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.objects.write import default_mutation_service


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


def _config(*, org_id: str = "synthetic-org", token: str = "expired-synthetic") -> DataLensConfig:
    return DataLensConfig(
        base_url="https://api.datalens.test",
        org_id=org_id,
        iam_token=token,
        read_retries=0,
        refresh_available=True,
        _configured_token=token,
    )


def test_runtime_owner_refreshes_one_401_and_updates_api_and_sdk_credentials() -> None:
    transport = SequenceTransport(
        [DataLensApiError("unauthenticated", http_status=401, response_received=True), {"entries": []}]
    )
    refreshes: list[str] = []

    def refresh() -> str:
        refreshes.append("once")
        return "fresh-synthetic"

    runtime = DataLensRuntime(_config(), api_transport=transport, credential_refresher=refresh)

    assert runtime.api.read("getWorkbooksList", {"pageSize": 1}) == {"entries": []}
    assert refreshes == ["once"]
    assert len(transport.calls) == 2
    assert runtime.config.iam_token == "fresh-synthetic"
    assert runtime.api.config is runtime.config
    assert runtime.sdk.config is runtime.config


def test_explicit_refresh_control_read_cannot_trigger_a_second_refresh() -> None:
    transport = SequenceTransport([DataLensApiError("still unauthenticated", http_status=401, response_received=True)])
    refreshes: list[str] = []
    runtime = DataLensRuntime(
        _config(),
        api_transport=transport,
        credential_refresher=lambda: refreshes.append("once") or "fresh-synthetic",
    )

    try:
        runtime.refresh_and_probe()
    except DataLensApiError as exc:
        assert exc.http_status == 401
    else:
        raise AssertionError("the control read must expose a rejected refreshed credential")

    assert refreshes == ["once"]
    assert len(transport.calls) == 1


def test_runtime_registry_reuses_clients_but_isolates_orgs_and_configured_tokens() -> None:
    registry = RuntimeRegistry(max_entries=2)
    first = registry.get(_config())
    assert registry.get(_config()) is first

    other_org = registry.get(_config(org_id="other-synthetic-org"))
    other_token = registry.get(_config(token="other-expired-synthetic"))

    assert other_org is not first
    assert other_token is not first
    assert registry.size == 2
    assert registry.get(_config(org_id="other-synthetic-org")) is other_org


def test_refresh_enabled_runtime_can_bootstrap_a_missing_token_before_probe() -> None:
    transport = SequenceTransport([{"entries": []}])
    runtime = DataLensRuntime(
        _config(token=""),
        api_transport=transport,
        credential_refresher=lambda: "fresh-synthetic",
    )

    assert runtime.probe_auth() == {"entries": []}
    assert len(transport.calls) == 1
    assert runtime.config.iam_token == "fresh-synthetic"


def test_runtime_refresh_uses_configured_yc_binary(monkeypatch) -> None:
    seen: list[str] = []
    config = _config(token="")
    config = DataLensConfig(
        base_url=config.base_url,
        org_id=config.org_id,
        iam_token=config.iam_token,
        read_retries=config.read_retries,
        yc_binary="/synthetic/yc",
        refresh_available=True,
        _configured_token="",
    )
    monkeypatch.setattr(
        runtime_module,
        "refresh_iam_token_with_yc",
        lambda *, yc_binary: seen.append(yc_binary) or "fresh-synthetic",
    )
    runtime = DataLensRuntime(config, api_transport=SequenceTransport([{"entries": []}]))

    assert runtime.probe_auth() == {"entries": []}
    assert seen == ["/synthetic/yc"]


def test_yc_refresh_restores_system_paths_needed_by_desktop_processes(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="fresh-synthetic\n")

    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(auth_module.subprocess, "run", fake_run)

    assert refresh_iam_token_with_yc(yc_binary="/synthetic/bin/yc") == "fresh-synthetic"
    assert seen["command"] == [
        "/synthetic/bin/yc",
        "iam",
        "create-token",
        "--no-browser",
        "--no-user-output",
    ]
    assert str(seen["env"]["PATH"]).split(":") == [
        "/synthetic/bin",
        "/usr/bin",
        "/bin",
        "/usr/local/bin",
        "/usr/sbin",
        "/sbin",
    ]


def test_server_reads_and_auth_probe_use_the_same_runtime_clients(monkeypatch) -> None:
    runtime = DataLensRuntime(_config(), api_transport=SequenceTransport([{"entries": []}]))
    monkeypatch.setattr(server, "get_runtime", lambda: runtime)

    assert server.dl_auth_check()["status"] == "healthy"
    service = server._read_service()
    assert service.api is runtime.api
    assert service.sdk is runtime.sdk


def test_default_mutation_service_uses_one_runtime_for_reader_and_backend(monkeypatch) -> None:
    runtime = DataLensRuntime(_config())
    monkeypatch.setattr("datalens_dev_mcp.api.runtime.get_runtime", lambda: runtime)

    service = default_mutation_service()

    assert service.reader.api is runtime.api
    assert service.reader.sdk is runtime.sdk
    assert service.backend is runtime.sdk


def test_sdk_read_uses_the_same_single_refresh_owner(monkeypatch) -> None:
    class Get:
        def __init__(self, outcome):
            self.outcome = outcome

        def dataset(self, **kwargs):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    class Client:
        def __init__(self, outcome):
            self.get = Get(outcome)

        def close(self):
            return None

    unauthorized = UnauthorizedError(APIErrorContext(status_code=401, code="UNAUTHENTICATED", message="expired"))
    clients = iter([Client(unauthorized), Client({"id": "dataset-synthetic"})])
    monkeypatch.setattr(datalens_sdk, "DataLensClientYC", lambda **kwargs: next(clients))
    refreshes: list[str] = []
    runtime = DataLensRuntime(
        _config(),
        credential_refresher=lambda: refreshes.append("once") or "fresh-synthetic",
    )

    assert runtime.sdk.get_object("dataset", "dataset-synthetic") == {"id": "dataset-synthetic"}
    assert refreshes == ["once"]
    assert runtime.sdk.config is runtime.config


def test_sdk_read_does_not_loop_when_refreshed_credential_is_rejected(monkeypatch) -> None:
    class Get:
        def dataset(self, **kwargs):
            raise UnauthorizedError(APIErrorContext(status_code=401, code="UNAUTHENTICATED", message="still expired"))

    class Client:
        get = Get()

        def close(self):
            return None

    monkeypatch.setattr(datalens_sdk, "DataLensClientYC", lambda **kwargs: Client())
    refreshes: list[str] = []
    runtime = DataLensRuntime(
        _config(),
        credential_refresher=lambda: refreshes.append("once") or "fresh-synthetic",
    )

    with pytest.raises(DataLensApiError) as error:
        runtime.sdk.get_object("dataset", "dataset-synthetic")

    assert error.value.http_status == 401
    assert refreshes == ["once"]
