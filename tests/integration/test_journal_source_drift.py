from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from datalens_dev_mcp.pipeline.build_identity import build_identity_hash
from datalens_dev_mcp.pipeline.execution_authorization import resolve_execution_authorization
from datalens_dev_mcp.pipeline.project_journal import JournalIdentityError, ProjectJournal
from datalens_dev_mcp.pipeline.target_binding import resolve_contract_target_binding, target_binding_hash
from datalens_dev_mcp.pipeline.task_contract import TargetContract, WorkspaceContract, create_task_contract


def _build(marker: str, *, branch: str = "") -> dict:
    payload = {
        "schema_id": "datalens_build_identity",
        "kind": "git",
        "commit": marker * 40,
        "branch": branch,
        "tree_hash": marker * 40,
        "package_content_hash": marker * 64,
        "package_release": "0.5.0",
        "provenance": {"publication_file_count": 1},
    }
    payload["identity_hash"] = build_identity_hash(payload)
    return payload


def _contract(root: Path) -> dict:
    return create_task_contract(
        raw_request="Update the known synthetic target",
        mode="update",
        route="wizard_native",
        workspace=WorkspaceContract(project_root=str(root)),
        target=TargetContract(dashboard_id="dashboard-a", object_ids=("chart-a",)),
    ).to_dict()


def test_same_release_changed_source_blocks_resume_but_branch_name_does_not() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        target = resolve_contract_target_binding(contract)
        original = _build("a", branch="feature")
        journal.initialize_task(
            contract,
            build_identity=original,
            target_binding=target,
            compile_receipt={"status": "compiled"},
            execution_grant=resolve_execution_authorization(contract),
        )
        renamed = dict(original, branch="renamed")
        journal.assert_write_resume_ready(contract, build_identity=renamed, target_binding=target)
        with pytest.raises(JournalIdentityError, match="SOURCE_IDENTITY_CONFLICT"):
            journal.assert_write_resume_ready(contract, build_identity=_build("b"), target_binding=target)


def test_target_revision_drift_is_not_reported_as_source_drift() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        target = resolve_contract_target_binding(contract)
        build = _build("a")
        journal.initialize_task(
            contract,
            build_identity=build,
            target_binding=target,
            compile_receipt={"status": "compiled"},
            execution_grant=resolve_execution_authorization(contract),
        )
        changed = dict(target, saved_revision="r2")
        changed["binding_hash"] = target_binding_hash(changed)
        with pytest.raises(JournalIdentityError, match="TARGET_BINDING_CONFLICT"):
            journal.assert_write_resume_ready(contract, build_identity=build, target_binding=changed)


def test_legacy_journal_without_build_identity_allows_read_but_blocks_write_resume() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = _contract(root)
        journal = ProjectJournal(root, contract["task_id"], storage_root=root / "journal")
        journal._ensure_layout()
        from datalens_dev_mcp.pipeline.artifacts import write_json
        from datalens_dev_mcp.pipeline.workflow_state import initial_workflow_state

        write_json(journal.contract_path, contract)
        write_json(journal.identity_path, {"contract_hash": contract["contract_hash"]})
        write_json(journal.state_path, initial_workflow_state(contract["task_id"], contract["contract_hash"]).to_dict())
        assert journal.load_contract()["contract_hash"] == contract["contract_hash"]
        with pytest.raises(JournalIdentityError, match="JOURNAL_IDENTITY_UPGRADE_REQUIRED"):
            journal.assert_write_resume_ready(
                contract,
                build_identity=_build("a"),
                target_binding=resolve_contract_target_binding(contract),
            )
