from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from datalens_dev_mcp.pipeline.build_identity import BuildIdentityResolver
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal, build_journal_identity
from datalens_dev_mcp.pipeline.target_binding import resolve_contract_target_binding
from datalens_dev_mcp.pipeline.task_identity import build_task_identity
from datalens_dev_mcp.pipeline.failure_classifier import classify_failure
from datalens_dev_mcp.pipeline.investigation import ARCHITECTURE_REVIEW_STATE
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
from datalens_dev_mcp.pipeline.workflow_state import WorkflowState, is_terminal, transition_name
from datalens_dev_mcp.pipeline.task_stage_receipts import validate_stage_receipt


WorkflowHandler = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class TransitionSpec:
    source: str
    target: str
    handler: str
    write: bool = False

    @property
    def name(self) -> str:
        return transition_name(self.source, self.target)


FIXED_TRANSITIONS: dict[str, TransitionSpec] = {
    "RESOLVED": TransitionSpec("RESOLVED", "BASELINE_READ", "read_baseline"),
    "BASELINE_READ": TransitionSpec("BASELINE_READ", "REFERENCE_BOUND", "bind_reference"),
    "REFERENCE_BOUND": TransitionSpec("REFERENCE_BOUND", "ROUTE_BOUND", "bind_route"),
    "ROUTE_BOUND": TransitionSpec("ROUTE_BOUND", "DATA_PROOF_PLANNED", "plan_data_proof"),
    "DATA_PROOF_PLANNED": TransitionSpec("DATA_PROOF_PLANNED", "SEMANTIC_PLAN_READY", "plan_semantic_change"),
    "SEMANTIC_PLAN_READY": TransitionSpec("SEMANTIC_PLAN_READY", "VALIDATED", "validate_plan"),
    "SAVED": TransitionSpec("SAVED", "SAVED_READBACK", "read_saved_state"),
    "PUBLISHED": TransitionSpec("PUBLISHED", "PUBLISHED_READBACK", "read_published_state"),
    "QA_COMPLETED": TransitionSpec("QA_COMPLETED", "COMPLETED", "verify_completion"),
}


class WorkflowEngine:
    """Deterministic, journal-backed owner of one compiled DataLens task."""

    def __init__(
        self,
        journal: ProjectJournal,
        contract: dict[str, Any],
        *,
        handlers: Mapping[str, WorkflowHandler],
        server_build: str = "",
        source_branch: str = "",
        source_tree: str = "",
        build_identity: dict[str, Any] | None = None,
        target_binding: dict[str, Any] | None = None,
        style_binding_hash: str = "",
        require_typed_receipts: bool = False,
    ) -> None:
        self.journal = journal
        # TaskContract is already a typed, hash-bound structure with no raw
        # request or credential fields. Redacting it after hashing can corrupt
        # legitimate paths/ids and make the persisted contract unverifiable.
        self.contract = deepcopy(contract)
        self.handlers = dict(handlers)
        self.require_typed_receipts = bool(require_typed_receipts)
        if build_identity is None and any((server_build, source_branch, source_tree)):
            compatibility = build_journal_identity(
                self.contract,
                server_build=server_build,
                source_branch=source_branch,
                source_tree=source_tree,
            )
            build_identity = dict(compatibility["build_identity"])
        self.build_identity = dict(build_identity or BuildIdentityResolver().resolve())
        self.target_binding = dict(target_binding or resolve_contract_target_binding(self.contract))
        self.style_binding_hash = str(style_binding_hash or "")
        self.identity = {
            **build_task_identity(
                self.contract,
                build_identity=self.build_identity,
                target_binding=self.target_binding,
                style_binding_hash=self.style_binding_hash,
            ),
            "build_identity": self.build_identity,
            "target_binding": self.target_binding,
        }
        if not str(self.build_identity.get("identity_hash") or ""):
            raise ValueError("WorkflowEngine requires a non-empty build identity hash")

    def resume(
        self,
        *,
        max_transitions: int | None = None,
        stop_states: set[str] | frozenset[str] | None = None,
    ) -> WorkflowState:
        with self.journal.locked(owner="workflow-engine"):
            self.journal.initialize(self.contract, identity=self.identity)
            state, _ = self.journal.replay()
            count = 0
            while not is_terminal(state):
                if stop_states and state.current_state in stop_states:
                    break
                if max_transitions is not None and count >= max_transitions:
                    break
                spec = self._next_spec(state)
                state = self._execute(state, spec)
                count += 1
            return state

    def _next_spec(self, state: WorkflowState) -> TransitionSpec:
        if state.current_state == "VALIDATED":
            if bool((self.contract.get("delivery") or {}).get("save")):
                return TransitionSpec("VALIDATED", "SAVED", "safe_apply_save", write=True)
            return TransitionSpec("VALIDATED", "QA_COMPLETED", "verify_read_only_result")
        if state.current_state == "SAVED_READBACK":
            if bool((self.contract.get("delivery") or {}).get("publish")):
                return TransitionSpec("SAVED_READBACK", "PUBLISHED", "publish_from_saved", write=True)
            return TransitionSpec("SAVED_READBACK", "QA_COMPLETED", "run_qa")
        if state.current_state == "PUBLISHED_READBACK":
            return TransitionSpec("PUBLISHED_READBACK", "QA_COMPLETED", "run_qa")
        if state.current_state == "RECONCILING":
            phase = str(state.reconciliation.get("phase") or "save")
            target = "PUBLISHED_READBACK" if phase == "publish" else "SAVED_READBACK"
            return TransitionSpec("RECONCILING", target, "reconcile_ambiguous_write")
        try:
            return FIXED_TRANSITIONS[state.current_state]
        except KeyError as exc:
            raise RuntimeError(f"workflow state has no deterministic transition: {state.current_state}") from exc

    def _execute(self, state: WorkflowState, spec: TransitionSpec) -> WorkflowState:
        idempotency_key = canonical_hash(
            {
                "task_id": self.journal.task_id,
                "contract_hash": self.contract.get("contract_hash"),
                "transition": spec.name,
            }
        )
        if idempotency_key in state.successful_idempotency_keys:
            replayed, _ = self.journal.replay()
            return replayed
        handler = self.handlers.get(spec.handler)
        if handler is None:
            return self._record_blocked(
                state,
                spec,
                idempotency_key,
                reason="required workflow handler is unavailable",
                details={"handler": spec.handler},
            )
        context = {
            "task_id": self.journal.task_id,
            "contract": self.contract,
            "state": state.to_dict(),
            "transition": spec.name,
            "idempotency_key": idempotency_key,
            "journal_root": str(self.journal.root),
            "build_identity_hash": self.build_identity.get("identity_hash"),
            "target_binding_hash": self.target_binding.get("binding_hash"),
        }
        try:
            # Handler output is canonical state used for validation,
            # reconciliation and receipts. Redaction belongs to the public
            # projection boundary and must never rewrite this value.
            result = deepcopy(handler(context) or {})
        except (TimeoutError, ConnectionError) as exc:
            if spec.write:
                return self._record_reconciliation(state, spec, idempotency_key, str(exc), ambiguous=True)
            classification = classify_failure(exc, operation=spec.handler, readonly=True)
            return self._record_retryable(
                state, spec, idempotency_key, classification.evidence, family=classification.family
            )
        except Exception as exc:  # noqa: BLE001
            classification = classify_failure(exc, operation=spec.handler, readonly=not spec.write)
            return self._record_failed(
                state, spec, idempotency_key, classification.evidence, family=classification.family
            )

        result_status = str(result.get("status") or "success")
        if self.require_typed_receipts:
            receipt_issues = validate_stage_receipt(
                result,
                task_id=self.journal.task_id,
                contract_hash=str(self.contract.get("contract_hash") or ""),
                transition=spec.name,
                build_identity_hash=str(self.build_identity.get("identity_hash") or ""),
                target_binding_hash=str(self.target_binding.get("binding_hash") or ""),
            )
            if receipt_issues:
                return self._record_blocked(
                    state,
                    spec,
                    idempotency_key,
                    reason="workflow stage did not return a valid typed receipt",
                    details={"receipt_issues": list(receipt_issues)},
                )
        if result_status in {"ambiguous", "partial"} and spec.write:
            return self._record_reconciliation(
                state,
                spec,
                idempotency_key,
                str(result.get("reason") or result_status),
                ambiguous=result_status == "ambiguous",
                result=result,
            )
        if result_status == "conflict":
            return self._record_conflict(state, spec, idempotency_key, result)
        if result_status == "blocked":
            return self._record_blocked(
                state,
                spec,
                idempotency_key,
                reason=str(result.get("reason") or "workflow blocked"),
                details=result,
            )
        if result_status in {"failed", "error"}:
            classification = classify_failure(result, operation=spec.handler, readonly=not spec.write)
            return self._record_failed(
                state,
                spec,
                idempotency_key,
                str(result.get("reason") or "handler failed"),
                family=str(result.get("failure_family") or classification.family),
                corrective_attempts=int(result.get("corrective_attempts") or 0),
            )
        if state.current_state == "RECONCILING" and result_status not in {"matched", "success"}:
            return self._record_blocked(
                state,
                spec,
                idempotency_key,
                reason="write reconciliation did not prove the expected target state",
                details=result,
            )
        receipt_uri = self.journal.write_receipt(f"{state.last_event_id + 1:08d}-{spec.handler}", result)
        next_transition = self._preview_next(spec.target, reconciliation={})
        return self.journal.append_transition(
            state,
            transition=spec.name,
            input_value=context,
            receipt_uri=receipt_uri,
            status="success",
            idempotency_key=idempotency_key,
            next_state=spec.target,
            next_transition=next_transition,
            event_details={
                "observed_facts": list(result.get("observed_facts") or [])[:20],
                "handler": spec.handler,
            },
        )

    def _record_reconciliation(
        self,
        state: WorkflowState,
        spec: TransitionSpec,
        key: str,
        reason: str,
        *,
        ambiguous: bool,
        result: dict[str, Any] | None = None,
    ) -> WorkflowState:
        phase = "publish" if spec.handler == "publish_from_saved" else "save"
        details = {
            "phase": phase,
            "ambiguous": ambiguous,
            "reason": reason,
            "expected_revision": (result or {}).get("expected_revision", ""),
            "object_statuses": (result or {}).get("object_statuses", []),
            "write_idempotency_key": key,
        }
        receipt = self.journal.write_receipt(f"{state.last_event_id + 1:08d}-{spec.handler}-uncertain", result or details)
        return self.journal.append_transition(
            state,
            transition=spec.name,
            input_value={"contract_hash": self.contract.get("contract_hash")},
            receipt_uri=receipt,
            status="retryable",
            idempotency_key=key,
            next_state="RECONCILING",
            next_transition="RECONCILING -> " + ("PUBLISHED_READBACK" if phase == "publish" else "SAVED_READBACK"),
            reconciliation=details,
        )

    def _record_conflict(self, state: WorkflowState, spec: TransitionSpec, key: str, result: dict[str, Any]) -> WorkflowState:
        blocker = {
            "reason": "external target revision changed",
            "semantic_diff": result.get("semantic_diff") or {},
            "expected_revision": result.get("expected_revision") or "",
            "actual_revision": result.get("actual_revision") or "",
        }
        receipt = self.journal.write_receipt(f"{state.last_event_id + 1:08d}-conflict", result)
        return self.journal.append_transition(
            state,
            transition=spec.name,
            input_value={"contract_hash": self.contract.get("contract_hash")},
            receipt_uri=receipt,
            status="blocked",
            idempotency_key=key,
            next_state="BLOCKED_CONFLICT",
            next_transition="",
            blocker=blocker,
        )

    def _record_blocked(
        self,
        state: WorkflowState,
        spec: TransitionSpec,
        key: str,
        *,
        reason: str,
        details: dict[str, Any],
    ) -> WorkflowState:
        blocker = {"reason": reason, "details": details}
        receipt = self.journal.write_receipt(f"{state.last_event_id + 1:08d}-blocked", blocker)
        return self.journal.append_transition(
            state,
            transition=spec.name,
            input_value={"contract_hash": self.contract.get("contract_hash")},
            receipt_uri=receipt,
            status="blocked",
            idempotency_key=key,
            next_state="BLOCKED",
            next_transition="",
            blocker=blocker,
        )

    def _record_retryable(
        self, state: WorkflowState, spec: TransitionSpec, key: str, reason: str, *, family: str = ""
    ) -> WorkflowState:
        return self.journal.append_transition(
            state,
            transition=spec.name,
            input_value={"contract_hash": self.contract.get("contract_hash")},
            receipt_uri="",
            status="retryable",
            idempotency_key=key,
            next_state=state.current_state,
            next_transition=spec.name,
            blocker={"reason": reason, "retryable": True, "failure_family": family},
        )

    def _record_failed(
        self,
        state: WorkflowState,
        spec: TransitionSpec,
        key: str,
        reason: str,
        *,
        family: str = "",
        corrective_attempts: int = 0,
    ) -> WorkflowState:
        architecture_review = corrective_attempts >= 3
        return self.journal.append_transition(
            state,
            transition=spec.name,
            input_value={"contract_hash": self.contract.get("contract_hash")},
            receipt_uri="",
            status="failed",
            idempotency_key=key,
            next_state=ARCHITECTURE_REVIEW_STATE if architecture_review else "FAILED",
            next_transition="",
            blocker={
                "reason": reason,
                "failure_family": family,
                "corrective_attempts": corrective_attempts,
                "architecture_review_required": architecture_review,
                "next_action": "review route and architecture" if architecture_review else "inspect boundary evidence",
            },
        )

    def _preview_next(self, target: str, *, reconciliation: dict[str, Any]) -> str:
        preview = WorkflowState(
            task_id=self.journal.task_id,
            contract_hash=str(self.contract.get("contract_hash") or ""),
            current_state=target,
            reconciliation=reconciliation,
        )
        if is_terminal(preview):
            return ""
        return self._next_spec(preview).name
