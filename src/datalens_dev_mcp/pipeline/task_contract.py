from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5


TaskMode = Literal["review", "diagnose", "plan", "create", "update", "redesign", "publish_only"]
OperationKind = Literal["inspect", "mutate", "verify_existing_effect"]
BrowserMode = Literal["forbidden", "optional", "required"]
BrowserPolicySource = Literal["explicit_user", "compiled_default", "workspace_policy"]


SOURCE_PRECEDENCE = (
    "current_user_request",
    "current_live_readback",
    "current_portfolio_source",
    "active_workspace_policy",
    "current_openapi_and_docs",
    "current_task_journal",
    "historical_examples",
    "historical_session_summaries",
)


@dataclass(frozen=True)
class WorkspaceContract:
    project_root: str
    portfolio_subproject: str = ""
    config_path: str = ""


@dataclass(frozen=True)
class TargetContract:
    workbook_id: str = ""
    dashboard_id: str = ""
    object_ids: tuple[str, ...] = ()
    object_types: tuple[str, ...] = ()
    saved_revision: str = ""
    published_revision: str = ""
    technology: str = ""


@dataclass(frozen=True)
class ScopeContract:
    allowed_objects: tuple[str, ...] = ()
    allowed_tabs: tuple[str, ...] = ()
    allowed_semantic_slots: tuple[str, ...] = ()
    forbidden_changes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceContract:
    kind: str = "none"
    locator: str = ""
    required_exact_style: bool = False
    source_hash: str = ""


@dataclass(frozen=True)
class BrowserPolicyContract:
    mode: BrowserMode = "optional"
    source: BrowserPolicySource = "compiled_default"


@dataclass(frozen=True)
class DeliveryContract:
    save: bool = False
    publish: bool = False
    destructive: bool = False


@dataclass(frozen=True)
class EffectContract:
    kind: str = "none"
    expected_state: str = ""


@dataclass(frozen=True)
class VerificationContract:
    required_live_reads: tuple[str, ...] = ()
    acceptance_required: bool = False
    remediation_enabled: bool = False
    remediation_requires_new_user_scope: bool = True


@dataclass(frozen=True)
class EvidenceContract:
    required_facts: tuple[str, ...] = ()
    available_facts: tuple[str, ...] = ()
    unavailable_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptanceCriterion:
    kind: str
    statement: str
    source: str = "current_user_request"
    hard: bool = True


@dataclass(frozen=True)
class QuestionPolicyContract:
    max_questions: int = 1
    discoverable_facts_must_be_read: bool = True


@dataclass(frozen=True)
class TaskContract:
    schema_id: str
    contract_version: int
    task_id: str
    raw_request_hash: str
    mode: TaskMode
    route: str
    operation_kind: OperationKind
    effect: EffectContract
    verification: VerificationContract
    workspace: WorkspaceContract
    target: TargetContract
    scope: ScopeContract
    reference: ReferenceContract
    browser_policy: BrowserPolicyContract
    delivery: DeliveryContract
    evidence: EvidenceContract
    acceptance: tuple[AcceptanceCriterion, ...]
    question_policy: QuestionPolicyContract
    stop_conditions: tuple[str, ...]
    corrections: tuple[str, ...]
    source_precedence: tuple[str, ...]
    contract_revision: int = 1
    parent_contract_hash: str = ""
    source_turn_hash: str = ""
    semantic_delta_hash: str = ""
    scope_revision: int = 1
    authorization_revision: int = 1
    contract_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))

    def verify_hash(self) -> bool:
        return self.contract_hash == task_contract_hash(self.to_dict())


def create_task_contract(
    *,
    raw_request: str,
    mode: TaskMode,
    route: str,
    operation_kind: OperationKind = "inspect",
    effect: EffectContract | None = None,
    verification: VerificationContract | None = None,
    workspace: WorkspaceContract,
    target: TargetContract | None = None,
    scope: ScopeContract | None = None,
    reference: ReferenceContract | None = None,
    browser_policy: BrowserPolicyContract | None = None,
    delivery: DeliveryContract | None = None,
    evidence: EvidenceContract | None = None,
    acceptance: tuple[AcceptanceCriterion, ...] = (),
    stop_conditions: tuple[str, ...] = (),
    corrections: tuple[str, ...] = (),
    task_id: str = "",
    contract_revision: int = 1,
    parent_contract_hash: str = "",
    source_turn_hash: str = "",
    semantic_delta_hash: str = "",
    scope_revision: int = 1,
    authorization_revision: int = 1,
) -> TaskContract:
    raw_hash = hashlib.sha256(raw_request.encode("utf-8")).hexdigest()
    resolved_target = target or TargetContract()
    stable_task_id = task_id or str(
        uuid5(
            NAMESPACE_URL,
            "|".join(
                (
                    raw_hash,
                    workspace.project_root,
                    resolved_target.workbook_id,
                    resolved_target.dashboard_id,
                    ",".join(resolved_target.object_ids),
                )
            ),
        )
    )
    contract = TaskContract(
        schema_id="datalens_task_contract",
        contract_version=2,
        task_id=stable_task_id,
        raw_request_hash=raw_hash,
        mode=mode,
        route=route,
        operation_kind=operation_kind,
        effect=effect or EffectContract(),
        verification=verification or VerificationContract(),
        workspace=workspace,
        target=resolved_target,
        scope=scope or ScopeContract(),
        reference=reference or ReferenceContract(),
        browser_policy=browser_policy or BrowserPolicyContract(),
        delivery=delivery or DeliveryContract(),
        evidence=evidence or EvidenceContract(),
        acceptance=acceptance,
        question_policy=QuestionPolicyContract(),
        stop_conditions=stop_conditions,
        corrections=corrections,
        source_precedence=SOURCE_PRECEDENCE,
        contract_revision=max(1, int(contract_revision)),
        parent_contract_hash=str(parent_contract_hash or ""),
        source_turn_hash=str(source_turn_hash or raw_hash),
        semantic_delta_hash=str(semantic_delta_hash or raw_hash),
        scope_revision=max(1, int(scope_revision)),
        authorization_revision=max(1, int(authorization_revision)),
    )
    return replace(contract, contract_hash=task_contract_hash(contract.to_dict()))


def task_contract_hash(contract: TaskContract | dict[str, Any]) -> str:
    payload = contract.to_dict() if isinstance(contract, TaskContract) else dict(contract)
    payload.pop("contract_hash", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_task_contract(contract: TaskContract | dict[str, Any]) -> tuple[str, ...]:
    payload = contract.to_dict() if isinstance(contract, TaskContract) else dict(contract)
    issues: list[str] = []
    if payload.get("schema_id") != "datalens_task_contract":
        issues.append("schema_id must be datalens_task_contract")
    if payload.get("contract_version") != 2:
        issues.append("contract_version must be 2")
    if not isinstance(payload.get("contract_revision"), int) or int(payload.get("contract_revision") or 0) < 1:
        issues.append("contract_revision must be a positive integer")
    for field_name in ("source_turn_hash", "semantic_delta_hash"):
        if len(str(payload.get(field_name) or "")) != 64:
            issues.append(f"{field_name} must be a SHA-256 digest")
    for field_name in ("scope_revision", "authorization_revision"):
        if not isinstance(payload.get(field_name), int) or int(payload.get(field_name) or 0) < 1:
            issues.append(f"{field_name} must be a positive integer")
    if payload.get("mode") not in {"review", "diagnose", "plan", "create", "update", "redesign", "publish_only"}:
        issues.append("mode is unsupported")
    operation_kind = payload.get("operation_kind", "inspect")
    if operation_kind not in {"inspect", "mutate", "verify_existing_effect"}:
        issues.append("operation_kind is unsupported")
    verification = payload.get("verification") or {}
    acceptance = payload.get("acceptance") or []
    delivery = payload.get("delivery") or {}
    if operation_kind == "verify_existing_effect":
        required_reads = verification.get("required_live_reads") or []
        for required in ("current_object", "saved_or_published_revision", "relations"):
            if required not in required_reads:
                issues.append(f"verification.required_live_reads must include {required}")
        if verification.get("acceptance_required") is not True or not acceptance:
            issues.append("verify_existing_effect requires a non-empty acceptance contract")
        if any(bool(delivery.get(key)) for key in ("save", "publish", "destructive")):
            issues.append("verify_existing_effect must have zero delivery side effects")
        if verification.get("remediation_enabled") is not False:
            issues.append("verify_existing_effect remediation must be disabled by default")
    if not str(payload.get("route") or "").strip():
        issues.append("route must not be empty")
    digest = str(payload.get("contract_hash") or "")
    if len(digest) != 64 or digest != task_contract_hash(payload):
        issues.append("contract_hash does not match canonical contract content")
    question_policy = payload.get("question_policy") or {}
    if question_policy.get("max_questions") != 1:
        issues.append("question_policy.max_questions must equal 1")
    return tuple(issues)


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_value(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value
