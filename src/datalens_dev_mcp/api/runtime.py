from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
from datalens_dev_mcp.api.client import DataLensApiClient, Transport
from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
from datalens_dev_mcp.config import DataLensConfig


class DataLensRuntime:
    """Own one coherent credential, API client, and SDK client set."""

    def __init__(
        self,
        config: DataLensConfig,
        *,
        api_transport: Transport | None = None,
        sdk_client: Any | None = None,
        credential_refresher: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self._credential_refresher = credential_refresher or (
            lambda: refresh_iam_token_with_yc(yc_binary=config.yc_binary)
        )
        token_refresher = self._refresh_credentials if config.refresh_available else None
        self.api = DataLensApiClient(config, transport=api_transport, token_refresher=token_refresher)
        self.sdk = SdkAdapter(config, client=sdk_client, token_refresher=token_refresher)

    def _refresh_credentials(self) -> str:
        token = self._credential_refresher().strip()
        self.config.remember_refreshed_token(token)
        self.config = replace(self.config, iam_token=token, credential_source="runtime_refresh")
        self.api.config = self.config
        self.sdk.replace_config(self.config)
        return token

    def probe_auth(self) -> dict[str, Any]:
        if not self.config.iam_token and self.config.refresh_available:
            self._refresh_credentials()
        return self.api.read("getWorkbooksList", {"pageSize": 1})

    def refresh_and_probe(self) -> dict[str, Any]:
        self._refresh_credentials()
        return self.api.read("getWorkbooksList", {"pageSize": 1}, allow_auth_refresh=False)

    def close(self) -> None:
        self.sdk.close()


class RuntimeRegistry:
    """Bounded process-local runtimes, isolated by credential and API identity."""

    def __init__(self, *, max_entries: int = 8) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[object, ...], DataLensRuntime] = OrderedDict()

    @property
    def size(self) -> int:
        return len(self._entries)

    def get(self, config: DataLensConfig) -> DataLensRuntime:
        key = config.runtime_identity()
        runtime = self._entries.get(key)
        if runtime is not None:
            self._entries.move_to_end(key)
            return runtime
        runtime = DataLensRuntime(config)
        self._entries[key] = runtime
        if len(self._entries) > self._max_entries:
            _, evicted = self._entries.popitem(last=False)
            evicted.close()
        return runtime

    def clear(self) -> None:
        for runtime in self._entries.values():
            runtime.close()
        self._entries.clear()


_RUNTIMES = RuntimeRegistry()


def get_runtime(config: DataLensConfig | None = None) -> DataLensRuntime:
    return _RUNTIMES.get(config or DataLensConfig.from_env())
