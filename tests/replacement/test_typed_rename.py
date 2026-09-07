from types import SimpleNamespace

import pytest

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


def test_name_only_update_uses_official_rename_without_raw_replace():
    renamed = []
    current = {"id": "synthetic", "revId": "r1", "name": "Old", "data": {"unknown": "keep"}}
    def rename(name):
        renamed.append(name)
        return {**current, "name": name}
    target = SimpleNamespace(response_snapshot=current, rename=rename)
    client = SimpleNamespace(get=SimpleNamespace(editor_chart=lambda **_: target))
    result = SdkAdapter(client=client).update("editor_chart", "synthetic", {**current, "name": "New"})
    assert renamed == ["New"]
    assert result["object"]["data"] == {"unknown": "keep"}


@pytest.mark.parametrize("rename_fails", [False, True])
def test_mixed_update_saves_then_renames_and_preserves_partial_outcome(rename_fails):
    from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError
    calls = []
    def rename(name):
        calls.append("rename")
        if rename_fails:
            raise DataLensApiError("synthetic rejected", http_status=400, response_received=True)
        return {"id": "synthetic", "name": name, "data": {"changed": True}}
    target = SimpleNamespace(response_snapshot={"id": "synthetic", "name": "Old", "data": {}}, rename=rename)
    def execute():
        calls.append("save")
        return target
    builder = SimpleNamespace(execute=execute)
    builder.mode = lambda _: builder
    client = SimpleNamespace(get=SimpleNamespace(editor_chart=lambda **_: target),
                             raw=SimpleNamespace(replace=SimpleNamespace(editor_chart=lambda **_: builder)))
    adapter = SdkAdapter(client=client)
    if rename_fails:
        with pytest.raises(UncertainWriteError, match="content saved"):
            adapter.update("editor_chart", "synthetic", {"id": "synthetic", "name": "New", "data": {"changed": True}})
    else:
        result = adapter.update("editor_chart", "synthetic", {"id": "synthetic", "name": "New", "data": {"changed": True}})
        assert result["object"]["name"] == "New"
    assert calls == ["save", "rename"]
