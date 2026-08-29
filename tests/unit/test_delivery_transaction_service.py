from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from datalens_dev_mcp.mcp.task_resources import read_task_resource, task_resource_uri
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.delivery_transaction_service import (
    DeliveryTransactionService,
    _attempt_marker,
    _read_payload,
)
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import (
    DeliveryContract,
    TargetContract,
    WorkspaceContract,
    create_task_contract,
)
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


class DeliveryClient:
    def __init__(self, object_ids: tuple[str, ...] = ("chart_a",)) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.saved = {object_id: _entry(object_id, "r2", f"saved-{object_id}") for object_id in object_ids}
        self.published = {object_id: _entry(object_id, "r2", f"saved-{object_id}") for object_id in object_ids}

    def rpc_exclusive_read(self, method: str, payload: dict) -> dict:
        self.calls.append((method, deepcopy(payload)))
        object_id = str(payload.get("chartId") or "")
        values = self.published if payload.get("branch") == "published" else self.saved
        return {"entry": deepcopy(values.get(object_id) or {})}


class DeliveryExecutor:
    def __init__(self) -> None:
        self.plans: list[dict] = []

    def __call__(self, plan: dict) -> dict:
        self.plans.append(deepcopy(plan))
        actions = []
        for item in plan.get("actions") or []:
            actions.append(
                {
                    "status": "completed",
                    "write_outcome": "confirmed_write",
                    "revisions": {"write": "r2"},
                }
            )
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
            "prepare": "module.exports={title:'Revenue'};",
        },
    }


def _fixture(root: Path, *, publish: bool = True, object_ids: tuple[str, ...] = ("chart_a",)) -> tuple[ProjectJournal, dict]:
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
    journal = ProjectJournal(root, contract["task_id"])
    journal.initialize(contract)
    plan_hash = "a" * 64
    write_json(journal.root / "plans" / "plan.json", {"plan_hash": plan_hash})
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


def _context(journal: ProjectJournal, transition: str) -> dict:
    return {
        "transition": transition,
        "build_identity_hash": str((read_json(journal.build_identity_path, {}) or {}).get("identity_hash") or ""),
        "target_binding_hash": str((read_json(journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
    }


def test_save_readback_publish_readback_are_four_separate_idempotent_stages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root)
        client = DeliveryClient()
        client.saved["chart_a"]["data"]["providerExtension"] = {"businessLabel": "Preserve exactly"}
        client.published["chart_a"] = deepcopy(client.saved["chart_a"])
        executor = DeliveryExecutor()
        service = DeliveryTransactionService(journal, contract, client=client, executor=executor)
        save = service.execute_save_stage(_context(journal, "VALIDATED -> SAVED"))
        restarted = DeliveryTransactionService(journal, contract, client=client, executor=executor)
        save_replay = restarted.execute_save_stage(_context(journal, "VALIDATED -> SAVED"))
        saved = restarted.read_saved_stage(_context(journal, "SAVED -> SAVED_READBACK"))
        publish = restarted.execute_publish_from_saved_stage(_context(journal, "SAVED_READBACK -> PUBLISHED"))
        published = restarted.read_published_stage(_context(journal, "PUBLISHED -> PUBLISHED_READBACK"))
        receipts = [
            read_json(journal.save_stage_receipt_path, {}),
            read_json(journal.saved_readback_receipt_path, {}),
            read_json(journal.publish_stage_receipt_path, {}),
            read_json(journal.published_readback_receipt_path, {}),
        ]
        save_attempt = read_json(journal.delivery_root / "save-stage-attempt.json", {})
        publish_attempt = read_json(journal.delivery_root / "publish-stage-attempt.json", {})
    assert [save["status"], save_replay["status"], saved["status"], publish["status"], published["status"]] == [
        "success", "success", "success", "success", "success"
    ]
    assert len(executor.plans) == 2
    assert all(action["readback_mode"] == "none" for plan in executor.plans for action in plan["actions"])
    assert executor.plans[1]["actions"][0]["payload"]["entry"]["data"]["providerExtension"] == {
        "businessLabel": "Preserve exactly"
    }
    for marker, phase, expected_revision in (
        (save_attempt, "save", "r1"),
        (publish_attempt, "publish", "r2"),
    ):
        assert marker["task_id"] == journal.task_id
        assert marker["contract_revision"] == 1
        assert marker["scope_revision"] == 1
        assert marker["authorization_revision"] == 1
        assert marker["phase"] == phase
        assert marker["object_id"] == "chart_a"
        assert marker["expected_provider_revision"] == expected_revision
        assert marker["attempt_id"]
        assert marker["idempotency_key"]
        assert marker["dispatched_at"]
        assert marker["resolved_at"]
        assert marker["final_receipt_hash"]
        assert marker["status"] == "completed"
        assert len(marker["attempts"]) == 1
    for receipt, phase, expected_revision in (
        (receipts[0], "save", "r1"),
        (receipts[2], "publish", "r2"),
    ):
        assert receipt["receipt_version"] == 2
        assert receipt["contract_revision"] == 1
        assert receipt["scope_revision"] == 1
        assert receipt["authorization_revision"] == 1
        assert receipt["phase"] == phase
        assert receipt["plan_hash"]
        assert receipt["object_id"] == "chart_a"
        assert receipt["expected_provider_revision"] == expected_revision
        assert receipt["attempt_id"]
        assert receipt["idempotency_key"]
        assert receipt["dispatched_at"]
        assert receipt["resolved_at"]
    assert [payload["branch"] for _method, payload in client.calls] == ["saved", "published"]
    for receipt, schema_name in zip(
        receipts,
        (
            "save-stage-receipt.schema.json",
            "saved-readback-receipt.schema.json",
            "publish-stage-receipt.schema.json",
            "published-readback-receipt.schema.json",
        ),
        strict=True,
    ):
        schema = read_json(Path(__file__).resolve().parents[2] / "schemas" / schema_name, {})
        assert not list(Draft202012Validator(schema).iter_errors(receipt))


def test_started_attempt_without_final_receipt_never_replays_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root)
        safe_plan = read_json(journal.root / "plans" / "safe-apply-plan.json", {})
        attempt = _attempt_marker(
            "save",
            task_id=journal.task_id,
            contract=contract,
            plan_hash="a" * 64,
            execution_plan_hash=canonical_hash(safe_plan),
            actions=list(safe_plan.get("actions") or []),
        )
        write_json(journal.delivery_root / "save-stage-attempt.json", attempt)
        executor = DeliveryExecutor()
        result = DeliveryTransactionService(
            journal,
            contract,
            client=DeliveryClient(),
            executor=executor,
        ).execute_save_stage(_context(journal, "VALIDATED -> SAVED"))
        final_attempt = read_json(journal.delivery_root / "save-stage-attempt.json", {})
        ambiguous_receipt = read_json(journal.save_stage_receipt_path, {})
    assert result["status"] == "ambiguous"
    assert executor.plans == []
    assert ambiguous_receipt["attempt_id"] == attempt["attempt_id"]
    assert final_attempt["status"] == "ambiguous"
    assert final_attempt["final_receipt_hash"] == ambiguous_receipt["receipt_hash"]


def test_resolved_prior_revision_attempt_does_not_block_amended_save() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root)
        executor = DeliveryExecutor()
        first = DeliveryTransactionService(
            journal,
            contract,
            client=DeliveryClient(),
            executor=executor,
        ).execute_save_stage(_context(journal, "VALIDATED -> SAVED"))
        prior_receipt = read_json(journal.save_stage_receipt_path, {})
        prior_attempt = read_json(journal.delivery_root / "save-stage-attempt.json", {})

        amended = deepcopy(contract)
        amended["contract_revision"] = 2
        amended["parent_contract_hash"] = contract["contract_hash"]
        amended["contract_hash"] = "b" * 64
        amended_plan_hash = "c" * 64
        write_json(journal.root / "plans" / "plan.json", {"plan_hash": amended_plan_hash})
        second = DeliveryTransactionService(
            journal,
            amended,
            client=DeliveryClient(),
            executor=executor,
        ).execute_save_stage(_context(journal, "VALIDATED -> SAVED"))
        current_attempt = read_json(journal.delivery_root / "save-stage-attempt.json", {})

    assert first["status"] == "success"
    assert prior_receipt["status"] == "success"
    assert prior_attempt["plan_hash"] != amended_plan_hash
    assert prior_attempt["contract_revision"] == 1
    assert prior_attempt["status"] == "completed"
    assert prior_attempt["final_receipt_hash"] == prior_receipt["receipt_hash"]
    assert second["status"] == "success"
    assert len(executor.plans) == 2
    assert current_attempt["plan_hash"] == amended_plan_hash
    assert current_attempt["contract_revision"] == 2
    assert current_attempt["attempt_id"] != prior_attempt["attempt_id"]


def test_readback_branch_is_only_sent_to_branch_aware_provider_methods() -> None:
    dataset = {
        "readback_method": "getDataset",
        "readback_payload": {"datasetId": "dataset_a", "workbookId": "book_demo", "branch": "saved"},
    }
    wizard = {
        "readback_method": "getWizardChart",
        "readback_payload": {"chartId": "chart_a"},
    }

    assert _read_payload(dataset, "published") == {
        "datasetId": "dataset_a",
        "workbookId": "book_demo",
    }
    assert _read_payload(wizard, "published") == {"chartId": "chart_a", "branch": "published"}


def test_stale_revision_is_conflict_with_zero_confirmed_writes() -> None:
    def stale_executor(plan: dict) -> dict:
        return {
            "ok": False,
            "status": "failed",
            "actions": [
                {
                    "status": "failed",
                    "write_outcome": "no_write",
                    "error": {"category": "stale_revision", "write_outcome": "no_write"},
                }
            ],
        }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root)
        result = DeliveryTransactionService(
            journal,
            contract,
            client=DeliveryClient(),
            executor=stale_executor,
        ).execute_save_stage(_context(journal, "VALIDATED -> SAVED"))
        receipt = read_json(journal.save_stage_receipt_path, {})
    assert result["status"] == "conflict"
    assert receipt["write_count"] == 0
    assert receipt["reason"] == "stale_revision"


def test_saved_and_published_receipt_schemas_are_not_interchangeable() -> None:
    saved_schema = read_json(Path(__file__).resolve().parents[2] / "schemas" / "saved-readback-receipt.schema.json", {})
    published_schema = read_json(
        Path(__file__).resolve().parents[2] / "schemas" / "published-readback-receipt.schema.json", {}
    )
    assert saved_schema["properties"]["schema_id"]["const"] != published_schema["properties"]["schema_id"]["const"]
    assert saved_schema["properties"]["branch"]["const"] == "saved"
    assert published_schema["properties"]["branch"]["const"] == "published"


def test_publish_requires_a_verified_saved_readback_receipt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root)
        executor = DeliveryExecutor()
        result = DeliveryTransactionService(
            journal,
            contract,
            client=DeliveryClient(),
            executor=executor,
        ).execute_publish_from_saved_stage(_context(journal, "SAVED_READBACK -> PUBLISHED"))
    assert result["status"] == "blocked"
    assert executor.plans == []


def test_private_publish_source_and_execution_plan_are_not_task_resources() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract = _fixture(root)
        client = DeliveryClient()
        executor = DeliveryExecutor()
        service = DeliveryTransactionService(journal, contract, client=client, executor=executor)
        service.execute_save_stage(_context(journal, "VALIDATED -> SAVED"))
        service.read_saved_stage(_context(journal, "SAVED -> SAVED_READBACK"))
        service.execute_publish_from_saved_stage(_context(journal, "SAVED_READBACK -> PUBLISHED"))

        assert journal.publish_execution_plan_path.is_file()
        for suffix in (
            "delivery/private/saved-readback-source.json",
            "delivery/private/publish-execution-plan.json",
        ):
            with pytest.raises(KeyError, match="bounded plans, receipts, snapshots, or evidence"):
                read_task_resource(task_resource_uri(journal.task_id, suffix), project_root=root)
