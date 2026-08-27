from __future__ import annotations

from collections import Counter
from pathlib import Path
import tempfile

import pytest

from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import DeliveryContract, WorkspaceContract, create_task_contract
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine


def _contract(root: Path) -> dict:
    return create_task_contract(
        raw_request="Update and publish target objects",
        mode="update",
        route="wizard_native",
        workspace=WorkspaceContract(project_root=str(root)),
        delivery=DeliveryContract(save=True, publish=True),
    ).to_dict()


def _handlers(calls: Counter, *, partial_publish: bool = False) -> dict:
    names = (
        "read_baseline", "bind_reference", "bind_route", "plan_data_proof", "plan_semantic_change",
        "validate_plan", "safe_apply_save", "read_saved_state", "publish_from_saved", "read_published_state",
        "run_qa", "verify_completion", "reconcile_ambiguous_write",
    )
    handlers = {}
    for name in names:
        def run(context: dict, current=name) -> dict:
            calls[current] += 1
            if current == "publish_from_saved" and partial_publish:
                return {
                    "status": "partial",
                    "object_statuses": [{"object_id": "a", "status": "published"}, {"object_id": "b", "status": "pending"}],
                }
            if current == "reconcile_ambiguous_write":
                return {"status": "matched", "object_statuses": [{"object_id": "b", "status": "published"}]}
            return {"status": "success", "handler": current}
        handlers[name] = run
    return handlers


def test_new_process_replays_event_written_before_state_checkpoint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        state = journal.initialize(contract)
        original_save = journal.save_state

        def crash_after_event(value):
            raise RuntimeError("simulated process crash")

        journal.save_state = crash_after_event  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="simulated process crash"):
            journal.append_transition(
                state,
                transition="RESOLVED -> BASELINE_READ",
                input_value={},
                receipt_uri="artifact://tasks/x/receipts/1.json",
                status="success",
                idempotency_key="baseline-key",
                next_state="BASELINE_READ",
                next_transition="BASELINE_READ -> REFERENCE_BOUND",
            )
        journal.save_state = original_save  # type: ignore[method-assign]
        restarted = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        replayed, _ = restarted.replay()
        assert replayed.current_state == "BASELINE_READ"
        assert replayed.last_event_id == 2


def test_partial_publish_is_reconciled_and_never_replayed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        calls = Counter()
        state = WorkflowEngine(journal, contract, handlers=_handlers(calls, partial_publish=True)).resume()
        assert state.current_state == "COMPLETED"
        assert calls["publish_from_saved"] == 1
        assert calls["reconcile_ambiguous_write"] == 1
        restarted = WorkflowEngine(journal, contract, handlers=_handlers(calls, partial_publish=True)).resume()
        assert restarted.current_state == "COMPLETED"
        assert calls["publish_from_saved"] == 1


def test_partial_save_is_reconciled_before_publish() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        calls = Counter()
        handlers = _handlers(calls)

        def partial_save(context: dict) -> dict:
            calls["safe_apply_save"] += 1
            return {
                "status": "partial",
                "object_statuses": [{"object_id": "a", "status": "saved"}, {"object_id": "b", "status": "pending"}],
            }

        handlers["safe_apply_save"] = partial_save
        state = WorkflowEngine(journal, contract, handlers=handlers).resume()
        assert state.current_state == "COMPLETED"
        assert calls["safe_apply_save"] == 1
        assert calls["reconcile_ambiguous_write"] == 1
        assert calls["publish_from_saved"] == 1


def test_process_crash_during_saved_readback_resumes_from_saved_receipt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        calls = Counter()
        handlers = _handlers(calls)

        def crash_readback(context: dict) -> dict:
            calls["read_saved_state"] += 1
            raise SystemExit("simulated hard crash")

        handlers["read_saved_state"] = crash_readback
        with pytest.raises(SystemExit, match="simulated hard crash"):
            WorkflowEngine(journal, contract, handlers=handlers).resume()
        assert calls["safe_apply_save"] == 1

        restarted_handlers = _handlers(calls)
        state = WorkflowEngine(journal, contract, handlers=restarted_handlers).resume()
        assert state.current_state == "COMPLETED"
        assert calls["safe_apply_save"] == 1
        assert calls["read_saved_state"] == 2
