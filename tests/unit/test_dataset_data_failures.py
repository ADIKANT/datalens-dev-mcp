from __future__ import annotations

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.pipeline.dataset_data_failures import classify_dataset_data_failure


def test_parameter_failure_is_not_misclassified_as_provider_unavailable() -> None:
    exc = DataLensApiError(
        "sanitized",
        http_status=400,
        remote_code="ERR.DS_API.FORMULA.PARAMETER.INVALID_VALUE",
    )
    assert classify_dataset_data_failure(exc) == "parameter_mismatch"


def test_transport_and_server_failures_keep_distinct_families() -> None:
    assert classify_dataset_data_failure(ConnectionError("offline")) == "ConnectionError"
    assert classify_dataset_data_failure(DataLensApiError("server", http_status=500)) == "provider_unavailable"
