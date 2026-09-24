from types import SimpleNamespace

import pytest
from datalens_sdk.errors import APIErrorContext, DataLensTransportError, NotFoundError

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


@pytest.mark.parametrize("code", ["operation_budget_exhausted", "operation_cancelled"])
def test_dispatched_read_keeps_budget_barrier_evidence(code):
    import httpx

    from datalens_dev_mcp.api.budget import operation_budget
    from datalens_dev_mcp.api.errors import error_response
    from datalens_dev_mcp.api.sdk_adapter import _BudgetedStream

    response = httpx.Response(200, stream=httpx.ByteStream(b"{}"),
                              request=httpx.Request("POST", "https://example.invalid/rpc/getDashboard"),
                              headers={"x-request-id": "read-receipt", "x-trace-id": "read-trace"})
    with operation_budget() as budget:
        if code == "operation_cancelled":
            budget.cancelled.set()
        else:
            budget.deadline = budget.started
        with pytest.raises(DataLensApiError) as caught:
            list(_BudgetedStream(response, budget))
    result = error_response(caught.value)
    assert result["status"] == code
    assert result["dispatch_state"] == "dispatched"
    assert result["response_received"] is True
    assert result["stage"] == "response_read"
    assert result["method"] == "getDashboard"
    assert result["http_status"] == 200
    assert result["request_id"] == "read-receipt"
    assert result["trace_id"] == "read-trace"
    assert "effect_outcome" not in result
    from datalens_dev_mcp.objects.cleanup import _relation_failure

    relation_issue = error_response(_relation_failure(result, "dependencies"))
    assert relation_issue == result
    write_result = error_response(caught.value, effect_possible=True)
    assert write_result["status"] == "write_outcome_unknown"
    assert write_result["effect_outcome"] == "unknown"


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

    client = SimpleNamespace(
        create=SimpleNamespace(
            editor_chart=SimpleNamespace(selector=lambda **_: SimpleNamespace(meta=lambda _: None, build=build))
        )
    )
    with pytest.raises(UncertainWriteError):
        SdkAdapter(client=client).create(
            {
                "name": "Synthetic",
                "object_type": "editor_chart",
                "variant": "control_node",
                "tabs": {"meta.json": "{}"},
            },
            {"workbook_id": "synthetic"},
        )


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_preparatory_sdk_read_failure_is_not_dispatched(operation):
    def fail(**kwargs):
        raise DataLensTransportError(method="POST", url="https://example.invalid", attempts=1, reason="timeout")

    adapter = SdkAdapter(client=SimpleNamespace(get=SimpleNamespace(dataset=fail, connection=fail)))
    with pytest.raises(DataLensApiError) as caught:
        if operation == "create":
            adapter.create({"object_type": "dataset", "name": "Synthetic",
                            "dataset": {"connection_id": "synthetic"}}, {"workbook_id": "synthetic"})
        elif operation == "update":
            adapter.update("dataset", "synthetic", {})
        else:
            adapter.delete("dataset", "synthetic")
    from datalens_dev_mcp.api.errors import error_response

    result = error_response(caught.value, effect_possible=True)
    assert result["dispatch_state"] == "not_dispatched"
    assert result["effect_outcome"] == "not_applied"
    assert result["code"] != "write_outcome_unknown"


@pytest.mark.parametrize("phase", ["build_validation", "response_lost", "rejected"])
def test_owned_sdk_request_hook_distinguishes_build_from_dispatch(monkeypatch, phase):
    import datalens_sdk
    import httpx

    from datalens_dev_mcp.api.errors import error_response
    from datalens_dev_mcp.config import DataLensConfig

    requests = []
    original_client = datalens_sdk.DataLensClientYC

    def handle(request):
        requests.append(request)
        if phase == "response_lost":
            raise httpx.ReadTimeout("synthetic lost response", request=request)
        return httpx.Response(409, json={"code": "CONFLICT", "message": "Synthetic conflict"})

    def client(**kwargs):
        return original_client(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(datalens_sdk, "DataLensClientYC", client)
    adapter = SdkAdapter(DataLensConfig(org_id="synthetic", iam_token="synthetic"))
    draft = {"object_type": "editor_chart", "name": "Synthetic", "variant": "control_node",
             "tabs": {"meta.json": "{}",
                      "params.js": "module.exports={};", "controls.js": "module.exports={controls:[]};"}}
    if phase == "build_validation":
        draft = {"object_type": "dataset", "name": "Synthetic", "snapshot": {"invalid": "value"}}
    try:
        with pytest.raises(Exception) as caught:
            adapter.create(draft, {"workbook_id": "synthetic"})
        result = error_response(caught.value, effect_possible=True)
        assert len(requests) == (0 if phase == "build_validation" else 1)
        assert result["effect_outcome"] == ("unknown" if phase == "response_lost" else "not_applied")
    finally:
        adapter.close()
