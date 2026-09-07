from __future__ import annotations

import re


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


class DataLensSafetyError(RuntimeError):
    """The requested effect cannot be performed safely with the available evidence."""
