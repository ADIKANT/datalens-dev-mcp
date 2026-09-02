from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from datalens_dev_mcp.pipeline.project_journal import (
    JournalIdentityError,
    ProjectJournal,
    TaskLockError,
    build_journal_identity,
)
from datalens_dev_mcp.pipeline.task_contract import DeliveryContract, WorkspaceContract, create_task_contract
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine


def _contract(root: Path, *, raw: str = "Update the target") -> dict:
    return create_task_contract(
        raw_request=raw,
        mode="update",
        route="wizard_native",
        workspace=WorkspaceContract(project_root=str(root)),
        delivery=DeliveryContract(save=True, publish=True),
    ).to_dict()


class ProjectJournalTests(unittest.TestCase):
    def test_default_runtime_state_is_external_to_subject_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "subject"
            state = Path(tmp) / "state"
            root.mkdir()
            with patch.dict(
                os.environ,
                {"DATALENS_MCP_TASKS_DIR": "", "XDG_STATE_HOME": str(state)},
                clear=False,
            ):
                journal = ProjectJournal(root, "external-state")
            self.assertEqual(journal.storage_root, (state / "datalens-dev-mcp" / "tasks").resolve())
            self.assertFalse((root / ".datalens-mcp").exists())

    def test_contract_hash_survives_project_path_containing_host_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session_id = "01a04d9d-ac5b-7102-b36b-d35e6ff58862"
            root = Path(tmp) / session_id / "project"
            root.mkdir(parents=True)
            contract = _contract(root)
            journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
            with patch.dict("os.environ", {"CODEX_SESSION_ID": session_id}, clear=False):
                state = journal.initialize(contract)
                journal.assert_resume_identity(contract)
                engine = WorkflowEngine(
                    journal,
                    contract,
                    handlers={"read_baseline": lambda _context: {"status": "success"}},
                    build_identity=json.loads(journal.build_identity_path.read_text(encoding="utf-8")),
                    target_binding=json.loads(journal.target_binding_path.read_text(encoding="utf-8")),
                )
                state = engine.resume(max_transitions=1)
            self.assertEqual(state.contract_hash, contract["contract_hash"])
            self.assertEqual(state.current_state, "BASELINE_READ")
            self.assertEqual(journal.load_contract(), contract)

    def test_project_journal_layout_identity_and_checkpoint_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = _contract(root)
            journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
            state = journal.initialize(contract)

            self.assertEqual(state.current_state, "RESOLVED")
            self.assertTrue(journal.contract_path.is_file())
            self.assertTrue(journal.state_path.is_file())
            self.assertLessEqual(journal.checkpoint_path.stat().st_size, 8192)
            self.assertGreaterEqual(
                {path.name for path in journal.root.iterdir()},
                {"contract.json", "state.json", "checkpoint.md", "plans", "receipts", "snapshots", "evidence", "locks"},
            )

    def test_scope_or_build_change_requires_new_task_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = _contract(root)
            journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
            journal.initialize(contract, identity=build_journal_identity(contract, server_build="build-a"))
            changed = dict(contract)
            changed["contract_hash"] = "0" * 64
            with self.assertRaisesRegex(JournalIdentityError, "scope or contract changed"):
                journal.assert_resume_identity(changed)
            with self.assertRaisesRegex(JournalIdentityError, "server build"):
                journal.assert_resume_identity(
                    contract,
                    identity=build_journal_identity(contract, server_build="build-b"),
                )

    def test_hash_chain_duplicate_suppression_and_corrupt_tail_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = _contract(root)
            journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
            state = journal.initialize(contract)
            state = journal.append_transition(
                state,
                transition="RESOLVED -> BASELINE_READ",
                input_value={"authorization": "Bearer very-secret-token-value"},
                receipt_uri="artifact://receipt/1",
                status="success",
                idempotency_key="key-1",
                next_state="BASELINE_READ",
                next_transition="BASELINE_READ -> REFERENCE_BOUND",
            )
            duplicate = journal.append_transition(
                state,
                transition="RESOLVED -> BASELINE_READ",
                input_value={},
                receipt_uri="artifact://receipt/duplicate",
                status="success",
                idempotency_key="key-1",
                next_state="BASELINE_READ",
                next_transition="BASELINE_READ -> REFERENCE_BOUND",
            )
            self.assertEqual(duplicate.last_event_id, 2)
            self.assertNotIn("very-secret-token-value", journal.events_path.read_text(encoding="utf-8"))

            with journal.events_path.open("a", encoding="utf-8") as handle:
                handle.write('{"broken":')
            replayed, corrupt = journal.replay()
            self.assertTrue(corrupt)
            self.assertEqual(replayed.last_event_id, 2)
            content = journal.events_path.read_text(encoding="utf-8")
            self.assertTrue(content.endswith("\n"))
            self.assertEqual(len(content.splitlines()), 2)

    def test_competing_lock_and_heartbeat_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = _contract(root)
            first = ProjectJournal(root, contract["task_id"], storage_root=root / "journal", lease_seconds=1)
            second = ProjectJournal(root, contract["task_id"], storage_root=root / "journal", lease_seconds=1)
            first.initialize(contract)
            with first.locked(owner="first"):
                self.assertFalse(first.lease_status()["stale"])
                with self.assertRaises(TaskLockError), second.locked(owner="second"):
                    pass
                lease = json.loads(first.lease_path.read_text(encoding="utf-8"))
                self.assertTrue(first.lease_status(now=float(lease["expires_epoch"]) + 1)["stale"])
                first.heartbeat(owner="first-refreshed")
                self.assertEqual(first.lease_status(now=time.time())["owner"], "first-refreshed")
            self.assertFalse(first.lease_status()["present"])


if __name__ == "__main__":
    unittest.main()
