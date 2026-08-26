from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RetryDecision:
    action: str
    retry: bool = False
    refresh_token: bool = False
    reconcile: bool = False
    delay_sec: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def retry_decision(
    family: str,
    *,
    readonly: bool,
    attempt: int = 0,
    max_attempts: int = 2,
    auth_probe: str = "not_run",
    refresh_attempted: bool = False,
    retry_after_sec: float | None = None,
) -> RetryDecision:
    """Return the only allowed recovery transition for a failure family."""

    if family == "AMBIGUOUS_WRITE":
        return RetryDecision("reconcile", reconcile=True, reason="writes with uncertain outcomes are never replayed")
    if family == "AUTH_403_PERMISSION_DENIED":
        return RetryDecision("fail", reason="permission denial cannot be repaired by token refresh")
    if family == "AUTH_401_TOKEN_INVALID_OR_EXPIRED":
        if auth_probe == "success":
            return RetryDecision("fail", reason="minimal probe succeeded; failure is not token-wide")
        if auth_probe != "auth_401":
            return RetryDecision("investigate", reason="token-wide failure was not proven")
        if refresh_attempted:
            return RetryDecision("fail", reason="the single token refresh was already attempted")
        return RetryDecision(
            "refresh_then_retry_read" if readonly else "refresh_for_future_requests",
            retry=readonly,
            refresh_token=True,
            reason="minimal probe also returned 401",
        )
    if family == "RATE_LIMIT_429":
        if not readonly or attempt >= max_attempts:
            return RetryDecision("fail", reason="rate-limit retry budget exhausted or operation is not a safe read")
        return RetryDecision(
            "wait_then_retry_read",
            retry=True,
            delay_sec=max(0.0, float(retry_after_sec or 0.0)),
            reason="shared cooldown applies before the bounded read retry",
        )
    if family in {"TRANSIENT_5XX", "NETWORK_TIMEOUT"}:
        if readonly and attempt < max_attempts:
            return RetryDecision("retry_read", retry=True, reason="bounded transient retry for a safe read")
        if not readonly and family == "NETWORK_TIMEOUT":
            return RetryDecision("reconcile", reconcile=True, reason="write transport failure has an ambiguous outcome")
    return RetryDecision("fail", reason="failure family is not retryable in this context")
