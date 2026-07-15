from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

from datalens_dev_mcp.api.auth import is_auth_failure, is_missing_credentials, refresh_iam_token_with_yc
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.validators.redaction import redact_text, sanitize_value

LEGACY_API_VERSION = "1"

COMPACT_READ_FALSE_KEYS = {
    "includeFavorite",
    "includeLinks",
    "includePermissions",
    "includePermissionsInfo",
}
PROTECTED_PAYLOAD_KEYS = {"entry", "data"}
class Transport(Protocol):
    def post_json(self, url: str, body: bytes, headers: dict[str, str]) -> bytes:
        ...


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
        self._last_request_at = 0.0
        self._selected_api_version = ""
        self._api_version_selection_reason = ""

    def headers(self, *, api_version: str | None = None) -> dict[str, str]:
        self.config.require_auth()
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "x-dl-api-version": api_version or self.config.api_version,
            "x-dl-org-id": self.config.org_id,
            "Authorization": f"Bearer {self.config.iam_token}",
        }

    def rpc(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        compacted_payload = compact_rpc_payload(payload or {}, method=method) or {}
        selected_api_version = self._resolve_api_version(method)
        try:
            return self._rpc_once(method, compacted_payload, api_version=selected_api_version)
        except Exception as first_exc:  # noqa: BLE001
            fallback_result = self._maybe_retry_readonly_legacy_version(
                method=method,
                compacted_payload=compacted_payload,
                selected_api_version=selected_api_version,
                exc=first_exc,
            )
            if fallback_result is not None:
                return fallback_result
            if is_missing_credentials(first_exc):
                raise first_exc
            if (
                str(self.config.api_version or "auto").strip().lower() == "auto"
                and not _is_readonly_method(method)
                and _is_version_specific_failure(first_exc)
            ):
                raise DataLensApiError(
                    f"{method} failed under compiled API version {selected_api_version}; "
                    "writes are not retried under another API version"
                ) from first_exc
            if not is_auth_failure(first_exc):
                raise
            if self.config.env_file_path:
                self._minimal_auth_probe()
                if self._reload_canonical_env_file("reloaded_after_401"):
                    try:
                        selected_api_version = self._resolve_api_version(method)
                        return self._rpc_once(method, compacted_payload, api_version=selected_api_version)
                    except Exception as reload_exc:  # noqa: BLE001
                        fallback_result = self._maybe_retry_readonly_legacy_version(
                            method=method,
                            compacted_payload=compacted_payload,
                            selected_api_version=selected_api_version,
                            exc=reload_exc,
                        )
                        if fallback_result is not None:
                            return fallback_result
                        if is_missing_credentials(reload_exc):
                            raise reload_exc
                        if not is_auth_failure(reload_exc):
                            raise
                        first_exc = reload_exc
            if self._can_refresh_token():
                try:
                    refreshed = self._refresh_token_once()
                    if refreshed:
                        self._persist_refreshed_token(refreshed)
                        self._reload_canonical_env_file("reloaded_after_refresh")
                        try:
                            selected_api_version = self._resolve_api_version(method)
                            return self._rpc_once(method, compacted_payload, api_version=selected_api_version)
                        except Exception as retry_exc:  # noqa: BLE001
                            fallback_result = self._maybe_retry_readonly_legacy_version(
                                method=method,
                                compacted_payload=compacted_payload,
                                selected_api_version=selected_api_version,
                                exc=retry_exc,
                            )
                            if fallback_result is not None:
                                return fallback_result
                            if is_auth_failure(retry_exc):
                                raise DataLensApiError(
                                    f"{method} auth_retry_failed_after_refresh: {_safe_auth_error(retry_exc)}"
                                ) from retry_exc
                            raise
                except Exception as refresh_exc:  # noqa: BLE001
                    if isinstance(refresh_exc, DataLensApiError) and "auth_retry_failed_after_refresh" in str(refresh_exc):
                        raise
                    raise DataLensApiError(
                        f"{method} failed with auth_invalid_or_expired; token_refresh_failed: "
                        f"{_safe_auth_error(refresh_exc)}"
                    ) from refresh_exc
            raise DataLensApiError(
                f"{method} failed with auth_invalid_or_expired; "
                "canonical_env_reload_failed_or_unavailable"
            ) from first_exc

    def _rpc_once(self, method: str, compacted_payload: dict[str, Any], *, api_version: str | None = None) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/rpc/{method}"
        body = json.dumps(compacted_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        attempts = 0
        if self.config.request_debug:
            self._log_request_debug(method, url, compacted_payload, api_version=api_version or self.config.api_version)
        while True:
            try:
                raw = self._post_json(url, body, api_version=api_version)
            except error.HTTPError as exc:
                raw_text = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 and attempts < self.config.rate_limit_retries:
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        backoff = float(retry_after) if retry_after else min(2**attempts, 10)
                    except ValueError:
                        backoff = min(2**attempts, 10)
                    time.sleep(backoff)
                    attempts += 1
                    continue
                if exc.code == 401:
                    raise DataLensApiError(
                        f"{method} failed with HTTP 401: auth_invalid_or_expired; "
                        f"compacted_payload_keys={compact_payload_keys(compacted_payload)}; "
                        f"detail={short_error_detail(raw_text)}"
                    ) from exc
                if exc.code == 400 and is_validation_error(raw_text):
                    raise DataLensApiError(
                        f"{method} failed with HTTP 400 VALIDATION_ERROR: {short_error_detail(raw_text)}; "
                        f"compacted_payload_keys={compact_payload_keys(compacted_payload)}"
                    ) from exc
                raise DataLensApiError(
                    f"{method} failed with HTTP {exc.code}: {short_error_detail(raw_text)}; "
                    f"compacted_payload_keys={compact_payload_keys(compacted_payload)}"
                ) from exc
            except error.URLError as exc:
                raise DataLensApiError(f"{method} failed before HTTP response: {exc.reason}") from exc

            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise DataLensApiError(f"{method} returned non-JSON response.") from exc

    def _can_refresh_token(self) -> bool:
        return self.token_refresher is not None or self.config.token_refresh_enabled

    def _resolve_api_version(self, method: str) -> str:
        configured = str(self.config.api_version or "auto").strip().lower()
        if configured and configured != "auto":
            compiled = _compiled_api_version()
            if not _is_readonly_method(method) and configured != compiled:
                detail = "unlocked_api_version_for_write; " if configured == "latest" else ""
                raise DataLensApiError(
                    f"{method} blocked before HTTP: api_version_mismatch_for_write; {detail}"
                    f"configured={configured}; compiled={compiled}"
                )
            self._selected_api_version = configured
            self._api_version_selection_reason = "explicit"
            return configured
        if self._selected_api_version and _is_readonly_method(method):
            return self._selected_api_version
        current = _compiled_api_version()
        self._selected_api_version = current
        self._api_version_selection_reason = "compiled_current_direct"
        return current

    def _maybe_retry_readonly_legacy_version(
        self,
        *,
        method: str,
        compacted_payload: dict[str, Any],
        selected_api_version: str,
        exc: Exception,
    ) -> dict[str, Any] | None:
        # API v1 compatibility is explicit-only. Auto is pinned to the reviewed
        # compiled contract and never changes request semantics after a failure.
        return None

    def _refresh_token_once(self) -> str:
        refresher = self.token_refresher
        if refresher is None and self.config.token_refresh_enabled:
            refresher = lambda: refresh_iam_token_with_yc(
                yc_binary=self.config.yc_binary,
                timeout_sec=self.config.token_refresh_timeout_sec,
            )
        if refresher is None:
            return ""
        refreshed = refresher()
        if refreshed:
            self.config = replace(self.config, iam_token=refreshed)
        return refreshed

    def _minimal_auth_probe(self) -> dict[str, Any]:
        try:
            return self._rpc_once(
                "getWorkbooksList",
                {"page": 1, "pageSize": 1},
                api_version=self._selected_api_version or _compiled_api_version(),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": _safe_auth_error(exc)}

    def _reload_canonical_env_file(self, reload_state: str) -> bool:
        if not self.config.env_file_path:
            return False
        reloaded = DataLensConfig.from_env(self.config.env_file_path, reload_state=reload_state)
        if not reloaded.iam_token:
            return False
        self.config = reloaded
        return True

    def _persist_refreshed_token(self, token: str) -> None:
        if not token or not self.config.env_file_path:
            return
        env_path = Path(self.config.env_file_path)
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
            elif stripped.startswith("DATALENS_ORG_ID=") and self.config.org_id:
                rendered.append(f"DATALENS_ORG_ID={self.config.org_id}")
                replaced_org = True
            else:
                rendered.append(line)
        if not replaced_token:
            rendered.append(f"DATALENS_IAM_TOKEN={token}")
        if self.config.org_id and not replaced_org:
            rendered.append(f"DATALENS_ORG_ID={self.config.org_id}")
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

    def _post_json(self, url: str, body: bytes, *, api_version: str | None = None) -> bytes:
        now = time.monotonic()
        delay = self.config.request_interval_sec - (now - self._last_request_at)
        if delay > 0:
            time.sleep(delay)
        self._last_request_at = time.monotonic()
        return self.transport.post_json(url, body, self.headers(api_version=api_version))

    def _log_request_debug(self, method: str, url: str, payload: dict[str, Any], *, api_version: str) -> None:
        debug_payload = {
            "method": method,
            "endpoint": url,
            "api_version": api_version,
            "org_id_present": bool(self.config.org_id),
            "token_present": bool(self.config.iam_token),
            "compacted_payload_keys": compact_payload_keys(payload),
        }
        print("DATALENS_REQUEST_DEBUG " + json.dumps(debug_payload, sort_keys=True), file=sys.stderr)

    def get_workbooks_list(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.rpc("getWorkbooksList", payload or {"page": 1, "pageSize": 100})

    def rpc_readonly(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
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
        return self.rpc(method, rpc_payload)


def _safe_auth_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    for key in ("DATALENS_IAM_TOKEN", "YC_IAM_TOKEN", "Authorization", "x-yacloud-subjecttoken", "token"):
        text = text.replace(key, "<redacted-key>")
    return text[:600]


def _compiled_api_version() -> str:
    from datalens_dev_mcp.api.methods import compiled_api_version

    return compiled_api_version()


def _is_readonly_method(method: str) -> bool:
    from datalens_dev_mcp.api.methods import is_readonly_method

    return is_readonly_method(method)


def _is_version_specific_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "x-dl-api-version" in text
        or "api version" in text
        or "unsupported version" in text
        or "version is not supported" in text
        or "invalid api version" in text
    )
