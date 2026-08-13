from __future__ import annotations


class DataLensApiError(RuntimeError):
    """Raised for sanitized DataLens API failures."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        remote_code: str = "",
        request_phase: str = "",
        response_received: bool | None = None,
        transport_category: str = "",
        retry_attempts: int = 0,
        retry_exhausted: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.remote_code = str(remote_code or "")
        self.request_phase = str(request_phase or "")
        self.response_received = response_received
        self.transport_category = str(transport_category or "")
        self.retry_attempts = max(0, int(retry_attempts))
        self.retry_exhausted = retry_exhausted


class DataLensSafetyError(RuntimeError):
    """Raised when a guarded operation is blocked by policy."""
