from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from datalens_dev_mcp.pipeline.artifacts import write_json
from datalens_dev_mcp.pipeline.build_identity import build_identity_hash
from datalens_dev_mcp.pipeline.execution_authorization import resolve_execution_authorization
from datalens_dev_mcp.pipeline.project_journal import JournalIdentityError, ProjectJournal, TaskLockError
from datalens_dev_mcp.pipeline.target_binding import create_live_target_binding, resolve_contract_target_binding
from datalens_dev_mcp.pipeline.task_contract import WorkspaceContract, create_task_contract
from datalens_dev_mcp.pipeline.task_identity import build_task_identity


def _contract(root: Path) -> dict:
    return create_task_contract(
        raw_request="Review one synthetic target",
        mode="review",
        route="unresolved",
        workspace=WorkspaceContract(project_root=str(root)),
    ).to_dict()


def _build(marker: str = "a") -> dict:
    payload = {
        "schema_id": "datalens_build_identity",
        "kind": "resource_manifest",
        "commit": "",
        "branch": "",
        "tree_hash": marker * 64,
        "package_content_hash": marker * 64,
        "package_release": "0.5.0",
        "provenance": {"test": True},
    }
    payload["identity_hash"] = build_identity_hash(payload)
    return payload


def _start(journal: ProjectJournal, contract: dict) -> tuple[bool, str]:
    state, receipt, created = journal.initialize_task(
        contract,
        build_identity=_build(),
        target_binding=resolve_contract_target_binding(contract),
        compile_receipt={"status": "compiled", "contract_hash": contract["contract_hash"]},
        execution_grant=resolve_execution_authorization(contract),
    )
    assert state.last_event_id == 1
    return created, receipt


def test_two_identical_concurrent_starts_are_created_once_or_report_busy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journals = [ProjectJournal(root, contract["task_id"], storage_root=root / "journal") for _ in range(2)]

        def attempt(journal: ProjectJournal):
            try:
                return _start(journal, contract)
            except TaskLockError:
                return "busy"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, journals))
        completed = [item for item in outcomes if item != "busy"]
        assert completed
        assert sum(bool(item[0]) for item in completed) == 1
        journal = journals[0]
        assert len(list((journal.root / "receipts").glob("task-compile-*.json"))) == 1
        events = journal.events_path.read_text(encoding="utf-8").splitlines()
        assert len(events) == 1


def test_crash_while_building_snapshot_leaves_no_partial_task(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        from datalens_dev_mcp.pipeline import project_journal as module

        original = module.write_json

        def fail_on_state(path, payload):
            if Path(path).name == "state.json":
                raise RuntimeError("simulated crash between contract and state")
            return original(path, payload)

        monkeypatch.setattr(module, "write_json", fail_on_state)
        with pytest.raises(RuntimeError, match="simulated crash"):
            _start(journal, contract)
        assert not journal.root.exists()
        assert not list((root / "journal").glob(f".{contract['task_id']}.init-*"))


def test_identical_start_after_live_discovery_reuses_persisted_binding_but_write_drift_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        created, _ = _start(journal, contract)
        assert created is True

        live = create_live_target_binding(
            workbook_id="book_demo",
            dashboard_id="",
            object_ids=["chart_demo"],
            object_types=["editor_chart"],
            saved_revision="chart-r1",
            published_revision="",
            payload_hash="a" * 64,
            layout_hash="",
            tabs_hash="",
            technology="editor_advanced",
            target_graph_hash="b" * 64,
        )
        build = _build()
        write_json(journal.target_binding_path, live)
        write_json(
            journal.identity_path,
            build_task_identity(contract, build_identity=build, target_binding=live),
        )

        restarted = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        created_again, receipt = _start(restarted, contract)
        assert created_again is False
        assert receipt

        drifted = create_live_target_binding(
            **{key: value for key, value in live.items() if key not in {"schema_id", "source", "binding_hash", "saved_revision"}},
            saved_revision="chart-r2",
        )
        with pytest.raises(JournalIdentityError, match="TARGET_BINDING_CONFLICT"):
            restarted.assert_write_resume_ready(
                contract,
                build_identity=build,
                target_binding=drifted,
            )
