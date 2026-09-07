from types import SimpleNamespace

import pytest
from datalens_sdk.errors import APIErrorContext, NotFoundError, DataLensTransportError

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


def test_sdk_read_preserves_confirmed_404():
    def missing(**kwargs):
        raise NotFoundError(APIErrorContext(status_code=404, code="NOT_FOUND", message="Synthetic missing"))
    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(editor_chart=missing)))
    with pytest.raises(DataLensApiError) as caught:
        adapter.get_object("editor_chart", "synthetic")
    assert caught.value.http_status == 404
    assert caught.value.response_received is True


def test_sdk_wrapped_transport_failure_keeps_create_uncertain():
    def build():
        raise DataLensTransportError(method="POST", url="https://example.invalid", attempts=1, reason="timeout")
    client = SimpleNamespace(create=SimpleNamespace(editor_chart=SimpleNamespace(
        selector=lambda **_: SimpleNamespace(meta=lambda _: None, build=build))))
    with pytest.raises(UncertainWriteError):
        SdkAdapter(client=client).create({"name": "Synthetic", "object_type": "editor_chart",
            "variant": "control_node", "tabs": {"meta.json": "{}"}}, {"workbook_id": "synthetic"})
