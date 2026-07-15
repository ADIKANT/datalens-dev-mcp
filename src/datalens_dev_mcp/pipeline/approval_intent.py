from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from datalens_dev_mcp.pipeline.target_lock import TargetLock, create_target_lock
from datalens_dev_mcp.pipeline.user_request import NormalizedUserRequest, normalize_user_request
from datalens_dev_mcp.pipeline.delivery_intent import DeliveryContext, resolve_delivery_intent


ApprovalStatus = Literal["approved", "blocked", "extra_confirmation_required", "save_only", "plan_only"]


@dataclass(frozen=True)
class SafeGates:
    writes_enabled: bool = False
    safe_apply_approved: bool = False
    fresh_readback_available: bool = False
    revision_preservation_available: bool = False
    saved_readback_available: bool = False
    publish_enabled: bool = False
    visual_contract_pass: bool = True
    performance_budget_pass: bool = True
    route_policy_pass: bool = True

    @property
    def pass_for_save(self) -> bool:
        return bool(
            self.writes_enabled
            and self.safe_apply_approved
            and self.fresh_readback_available
            and self.revision_preservation_available
            and self.visual_contract_pass
            and self.performance_budget_pass
            and self.route_policy_pass
        )

    @property
    def pass_for_publish(self) -> bool:
        return bool(self.pass_for_save and self.saved_readback_available and self.publish_enabled)

    def missing_for_save(self) -> list[str]:
        checks = {
            "writes_enabled": self.writes_enabled,
            "safe_apply_approved": self.safe_apply_approved,
            "fresh_readback_available": self.fresh_readback_available,
            "revision_preservation_available": self.revision_preservation_available,
            "visual_contract_pass": self.visual_contract_pass,
            "performance_budget_pass": self.performance_budget_pass,
            "route_policy_pass": self.route_policy_pass,
        }
        return [name for name, ok in checks.items() if not ok]

    def missing_for_publish(self) -> list[str]:
        missing = self.missing_for_save()
        if not self.saved_readback_available:
            missing.append("saved_readback_available")
        if not self.publish_enabled:
            missing.append("publish_enabled")
        return missing


@dataclass(frozen=True)
class ApprovalIntentDecision:
    status: ApprovalStatus
    approved: bool
    approval_source: str
    target_lock_hash: str
    default_delivery: list[str]
    publish_expected: bool
    save_expected: bool
    blocked_reasons: list[str] = field(default_factory=list)
    extra_confirmation_reasons: list[str] = field(default_factory=list)
    required_next_gates: list[str] = field(default_factory=list)
    literal_chat_phrase_required: bool = False
    delivery_state: str = ""
    delivery_reason: str = ""
    policy: str = "2026-07-01.delivery_approval_policy_v4"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ApprovalIntentResolver:
    IMPLEMENTING_INTENTS = {"implement", "fix", "enhance", "redesign", "update"}
    APPROVAL_PRIORITY = (
        "codex_tool_approval",
        "project_manifest_operator_approval",
        "goal_objective_file",
        "explicit_chat_approval",
        "current_user_request",
    )

    def resolve(
        self,
        request: str | NormalizedUserRequest,
        *,
        target_lock: TargetLock | dict[str, Any] | None = None,
        safe_gates: SafeGates | dict[str, Any] | None = None,
        approval_sources: list[str] | None = None,
    ) -> ApprovalIntentDecision:
        normalized = request if isinstance(request, NormalizedUserRequest) else normalize_user_request(str(request))
        sources = list(dict.fromkeys([*(normalized.approval_sources or []), *(approval_sources or [])]))
        lock = target_lock if isinstance(target_lock, TargetLock) else create_target_lock(normalized, **(target_lock or {}))
        gates = safe_gates if isinstance(safe_gates, SafeGates) else SafeGates(**(safe_gates or {}))
        approval_source = self._approval_source(sources)
        delivery_decision = resolve_delivery_intent(
            normalized,
            DeliveryContext(
                target_known=lock.known,
                writes_enabled=gates.writes_enabled,
                save_enabled=gates.writes_enabled,
                publish_enabled=gates.publish_enabled,
                safe_apply_approved=gates.safe_apply_approved,
                approval_source=approval_source,
                approval_sources=sources,
                fresh_readback_available=gates.fresh_readback_available,
                revision_preservation_available=gates.revision_preservation_available,
                saved_readback_available=gates.saved_readback_available,
                saved_readback_fresh=gates.saved_readback_available,
                destructive_operation=bool(normalized.destructive_actions),
                target_lock_status=lock.status,
                target_lock_hash=lock.lock_hash,
                target_workbook_id=lock.target_workbook_id,
                target_dashboard_id=lock.target_dashboard_id,
                target_chart_id=lock.target_chart_id,
            ),
        )

        if normalized.destructive_actions:
            return ApprovalIntentDecision(
                status="extra_confirmation_required",
                approved=False,
                approval_source=approval_source,
                target_lock_hash=lock.lock_hash,
                default_delivery=[],
                publish_expected=False,
                save_expected=False,
                extra_confirmation_reasons=normalized.destructive_actions,
                required_next_gates=["explicit_extra_confirmation"],
                delivery_state=delivery_decision.state,
                delivery_reason=delivery_decision.reason,
            )
        if normalized.publish_override in {"plan_only", "dry_run"} or normalized.task_intent == "plan":
            return ApprovalIntentDecision(
                status="plan_only",
                approved=False,
                approval_source=approval_source,
                target_lock_hash=lock.lock_hash,
                default_delivery=[],
                publish_expected=False,
                save_expected=False,
                delivery_state=delivery_decision.state,
                delivery_reason=delivery_decision.reason,
            )
        if normalized.publish_override in {"draft", "save_only", "no_publish"}:
            missing = gates.missing_for_save()
            return ApprovalIntentDecision(
                status="save_only" if not missing and lock.known else "blocked",
                approved=not missing and lock.known and bool(approval_source),
                approval_source=approval_source,
                target_lock_hash=lock.lock_hash,
                default_delivery=["save", "saved_readback"] if not missing and lock.known else [],
                publish_expected=False,
                save_expected=True,
                blocked_reasons=[] if lock.known else ["target_lock_not_locked"],
                required_next_gates=missing,
                delivery_state=delivery_decision.state,
                delivery_reason=delivery_decision.reason,
            )
        if normalized.task_intent not in self.IMPLEMENTING_INTENTS:
            return ApprovalIntentDecision(
                status="blocked",
                approved=False,
                approval_source=approval_source,
                target_lock_hash=lock.lock_hash,
                default_delivery=[],
                publish_expected=False,
                save_expected=False,
                blocked_reasons=["not_implementation_intent"],
                delivery_state=delivery_decision.state,
                delivery_reason=delivery_decision.reason,
            )
        if not lock.known:
            return ApprovalIntentDecision(
                status="blocked",
                approved=False,
                approval_source=approval_source,
                target_lock_hash=lock.lock_hash,
                default_delivery=[],
                publish_expected=True,
                save_expected=True,
                blocked_reasons=["target_lock_not_locked"],
                required_next_gates=["target_lock"],
                delivery_state=delivery_decision.state,
                delivery_reason=delivery_decision.reason,
            )
        if not approval_source:
            return ApprovalIntentDecision(
                status="blocked",
                approved=False,
                approval_source="",
                target_lock_hash=lock.lock_hash,
                default_delivery=[],
                publish_expected=True,
                save_expected=True,
                blocked_reasons=["approval_source_missing"],
                delivery_state=delivery_decision.state,
                delivery_reason=delivery_decision.reason,
            )
        missing = gates.missing_for_publish()
        if missing:
            return ApprovalIntentDecision(
                status="blocked",
                approved=False,
                approval_source=approval_source,
                target_lock_hash=lock.lock_hash,
                default_delivery=["save", "saved_readback", "publish", "published_readback"],
                publish_expected=True,
                save_expected=True,
                blocked_reasons=["safe_gate_missing"],
                required_next_gates=missing,
                delivery_state=delivery_decision.state,
                delivery_reason=delivery_decision.reason,
            )
        return ApprovalIntentDecision(
            status="approved",
            approved=True,
            approval_source=approval_source,
            target_lock_hash=lock.lock_hash,
            default_delivery=["save", "saved_readback", "publish", "published_readback"],
            publish_expected=True,
            save_expected=True,
            delivery_state=delivery_decision.state,
            delivery_reason=delivery_decision.reason,
        )

    def _approval_source(self, sources: list[str]) -> str:
        source_set = set(sources)
        for source in self.APPROVAL_PRIORITY:
            if source in source_set:
                return source
        return ""


def resolve_approval_intent(
    request: str | NormalizedUserRequest,
    *,
    target_lock: TargetLock | dict[str, Any] | None = None,
    safe_gates: SafeGates | dict[str, Any] | None = None,
    approval_sources: list[str] | None = None,
) -> ApprovalIntentDecision:
    return ApprovalIntentResolver().resolve(
        request,
        target_lock=target_lock,
        safe_gates=safe_gates,
        approval_sources=approval_sources,
    )
