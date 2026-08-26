from __future__ import annotations

from collections import Counter
from pathlib import Path
import tempfile
import unittest

from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.task_contract import DeliveryContract, WorkspaceContract, create_task_contract
from datalens_dev_mcp.pipeline.workflow_engine import WorkflowEngine


HANDLER_NAMES = (
    "read_baseline", "bind_reference", "bind_route", "plan_data_proof", "plan_semantic_change",
    "validate_plan", "safe_apply_save", "read_saved_state", "publish_from_saved", "read_published_state",
    "run_qa", "verify_completion", "verify_read_only_result", "reconcile_ambiguous_write",
)


def _contract(root: Path, *, save: bool = True, publish: bool = True) -> dict:
    return create_task_contract(
        raw_request="Update and publish the known target",
        mode="update",
        route="wizard_native",
        workspace=WorkspaceContract(project_root=str(root)),
        delivery=DeliveryContract(save=save, publish=publish),
    ).to_dict()


def _handlers(counter: Counter, overrides: dict | None = None) -> dict:
    def handler(name: str):
        def run(context: dict) -> dict:
            counter[name] += 1
            return {"status": "success", "handler": name, "revision": counter[name]}
        return run
    values = {name: handler(name) for name in HANDLER_NAMES}
    values.update(overrides or {})
    return values


class WorkflowEngineTests(unittest.TestCase):
    def test_engine_resumes_after_plan_without_repeating_completed_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = _contract(root)
            journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
            calls = Counter()
            first = WorkflowEngine(journal, contract, handlers=_handlers(calls)).resume(max_transitions=5)
            self.assertEqual(first.current_state, "SEMANTIC_PLAN_READY")
            second = WorkflowEngine(journal, contract, handlers=_handlers(calls)).resume()
            self.assertEqual(second.current_state, "COMPLETED")
            self.assertTrue(all(count == 1 for count in calls.values()))

    def test_ambiguous_save_reconciles_before_any_second_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = _contract(root, publish=False)
            journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
            calls = Counter()

            def ambiguous_save(context: dict) -> dict:
                calls["safe_apply_save"] += 1
                raise TimeoutError("connection ended after request upload")

            def reconcile(context: dict) -> dict:
                calls["reconcile_ambiguous_write"] += 1
                return {"status": "matched", "actual_revision": "saved-r2"}

            state = WorkflowEngine(
                journal,
                contract,
                handlers=_handlers(calls, {"safe_apply_save": ambiguous_save, "reconcile_ambiguous_write": reconcile}),
            ).resume()
            self.assertEqual(state.current_state, "COMPLETED")
            self.assertEqual(calls["safe_apply_save"], 1)
            self.assertEqual(calls["reconcile_ambiguous_write"], 1)

    def test_external_revision_change_blocks_with_semantic_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = _contract(root, publish=False)
            journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
            calls = Counter()

            def conflict(context: dict) -> dict:
                calls["read_saved_state"] += 1
                return {
                    "status": "conflict",
                    "expected_revision": "r1",
                    "actual_revision": "r2",
                    "semantic_diff": {"changed": ["chart-a"]},
                }

            state = WorkflowEngine(
                journal,
                contract,
                handlers=_handlers(calls, {"read_saved_state": conflict}),
            ).resume()
            self.assertEqual(state.current_state, "BLOCKED_CONFLICT")
            self.assertEqual(state.blocker["semantic_diff"], {"changed": ["chart-a"]})


if __name__ == "__main__":
    unittest.main()
