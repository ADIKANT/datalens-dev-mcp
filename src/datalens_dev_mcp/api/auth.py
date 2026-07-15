from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

from datalens_dev_mcp.api.errors import DataLensApiError


def is_auth_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "http 401" in text
        or "auth_invalid_or_expired" in text
        or "unauthenticated" in text
        or is_missing_credentials(exc)
    )


def is_missing_credentials(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "blocked_live_credentials" in text
        or "missing datalens_iam_token" in text
        or "missing yc_iam_token" in text
        or "missing datalens_org_id" in text
    )


def classify_auth_probe_failure(exc: Exception) -> dict[str, str]:
    """Classify a failed minimal auth probe without returning credential data."""

    text = str(exc).lower()
    if is_missing_credentials(exc):
        category = "missing_credentials"
        next_action = (
            "Configure DATALENS_ORG_ID and an IAM token, or enable yc token refresh, "
            "then retry dl_auth_probe."
        )
    elif any(
        marker in text
        for marker in (
            "initial_token_bootstrap_failed",
            "yc iam create-token failed",
            "yc iam create-token could not be started",
            "yc iam create-token timed out",
            "token_refresh_failed",
        )
    ):
        category = "yc_reauthentication_required"
        next_action = "Restore an authenticated yc CLI profile, then retry dl_auth_probe."
    elif any(marker in text for marker in ("http 401", "auth_invalid_or_expired", "unauthenticated")):
        category = "expired_token"
        next_action = "Refresh the IAM token or enable yc refresh, then retry dl_auth_probe."
    elif any(
        marker in text
        for marker in (
            "http 403",
            "permission_denied",
            "permission denied",
            "access denied",
            "forbidden",
            "organization access",
        )
    ):
        category = "organization_access_denied"
        next_action = "Check DATALENS_ORG_ID and the DataLens roles granted to the active Yandex Cloud identity."
    elif any(
        marker in text
        for marker in (
            "failed before http response",
            "connection refused",
            "connection reset",
            "name or service not known",
            "temporary failure",
            "timed out",
            "timeout",
            "network is unreachable",
        )
    ):
        category = "transport_failure"
        next_action = "Check network, proxy, DNS, API base URL, and request timeout, then retry dl_auth_probe."
    else:
        category = "api_failure"
        next_action = "Check the sanitized API error and DataLens API status, then retry dl_auth_probe."
    return {"category": category, "next_action": next_action}


def request_with_auth_refresh(
    operation: Callable[[], Any],
    *,
    refresh_token: Callable[[], str] | None,
    operation_label: str,
) -> Any:
    """Run one operation, refresh once on auth failure, then retry once."""
    try:
        return operation()
    except Exception as first_exc:  # noqa: BLE001
        if not is_auth_failure(first_exc):
            raise
        if refresh_token is None:
            raise DataLensApiError(
                f"{operation_label} failed with auth_invalid_or_expired; "
                "token_refresh_failed: no refresh callback or DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1 configured"
            ) from first_exc
        try:
            refreshed = refresh_token()
        except Exception as refresh_exc:  # noqa: BLE001
            raise DataLensApiError(
                f"{operation_label} failed with auth_invalid_or_expired; token_refresh_failed: "
                f"{_safe_auth_error(refresh_exc)}"
            ) from refresh_exc
        if not refreshed:
            raise DataLensApiError(
                f"{operation_label} failed with auth_invalid_or_expired; token_refresh_failed: empty refreshed token"
            ) from first_exc
        try:
            return operation()
        except Exception as retry_exc:  # noqa: BLE001
            if is_auth_failure(retry_exc):
                raise DataLensApiError(
                    f"{operation_label} auth_retry_failed_after_refresh: {_safe_auth_error(retry_exc)}"
                ) from retry_exc
            raise


def refresh_iam_token_with_yc(*, yc_binary: str = "yc", timeout_sec: float = 15.0) -> str:
    try:
        result = subprocess.run(
            [yc_binary, "iam", "create-token"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise DataLensApiError("yc iam create-token timed out") from exc
    except OSError as exc:
        raise DataLensApiError("yc iam create-token could not be started") from exc
    if result.returncode != 0:
        raise DataLensApiError("yc iam create-token failed; stderr is intentionally not echoed")
    token = result.stdout.strip()
    if not token:
        raise DataLensApiError("yc iam create-token returned an empty token")
    if any(ch.isspace() for ch in token):
        raise DataLensApiError("yc iam create-token returned an invalid whitespace-containing token")
    return token


def _safe_auth_error(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    for key in ("DATALENS_IAM_TOKEN", "YC_IAM_TOKEN", "Authorization", "x-yacloud-subjecttoken", "token"):
        text = text.replace(key, "<redacted-key>")
    return text[:600]


def token_refresh_operator_note() -> dict[str, str]:
    return {
        "mode": "refresh_once_on_auth_failure",
        "command": "yc iam create-token",
        "policy": (
            "Never print token values, prefixes, lengths, Authorization, "
            "x-yacloud-subjecttoken, DATALENS_IAM_TOKEN, or YC_IAM_TOKEN."
        ),
    }
