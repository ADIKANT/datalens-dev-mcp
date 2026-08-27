from __future__ import annotations

from typing import Any


def classify_dataset_data_failure(exc: BaseException) -> str:
    remote_code = str(getattr(exc, "remote_code", "") or "").upper()
    http_status = getattr(exc, "http_status", None)
    if "FORMULA.PARAMETER" in remote_code:
        return "parameter_mismatch"
    if isinstance(http_status, int) and http_status == 400:
        if any(token in remote_code for token in ("FIELD", "SCHEMA", "COLUMN")):
            return "schema_field_mismatch"
        return "request_rejected"
    if isinstance(http_status, int) and http_status in {401, 403}:
        return "access_denied"
    if isinstance(http_status, int) and http_status >= 500:
        return "provider_unavailable"
    return exc.__class__.__name__


def dataset_failure_receipt(exc: BaseException) -> dict[str, Any]:
    return {
        "error_family": classify_dataset_data_failure(exc),
        "http_status": getattr(exc, "http_status", None),
        "remote_code": str(getattr(exc, "remote_code", "") or ""),
    }
