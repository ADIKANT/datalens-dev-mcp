import httpx
import pytest
from datalens_sdk import DataLensClientYC

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


@pytest.mark.parametrize("failure", ["timeout", "server_error"])
def test_real_sdk_editor_create_does_not_replay_ambiguous_write(failure):
    requests = []

    def transport(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic lost response", request=request)
        return httpx.Response(503, json={"code": "UNAVAILABLE", "message": "synthetic temporary failure"})

    with DataLensClientYC(auth=None, base_url="https://example.invalid", transport=httpx.MockTransport(transport)) as client:
        error_type = UncertainWriteError if failure == "timeout" else DataLensApiError
        with pytest.raises(error_type) as error:
            SdkAdapter(client=client).create({
                "object_type": "editor_chart", "variant": "control_node", "name": "Synthetic selector",
                "tabs": {"meta.json": "{}", "params.js": "module.exports={};",
                         "controls.js": "module.exports={controls:[]};"},
            }, {"workbook_id": "synthetic-workbook"})
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/createEditorChart")
    if failure == "server_error":
        assert error.value.http_status == 503
        assert error.value.response_received is True
