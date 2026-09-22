from __future__ import annotations

import math
import re
import uuid
from typing import Any

ERROR_DIAGNOSTIC_FIELDS = ("stage", "method", "http_status", "provider_code", "request_id", "trace_id", "retry_after_sec",
                           "response_received")


def safe_diagnostic_id(value: Any) -> str | None:
    """Only short identifier-shaped provider metadata, never arbitrary response text."""
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value) else None


def response_diagnostics(headers: Any) -> dict[str, str | None]:
    # Read this allowlist only; do not copy response headers or parse login/error bodies.
    return {"request_id": safe_diagnostic_id(headers.get("x-request-id")) if headers else None,
            "trace_id": safe_diagnostic_id(headers.get("x-trace-id")) if headers else None}


def safe_error_text(error: BaseException) -> str:
    text = str(error) or type(error).__name__
    if re.search(r"(?i)<(?:!doctype\s+html|html|body)\b", text):
        return "Provider returned an HTML response; inspect the configured API endpoint and authentication."
    text = re.sub(r"(?i)bearer\s+[^\s,;\"']+", "Bearer <redacted>", text)
    text = re.sub(
        r"(?i)(DATALENS_IAM_TOKEN|YC_IAM_TOKEN|Authorization|x-dl-org-id)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        text,
    )
    return text[:600]


class DataLensApiError(RuntimeError):
    """A secret-safe provider or transport error."""

    def __init__(
        self,
        message: str,
        *,
        method: str = "",
        http_status: int | None = None,
        response_received: bool | None = None,
        remote_code: str = "",
        dispatch_state: str | None = None,
        retry_after_sec: float | None = None,
        stage: str = "provider_request",
        request_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.method = safe_diagnostic_id(method)
        self.http_status = http_status
        self.response_received = response_received
        self.remote_code = safe_diagnostic_id(remote_code) or ""
        self.dispatch_state = dispatch_state
        self.retry_after_sec = (
            float(retry_after_sec)
            if isinstance(retry_after_sec, (int, float)) and not isinstance(retry_after_sec, bool)
            and math.isfinite(retry_after_sec) and retry_after_sec >= 0 else None
        )
        self.stage = safe_diagnostic_id(stage)
        self.request_id = safe_diagnostic_id(request_id)
        self.trace_id = safe_diagnostic_id(trace_id)


class UncertainWriteError(DataLensApiError):
    """A mutation may have applied, including a partial composite effect."""


class CredentialRefreshError(DataLensApiError):
    """Allowlisted helper diagnostics, never captured credential output."""

    def __init__(self, code: str, *, exit_status: int | None = None,
                 stage: str = "credential_helper", elapsed_sec: float | None = None) -> None:
        super().__init__(f"Credential refresh: {code}")
        self.code = code
        self.exit_status = exit_status
        self.stage = stage
        self.elapsed_sec = elapsed_sec
        self.diagnostic_id = uuid.uuid4().hex


class DataLensSafetyError(RuntimeError):
    """The requested effect cannot be performed safely with the available evidence."""


class WritePreconditionError(ValueError):
    """An adapter rejected stale or missing revision evidence before transport."""


class InputContractError(ValueError):
    """Invalid input rejected by an owner before any external effect is possible."""


def is_confirmed_rejection(error: BaseException) -> bool:
    """Only explicit request rejection proves that an attempted write was not applied."""
    return (
        isinstance(error, DataLensApiError)
        and not isinstance(error, UncertainWriteError)
        and error.response_received is True
        and error.http_status in {400, 401, 403, 404, 405, 409, 412, 413, 415, 422, 429}
    )


def error_response(error: BaseException, *, effect_possible: bool = False) -> dict[str, Any]:
    """Describe an error by effect evidence, never by exception class alone."""
    status = getattr(error, "http_status", None)
    not_dispatched = (isinstance(error, (InputContractError, DataLensSafetyError, WritePreconditionError))
                      or getattr(error, "dispatch_state", None) == "not_dispatched")
    effect_possible = effect_possible and not not_dispatched
    if isinstance(error, InputContractError):
        code = "input_error"
        action = "Correct the stated input contract; the request was rejected before provider dispatch."
    elif isinstance(error, DataLensSafetyError):
        code, action = "safety_precondition_failed", "Resolve the stated local safety precondition before dispatch."
    elif isinstance(error, WritePreconditionError):
        code = "revision_conflict"
        action = "Read the current full target and recompute the patch with fresh revisions before writing."
    elif isinstance(error, UncertainWriteError) or (effect_possible and not is_confirmed_rejection(error)):
        code = "write_outcome_unknown"
        action = "Inspect the existing operation_id and reconcile exact target readback; do not replay the write."
    elif isinstance(error, CredentialRefreshError):
        code = error.code
        action = {
            "credential_helper_unavailable": "Check the configured yc executable and its launch permissions, then call dl_auth_refresh.",
            "interactive_login_required": "Use dl_auth_refresh for the existing yc profile's external-browser sign-in and API verification; the user handles any required password or MFA. If yc still requires profile setup, follow its supported same-account login.",
            "credential_refresh_timeout": (
                "The browser-enabled yc attempt timed out. Check whether external-browser sign-in or MFA is pending, and bounded helper/network evidence; do not repeat an unchanged failure."
                if error.stage == "browser_credential_helper" else
                "The noninteractive yc attempt timed out; this alone does not establish a network failure or login requirement. For authorized sign-in use dl_auth_refresh once with its default external-browser recovery."
            ),
            "credential_refresh_failed": "The helper failed without confirmed login evidence. Check its safe exit status and local diagnostics, then call dl_auth_refresh.",
            "credential_invalid": "The helper returned no valid credential. Check the configured helper, then call dl_auth_refresh.",
        }[code]
    elif isinstance(error, DataLensApiError):
        code = {401: "authentication_failed", 403: "permission_denied", 404: "not_found",
                409: "revision_conflict", 412: "revision_conflict", 429: "rate_limited"}.get(status)
        code = code or (error.remote_code if error.remote_code in {"response_too_large", "invalid_json", "invalid_response", "read_budget_exhausted", "operation_cancelled", "operation_budget_exhausted", "incomplete_relations"}
                        else "provider_rejected" if is_confirmed_rejection(error) else "provider_error")
        action = {
            "authentication_failed": "The API rejected the credential. Use dl_auth_check and the configured authentication recovery; verify API access before resuming the original read.",
            "permission_denied": "The API denied this scope. Check access to the exact target; a 403 alone does not require login or credential refresh.",
            "not_found": "Check the exact object type, ID and branch before continuing.",
            "revision_conflict": "Read the current full target, preserve manual changes, then recompute the patch.",
            "provider_rejected": "Correct the rejected request using its reference contract before a new attempt.",
            "rate_limited": (
                "Keep the payload unchanged and reduce request intensity. "
                + (f"Wait at least {error.retry_after_sec:g} seconds before continuing. "
                   if error.retry_after_sec is not None else
                   "Retry-After is unavailable or invalid; this does not mean zero delay. Avoid an immediate retry. ")
                + "Resume only the same safe read within the remaining bounded budget; "
                "if the wait or attempts exceed that budget, defer the read without polling or shortening the wait. "
                "Do not stack retry loops or automatically replay a write; inspect its operation receipt and effect outcome."
            ),
            "provider_error": "Retry the scoped read when the provider is available.",
            "response_too_large": "Use a smaller page or bounded query. For a required full object, configure a reviewed larger response limit; no truncated state is usable for writes.",
            "invalid_json": "Check the selected API endpoint and response contract; no response body is echoed.",
            "invalid_response": "Check the exact endpoint response contract; incomplete state cannot prove absence.",
            "read_budget_exhausted": "The bounded read budget expired; resume the exact safe read when the provider is available.",
            "operation_cancelled": "No further dispatch is admitted. Reconcile any previously admitted write by operation_id; cancellation does not prove non-application.",
            "operation_budget_exhausted": "Inspect completed and remaining reads. Incomplete preview cannot authorize deletion; do not automatically repeat the full scan.",
            "incomplete_relations": "Resolve the incomplete API-visible dependency evidence; this preview cannot authorize deletion.",
        }[code]
    elif isinstance(error, (ValueError, TypeError)):
        code, action = "input_error", "Correct the indicated argument using tools/list inputSchema; no provider call is needed."
    else:
        code, action = "internal_error", "Inspect the local failure before continuing."
    result: dict[str, Any] = {"ok": False, "status": code, "code": code,
                              "error": safe_error_text(error), "next_action": action}
    if not_dispatched:
        result.update(dispatch_state="not_dispatched", effect_outcome="not_applied")
    elif effect_possible or isinstance(error, UncertainWriteError):
        result.update(dispatch_state="dispatched", effect_outcome="not_applied" if is_confirmed_rejection(error) else "unknown")
    if status is not None:
        result["http_status"] = status
    if isinstance(error, DataLensApiError):
        result.update(response_received=error.response_received, stage=error.stage, method=error.method, provider_code=error.remote_code or None,
                      request_id=error.request_id, trace_id=error.trace_id)
        if error.retry_after_sec is not None:
            result["retry_after_sec"] = error.retry_after_sec
    if isinstance(error, CredentialRefreshError):
        result["diagnostic_id"] = error.diagnostic_id
        result["helper_exit_status"] = error.exit_status
        result["stage"] = error.stage
        result["elapsed_sec"] = error.elapsed_sec
    return result
