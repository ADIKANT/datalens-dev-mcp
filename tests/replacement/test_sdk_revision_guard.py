from types import SimpleNamespace

import pytest

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


@pytest.mark.parametrize("publish", [False, True])
def test_replace_rejects_revision_change_during_sdk_target_fetch(publish):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(execute=lambda **_: {"id": "synthetic-chart"})

    client = SimpleNamespace(
        get=SimpleNamespace(dashboard=lambda **_: {"id": "synthetic-chart", "revId": "manual-r2"}),
        raw=SimpleNamespace(replace=SimpleNamespace(dashboard=factory)),
    )
    adapter = SdkAdapter(client=client)
    with pytest.raises(ValueError, match="revision changed"):
        adapter._replace("dashboard", "synthetic-chart", {"revId": "observed-r1", "data": {}}, publish=publish)
    assert calls == []
