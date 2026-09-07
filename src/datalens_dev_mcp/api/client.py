from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any, Protocol
from urllib import error, request

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
from datalens_dev_mcp.config import DataLensConfig


class Transport(Protocol):
    def call(self, method: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]: ...


class HttpJsonTransport:
    def __init__(self, base_url: str, timeout_sec: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def call(self, method: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/rpc/{method}",
            data=body,
            headers=dict(headers),
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_sec) as response:
                raw = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise DataLensApiError(
                f"{method} failed with HTTP {exc.code}: {detail}",
                method=method,
                http_status=exc.code,
                response_received=True,
            ) from exc
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DataLensApiError(
                f"{method} returned a non-JSON response",
                method=method,
                response_received=True,
            ) from exc
        if not isinstance(result, dict):
            raise DataLensApiError(
                f"{method} returned a non-object response",
                method=method,
                response_received=True,
            )
        return result


class DataLensApiClient:
    def __init__(
        self,
        config: DataLensConfig,
        *,
        transport: Transport | None = None,
        token_refresher: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or HttpJsonTransport(config.base_url, config.request_timeout_sec)
        self.token_refresher = token_refresher

    def _headers(self) -> dict[str, str]:
        self.config.require_auth()
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.config.iam_token}",
            "x-dl-org-id": self.config.org_id,
            "x-dl-api-version": "1",
        }

    def read(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_auth_refresh: bool = True,
    ) -> dict[str, Any]:
        auth_refreshed = False
        transient_attempts = 0
        while True:
            try:
                return self.transport.call(method, dict(payload or {}), self._headers())
            except DataLensApiError as exc:
                if (
                    exc.http_status == 401
                    and allow_auth_refresh
                    and not auth_refreshed
                    and self.token_refresher is not None
                ):
                    token = self.token_refresher().strip()
                    if not token:
                        raise DataLensApiError("DataLens token refresh returned no credential", method=method) from exc
                    if self.config.iam_token != token:
                        self.config = replace(self.config, iam_token=token, credential_source="refreshed")
                    auth_refreshed = True
                    continue
                if exc.http_status in {429, 500, 502, 503, 504} and transient_attempts < self.config.read_retries:
                    transient_attempts += 1
                    continue
                raise
            except (TimeoutError, ConnectionError, OSError) as exc:
                if transient_attempts < self.config.read_retries:
                    transient_attempts += 1
                    continue
                raise DataLensApiError(
                    f"{method} failed before an HTTP response",
                    method=method,
                    response_received=False,
                ) from exc

    def write(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self.transport.call(method, dict(payload or {}), self._headers())
        except DataLensApiError:
            raise
        except (TimeoutError, ConnectionError, OSError) as exc:
            raise UncertainWriteError(
                f"{method} outcome is uncertain; reconcile before retrying",
                method=method,
                response_received=False,
            ) from exc

    def rpc_readonly(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.read(method, payload)

    def rpc(self, method: str, payload: dict[str, Any] | None = None, *, readonly: bool = False) -> dict[str, Any]:
        return self.read(method, payload) if readonly else self.write(method, payload)
