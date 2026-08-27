from __future__ import annotations

import tempfile
from pathlib import Path

from datalens_dev_mcp.pipeline.artifacts import read_json
from tests.integration.test_public_save_restart_publish import (
    Executor,
    Provider,
    _engine,
    _fixture,
    _handlers,
)


def test_multi_object_delivery_binds_every_object_in_all_four_receipts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        object_ids = ("chart_a", "chart_b")
        journal, contract = _fixture(root, publish=True, object_ids=object_ids)
        provider = Provider(object_ids)
        executor = Executor()
        completed = _engine(journal, contract, _handlers(journal, contract, provider, executor)).resume()

        assert completed.current_state == "COMPLETED"
        assert [len(plan["actions"]) for plan in executor.plans] == [2, 2]
        for path in (
            journal.save_stage_receipt_path,
            journal.saved_readback_receipt_path,
            journal.publish_stage_receipt_path,
            journal.published_readback_receipt_path,
        ):
            receipt = read_json(path, {})
            observed = receipt.get("objects") or receipt.get("object_statuses")
            assert {item["object_id"] for item in observed} == set(object_ids)
