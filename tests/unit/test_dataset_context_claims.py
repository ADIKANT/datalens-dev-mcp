from __future__ import annotations

from datalens_dev_mcp.pipeline.dataset_context_profile import build_dataset_context_profile


def test_sample_uniqueness_never_becomes_global_uniqueness_claim() -> None:
    profile = build_dataset_context_profile(
        dataset_id="dataset_demo",
        workbook_id="",
        dataset_revision="r1",
        query_set_hash="a" * 64,
        schema_hash="b" * 64,
        field_catalog=[{"guid": "id_guid", "name": "id", "type": "string"}],
        rows=[{"id_guid": "a"}, {"id_guid": "b"}],
        pages_read=1,
        requested_limit=100,
        deterministic=False,
    )
    assert "global_uniqueness" in profile["forbidden_claims"]
    assert all("global" not in claim for claim in profile["admissible_claims"])
