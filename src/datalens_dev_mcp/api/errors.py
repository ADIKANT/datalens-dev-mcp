from __future__ import annotations


class DataLensApiError(RuntimeError):
    """Raised for sanitized DataLens API failures."""


class DataLensSafetyError(RuntimeError):
    """Raised when a guarded operation is blocked by policy."""
