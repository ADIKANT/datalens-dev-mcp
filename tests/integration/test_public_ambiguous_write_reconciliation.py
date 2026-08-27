from __future__ import annotations

import json
import tempfile
from pathlib import Path

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from tests.integration.test_public_save_restart_publish import (
    Executor,
    Provider,
    _engine,
    _fixture,
    _handlers,
)


def test_ambiguous_publish_reconciles_published_only_without_replaying_publish() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root, publish=True)
        provider = Provider(("chart_a",))
        executor = Executor()
        saved = _engine(journal, contract, _handlers(journal, contract, provider, executor)).resume(
            stop_states={"SAVED_READBACK"}
        )
        assert saved.current_state == "SAVED_READBACK"
        assert len(executor.plans) == 1

        publish_plan_path = journal.root / "plans" / "publish-safe-apply-plan.json"
        service_handlers = _handlers(journal, contract, provider, executor)
        publish_result = service_handlers["publish_from_saved"](
            {
                "task_id": journal.task_id,
                "contract": contract,
                "state": saved.to_dict(),
                "transition": "SAVED_READBACK -> PUBLISHED",
                "build_identity_hash": read_json(journal.build_identity_path, {})["identity_hash"],
                "target_binding_hash": read_json(journal.target_binding_path, {})["binding_hash"],
            }
        )
        assert publish_result["status"] == "success"
        assert len(executor.plans) == 2
        journal.publish_stage_receipt_path.unlink()
        write_json(
            journal.delivery_root / "publish-stage-attempt.json",
            {"schema_id": "datalens_delivery_write_attempt", "status": "started"},
        )
        assert publish_plan_path.is_file()

        restarted = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        completed = _engine(
            restarted,
            contract,
            _handlers(restarted, contract, provider, executor),
        ).resume()

        assert completed.current_state == "COMPLETED", json.dumps(completed.to_dict(), indent=2)
        assert len(executor.plans) == 2
        receipt = read_json(restarted.published_readback_receipt_path, {})
        assert receipt["reconciliation"] is True
        assert [payload["branch"] for _method, payload in provider.calls][-1] == "published"


def test_publish_timeout_reconciles_exact_phase_without_a_second_publish() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root, publish=True)
        provider = Provider(("chart_a",))
        base_executor = Executor()
        dispatched: list[dict] = []

        def timeout_on_publish(plan: dict) -> dict:
            dispatched.append(plan)
            if plan["actions"][0]["payload"]["mode"] == "publish":
                raise TimeoutError("provider response lost after publish dispatch")
            return base_executor(plan)

        completed = _engine(
            journal,
            contract,
            _handlers(journal, contract, provider, timeout_on_publish),
        ).resume()

        assert completed.current_state == "COMPLETED", json.dumps(completed.to_dict(), indent=2)
        assert len(dispatched) == 2
        assert [plan["actions"][0]["payload"]["mode"] for plan in dispatched] == ["save", "publish"]
        assert read_json(journal.published_readback_receipt_path, {})["reconciliation"] is True
