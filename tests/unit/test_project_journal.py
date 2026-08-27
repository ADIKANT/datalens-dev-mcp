from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from datalens_dev_mcp.pipeline.project_journal import (
    JournalIdentityError,
    ProjectJournal,
    TaskLockError,
    build_journal_identity,
)
from datalens_dev_mcp.pipeline.task_contract import DeliveryContract, WorkspaceContract, create_task_contract


def _contract(root: Path, *, raw: str = "Update the target") -> dict:
    return create_task_contract(
        raw_request=raw,
        mode="update",
        route="wizard_native",
        workspace=WorkspaceContract(project_root=str(root)),
        delivery=DeliveryContract(save=True, publish=True),
    ).to_dict()


class ProjectJournalTests(unittest.TestCase):
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
                with self.assertRaises(TaskLockError):
                    with second.locked(owner="second"):
                        pass
                lease = json.loads(first.lease_path.read_text(encoding="utf-8"))
                self.assertTrue(first.lease_status(now=float(lease["expires_epoch"]) + 1)["stale"])
                first.heartbeat(owner="first-refreshed")
                self.assertEqual(first.lease_status(now=time.time())["owner"], "first-refreshed")
            self.assertFalse(first.lease_status()["present"])


if __name__ == "__main__":
    unittest.main()
