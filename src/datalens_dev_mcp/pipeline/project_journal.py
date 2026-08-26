from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import time
from typing import Any, Iterator

from datalens_dev_mcp import __version__
from datalens_dev_mcp.pipeline.artifacts import append_jsonl, read_json, write_json, write_text
from datalens_dev_mcp.pipeline.task_contract import task_contract_hash
from datalens_dev_mcp.pipeline.evidence_compaction import compact_task_evidence
from datalens_dev_mcp.pipeline.workflow_checkpoint import render_checkpoint
from datalens_dev_mcp.pipeline.workflow_events import create_workflow_event
from datalens_dev_mcp.pipeline.workflow_replay import repair_corrupt_event_tail, replay_workflow
from datalens_dev_mcp.pipeline.workflow_state import WorkflowState, initial_workflow_state
from datalens_dev_mcp.validators.redaction import sanitize_value


TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class JournalError(RuntimeError):
    pass


class JournalIdentityError(JournalError):
    pass


class TaskLockError(JournalError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_journal_identity(
    contract: dict[str, Any],
    *,
    server_build: str = "",
    source_branch: str = "",
    source_tree: str = "",
) -> dict[str, Any]:
    workspace = contract.get("workspace") or {}
    target = contract.get("target") or {}
    return {
        "project_root": str(Path(str(workspace.get("project_root") or ".")).resolve()),
        "portfolio_subproject": str(workspace.get("portfolio_subproject") or ""),
        "target": {
            "workbook_id": str(target.get("workbook_id") or ""),
            "dashboard_id": str(target.get("dashboard_id") or ""),
            "object_ids": sorted(str(item) for item in target.get("object_ids") or []),
        },
        "contract_hash": str(contract.get("contract_hash") or task_contract_hash(contract)),
        "server_package": "datalens-dev-mcp",
        "server_version": __version__,
        "server_build": str(server_build or __version__),
        "source_branch": str(source_branch or ""),
        "source_tree": str(source_tree or ""),
    }


class ProjectJournal:
    def __init__(
        self,
        project_root: str | Path,
        task_id: str,
        *,
        storage_root: str | Path | None = None,
        lease_seconds: float = 30.0,
    ) -> None:
        if not TASK_ID_RE.fullmatch(task_id):
            raise ValueError("task_id contains unsafe path characters")
        self.project_root = Path(project_root).resolve()
        configured = storage_root or os.environ.get("DATALENS_MCP_TASKS_DIR")
        base = Path(configured) if configured else self.project_root / ".datalens-mcp" / "tasks"
        if not base.is_absolute():
            base = self.project_root / base
        self.storage_root = base.resolve()
        self.task_id = task_id
        self.root = self.storage_root / task_id
        self.contract_path = self.root / "contract.json"
        self.state_path = self.root / "state.json"
        self.events_path = self.root / "events.jsonl"
        self.checkpoint_path = self.root / "checkpoint.md"
        self.compact_context_path = self.root / "compact-context.json"
        self.identity_path = self.root / "identity.json"
        self.lock_path = self.root / "locks" / "task.lock"
        self.lease_path = self.root / "locks" / "lease.json"
        self.lease_seconds = max(1.0, float(lease_seconds))
        self._lock_handle: Any = None
        self._lock_depth = 0

    def initialize(self, contract: dict[str, Any], *, identity: dict[str, Any] | None = None) -> WorkflowState:
        self._ensure_layout()
        safe_contract = sanitize_value(contract)
        if str(safe_contract.get("task_id") or "") != self.task_id:
            raise JournalIdentityError("contract task_id does not match journal task_id")
        digest = str(safe_contract.get("contract_hash") or "")
        if digest != task_contract_hash(safe_contract):
            raise JournalIdentityError("contract hash is invalid")
        expected = identity or build_journal_identity(safe_contract)
        if self.contract_path.exists():
            self.assert_resume_identity(safe_contract, identity=expected)
            state, _ = self.replay()
            return state
        write_json(self.contract_path, safe_contract)
        write_json(self.identity_path, sanitize_value(expected))
        state = initial_workflow_state(self.task_id, digest)
        self.save_state(state)
        self.write_checkpoint(state)
        return state

    def assert_resume_identity(self, contract: dict[str, Any], *, identity: dict[str, Any] | None = None) -> None:
        existing_contract = read_json(self.contract_path, {}) or {}
        existing_identity = read_json(self.identity_path, {}) or {}
        requested = identity or build_journal_identity(contract)
        if existing_contract.get("contract_hash") != contract.get("contract_hash"):
            raise JournalIdentityError("task scope or contract changed; create a new task revision")
        if existing_identity != sanitize_value(requested):
            raise JournalIdentityError("project, target, server build, or source tree changed; create a new task revision")

    def load_contract(self) -> dict[str, Any]:
        value = read_json(self.contract_path, {}) or {}
        if not value:
            raise JournalError("journal contract is missing")
        return value

    def load_state(self) -> WorkflowState:
        value = read_json(self.state_path, {}) or {}
        if not value:
            contract = self.load_contract()
            return initial_workflow_state(self.task_id, str(contract.get("contract_hash") or ""))
        return WorkflowState.from_dict(value)

    def save_state(self, state: WorkflowState) -> None:
        write_json(self.state_path, sanitize_value(state.to_dict()))

    def replay(self) -> tuple[WorkflowState, bool]:
        contract = self.load_contract()
        state, corrupt_tail = replay_workflow(
            events_path=self.events_path,
            task_id=self.task_id,
            contract_hash=str(contract.get("contract_hash") or ""),
        )
        if corrupt_tail:
            repair_corrupt_event_tail(self.events_path)
        self.save_state(state)
        self.write_checkpoint(state)
        return state, corrupt_tail

    def append_transition(
        self,
        state: WorkflowState,
        *,
        transition: str,
        input_value: Any,
        receipt_uri: str,
        status: str,
        idempotency_key: str,
        next_state: str,
        next_transition: str,
        blocker: dict[str, Any] | None = None,
        reconciliation: dict[str, Any] | None = None,
        event_details: dict[str, Any] | None = None,
    ) -> WorkflowState:
        if status == "success" and idempotency_key in state.successful_idempotency_keys:
            return state
        event = create_workflow_event(
            event_id=state.last_event_id + 1,
            previous_hash=state.last_event_hash,
            task_id=self.task_id,
            transition=transition,
            input_value=input_value,
            result_receipt=receipt_uri,
            status=status,
            timestamp=utc_now(),
            idempotency_key=idempotency_key,
            details={
                **(event_details or {}),
                "next_state": next_state,
                "next_transition": next_transition,
                "blocker": blocker or {},
                "reconciliation": reconciliation or {},
            },
        )
        append_jsonl(self.events_path, event)
        completed = state.completed_transitions + ((transition,) if status == "success" else ())
        keys = state.successful_idempotency_keys + ((idempotency_key,) if status == "success" else ())
        receipts = state.receipt_uris + ((receipt_uri,) if receipt_uri and receipt_uri not in state.receipt_uris else ())
        updated = replace(
            state,
            current_state=next_state,
            next_transition=next_transition,
            completed_transitions=completed,
            successful_idempotency_keys=keys,
            receipt_uris=receipts,
            blocker=sanitize_value(blocker or {}),
            reconciliation=sanitize_value(reconciliation or {}),
            last_event_id=int(event["event_id"]),
            last_event_hash=str(event["event_hash"]),
            revision=state.revision + 1,
        )
        self.save_state(updated)
        self.write_checkpoint(updated)
        return updated

    def receipt_uri(self, relative: str) -> str:
        clean = Path(relative)
        if clean.is_absolute() or ".." in clean.parts:
            raise ValueError("journal artifact path must be relative")
        return f"artifact://tasks/{self.task_id}/{clean.as_posix()}"

    def write_receipt(self, name: str, payload: dict[str, Any]) -> str:
        relative = Path("receipts") / f"{name}.json"
        write_json(self.root / relative, sanitize_value(payload))
        return self.receipt_uri(relative.as_posix())

    def write_checkpoint(self, state: WorkflowState) -> None:
        if not self.contract_path.exists():
            return
        contract = self.load_contract()
        criteria = [str(item.get("statement") or "") for item in contract.get("acceptance") or []]
        write_text(
            self.checkpoint_path,
            render_checkpoint(contract=contract, state=state.to_dict(), completion_criteria=criteria),
        )
        write_json(
            self.compact_context_path,
            compact_task_evidence(
                policy_version=__version__,
                task_contract=contract,
                target_binding=contract.get("target") or {},
                style_binding=contract.get("style_binding") or {},
                checkpoint=state.to_dict(),
                active_blocker=state.blocker,
                next_transition=state.next_transition,
                artifact_root=self.root,
            ),
        )

    @contextmanager
    def locked(self, *, owner: str = "") -> Iterator[None]:
        if self._lock_depth:
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return
        self._ensure_layout()
        handle = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise TaskLockError("task journal is already locked by another process") from exc
        self._lock_handle = handle
        self._lock_depth = 1
        self.heartbeat(owner=owner)
        try:
            yield
        finally:
            self._lock_depth = 0
            self._lock_handle = None
            self.lease_path.unlink(missing_ok=True)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def heartbeat(self, *, owner: str = "") -> None:
        now = time.time()
        write_json(
            self.lease_path,
            {
                "schema_id": "datalens_workflow_lease",
                "task_id": self.task_id,
                "owner": owner or f"{socket.gethostname()}:{os.getpid()}",
                "pid": os.getpid(),
                "heartbeat_epoch": now,
                "expires_epoch": now + self.lease_seconds,
            },
        )

    def lease_status(self, *, now: float | None = None) -> dict[str, Any]:
        lease = read_json(self.lease_path, {}) or {}
        if not lease:
            return {"present": False, "stale": False}
        current = time.time() if now is None else now
        return {**lease, "present": True, "stale": current > float(lease.get("expires_epoch") or 0)}

    def _ensure_layout(self) -> None:
        for relative in ("plans", "receipts", "snapshots", "evidence", "locks"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
