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


def test_mixed_name_content_update_is_not_silently_partially_applied():
    target = SimpleNamespace(response_snapshot={"id": "synthetic", "name": "Old", "data": {}},
                             rename=lambda _: pytest.fail("unexpected rename"))
    client = SimpleNamespace(get=SimpleNamespace(editor_chart=lambda **_: target))
    with pytest.raises(ValueError, match="separate explicit updates"):
        SdkAdapter(client=client).update("editor_chart", "synthetic", {"id": "synthetic", "name": "New", "data": {"changed": True}})
