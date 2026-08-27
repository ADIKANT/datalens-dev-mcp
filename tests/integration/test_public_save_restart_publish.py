from __future__ import annotations

import tempfile
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import pytest

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.delivery_transaction_service import DeliveryTransactionService
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import (
    DeliveryContract,
    TargetContract,
    WorkspaceContract,
    create_task_contract,
)
from datalens_dev_mcp.pipeline.task_stage_receipts import build_stage_receipt
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine


class Provider:
    def __init__(self, object_ids: tuple[str, ...], *, omit_saved: frozenset[str] = frozenset()) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.saved = {
            object_id: _entry(object_id, "r2", f"saved-{object_id}")
            for object_id in object_ids
            if object_id not in omit_saved
        }
        self.published = {
            object_id: _entry(object_id, "r2", f"saved-{object_id}")
            for object_id in object_ids
        }

    def rpc_exclusive_read(self, method: str, payload: dict) -> dict:
        self.calls.append((method, deepcopy(payload)))
        object_id = str(payload.get("chartId") or "")
        branch = self.published if payload.get("branch") == "published" else self.saved
        return {"entry": deepcopy(branch.get(object_id) or {})}


class Executor:
    def __init__(self, *, hard_crash: bool = False) -> None:
        self.plans: list[dict] = []
        self.hard_crash = hard_crash

    def __call__(self, plan: dict) -> dict:
        self.plans.append(deepcopy(plan))
        if self.hard_crash:
            self.hard_crash = False
            raise SystemExit("simulated process loss after provider request dispatch")
        actions = [
            {"status": "completed", "write_outcome": "confirmed_write", "revisions": {"write": "r2"}}
            for _ in plan.get("actions") or []
        ]
        return {
            "ok": True,
            "status": "completed",
            "confirmed_write_action_indices": list(range(len(actions))),
            "actions": actions,
        }


def _entry(object_id: str, revision: str, saved_id: str) -> dict:
    return {
        "entryId": object_id,
        "revId": revision,
        "savedId": saved_id,
        "data": {
            "meta": "{}",
            "sources": "module.exports={};",
            "prepare": "module.exports={title:'Synthetic'};",
        },
    }


def _fixture(
    root: Path,
    *,
    publish: bool,
    object_ids: tuple[str, ...] = ("chart_a",),
) -> tuple[ProjectJournal, dict]:
    contract = create_task_contract(
        raw_request="Update and publish synthetic charts" if publish else "Update and save synthetic charts",
        mode="update",
        route="editor_advanced",
        workspace=WorkspaceContract(project_root=str(root)),
        target=TargetContract(
            workbook_id="book_demo",
            object_ids=object_ids,
            object_types=tuple("editor_chart" for _ in object_ids),
        ),
        delivery=DeliveryContract(save=True, publish=publish),
    ).to_dict()
    journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
    journal.initialize(contract)
    write_json(journal.root / "plans" / "plan.json", {"plan_hash": "a" * 64})
    write_json(
        journal.root / "plans" / "safe-apply-plan.json",
        {
            "schema_id": "safe_apply_plan",
            "actions": [
                {
                    "object_id": object_id,
                    "object_type": "editor_chart",
                    "method": "updateEditorChart",
                    "expected_revision": "r1",
                    "payload": {"mode": "save", "entry": _entry(object_id, "r1", f"old-{object_id}")},
                    "fresh_read_method": "getEditorChart",
                    "fresh_read_payload": {"chartId": object_id, "branch": "saved"},
                    "readback_method": "getEditorChart",
                    "readback_payload": {"chartId": object_id, "branch": "saved"},
                    "readback_mode": "full",
                    "readback_required": True,
                }
                for object_id in object_ids
            ],
        },
    )
    return journal, contract


def _generic_handler(context: dict) -> dict:
    return build_stage_receipt(
        task_id=str(context["task_id"]),
        contract_hash=str(context["contract"]["contract_hash"]),
        transition=str(context["transition"]),
        status="success",
        build_identity_hash=str(context["build_identity_hash"]),
        target_binding_hash=str(context["target_binding_hash"]),
    )


def _handlers(
    journal: ProjectJournal,
    contract: dict,
    provider: Provider,
    executor: Callable[[dict], dict],
) -> dict[str, Callable[[dict], dict]]:
    names = (
        "read_baseline",
        "bind_reference",
        "bind_route",
        "plan_data_proof",
        "plan_semantic_change",
        "validate_plan",
        "run_qa",
        "verify_completion",
        "verify_read_only_result",
    )
    handlers = {name: _generic_handler for name in names}
    service = DeliveryTransactionService(journal, contract, client=provider, executor=executor)
    handlers.update(
        {
            "safe_apply_save": service.execute_save_stage,
            "read_saved_state": service.read_saved_stage,
            "publish_from_saved": service.execute_publish_from_saved_stage,
            "read_published_state": service.read_published_stage,
            "reconcile_ambiguous_write": service.reconcile_ambiguous_write,
        }
    )
    return handlers


def _engine(journal: ProjectJournal, contract: dict, handlers: dict) -> WorkflowEngine:
    return WorkflowEngine(
        journal,
        contract,
        handlers=handlers,
        build_identity=read_json(journal.build_identity_path, {}),
        target_binding=read_json(journal.target_binding_path, {}),
        require_typed_receipts=True,
    )


def test_public_save_restart_publish_executes_each_write_once() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root, publish=True)
        provider = Provider(("chart_a",))
        executor = Executor()
        saved = _engine(journal, contract, _handlers(journal, contract, provider, executor)).resume(
            stop_states={"SAVED"}
        )
        assert saved.current_state == "SAVED"
        assert len(executor.plans) == 1

        restarted = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        completed = _engine(
            restarted,
            contract,
            _handlers(restarted, contract, provider, executor),
        ).resume()

        assert completed.current_state == "COMPLETED"
        assert len(executor.plans) == 2
        assert [plan["actions"][0]["payload"]["mode"] for plan in executor.plans] == ["save", "publish"]
        assert [payload["branch"] for _method, payload in provider.calls] == ["saved", "published"]


def test_public_save_only_stops_without_publish() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root, publish=False)
        provider = Provider(("chart_a",))
        executor = Executor()
        completed = _engine(journal, contract, _handlers(journal, contract, provider, executor)).resume()

        assert completed.current_state == "COMPLETED"
        assert len(executor.plans) == 1
        assert executor.plans[0]["actions"][0]["payload"]["mode"] == "save"
        assert not journal.publish_stage_receipt_path.exists()
        assert [payload["branch"] for _method, payload in provider.calls] == ["saved"]


def test_public_ambiguous_save_reconciles_by_read_without_write_replay() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root, publish=False)
        provider = Provider(("chart_a",))
        executor = Executor(hard_crash=True)
        with pytest.raises(SystemExit, match="simulated process loss"):
            _engine(journal, contract, _handlers(journal, contract, provider, executor)).resume()
        assert len(executor.plans) == 1

        restarted = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        completed = _engine(
            restarted,
            contract,
            _handlers(restarted, contract, provider, executor),
        ).resume()

        assert completed.current_state == "COMPLETED"
        assert len(executor.plans) == 1
        assert read_json(restarted.saved_readback_receipt_path, {})["reconciliation"] is True


def test_public_multi_object_missing_saved_readback_blocks_before_publish() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        object_ids = ("chart_a", "chart_b")
        journal, contract = _fixture(root, publish=True, object_ids=object_ids)
        provider = Provider(object_ids, omit_saved=frozenset({"chart_b"}))
        executor = Executor()
        blocked = _engine(journal, contract, _handlers(journal, contract, provider, executor)).resume()

        assert blocked.current_state == "BLOCKED"
        assert len(executor.plans) == 1
        assert not journal.publish_stage_receipt_path.exists()
        objects = read_json(journal.saved_readback_receipt_path, {})["objects"]
        assert [item["complete"] for item in objects] == [True, False]


def test_state_saved_without_a_valid_save_receipt_blocks_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root, publish=False)
        provider = Provider(("chart_a",))
        executor = Executor()
        state = _engine(journal, contract, _handlers(journal, contract, provider, executor)).resume(
            stop_states={"SAVED"}
        )
        assert state.current_state == "SAVED"
        journal.save_stage_receipt_path.write_text("{}", encoding="utf-8")

        restarted = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        blocked = _engine(
            restarted,
            contract,
            _handlers(restarted, contract, provider, executor),
        ).resume()

        assert blocked.current_state == "BLOCKED"
        assert len(executor.plans) == 1
