from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from urllib import error, request

from datalens_dev_mcp.api.budget import check_dispatch, current_budget
from datalens_dev_mcp.api.errors import DataLensApiError, InputContractError, UncertainWriteError, response_diagnostics
from datalens_dev_mcp.api.schemas import OperationRegistry
from datalens_dev_mcp.config import DataLensConfig


class Transport(Protocol):
    def call(self, method: str, payload: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]: ...


def _retry_after(value: str | None) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"[0-9]+", value):
            seconds = float(value)
        else:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
    except (ValueError, TypeError, OverflowError):
        return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


class HttpJsonTransport:
    def __init__(self, base_url: str, timeout_sec: float = 30.0, *, max_response_bytes: int = 32 * 1024 * 1024) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.max_response_bytes = max_response_bytes

    def call(self, method: str, payload: dict[str, Any], headers: Mapping[str, str],
             *, deadline: float | None = None) -> dict[str, Any]:
        try:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            req = request.Request(f"{self.base_url}/rpc/{method}", data=body, headers=dict(headers), method="POST")
        except (ValueError, TypeError, UnicodeError) as exc:
            raise InputContractError("Request could not be encoded before dispatch") from exc
        deadline = deadline if deadline is not None else time.monotonic() + self.timeout_sec
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DataLensApiError("Read budget expired before dispatch", method=method,
                                   remote_code="read_budget_exhausted", dispatch_state="not_dispatched")
        response_received, http_status = None, None
        diagnostics = {"request_id": None, "trace_id": None}
        try:
            try:
                readonly = OperationRegistry.load().get(method)["effect"] == "read"
            except KeyError:
                readonly = False
            operation_remaining = check_dispatch(readonly=readonly)
            if operation_remaining is not None:
                remaining = min(remaining, operation_remaining)
                deadline = min(deadline, time.monotonic() + operation_remaining)
            with request.urlopen(req, timeout=min(self.timeout_sec, remaining)) as response:
                response_received, http_status = True, getattr(response, "status", None)
                diagnostics = response_diagnostics(getattr(response, "headers", None))
                chunks = []
                size = 0
                read = getattr(response, "read1", response.read)
                while True:
                    budget = current_budget.get()
                    if budget is not None:
                        try:
                            budget.check()
                        except DataLensApiError as exc:
                            # This request already crossed dispatch, even if cancellation
                            # prevents consuming its response. A write remains unknown.
                            exc.dispatch_state = "dispatched"
                            exc.response_received = True
                            exc.http_status = getattr(response, "status", None)
                            exc.stage = "response_read"
                            exc.method = method
                            exc.request_id = diagnostics["request_id"]
                            exc.trace_id = diagnostics["trace_id"]
                            raise
                    if time.monotonic() >= deadline:
                        raise DataLensApiError("Response read budget expired", method=method,
                                               remote_code="read_budget_exhausted", response_received=True,
                                               stage="response_read", **diagnostics)
                    chunk = read(min(65536, self.max_response_bytes + 1 - size))
                    size += len(chunk)
                    if size > self.max_response_bytes:
                        raise DataLensApiError(f"{method} response exceeds {self.max_response_bytes} bytes; no state returned",
                                               method=method, remote_code="response_too_large", response_received=True,
                                               stage="response_read", **diagnostics)
                    if not chunk:
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks)
        except error.HTTPError as exc:
            # Keep only allowlisted correlation metadata; never buffer an error/login body.
            retry_after = _retry_after(exc.headers.get("Retry-After") if exc.headers else None)
            diagnostics = response_diagnostics(exc.headers)
            exc.close()
            raise DataLensApiError(f"{method} failed with HTTP {exc.code}", method=method, http_status=exc.code,
                                   response_received=True, retry_after_sec=retry_after,
                                   stage="provider_response", **diagnostics) from exc
        except (TimeoutError, ConnectionError, error.URLError) as exc:
            budget = current_budget.get()
            if budget is not None:
                try:
                    budget.check()
                except DataLensApiError as stopped:
                    # A timeout caused by the operation deadline is still a
                    # dispatched request, not a fresh read to retry.
                    raise DataLensApiError(str(stopped), method=method, remote_code=stopped.remote_code,
                                           dispatch_state="dispatched", response_received=response_received,
                                           http_status=http_status,
                                           stage="response_read" if response_received else "transport",
                                           **diagnostics) from exc
            raise
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise DataLensApiError(f"{method} returned invalid JSON", method=method, remote_code="invalid_json",
                                   response_received=True, stage="response_decode", **diagnostics) from exc
        if not isinstance(result, dict):
            raise DataLensApiError(f"{method} returned a non-object response", method=method,
                                   remote_code="invalid_response", response_received=True,
                                   stage="response_validation", **diagnostics)
        return result


class DataLensApiClient:
    def __init__(self, config: DataLensConfig, *, transport: Transport | None = None,
                 token_refresher: Callable[[], str] | None = None) -> None:
        self.config = config
        self.transport = transport or HttpJsonTransport(config.base_url, config.request_timeout_sec,
                                                        max_response_bytes=config.max_response_bytes)
        self.token_refresher = token_refresher
        self.operation_registry = OperationRegistry.load()

    def _headers(self, method: str) -> dict[str, str]:
        self.config.require_auth()
        try:
            api_version = str(self.operation_registry.get(method).get("api_version", "3"))
        except KeyError:
            api_version = "3"
        headers = {"accept": "application/json", "content-type": "application/json",
                   "authorization": f"Bearer {self.config.iam_token}", "x-dl-api-version": api_version}
        if self.config.installation == "yacloud":
            headers["x-dl-org-id"] = self.config.org_id
        return headers

    def read(self, method: str, payload: dict[str, Any] | None = None, *, allow_auth_refresh: bool = True) -> dict[str, Any]:
        auth_refreshed = False
        transient_attempts = 0
        deadline = time.monotonic() + self.config.read_budget_sec
        budget = current_budget.get()
        if budget is not None:
            deadline = min(deadline, budget.deadline)
        while True:
            if budget is not None:
                budget.check()
            if time.monotonic() >= deadline:
                raise DataLensApiError(f"{method} exhausted its safe read budget", method=method,
                                       remote_code="read_budget_exhausted")
            try:
                headers = self._headers(method)
                if isinstance(self.transport, HttpJsonTransport):
                    return self.transport.call(method, dict(payload or {}), headers, deadline=deadline)
                return self.transport.call(method, dict(payload or {}), headers)
            except DataLensApiError as exc:
                if (exc.http_status == 401 and allow_auth_refresh and not auth_refreshed
                        and self.token_refresher is not None):
                    token = self.token_refresher().strip()
                    if not token:
                        raise DataLensApiError("DataLens token refresh returned no credential", method=method) from exc
                    if self.config.iam_token != token:
                        self.config = replace(self.config, iam_token=token, credential_source="refreshed")
                    auth_refreshed = True
                    continue
                if exc.http_status not in {429, 500, 502, 503, 504}:
                    raise
                failure = exc
            except (TimeoutError, ConnectionError, error.URLError) as exc:
                failure = DataLensApiError(f"{method} failed before an HTTP response", method=method,
                                           response_received=False, stage="transport")
                failure.__cause__ = exc
            if transient_attempts >= self.config.read_retries:
                raise failure
            delay = max(min(0.25 * 2 ** transient_attempts, 2.0), failure.retry_after_sec or 0.0)
            # Do not shorten a provider's Retry-After or wait indefinitely.
            if delay > 5.0 or delay >= deadline - time.monotonic():
                raise failure
            time.sleep(delay)
            transient_attempts += 1

    def write(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            request_payload = dict(payload or {})
            headers = self._headers(method)
        except DataLensApiError as exc:
            exc.dispatch_state = "not_dispatched"
            raise
        except (ValueError, TypeError) as exc:
            raise InputContractError("Invalid request before dispatch") from exc
        try:
            return self.transport.call(method, request_payload, headers)
        except (DataLensApiError, InputContractError):
            raise
        except (TimeoutError, ConnectionError, OSError, ValueError, TypeError) as exc:
            raise UncertainWriteError(f"{method} outcome is unknown; preserve the operation and do not replay",
                                       method=method, response_received=False, stage="transport") from exc

    def rpc_readonly(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.read(method, payload)

    def rpc(self, method: str, payload: dict[str, Any] | None = None, *, readonly: bool = False) -> dict[str, Any]:
        return self.read(method, payload) if readonly else self.write(method, payload)
