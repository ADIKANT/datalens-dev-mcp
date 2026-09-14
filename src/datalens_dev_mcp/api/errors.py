from __future__ import annotations

import re
import uuid
from typing import Any


def safe_error_text(error: BaseException) -> str:
    text = str(error) or type(error).__name__
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
    ) -> None:
        super().__init__(message)
        self.method = method
        self.http_status = http_status
        self.response_received = response_received
        self.remote_code = remote_code


class UncertainWriteError(DataLensApiError):
    """A mutation may have reached DataLens but no response was received."""


class CredentialRefreshError(DataLensApiError):
    """Allowlisted helper diagnostics, never captured credential output."""

    def __init__(self, code: str, *, exit_status: int | None = None) -> None:
        super().__init__(f"Credential refresh: {code}")
        self.code = code
        self.exit_status = exit_status
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
            "interactive_login_required": "Complete the configured yc profile's interactive login in the same account, then call dl_auth_refresh to verify API access and resume the original read.",
            "credential_refresh_timeout": "The timeout cause is unknown. Check bounded helper availability and network reachability before calling dl_auth_refresh; login is not established as necessary.",
            "credential_refresh_failed": "The helper failed without confirmed login evidence. Check its safe exit status and local diagnostics, then call dl_auth_refresh.",
            "credential_invalid": "The helper returned no valid credential. Check the configured helper, then call dl_auth_refresh.",
        }[code]
    elif isinstance(error, DataLensApiError):
        code = {401: "authentication_failed", 403: "permission_denied", 404: "not_found",
                409: "revision_conflict", 412: "revision_conflict"}.get(status)
        code = code or ("provider_rejected" if is_confirmed_rejection(error) else "provider_error")
        action = {
            "authentication_failed": "The API rejected the credential. Use dl_auth_check and the configured authentication recovery; verify API access before resuming the original read.",
            "permission_denied": "The API denied this scope. Check access to the exact target; a 403 alone does not require login or credential refresh.",
            "not_found": "Check the exact object type, ID and branch before continuing.",
            "revision_conflict": "Read the current full target, preserve manual changes, then recompute the patch.",
            "provider_rejected": "Correct the rejected request using its reference contract before a new attempt.",
            "provider_error": "Retry the scoped read when the provider is available.",
        }[code]
    elif isinstance(error, (ValueError, TypeError)):
        code, action = "input_error", "Correct the indicated argument using tools/list inputSchema; no provider call is needed."
    else:
        code, action = "internal_error", "Inspect the local failure before continuing."
    result: dict[str, Any] = {"ok": False, "status": code, "code": code,
                              "error": safe_error_text(error), "next_action": action}
    if status is not None:
        result["http_status"] = status
    if isinstance(error, CredentialRefreshError):
        result["diagnostic_id"] = error.diagnostic_id
        result["helper_exit_status"] = error.exit_status
    return result
