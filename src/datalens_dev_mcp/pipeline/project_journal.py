from __future__ import annotations

import fcntl
import os
import re
import shutil
import socket
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datalens_dev_mcp import __version__
from datalens_dev_mcp.pipeline.artifacts import append_jsonl, read_json, write_json, write_text
from datalens_dev_mcp.pipeline.build_identity import BuildIdentityResolver, build_identity_hash, validate_build_identity
from datalens_dev_mcp.pipeline.evidence_compaction import compact_task_evidence
from datalens_dev_mcp.pipeline.reference_binding import validate_reference_binding
from datalens_dev_mcp.pipeline.style_binding_receipt import validate_style_binding_receipt
from datalens_dev_mcp.pipeline.target_binding import resolve_contract_target_binding, validate_target_binding
from datalens_dev_mcp.pipeline.target_graph import validate_target_graph
from datalens_dev_mcp.pipeline.task_contract import task_contract_hash
from datalens_dev_mcp.pipeline.task_identity import build_task_identity, validate_task_identity
from datalens_dev_mcp.pipeline.workflow_checkpoint import render_checkpoint
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash, create_workflow_event
from datalens_dev_mcp.pipeline.workflow_replay import repair_corrupt_event_tail, replay_workflow
from datalens_dev_mcp.pipeline.workflow_state import WorkflowState, initial_workflow_state

TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class JournalError(RuntimeError):
    pass


class JournalIdentityError(JournalError):
    pass


class TaskLockError(JournalError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def default_runtime_state_root() -> Path:
    """Return the canonical user-scoped runtime root outside subject projects."""

    configured = str(os.environ.get("XDG_STATE_HOME") or "").strip()
    base = Path(configured).expanduser() if configured else Path.home() / ".local" / "state"
    return (base / "datalens-dev-mcp").resolve()


def build_journal_identity(
    contract: dict[str, Any],
    *,
    server_build: str = "",
    source_branch: str = "",
    source_tree: str = "",
) -> dict[str, Any]:
    target_binding = resolve_contract_target_binding(contract)
    marker = str(server_build or __version__)
    tree = str(source_tree or canonical_hash({"server_build": marker}))
    build_identity = {
        "schema_id": "datalens_build_identity",
        "kind": "resource_manifest",
        "commit": "",
        "branch": str(source_branch or ""),
        "tree_hash": tree,
        "package_content_hash": tree,
        "package_release": __version__,
        "provenance": {"compatibility_server_build": marker},
    }
    build_identity["identity_hash"] = build_identity_hash(build_identity)
    return {
        **build_task_identity(contract, build_identity=build_identity, target_binding=target_binding),
        "build_identity": build_identity,
        "target_binding": target_binding,
        "server_build": marker,
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
        base = Path(configured).expanduser() if configured else default_runtime_state_root() / "tasks"
        if not base.is_absolute():
            base = self.project_root / base
        self.storage_root = base.resolve()
        self.task_id = task_id
        self.root = self.storage_root / task_id
        self.contract_path = self.root / "contract.json"
        self.contract_revisions_path = self.root / "contract-revisions.json"
        self.contracts_root = self.root / "contracts"
        self.amendment_pending_path = self.root / "amendment-pending.json"
        self.state_path = self.root / "state.json"
        self.events_path = self.root / "events.jsonl"
        self.checkpoint_path = self.root / "checkpoint.md"
        self.compact_context_path = self.root / "compact-context.json"
        self.identity_path = self.root / "identity.json"
        self.build_identity_path = self.root / "build-identity.json"
        self.target_binding_path = self.root / "target-binding.json"
        self.target_graph_path = self.root / "target-graph.json"
        self.reference_binding_path = self.root / "reference-binding.json"
        self.style_binding_path = self.root / "style-binding.json"
        self.discovery_path = self.root / "discovery.json"
        self.execution_authorization_path = self.root / "execution-authorization.json"
        self.delivery_root = self.root / "delivery"
        self.save_stage_receipt_path = self.delivery_root / "save-stage-receipt.json"
        self.saved_readback_receipt_path = self.delivery_root / "saved-readback-receipt.json"
        self.publish_stage_receipt_path = self.delivery_root / "publish-stage-receipt.json"
        self.published_readback_receipt_path = self.delivery_root / "published-readback-receipt.json"
        self.publish_execution_plan_path = self.delivery_root / "private" / "publish-execution-plan.json"
        self.lock_path = self.storage_root / ".locks" / f"{self.task_id}.lock"
        self.lease_path = self.storage_root / ".locks" / f"{self.task_id}.lease.json"
        self.lease_seconds = max(1.0, float(lease_seconds))
        self._lock_handle: Any = None
        self._lock_depth = 0

    def initialize(self, contract: dict[str, Any], *, identity: dict[str, Any] | None = None) -> WorkflowState:
        # The validated contract contains typed identifiers, booleans, and
        # hashes but no raw request or credential fields. Generic value
        # redaction here can corrupt a legitimate project path when it happens
        # to contain a host session id, which also invalidates contract_hash.
        safe_contract = deepcopy(contract)
        if str(safe_contract.get("task_id") or "") != self.task_id:
            raise JournalIdentityError("contract task_id does not match journal task_id")
        digest = str(safe_contract.get("contract_hash") or "")
        if digest != task_contract_hash(safe_contract):
            raise JournalIdentityError("contract hash is invalid")
        expected = identity or build_journal_identity(safe_contract)
        build_identity = dict(expected.get("build_identity") or BuildIdentityResolver().resolve())
        target_binding = dict(expected.get("target_binding") or resolve_contract_target_binding(safe_contract))
        with self.locked(owner="journal-initialize"):
            if self.contract_path.exists():
                self.assert_resume_identity(safe_contract, build_identity=build_identity)
                state, _ = self.replay()
                return state
            state, _, _ = self.initialize_task(
                safe_contract,
                build_identity=build_identity,
                target_binding=target_binding,
                compile_receipt={"status": "compiled", "source": "workflow_engine"},
                execution_grant={},
            )
            return state

    def initialize_task(
        self,
        contract: dict[str, Any],
        *,
        build_identity: dict[str, Any],
        target_binding: dict[str, Any],
        compile_receipt: dict[str, Any],
        execution_grant: dict[str, Any],
    ) -> tuple[WorkflowState, str, bool]:
        """Create the complete initial journal snapshot as one atomic directory install."""

        safe_contract = deepcopy(contract)
        if str(safe_contract.get("task_id") or "") != self.task_id:
            raise JournalIdentityError("contract task_id does not match journal task_id")
        digest = str(safe_contract.get("contract_hash") or "")
        if digest != task_contract_hash(safe_contract):
            raise JournalIdentityError("contract hash is invalid")
        build_issues = validate_build_identity(build_identity)
        if build_issues:
            raise JournalIdentityError("invalid build identity: " + "; ".join(build_issues))
        target_issues = validate_target_binding(target_binding)
        if target_issues:
            raise JournalIdentityError("invalid target binding: " + "; ".join(target_issues))
        identity = build_task_identity(
            safe_contract,
            build_identity=build_identity,
            target_binding=target_binding,
        )
        with self.locked(owner="task-start"):
            if self.contract_path.exists():
                self.assert_resume_identity(
                    safe_contract,
                    build_identity=build_identity,
                )
                state, _ = self.replay()
                return state, self._compile_receipt_uri(), False
            if self.root.exists():
                raise JournalIdentityError("JOURNAL_PARTIAL_INITIALIZATION: task root exists without a contract")
            staging = Path(tempfile.mkdtemp(prefix=f".{self.task_id}.init-", dir=self.storage_root))
            try:
                state, compile_uri = self._write_initial_snapshot(
                    staging,
                    contract=safe_contract,
                    identity=identity,
                    build_identity=build_identity,
                    target_binding=target_binding,
                    compile_receipt=compile_receipt,
                    execution_grant=execution_grant,
                )
                os.replace(staging, self.root)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            return state, compile_uri, True

    def assert_resume_identity(
        self,
        contract: dict[str, Any],
        *,
        identity: dict[str, Any] | None = None,
        build_identity: dict[str, Any] | None = None,
        target_binding: dict[str, Any] | None = None,
    ) -> None:
        existing_contract = read_json(self.contract_path, {}) or {}
        existing_identity = read_json(self.identity_path, {}) or {}
        if existing_contract.get("contract_hash") != contract.get("contract_hash"):
            raise JournalIdentityError("task scope or contract changed; create a new task revision")
        persisted_build = read_json(self.build_identity_path, {}) or {}
        persisted_target = read_json(self.target_binding_path, {}) or {}
        if not persisted_build or not existing_identity.get("build_identity_hash"):
            raise JournalIdentityError(
                "JOURNAL_IDENTITY_UPGRADE_REQUIRED: write resume requires a persisted build identity"
            )
        requested_build = build_identity or dict((identity or {}).get("build_identity") or persisted_build)
        requested_target = target_binding or dict((identity or {}).get("target_binding") or persisted_target)
        requested = identity or build_task_identity(
            contract,
            build_identity=requested_build,
            target_binding=requested_target,
            style_binding_hash=str(existing_identity.get("style_binding_hash") or ""),
        )
        issues = validate_task_identity(
            existing_identity,
            build_identity=persisted_build,
            target_binding=persisted_target,
        )
        if issues:
            raise JournalIdentityError("JOURNAL_IDENTITY_INVALID: " + "; ".join(issues))
        if existing_identity.get("build_identity_hash") != requested.get("build_identity_hash"):
            raise JournalIdentityError(
                "SOURCE_IDENTITY_CONFLICT: server build/source tree changed; create a new task revision"
            )
        if existing_identity.get("target_binding_hash") != requested.get("target_binding_hash"):
            raise JournalIdentityError(
                "TARGET_BINDING_CONFLICT: target revision or binding changed; replan from a fresh target read"
            )
        if existing_identity.get("style_binding_hash") != requested.get("style_binding_hash"):
            raise JournalIdentityError(
                "STYLE_BINDING_CONFLICT: style binding changed; replan from a fresh reference read"
            )

    def assert_write_resume_ready(
        self,
        contract: dict[str, Any],
        *,
        build_identity: dict[str, Any],
        target_binding: dict[str, Any] | None = None,
    ) -> None:
        self.assert_resume_identity(
            contract,
            build_identity=build_identity,
            target_binding=target_binding or (read_json(self.target_binding_path, {}) or {}),
        )

    def bind_discovery(
        self,
        contract: dict[str, Any],
        *,
        target_binding: dict[str, Any],
        target_graph: dict[str, Any],
        reference_binding: dict[str, Any],
        style_binding: dict[str, Any],
        baselines: dict[str, dict[str, Any]],
        discovery_receipt: dict[str, Any],
    ) -> dict[str, Any]:
        issues = [
            *validate_target_binding(target_binding),
            *validate_target_graph(target_graph),
            *validate_reference_binding(reference_binding),
            *validate_style_binding_receipt(style_binding),
        ]
        if issues:
            raise JournalIdentityError("invalid discovery binding: " + "; ".join(issues))
        with self.locked(owner="target-discovery-binding"):
            state, _ = self.replay()
            existing = read_json(self.target_binding_path, {}) or {}
            blocker = dict(state.blocker or {})
            blocker_details = dict(blocker.get("details") or {})
            blocker_missing = {
                str(value) for value in blocker_details.get("missing_requirements") or []
            }
            retrying_blocked_discovery = (
                state.current_state == "BLOCKED"
                and not self.discovery_path.is_file()
                and (
                    str(blocker.get("code") or "") == "BLOCKED_DISCOVERY"
                    or (
                        str(blocker.get("reason") or "") == "live target discovery is unavailable"
                        and bool(blocker_missing & {"live_target_binding", "target_graph"})
                    )
                )
            )
            if not retrying_blocked_discovery and (
                state.current_state != "RESOLVED" or state.last_event_id > 1
            ):
                if existing.get("binding_hash") != target_binding.get("binding_hash"):
                    raise JournalIdentityError(
                        "TARGET_BINDING_CONFLICT: discovery changed after workflow progress; start a new task revision"
                    )
                return read_json(self.discovery_path, {}) or discovery_receipt
            build_identity = read_json(self.build_identity_path, {}) or {}
            identity = build_task_identity(
                contract,
                build_identity=build_identity,
                target_binding=target_binding,
                style_binding_hash=str(style_binding.get("binding_hash") or ""),
            )
            write_json(self.target_binding_path, deepcopy(target_binding))
            write_json(self.target_graph_path, deepcopy(target_graph))
            write_json(self.reference_binding_path, deepcopy(reference_binding))
            write_json(self.style_binding_path, deepcopy(style_binding))
            write_json(self.identity_path, deepcopy(identity))
            baseline_refs: list[dict[str, str]] = []
            for name, payload in sorted(baselines.items()):
                digest = canonical_hash(payload)
                relative = Path("snapshots") / f"baseline-{digest[:20]}.json"
                write_json(self.root / relative, deepcopy(payload))
                baseline_refs.append(
                    {
                        "name_hash": canonical_hash(name),
                        "artifact_uri": self.receipt_uri(relative.as_posix()),
                        "sha256": digest,
                    }
                )
            receipt = {
                **deepcopy(discovery_receipt),
                "target_binding_hash": target_binding.get("binding_hash"),
                "target_graph_hash": target_graph.get("graph_hash"),
                "reference_binding_hash": reference_binding.get("binding_hash"),
                "style_binding_hash": style_binding.get("binding_hash"),
                "baseline_refs": baseline_refs,
            }
            receipt["discovery_hash"] = canonical_hash(receipt)
            write_json(self.discovery_path, receipt)
            self.write_checkpoint(state)
            return receipt

    def load_contract(self) -> dict[str, Any]:
        if self.amendment_pending_path.is_file() and not self._lock_depth:
            raise JournalIdentityError(
                "CONTRACT_AMENDMENT_RECOVERY_REQUIRED: an interrupted amendment must be reconciled before resume"
            )
        value = read_json(self.contract_path, {}) or {}
        if not value:
            raise JournalError("journal contract is missing")
        return value

    def install_contract_amendment(
        self,
        *,
        expected_contract_revision: int,
        expected_state: str,
        expected_hash: str,
        amendment_key: str,
        amendment: dict[str, Any],
        new_contract: dict[str, Any],
        execution_grant: dict[str, Any],
        next_state: str,
        next_transition: str,
        invalidated_artifacts: list[str],
        preserved_artifacts: list[str],
        build_identity: dict[str, Any],
        target_binding: dict[str, Any] | None = None,
        target_graph: dict[str, Any] | None = None,
        reference_binding: dict[str, Any] | None = None,
        style_binding: dict[str, Any] | None = None,
        discovery: dict[str, Any] | None = None,
        baselines: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[WorkflowState, dict[str, Any], bool]:
        """Install one immutable contract amendment under the task lock.

        A durable pending marker makes crash recovery fail closed instead of
        exposing a mixed contract/plan projection.
        """

        with self.locked(owner="task-amendment"):
            current = self.load_contract()
            state, _ = self.replay()
            current_revision = int(current.get("contract_revision") or 1)
            index = read_json(self.contract_revisions_path, {}) or {}
            existing_amendments = list(index.get("amendments") or [])
            duplicate = next(
                (item for item in existing_amendments if item.get("amendment_key") == amendment_key),
                None,
            )
            if duplicate:
                return state, duplicate, False
            if current_revision != int(expected_contract_revision):
                raise JournalIdentityError(
                    f"CONTRACT_REVISION_CONFLICT: expected {expected_contract_revision}, current {current_revision}"
                )
            from datalens_dev_mcp.pipeline.task_state_projection import public_task_state, task_state_etag

            if expected_state and public_task_state(state.current_state) != expected_state:
                raise JournalIdentityError("expected task state does not match persisted state")
            if expected_hash and task_state_etag(state) != expected_hash:
                raise JournalIdentityError("expected task hash does not match persisted state")
            if state.current_state in {
                "COMPLETED", "BLOCKED_CONFLICT", "FAILED", "FAILED_ARCHITECTURE_REVIEW_REQUIRED"
            }:
                raise JournalIdentityError(
                    "TERMINAL_TASK_AMENDMENT_FORBIDDEN: start a new task for a terminal workflow"
                )
            if str(new_contract.get("task_id") or "") != self.task_id:
                raise JournalIdentityError("amended contract changed stable task_id")
            if int(new_contract.get("contract_revision") or 0) != current_revision + 1:
                raise JournalIdentityError("amended contract revision is not the next revision")
            if new_contract.get("parent_contract_hash") != current.get("contract_hash"):
                raise JournalIdentityError("amended contract parent hash mismatch")
            if task_contract_hash(new_contract) != new_contract.get("contract_hash"):
                raise JournalIdentityError("amended contract hash is invalid")

            resolved_target = dict(target_binding or (read_json(self.target_binding_path, {}) or {}))
            resolved_style = dict(style_binding or (read_json(self.style_binding_path, {}) or {}))
            identity = build_task_identity(
                new_contract,
                build_identity=build_identity,
                target_binding=resolved_target,
                style_binding_hash=str(resolved_style.get("binding_hash") or ""),
            )
            pending = {
                "schema_id": "datalens_contract_amendment_transaction",
                "amendment_key": amendment_key,
                "parent_contract_hash": current.get("contract_hash"),
                "contract_hash": new_contract.get("contract_hash"),
                "contract_revision": new_contract.get("contract_revision"),
            }
            write_json(self.amendment_pending_path, pending)
            try:
                self.contracts_root.mkdir(parents=True, exist_ok=True)
                current_name = f"contract-r{current_revision:04d}-{str(current.get('contract_hash') or '')[:16]}.json"
                new_name = (
                    f"contract-r{int(new_contract['contract_revision']):04d}-"
                    f"{str(new_contract.get('contract_hash') or '')[:16]}.json"
                )
                write_json(self.contracts_root / current_name, current)
                write_json(self.contracts_root / new_name, new_contract)

                plan_root = self.root / "plans"
                if plan_root.is_dir() and any(plan_root.iterdir()):
                    archive = self.root / "contract-artifacts" / f"r{current_revision:04d}" / "plans"
                    if not archive.exists():
                        archive.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(plan_root, archive)
                    shutil.rmtree(plan_root)
                plan_root.mkdir(parents=True, exist_ok=True)

                write_json(self.execution_authorization_path, execution_grant)
                if target_binding is not None:
                    write_json(self.target_binding_path, deepcopy(target_binding))
                if target_graph is not None:
                    write_json(self.target_graph_path, deepcopy(target_graph))
                if reference_binding is not None:
                    write_json(self.reference_binding_path, deepcopy(reference_binding))
                if style_binding is not None:
                    write_json(self.style_binding_path, deepcopy(style_binding))
                if discovery is not None:
                    discovery_payload = deepcopy(discovery)
                    baseline_refs: list[dict[str, str]] = []
                    for name, payload in sorted((baselines or {}).items()):
                        digest = canonical_hash(payload)
                        relative = Path("snapshots") / f"baseline-{digest[:20]}.json"
                        write_json(self.root / relative, deepcopy(payload))
                        baseline_refs.append(
                            {
                                "name_hash": canonical_hash(name),
                                "artifact_uri": self.receipt_uri(relative.as_posix()),
                                "sha256": digest,
                            }
                        )
                    discovery_payload["baseline_refs"] = baseline_refs
                    discovery_payload["discovery_hash"] = canonical_hash(discovery_payload)
                    write_json(self.discovery_path, discovery_payload)
                write_json(self.identity_path, deepcopy(identity))
                write_json(self.contract_path, new_contract)

                receipt_payload = {
                    **deepcopy(amendment),
                    "schema_id": "datalens_contract_amendment_receipt",
                    "task_id": self.task_id,
                    "amendment_key": amendment_key,
                    "contract_revision": new_contract.get("contract_revision"),
                    "parent_contract_hash": current.get("contract_hash"),
                    "contract_hash": new_contract.get("contract_hash"),
                    "source_turn_hash": new_contract.get("source_turn_hash"),
                    "semantic_delta_hash": new_contract.get("semantic_delta_hash"),
                    "scope_revision": new_contract.get("scope_revision"),
                    "authorization_revision": new_contract.get("authorization_revision"),
                    "invalidated_artifacts": invalidated_artifacts,
                    "preserved_artifacts": preserved_artifacts,
                }
                receipt_uri = self.write_receipt(
                    f"contract-amendment-r{int(new_contract['contract_revision']):04d}",
                    receipt_payload,
                )
                state = self.append_transition(
                    state,
                    transition=f"CONTRACT_AMENDED_R{current_revision}_TO_R{int(new_contract['contract_revision'])}",
                    input_value={
                        "parent_contract_hash": current.get("contract_hash"),
                        "contract_hash": new_contract.get("contract_hash"),
                        "source_turn_hash": new_contract.get("source_turn_hash"),
                        "semantic_delta_hash": new_contract.get("semantic_delta_hash"),
                    },
                    receipt_uri=receipt_uri,
                    status="success",
                    idempotency_key=amendment_key,
                    next_state=next_state,
                    next_transition=next_transition,
                    event_details={
                        "contract_revision": new_contract.get("contract_revision"),
                        "scope_revision": new_contract.get("scope_revision"),
                        "authorization_revision": new_contract.get("authorization_revision"),
                        "invalidated_artifacts": invalidated_artifacts,
                        "preserved_artifacts": preserved_artifacts,
                    },
                )
                record = {
                    "amendment_key": amendment_key,
                    "source_event_id": str(amendment.get("source_event_id") or ""),
                    "source_turn_hash": new_contract.get("source_turn_hash"),
                    "parent_contract_hash": current.get("contract_hash"),
                    "revision": new_contract.get("contract_revision"),
                    "contract_hash": new_contract.get("contract_hash"),
                    "receipt_uri": receipt_uri,
                }
                revisions = list(index.get("revisions") or [])
                if not revisions:
                    revisions.append(
                        {
                            "revision": current_revision,
                            "contract_hash": current.get("contract_hash"),
                            "artifact": f"contracts/{current_name}",
                        }
                    )
                revisions.append(
                    {
                        "revision": new_contract.get("contract_revision"),
                        "contract_hash": new_contract.get("contract_hash"),
                        "parent_contract_hash": current.get("contract_hash"),
                        "artifact": f"contracts/{new_name}",
                    }
                )
                write_json(
                    self.contract_revisions_path,
                    {
                        "schema_id": "datalens_contract_revision_chain",
                        "task_id": self.task_id,
                        "current_revision": new_contract.get("contract_revision"),
                        "revisions": revisions,
                        "amendments": [*existing_amendments, record],
                    },
                )
                self.amendment_pending_path.unlink(missing_ok=True)
                return state, record, True
            except BaseException:  # noqa: TRY203 - durable marker must survive interrupted amendments.
                # Keep the durable marker so the next public operation fails
                # closed instead of accepting a mixed projection.
                raise

    def load_state(self) -> WorkflowState:
        value = read_json(self.state_path, {}) or {}
        if not value:
            contract = self.load_contract()
            return initial_workflow_state(self.task_id, str(contract.get("contract_hash") or ""))
        return WorkflowState.from_dict(value)

    def save_state(self, state: WorkflowState) -> None:
        write_json(self.state_path, deepcopy(state.to_dict()))

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
            blocker=deepcopy(blocker or {}),
            reconciliation=deepcopy(reconciliation or {}),
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
        write_json(self.root / relative, deepcopy(payload))
        return self.receipt_uri(relative.as_posix())

    def _compile_receipt_uri(self) -> str:
        candidates = sorted((self.root / "receipts").glob("task-compile-*.json"))
        if not candidates:
            raise JournalIdentityError("journal compile receipt is missing")
        return self.receipt_uri(candidates[0].relative_to(self.root).as_posix())

    def _write_initial_snapshot(
        self,
        base: Path,
        *,
        contract: dict[str, Any],
        identity: dict[str, Any],
        build_identity: dict[str, Any],
        target_binding: dict[str, Any],
        compile_receipt: dict[str, Any],
        execution_grant: dict[str, Any],
    ) -> tuple[WorkflowState, str]:
        for relative in ("plans", "receipts", "snapshots", "evidence", "delivery", "locks", "contracts"):
            (base / relative).mkdir(parents=True, exist_ok=True)
        canonical_receipt = deepcopy(compile_receipt)
        receipt_digest = canonical_hash(canonical_receipt)
        receipt_name = f"task-compile-{receipt_digest[:16]}.json"
        receipt_relative = Path("receipts") / receipt_name
        compile_uri = self.receipt_uri(receipt_relative.as_posix())
        write_json(base / "contract.json", contract)
        contract_name = f"contract-r0001-{str(contract.get('contract_hash') or '')[:16]}.json"
        write_json(base / "contracts" / contract_name, contract)
        write_json(
            base / "contract-revisions.json",
            {
                "schema_id": "datalens_contract_revision_chain",
                "task_id": self.task_id,
                "current_revision": int(contract.get("contract_revision") or 1),
                "revisions": [
                    {
                        "revision": int(contract.get("contract_revision") or 1),
                        "contract_hash": contract.get("contract_hash"),
                        "artifact": f"contracts/{contract_name}",
                    }
                ],
                "amendments": [],
            },
        )
        write_json(base / "identity.json", deepcopy(identity))
        write_json(base / "build-identity.json", deepcopy(build_identity))
        write_json(base / "target-binding.json", deepcopy(target_binding))
        write_json(base / "execution-authorization.json", execution_grant)
        write_json(base / receipt_relative, canonical_receipt)
        event = create_workflow_event(
            event_id=1,
            previous_hash="",
            task_id=self.task_id,
            transition="TASK_COMPILED -> RESOLVED",
            input_value={
                "contract_hash": contract.get("contract_hash"),
                "build_identity_hash": build_identity.get("identity_hash"),
                "target_binding_hash": target_binding.get("binding_hash"),
            },
            result_receipt=compile_uri,
            status="success",
            timestamp=utc_now(),
            idempotency_key=canonical_hash(
                {"task_id": self.task_id, "transition": "TASK_COMPILED -> RESOLVED"}
            ),
            details={
                "next_state": "RESOLVED",
                "next_transition": "RESOLVED -> BASELINE_READ",
                "blocker": {},
                "reconciliation": {},
            },
        )
        append_jsonl(base / "events.jsonl", event)
        state = replace(
            initial_workflow_state(self.task_id, str(contract.get("contract_hash") or "")),
            completed_transitions=("TASK_COMPILED -> RESOLVED",),
            successful_idempotency_keys=(str(event["idempotency_key"]),),
            receipt_uris=(compile_uri,),
            last_event_id=1,
            last_event_hash=str(event["event_hash"]),
            revision=2,
        )
        write_json(base / "state.json", state.to_dict())
        criteria = [str(item.get("statement") or "") for item in contract.get("acceptance") or []]
        write_text(
            base / "checkpoint.md",
            render_checkpoint(contract=contract, state=state.to_dict(), completion_criteria=criteria),
        )
        write_json(
            base / "compact-context.json",
            compact_task_evidence(
                policy_version=__version__,
                task_contract=contract,
                build_identity=build_identity,
                task_identity=identity,
                target_binding=target_binding,
                style_binding={},
                checkpoint=state.to_dict(),
                active_blocker={},
                next_transition=state.next_transition,
                artifact_root=base,
            ),
        )
        return state, compile_uri

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
                build_identity=read_json(self.build_identity_path, {}) or {},
                task_identity=read_json(self.identity_path, {}) or {},
                target_binding=read_json(self.target_binding_path, {}) or contract.get("target") or {},
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
        self._ensure_storage_layout()
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

    def _ensure_storage_layout(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        (self.storage_root / ".locks").mkdir(parents=True, exist_ok=True)
