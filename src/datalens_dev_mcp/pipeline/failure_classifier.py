from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from datalens_dev_mcp.validators.redaction import redact_text, sanitize_value


FAILURE_FAMILIES = frozenset(
    {
        "AUTH_401_TOKEN_INVALID_OR_EXPIRED",
        "AUTH_403_PERMISSION_DENIED",
        "NOT_FOUND_404",
        "REVISION_CONFLICT",
        "RATE_LIMIT_429",
        "TRANSIENT_5XX",
        "NETWORK_TIMEOUT",
        "AMBIGUOUS_WRITE",
        "SCHEMA_INVALID",
        "ROUTE_INVALID",
        "DATA_EMPTY_EXPECTED",
        "DATA_EMPTY_UNEXPECTED",
        "STYLE_BINDING_STALE",
        "PATCH_ANCHOR_STALE",
        "BROWSER_FORBIDDEN",
        "BROWSER_REQUIRED_MISSING",
        "NO_PROGRESS",
        "TOOL_OR_CAPABILITY_UNAVAILABLE",
    }
)


@dataclass(frozen=True)
class FailureClassification:
    family: str
    retry_policy: str
    severity: str
    http_status: int | None = None
    remote_code: str = ""
    response_received: bool | None = None
    evidence: str = ""
    schema_id: str = "datalens_failure_classification"

    def to_dict(self) -> dict[str, Any]:
        return sanitize_value(asdict(self))


_MESSAGE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("REVISION_CONFLICT", ("revision conflict", "rev_id", "revision changed", "conflict")),
    ("SCHEMA_INVALID", ("schema invalid", "validation_error", "schema validation")),
    ("ROUTE_INVALID", ("route invalid", "invalid route", "route is not")),
    ("STYLE_BINDING_STALE", ("style binding stale", "stale style binding")),
    ("PATCH_ANCHOR_STALE", ("patch anchor stale", "stale patch anchor")),
    ("BROWSER_FORBIDDEN", ("browser forbidden", "browser is forbidden")),
    ("BROWSER_REQUIRED_MISSING", ("browser required", "browser evidence missing")),
    ("DATA_EMPTY_UNEXPECTED", ("empty unexpected", "unexpected empty", "no rows unexpectedly")),
    ("DATA_EMPTY_EXPECTED", ("empty expected", "expected empty")),
    ("NO_PROGRESS", ("no progress", "unchanged poll", "same failure")),
    ("TOOL_OR_CAPABILITY_UNAVAILABLE", ("handler is unavailable", "capability unavailable", "tool unavailable")),
)


def classify_failure(
    failure: BaseException | dict[str, Any] | str,
    *,
    operation: str = "",
    readonly: bool | None = None,
    write_ambiguous: bool = False,
    empty_expected: bool | None = None,
) -> FailureClassification:
    """Classify a sanitized failure into one stable recovery family."""

    if write_ambiguous:
        return _classification("AMBIGUOUS_WRITE", evidence="write outcome requires readback reconciliation")
    status = _value(failure, "http_status")
    remote_code = str(_value(failure, "remote_code") or "")[:120]
    response_received = _value(failure, "response_received")
    transport = str(_value(failure, "transport_category") or "").lower()
    message = _safe_evidence(failure)
    lowered = message.lower()
    if status == 401:
        family = "AUTH_401_TOKEN_INVALID_OR_EXPIRED"
    elif status == 403:
        family = "AUTH_403_PERMISSION_DENIED"
    elif status == 404:
        family = "NOT_FOUND_404"
    elif status == 429:
        family = "RATE_LIMIT_429"
    elif status in {500, 502, 503, 504}:
        family = "TRANSIENT_5XX"
    elif isinstance(failure, (TimeoutError, ConnectionError)) or "timeout" in transport or "timed out" in lowered:
        family = "NETWORK_TIMEOUT"
    elif empty_expected is not None:
        family = "DATA_EMPTY_EXPECTED" if empty_expected else "DATA_EMPTY_UNEXPECTED"
    else:
        family = next(
            (candidate for candidate, markers in _MESSAGE_RULES if any(marker in lowered for marker in markers)),
            "TOOL_OR_CAPABILITY_UNAVAILABLE",
        )
    retry_policy, severity = _policy(family, readonly=readonly)
    return FailureClassification(
        family=family,
        retry_policy=retry_policy,
        severity=severity,
        http_status=int(status) if isinstance(status, int) else None,
        remote_code=remote_code,
        response_received=response_received if isinstance(response_received, bool) else None,
        evidence=f"{operation}: {message}"[:600] if operation else message[:600],
    )


def _classification(family: str, *, evidence: str = "", readonly: bool | None = None) -> FailureClassification:
    retry_policy, severity = _policy(family, readonly=readonly)
    return FailureClassification(family, retry_policy, severity, evidence=redact_text(evidence)[:600])


def _policy(family: str, *, readonly: bool | None) -> tuple[str, str]:
    if family == "AMBIGUOUS_WRITE":
        return "reconcile", "critical"
    if family in {"AUTH_403_PERMISSION_DENIED", "NOT_FOUND_404", "SCHEMA_INVALID", "ROUTE_INVALID", "BROWSER_FORBIDDEN"}:
        return "never", "error"
    if family in {"AUTH_401_TOKEN_INVALID_OR_EXPIRED", "RATE_LIMIT_429", "TRANSIENT_5XX", "NETWORK_TIMEOUT"}:
        return ("safe_read_only" if readonly is not False else "never"), "warning"
    if family in {"DATA_EMPTY_EXPECTED"}:
        return "none", "info"
    return "investigate", "error"


def _value(failure: BaseException | dict[str, Any] | str, name: str) -> Any:
    if isinstance(failure, dict):
        return failure.get(name)
    return getattr(failure, name, None)


def _safe_evidence(failure: BaseException | dict[str, Any] | str) -> str:
    if isinstance(failure, dict):
        value = str(sanitize_value(failure))
    else:
        value = str(failure) or failure.__class__.__name__
    value = re.sub(r"(?i)authorization\s*[:=]\s*(?:bearer\s+)?\S+", "Authorization=<redacted>", value)
    value = re.sub(r"(?i)bearer\s+\S+", "Bearer <redacted>", value)
    value = re.sub(r"(?i)(iam[_-]?token|subjecttoken)\s*[:=]\s*\S+", r"\1=<redacted>", value)
    return redact_text(value)[:600]
