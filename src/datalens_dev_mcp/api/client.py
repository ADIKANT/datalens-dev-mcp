from __future__ import annotations

import json
import os
import random
import socket
import ssl
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from threading import RLock
from typing import Any, Protocol
from urllib import error, request

from datalens_dev_mcp.api.auth import is_auth_failure, is_missing_credentials, refresh_iam_token_with_yc
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.api.scheduler import REQUEST_SCHEDULER, TOKEN_REFRESH_COORDINATOR
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.pipeline.failure_classifier import classify_failure
from datalens_dev_mcp.pipeline.retry_controller import retry_decision
from datalens_dev_mcp.validators.redaction import redact_text, sanitize_value

COMPACT_READ_FALSE_KEYS = {
    "includeFavorite",
    "includeLinks",
    "includePermissions",
    "includePermissionsInfo",
}
PROTECTED_PAYLOAD_KEYS = {"entry", "data"}


class Transport(Protocol):
    def post_json(self, url: str, body: bytes, headers: dict[str, str]) -> bytes: ...


class UrlLibTransport:
    def __init__(self, timeout_sec: float = 30.0) -> None:
        self.timeout_sec = float(timeout_sec)
        if self.timeout_sec <= 0:
            raise ValueError("request timeout must be greater than zero")

    def post_json(self, url: str, body: bytes, headers: dict[str, str]) -> bytes:
        req = request.Request(url, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=self.timeout_sec) as response:
            return response.read()


@dataclass(frozen=True)
class SanitizedHttpError:
    status: int
    detail: str


def compact_rpc_payload(value: Any, *, method: str = "", parent_key: str | None = None) -> Any:
    preserve_empty_values = _preserve_empty_rpc_values(method)
    if parent_key in PROTECTED_PAYLOAD_KEYS:
        return value
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
        return value if preserve_empty_values else None
    if isinstance(value, bool):
        if value is False and _compact_optional_read_false(method, parent_key):
            return None
        return value
    if isinstance(value, list):
        items = [compact_rpc_payload(item, method=method, parent_key=parent_key) for item in value]
        compacted = [item for item in items if item is not None]
        if compacted:
            return compacted
        return [] if preserve_empty_values else None
    if isinstance(value, dict):
        compacted: dict[str, Any] = {}
        for key, item in value.items():
            compacted_item = compact_rpc_payload(item, method=method, parent_key=key)
            if compacted_item is not None:
                compacted[key] = compacted_item
        if compacted:
            return compacted
        return {} if preserve_empty_values else None
    return value


def compact_payload_keys(value: Any) -> list[str]:
    return sorted(value.keys()) if isinstance(value, dict) else []


def _preserve_empty_rpc_values(method: str) -> bool:
    from datalens_dev_mcp.api.methods import is_write_method

    return is_write_method(method)


def _compact_optional_read_false(method: str, parent_key: str | None) -> bool:
    if parent_key not in COMPACT_READ_FALSE_KEYS:
        return False
    if not method:
        return False
    from datalens_dev_mcp.api.methods import is_readonly_method

    return is_readonly_method(method)


def _sanitize_json_value(value: Any) -> Any:
    return sanitize_value(value)


def short_error_detail(raw: str) -> str:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return redact_text(raw)[:600]
    details = []
    sanitized = _sanitize_json_value(parsed)
    for key in ("code", "message", "details", "error", "description"):
        if key in sanitized:
            details.append(f"{key}={sanitized[key]!r}")
    return "; ".join(details) if details else json.dumps(sanitized, ensure_ascii=False)[:600]


def remote_error_code(raw: str) -> str:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    for key in ("code", "errorCode", "error_code", "status"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    nested = parsed.get("error")
    if isinstance(nested, dict):
        for key in ("code", "errorCode", "error_code"):
            value = nested.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
    return ""


def is_validation_error(raw: str) -> bool:
    if "VALIDATION_ERROR" in raw:
        return True
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return any(str(value).upper() == "VALIDATION_ERROR" for value in parsed.values())


class DataLensApiClient:
    def __init__(
        self,
        config: DataLensConfig,
        *,
        transport: Transport | None = None,
        token_refresher: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UrlLibTransport(config.request_timeout_sec)
        self.token_refresher = token_refresher
        self._state_lock = RLock()

    def headers(self) -> dict[str, str]:
        with self._state_lock:
            config = self.config
        config.require_auth()
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "x-dl-api-version": _compiled_api_version(),
            "x-dl-org-id": config.org_id,
            "Authorization": f"Bearer {config.iam_token}",
        }

    def rpc(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        exclusive: bool = False,
    ) -> dict[str, Any]:
        self._reload_canonical_env_file("reloaded_before_rpc", require_token=False)
        self._bootstrap_missing_token()
        compacted_payload = compact_rpc_payload(payload or {}, method=method) or {}
        readonly = _is_readonly_method(method)
        try:
            return self._rpc_once(
                method,
                compacted_payload,
                exclusive=exclusive,
            )
        except Exception as first_exc:
            if is_missing_credentials(first_exc):
                raise
            if not is_auth_failure(first_exc):
                raise
            classified = classify_failure(first_exc, operation=method, readonly=readonly)
            probe = self._minimal_auth_probe()
            decision = retry_decision(
                classified.family,
                readonly=readonly,
                auth_probe=str(probe.get("status") or "other_failure"),
            )
            if decision.refresh_token and self._can_refresh_token():
                try:
                    refreshed = self._refresh_token_once()
                    if refreshed:
                        self.persist_refreshed_token(refreshed)
                        self._reload_canonical_env_file("reloaded_after_refresh")
                        if decision.retry:
                            try:
                                return self._rpc_once(
                                    method,
                                    compacted_payload,
                                    exclusive=exclusive,
                                )
                            except Exception as retry_exc:
                                if is_auth_failure(retry_exc):
                                    raise DataLensApiError(
                                        f"{method} auth_retry_failed_after_refresh",
                                        failure_family="AUTH_401_TOKEN_INVALID_OR_EXPIRED",
                                    ) from retry_exc
                                raise
                        raise DataLensApiError(
                            f"{method} was not replayed after token refresh because it is not a safe read",
                            failure_family="AUTH_401_TOKEN_INVALID_OR_EXPIRED",
                        ) from first_exc
                except Exception as refresh_exc:
                    if isinstance(refresh_exc, DataLensApiError) and (
                        "auth_retry_failed_after_refresh" in str(refresh_exc)
                        or "was not replayed after token refresh" in str(refresh_exc)
                    ):
                        raise
                    raise DataLensApiError(
                        f"{method} failed with auth_invalid_or_expired; token_refresh_failed",
                        failure_family="AUTH_401_TOKEN_INVALID_OR_EXPIRED",
                    ) from refresh_exc
            raise DataLensApiError(
                f"{method} failed with auth_invalid_or_expired; recovery_action={decision.action}; "
                f"probe_status={probe.get('status', 'other_failure')}",
                failure_family="AUTH_401_TOKEN_INVALID_OR_EXPIRED",
            ) from first_exc

    def _rpc_once(
        self,
        method: str,
        compacted_payload: dict[str, Any],
        *,
        exclusive: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/rpc/{method}"
        body = json.dumps(compacted_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        rate_limit_attempts = 0
        transient_attempts = 0
        readonly = _is_readonly_method(method)
        if self.config.request_debug:
            self._log_request_debug(method, url, compacted_payload)
        while True:
            try:
                raw = self._post_json(
                    method,
                    url,
                    body,
                    exclusive=exclusive,
                )
            except error.HTTPError as exc:
                raw_text = exc.read().decode("utf-8", errors="replace")
                error_details = {
                    "http_status": int(exc.code),
                    "remote_code": remote_error_code(raw_text),
                    "request_phase": "response",
                    "response_received": True,
                }
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    backoff = _retry_after_seconds(
                        retry_after,
                        fallback=min(2**rate_limit_attempts, 10),
                    )
                    REQUEST_SCHEDULER.note_rate_limit(
                        key=self._scheduler_key(),
                        method=method,
                        retry_after_sec=backoff,
                    )
                    if readonly and rate_limit_attempts < self.config.rate_limit_retries:
                        rate_limit_attempts += 1
                        continue
                if (
                    readonly
                    and exc.code in {500, 502, 503, 504}
                    and transient_attempts < self.config.read_transient_retries
                ):
                    transient_attempts += 1
                    REQUEST_SCHEDULER.note_transient_retry(key=self._scheduler_key(), method=method)
                    _transient_retry_pause(transient_attempts)
                    continue
                if exc.code == 401:
                    raise DataLensApiError(
                        f"{method} failed with HTTP 401: auth_invalid_or_expired; "
                        f"compacted_payload_keys={compact_payload_keys(compacted_payload)}; "
                        f"detail={short_error_detail(raw_text)}",
                        **error_details,
                        failure_family="AUTH_401_TOKEN_INVALID_OR_EXPIRED",
                    ) from exc
                if exc.code == 400 and is_validation_error(raw_text):
                    raise DataLensApiError(
                        f"{method} failed with HTTP 400 VALIDATION_ERROR: {short_error_detail(raw_text)}; "
                        f"compacted_payload_keys={compact_payload_keys(compacted_payload)}",
                        remote_code=error_details["remote_code"] or "VALIDATION_ERROR",
                        http_status=400,
                        request_phase="response",
                        response_received=True,
                    ) from exc
                raise DataLensApiError(
                    f"{method} failed with HTTP {exc.code}: {short_error_detail(raw_text)}; "
                    f"compacted_payload_keys={compact_payload_keys(compacted_payload)}",
                    **error_details,
                    failure_family=(
                        "AUTH_403_PERMISSION_DENIED"
                        if exc.code == 403
                        else "NOT_FOUND_404"
                        if exc.code == 404
                        else "RATE_LIMIT_429"
                        if exc.code == 429
                        else "TRANSIENT_5XX"
                        if exc.code in {500, 502, 503, 504}
                        else ""
                    ),
                    retry_after_sec=(backoff if exc.code == 429 else None),
                ) from exc
            except Exception as exc:
                transport_category = _transport_error_category(exc)
                if (
                    readonly
                    and _is_transient_transport_category(transport_category)
                    and transient_attempts < self.config.read_transient_retries
                ):
                    transient_attempts += 1
                    REQUEST_SCHEDULER.note_transient_retry(key=self._scheduler_key(), method=method)
                    _transient_retry_pause(transient_attempts)
                    continue
                if transport_category:
                    retry_exhausted = bool(
                        readonly
                        and _is_transient_transport_category(transport_category)
                        and transient_attempts >= self.config.read_transient_retries
                    )
                    raise DataLensApiError(
                        f"{method} failed before HTTP response: transport_category={transport_category}; "
                        f"read_retry_attempts={transient_attempts}; retry_exhausted={str(retry_exhausted).lower()}",
                        request_phase="transport",
                        response_received=False,
                        transport_category=transport_category,
                        retry_attempts=transient_attempts,
                        retry_exhausted=retry_exhausted,
                        failure_family="NETWORK_TIMEOUT"
                        if _is_transient_transport_category(transport_category)
                        else "",
                    ) from exc
                raise

            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise DataLensApiError(
                    f"{method} returned non-JSON response.",
                    request_phase="response_decode",
                    response_received=True,
                ) from exc

    def _can_refresh_token(self) -> bool:
        return self.token_refresher is not None or self.config.token_refresh_enabled

    def _bootstrap_missing_token(self) -> bool:
        """Mint and persist the initial IAM token when refresh is configured."""

        if self.config.iam_token:
            return False
        if not self.config.org_id or not self._can_refresh_token():
            return False
        try:
            refreshed = self._refresh_token_once()
            if not refreshed:
                raise DataLensApiError("yc iam create-token returned an empty token")
            self.persist_refreshed_token(refreshed)
            if self.config.env_file_path:
                self._reload_canonical_env_file("bootstrapped_with_yc", require_token=True)
            return True
        except Exception as exc:
            raise DataLensApiError(f"initial_token_bootstrap_failed: {_safe_auth_error(exc)}") from exc

    def _refresh_token_once(self) -> str:
        with self._state_lock:
            config = self.config
            refresher = self.token_refresher
        if refresher is None and config.token_refresh_enabled:
            refresher = lambda: refresh_iam_token_with_yc(
                yc_binary=config.yc_binary,
                timeout_sec=config.token_refresh_timeout_sec,
            )
        if refresher is None:
            return ""
        refreshed = TOKEN_REFRESH_COORDINATOR.refresh(self._token_refresh_key(), refresher)
        if refreshed:
            with self._state_lock:
                self.config = replace(self.config, iam_token=refreshed, credential_source="token_refresh")
        return refreshed

    def _minimal_auth_probe(self) -> dict[str, Any]:
        try:
            self._rpc_once(
                "getWorkbooksList",
                {"page": 1, "pageSize": 1},
            )
            return {"ok": True, "status": "success"}
        except Exception as exc:  # noqa: BLE001
            classified = classify_failure(exc, operation="getWorkbooksList", readonly=True)
            return {
                "ok": False,
                "status": "auth_401" if classified.family == "AUTH_401_TOKEN_INVALID_OR_EXPIRED" else "other_failure",
                "failure_family": classified.family,
            }

    def _reload_canonical_env_file(self, reload_state: str, *, require_token: bool = True) -> bool:
        with self._state_lock:
            if not self.config.env_file_path:
                return False
            reloaded = self.config.reload_canonical_env(reload_state=reload_state)
            if require_token and not reloaded.iam_token:
                return False
            self.config = reloaded
            return reloaded.env_file_loaded

    def persist_refreshed_token(self, token: str) -> None:
        """Atomically persist a refreshed token to the configured canonical env file."""

        with self._state_lock:
            config = self.config
        if not token or not config.env_file_path:
            return
        env_path = Path(config.env_file_path)
        env_path.parent.mkdir(parents=True, exist_ok=True)
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
        rendered: list[str] = []
        replaced_token = False
        replaced_org = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("DATALENS_IAM_TOKEN="):
                rendered.append(f"DATALENS_IAM_TOKEN={token}")
                replaced_token = True
            elif stripped.startswith("DATALENS_ORG_ID=") and config.org_id:
                rendered.append(f"DATALENS_ORG_ID={config.org_id}")
                replaced_org = True
            else:
                rendered.append(line)
        if not replaced_token:
            rendered.append(f"DATALENS_IAM_TOKEN={token}")
        if config.org_id and not replaced_org:
            rendered.append(f"DATALENS_ORG_ID={config.org_id}")
        fd, tmp_name = tempfile.mkstemp(prefix=f".{env_path.name}.", suffix=".tmp", dir=env_path.parent)
        tmp_path = Path(tmp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("\n".join(rendered) + "\n")
            tmp_path.replace(env_path)
            os.chmod(env_path, 0o600)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def _post_json(
        self,
        method: str,
        url: str,
        body: bytes,
        *,
        exclusive: bool = False,
    ) -> bytes:
        with self._state_lock:
            config = self.config
        return REQUEST_SCHEDULER.execute(
            key=self._scheduler_key(),
            method=method,
            readonly=_is_readonly_method(method),
            exclusive=exclusive,
            interval_sec=config.request_interval_sec,
            max_read_concurrency=config.max_read_concurrency,
            operation=lambda: self.transport.post_json(url, body, self.headers()),
        )

    def _scheduler_key(self) -> str:
        with self._state_lock:
            # A process normally represents one DataLens user. Keep all clients
            # for the same API endpoint behind one limiter even when a workflow
            # touches more than one organization.
            return self.config.base_url.rstrip("/")

    def _token_refresh_key(self) -> str:
        with self._state_lock:
            config = self.config
        custom_refresher = f"custom:{id(self.token_refresher)}" if self.token_refresher is not None else "yc"
        return (
            f"{config.base_url.rstrip('/')}|{config.org_id or '<missing-org>'}|"
            f"{config.env_file_path or '<no-env-file>'}|{custom_refresher}"
        )

    def _log_request_debug(self, method: str, url: str, payload: dict[str, Any]) -> None:
        debug_payload = {
            "method": method,
            "endpoint": url,
            "api_version": _compiled_api_version(),
            "org_id_present": bool(self.config.org_id),
            "token_present": bool(self.config.iam_token),
            "compacted_payload_keys": compact_payload_keys(payload),
        }
        print("DATALENS_REQUEST_DEBUG " + json.dumps(debug_payload, sort_keys=True), file=sys.stderr)

    def get_workbooks_list(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.rpc("getWorkbooksList", payload or {"page": 1, "pageSize": 100})

    def rpc_readonly(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        exclusive: bool = False,
    ) -> dict[str, Any]:
        from datalens_dev_mcp.api.methods import is_readonly_method
        from datalens_dev_mcp.api.request_compiler import validate_method_request

        if not is_readonly_method(method):
            raise DataLensApiError(f"{method} is not a curated read-only method.")
        rpc_payload = payload or {}
        validation = validate_method_request(method, rpc_payload)
        if not validation["ok"]:
            raise DataLensApiError(
                f"{method} blocked before HTTP: datalens_validation_error: {'; '.join(validation['issues'])}"
            )
        return self.rpc(method, rpc_payload, exclusive=exclusive)

    def rpc_exclusive_read(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.rpc_readonly(method, payload, exclusive=True)


def _safe_auth_error(exc: Exception) -> str:
    return redact_text(str(exc) or exc.__class__.__name__)[:600]


def _compiled_api_version() -> str:
    from datalens_dev_mcp.api.methods import compiled_api_version

    return compiled_api_version()


def _is_readonly_method(method: str) -> bool:
    from datalens_dev_mcp.api.methods import is_readonly_method

    return is_readonly_method(method)


def _retry_after_seconds(value: str | None, *, fallback: float, wall_time: float | None = None) -> float:
    raw = str(value or "").strip()
    if not raw:
        return max(0.0, float(fallback))
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        now = datetime.fromtimestamp(time.time() if wall_time is None else wall_time, tz=UTC)
        return max(0.0, (parsed - now).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return max(0.0, float(fallback))


TRANSIENT_TRANSPORT_CATEGORIES = {
    "connection_reset",
    "incomplete_read",
    "remote_disconnected",
    "temporarily_unavailable",
    "tls_connection_closed",
    "tls_handshake_timeout",
    "tls_unexpected_eof",
    "transport_timeout",
}


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain: list[BaseException] = []
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        if isinstance(current, error.URLError) and isinstance(current.reason, BaseException):
            pending.append(current.reason)
        for nested in (current.__cause__, current.__context__):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return chain


def _transport_error_category(exc: BaseException) -> str:
    chain = _exception_chain(exc)
    text = " | ".join(str(item).lower() for item in chain)
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain):
        return "tls_certificate_failure"
    if any(isinstance(item, ssl.SSLEOFError) for item in chain) or any(
        marker in text
        for marker in (
            "unexpected_eof_while_reading",
            "unexpected eof while reading",
            "eof occurred in violation of protocol",
        )
    ):
        return "tls_unexpected_eof"
    if "handshake" in text and any(marker in text for marker in ("timed out", "timeout", "ssl connection timeout")):
        return "tls_handshake_timeout"
    if any(isinstance(item, ssl.SSLZeroReturnError) for item in chain):
        return "tls_connection_closed"
    if any(isinstance(item, ssl.SSLError) for item in chain):
        return "tls_failure"
    if any(isinstance(item, IncompleteRead) for item in chain):
        return "incomplete_read"
    if any(isinstance(item, RemoteDisconnected) for item in chain) or "remote end closed" in text:
        return "remote_disconnected"
    if any(isinstance(item, (ConnectionResetError, ConnectionAbortedError)) for item in chain) or any(
        marker in text for marker in ("connection reset", "connection aborted")
    ):
        return "connection_reset"
    if any(isinstance(item, (TimeoutError, socket.timeout)) for item in chain) or any(
        marker in text
        for marker in (
            "timed out",
            "timeout",
            "read timed out",
            "connection timed out",
        )
    ):
        return "transport_timeout"
    if "temporarily unavailable" in text:
        return "temporarily_unavailable"
    if isinstance(exc, error.URLError):
        return "transport_failure"
    return ""


def _is_transient_transport_category(category: str) -> bool:
    return category in TRANSIENT_TRANSPORT_CATEGORIES


def _is_transient_read_error(exc: Exception) -> bool:
    return _is_transient_transport_category(_transport_error_category(exc))


def _transient_retry_pause(attempt: int) -> None:
    backoff = min(0.25 * (2 ** max(0, attempt - 1)), 1.0)
    time.sleep(backoff + random.uniform(0.0, 0.1))
