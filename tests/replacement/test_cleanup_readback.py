import pytest
from test_l08_maintenance import Deleter, Reader

from datalens_dev_mcp.objects.cleanup import CleanupService


def test_preserved_dependency_reached_through_non_candidate_is_kept():
    reader = Reader()
    reader.relations = {
        "dash": [{"id": "middle", "type": "wizard_chart"}],
        "middle": [{"id": "shared", "type": "dataset"}],
        "shared": [],
    }
    result = CleanupService(reader=reader, deleter=Deleter()).preview(
        [{"object_type": "dataset", "object_id": "shared"}],
        preserve_roots=[{"object_type": "dashboard", "object_id": "dash"}],
    )
    assert result["complete"]
    assert result["delete"] == []


def test_incomplete_dependency_preview_cannot_be_applied():
    reader, deleter = Reader(), Deleter()
    reader.object_relations = lambda _: {"complete": False, "relations": []}
    service = CleanupService(reader=reader, deleter=deleter)
    preview = service.preview(
        [{"object_type": "dataset", "object_id": "shared"}],
        preserve_roots=[{"object_type": "dashboard", "object_id": "dash"}],
    )
    with pytest.raises(ValueError, match="complete dependency preview"):
        service.apply(preview, confirmed_delete=preview["delete"])
    assert deleter.calls == []


def test_successful_delete_response_is_not_proof_of_absence():
    service = CleanupService(reader=Reader(), deleter=Deleter())
    preview = service.preview([{"object_type": "dataset", "object_id": "shared"}], preserve_roots=[])
    result = service.apply(preview, confirmed_delete=preview["delete"])
    assert not result["ok"]
    assert result["results"][0]["status"] == "uncertain"
