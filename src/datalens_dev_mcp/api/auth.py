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
