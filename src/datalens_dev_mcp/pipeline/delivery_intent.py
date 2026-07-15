from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Any, Literal

from datalens_dev_mcp.config import DataLensConfig, env_flag
from datalens_dev_mcp.pipeline.target_lock import TargetLock
from datalens_dev_mcp.pipeline.user_request import NormalizedUserRequest, normalize_user_request
from datalens_dev_mcp.runtime_resources import resource_json


POLICY_RESOURCE = "config/datalens_delivery_policy.json"
DeliveryState = Literal[
    "read_only",
    "plan_only",
    "save_only",
    "save_then_publish",
    "publish_from_saved",
    "blocked",
]
Intent = Literal[
    "read_only_review",
    "plan_only",
    "dry_run",
    "save_only_draft",
    "save_and_publish_delivery",
    "publish_from_saved",
    "blocked_missing_target",
    "blocked_missing_write_gates",
    "blocked_manual_review",
]

IMPLEMENTATION_INTENTS = {"implement", "fix", "enhance", "redesign", "update"}
PLAN_OVERRIDES = {"plan_only", "dry_run"}
SAVE_ONLY_OVERRIDES = {"draft", "save_only", "no_publish"}
SUFFICIENT_APPROVAL_SOURCES = (
    "codex_tool_approval",
    "project_manifest_operator_approval",
    "goal_objective_file",
    "explicit_chat_approval",
    "current_user_request",
    "safe_apply_session_approval",
)


@dataclass(frozen=True)
class DeliveryContext:
    target_known: bool = False
    writes_enabled: bool = False
    save_enabled: bool | None = None
    publish_enabled: bool | None = None
    safe_apply_approved: bool = False
    approval_source: str = ""
    approval_sources: list[str] = field(default_factory=list)
    fresh_readback_available: bool = False
    revision_preservation_available: bool = False
    destructive_operation: bool = False
    publish_disabled_by_policy: bool = False
    saved_readback_available: bool = False
    saved_readback_fresh: bool | None = None
    proof_path: str = ""
    target_lock_status: str = ""
    target_lock_hash: str = ""
    target_workbook_id: str = ""
    target_dashboard_id: str = ""
    target_chart_id: str = ""


@dataclass(frozen=True)
class DeliveryIntentInputs:
    task_intent: str = "unknown"
    publish_override: str = "none"
    target_known: bool = False
    target_lock_status: str = ""
    target_lock_hash: str = ""
    writes_enabled: bool = False
    save_enabled: bool = False
    publish_enabled: bool = False
    safe_apply_approved: bool = False
    approval_source: str = ""
    approval_sources: list[str] = field(default_factory=list)
    user_opt_out_phrases: list[str] = field(default_factory=list)
    workbook_id: str = ""
    dashboard_id: str = ""
    chart_id: str = ""
    fresh_readback_available: bool = False
    revision_preservation_available: bool = False
    saved_readback_available: bool = False
    saved_readback_fresh: bool = False
    destructive_operation: bool = False
    proof_path: str = ""

    @property
    def has_approval(self) -> bool:
        return bool(self.safe_apply_approved and self.approval_source)


@dataclass(frozen=True)
class DeliveryIntentDecision:
    state: DeliveryState
    reason: str
    required_gates: list[str] = field(default_factory=list)
    satisfied_gates: list[str] = field(default_factory=list)
    next_action: str = ""
    proof_path: str = ""
    policy: str = "2026-07-01.delivery_intent_state_machine.v2"
    task_intent: str = "unknown"
    approval_source: str = ""
    target_lock_status: str = ""
    target_lock_hash: str = ""
    workbook_id: str = ""
    dashboard_id: str = ""
    chart_id: str = ""
    save_stage_status: str = ""
    publish_stage_status: str = ""
    saved_readback_path: str = ""
    published_readback_path: str = ""
    user_opt_out_phrases: list[str] = field(default_factory=list)
    saved_readback_fresh: bool = False
    publish_expected: bool = False
    writes_expected: bool = False
    approval_reuse_for_publish: bool = False
    intent: Intent = "read_only_review"
    blocked_reasons: list[str] = field(default_factory=list)
    default_delivery: list[str] = field(default_factory=list)
    literal_chat_phrase_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Compatibility fields retained for older trace scripts and tests.
        payload["required_next_gates"] = list(self.required_gates)
        payload["gates"] = list(self.required_gates)
        payload["target_branch"] = self.target_branch
        payload["next_actions"] = self.next_actions
        payload["missing_gates"] = [gate for gate in self.required_gates if gate not in self.satisfied_gates]
        return payload

    @property
    def required_next_gates(self) -> list[str]:
        return list(self.required_gates)

    @property
    def target_branch(self) -> str:
        if self.state in {"save_then_publish", "publish_from_saved"}:
            return "published"
        if self.state == "save_only":
            return "saved"
        return "none"

    @property
    def next_actions(self) -> list[str]:
        if self.state == "read_only":
            return ["Keep workflow read-only."]
        if self.state == "plan_only":
            return ["Keep workflow plan-only or dry-run."]
        if self.state == "save_only":
            return ["Create or execute save-mode safe apply.", "Run saved readback.", "Do not create a publish plan."]
        if self.state == "save_then_publish":
            return [
                "Create save-mode safe apply.",
                "Execute approved save.",
                "Run saved readback.",
                "Create publish-from-saved plan.",
                "Execute approved publish.",
                "Run published readback.",
            ]
        if self.state == "publish_from_saved":
            return ["Create publish-from-saved plan.", "Execute approved publish.", "Run published readback."]
        missing = [gate for gate in self.required_gates if gate not in self.satisfied_gates]
        return [f"Satisfy gate: {gate}" for gate in missing] or ["Stop until required gates are satisfied."]


class DeliveryIntentPolicy:
    """State machine for save/publish delivery intent across production paths."""

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or load_delivery_policy()

    def decide(
        self,
        request: str | NormalizedUserRequest,
        context: DeliveryContext | dict[str, Any] | None = None,
    ) -> DeliveryIntentDecision:
        normalized = _normalized_request(request, context)
        inputs = _inputs_from_request(normalized, context)

        if inputs.destructive_operation:
            return _decision(
                state="blocked",
                intent="blocked_manual_review",
                inputs=inputs,
                reason="Destructive, move, permission, or credential operation requires separate manual review.",
                required_gates=["explicit_extra_confirmation"],
                blocked_reasons=["destructive_operation"],
                next_action="Stop and request separate approval for the destructive operation.",
            )

        if inputs.publish_override in PLAN_OVERRIDES or inputs.task_intent == "plan":
            return _decision(
                state="plan_only",
                intent="dry_run" if inputs.publish_override == "dry_run" else "plan_only",
                inputs=inputs,
                reason="Plan-only or dry-run request does not save or publish.",
                next_action="Return a plan or dry-run result only.",
            )

        if inputs.task_intent == "review" or inputs.task_intent == "unknown":
            return _decision(
                state="read_only",
                intent="read_only_review",
                inputs=inputs,
                reason="Review, audit, inspect, diagnose, or unknown intent remains read-only.",
                next_action="Return read-only diagnostics or ask for an implementation target.",
            )

        if inputs.publish_override in SAVE_ONLY_OVERRIDES:
            return self._save_only(inputs)

        if inputs.task_intent in IMPLEMENTATION_INTENTS:
            return self._save_then_publish(inputs)

        return _decision(
            state="read_only",
            intent="read_only_review",
            inputs=inputs,
            reason="Request did not resolve to an implementation delivery intent.",
            next_action="Keep workflow read-only.",
        )

    def _save_only(self, inputs: DeliveryIntentInputs) -> DeliveryIntentDecision:
        required = ["target_lock", "writes_enabled", "save_enabled", "safe_apply_session_approval"]
        satisfied = _satisfied_gates(inputs, include_publish=False)
        missing = [gate for gate in required if gate not in satisfied]
        if missing:
            return _decision(
                state="blocked",
                intent="blocked_missing_write_gates" if inputs.target_known else "blocked_missing_target",
                inputs=inputs,
                reason="Save-only delivery is blocked until target, runtime write/save flags, and tool approval are present.",
                required_gates=required,
                satisfied_gates=satisfied,
                blocked_reasons=missing,
                publish_expected=False,
                writes_expected=True,
                next_action=f"Satisfy gate: {missing[0]}",
            )
        return _decision(
            state="save_only",
            intent="save_only_draft",
            inputs=inputs,
            reason="Draft, review-before-publish, save-only, or no-publish wording stops after saved readback.",
            required_gates=[*required, "fresh_readback", "revision_preservation", "saved_readback"],
            satisfied_gates=satisfied,
            publish_expected=False,
            writes_expected=True,
            default_delivery=["save", "saved_readback"],
            next_action="Execute save, then run saved readback; do not publish.",
        )

    def _save_then_publish(self, inputs: DeliveryIntentInputs) -> DeliveryIntentDecision:
        required = [
            "target_lock",
            "writes_enabled",
            "save_enabled",
            "publish_enabled",
            "safe_apply_session_approval",
        ]
        satisfied = _satisfied_gates(inputs, include_publish=True)
        missing = [gate for gate in required if gate not in satisfied]
        if missing:
            return _decision(
                state="blocked",
                intent="blocked_missing_target" if "target_lock" in missing else "blocked_missing_write_gates",
                inputs=inputs,
                reason=(
                    "Implementation/fix/enhance/redesign delivery is blocked until target, runtime "
                    "write/save/publish flags, and Codex/tool approval are present."
                ),
                required_gates=required,
                satisfied_gates=satisfied,
                blocked_reasons=missing,
                publish_expected=True,
                writes_expected=True,
                default_delivery=["save", "saved_readback", "publish", "published_readback"],
                next_action=f"Satisfy gate: {missing[0]}",
            )

        if inputs.saved_readback_available:
            publish_required = [*required, "fresh_readback", "revision_preservation", "saved_readback_fresh"]
            publish_satisfied = _satisfied_gates(inputs, include_publish=True)
            if not inputs.saved_readback_fresh:
                return _decision(
                    state="blocked",
                    intent="blocked_missing_write_gates",
                    inputs=inputs,
                    reason="Publish is blocked because saved readback is missing, invalid, stale, or not from the saved branch.",
                    required_gates=publish_required,
                    satisfied_gates=publish_satisfied,
                    blocked_reasons=["saved_readback_fresh"],
                    publish_expected=True,
                    writes_expected=True,
                    default_delivery=["save", "saved_readback", "publish", "published_readback"],
                    next_action="Refresh saved readback before publishing.",
                )
            return _decision(
                state="publish_from_saved",
                intent="publish_from_saved",
                inputs=inputs,
                reason="Publish may proceed only from fresh saved-branch readback.",
                required_gates=[*publish_required, "published_readback"],
                satisfied_gates=publish_satisfied,
                publish_expected=True,
                writes_expected=True,
                default_delivery=["save", "saved_readback", "publish", "published_readback"],
                next_action="Execute publish from saved readback, then run published readback.",
            )

        return _decision(
            state="save_then_publish",
            intent="save_and_publish_delivery",
            inputs=inputs,
            reason=(
                "Implementation/fix/enhance/redesign with known target and Codex/tool approval proceeds "
                "save -> saved readback -> publish from saved readback -> published readback."
            ),
            required_gates=[
                *required,
                "fresh_readback",
                "revision_preservation",
                "saved_readback_fresh",
                "published_readback",
            ],
            satisfied_gates=satisfied,
            publish_expected=True,
            writes_expected=True,
            default_delivery=["save", "saved_readback", "publish", "published_readback"],
            next_action="Execute save, then run saved readback and publish from that saved readback.",
        )


@lru_cache(maxsize=1)
def load_delivery_policy() -> dict[str, Any]:
    return resource_json(POLICY_RESOURCE)


def resolve_delivery_intent(
    user_text: str | NormalizedUserRequest,
    context: DeliveryContext | dict[str, Any] | None = None,
) -> DeliveryIntentDecision:
    return DeliveryIntentPolicy().decide(user_text, context)


def delivery_context_from_env(
    *,
    target_known: bool = False,
    approved: bool = False,
    approval_source: str = "",
    approval_sources: list[str] | None = None,
    fresh_readback_available: bool = False,
    revision_preservation_available: bool = False,
    saved_readback_available: bool = False,
    saved_readback_fresh: bool | None = None,
    destructive_operation: bool = False,
    proof_path: str = "",
    target_lock: TargetLock | dict[str, Any] | None = None,
    target_workbook_id: str = "",
    target_dashboard_id: str = "",
    target_chart_id: str = "",
) -> DeliveryContext:
    config = DataLensConfig.from_env()
    publish_enabled = env_flag("DATALENS_MCP_LIVE_ALLOW_PUBLISH", False)
    save_enabled = env_flag("DATALENS_MCP_LIVE_ALLOW_SAVE", False)
    return DeliveryContext(
        target_known=target_known or _target_lock_known(target_lock),
        writes_enabled=bool(config.write_enabled),
        save_enabled=save_enabled,
        publish_enabled=publish_enabled,
        safe_apply_approved=approved,
        approval_source=_default_approval_source(approved, approval_source, approval_sources or []),
        approval_sources=approval_sources or [],
        fresh_readback_available=fresh_readback_available,
        revision_preservation_available=revision_preservation_available,
        saved_readback_available=saved_readback_available,
        saved_readback_fresh=saved_readback_fresh,
        destructive_operation=destructive_operation,
        publish_disabled_by_policy=not publish_enabled,
        proof_path=proof_path,
        target_lock_status=_target_lock_value(target_lock, "status"),
        target_lock_hash=_target_lock_value(target_lock, "lock_hash"),
        target_workbook_id=target_workbook_id or _target_lock_value(target_lock, "target_workbook_id"),
        target_dashboard_id=target_dashboard_id or _target_lock_value(target_lock, "target_dashboard_id"),
        target_chart_id=target_chart_id or _target_lock_value(target_lock, "target_chart_id"),
    )


def resolve_delivery_intent_from_env(
    user_text: str,
    *,
    default_text: str = "plan only",
    target_known: bool = False,
    approved: bool = False,
    approval_source: str = "",
    approval_sources: list[str] | None = None,
    fresh_readback_available: bool = False,
    revision_preservation_available: bool = False,
    saved_readback_available: bool = False,
    saved_readback_fresh: bool | None = None,
    destructive_operation: bool = False,
    proof_path: str = "",
    target_lock: TargetLock | dict[str, Any] | None = None,
    target_workbook_id: str = "",
    target_dashboard_id: str = "",
    target_chart_id: str = "",
) -> dict[str, Any]:
    context = delivery_context_from_env(
        target_known=target_known,
        approved=approved,
        approval_source=approval_source,
        approval_sources=approval_sources,
        fresh_readback_available=fresh_readback_available,
        revision_preservation_available=revision_preservation_available,
        saved_readback_available=saved_readback_available,
        saved_readback_fresh=saved_readback_fresh,
        destructive_operation=destructive_operation,
        proof_path=proof_path,
        target_lock=target_lock,
        target_workbook_id=target_workbook_id,
        target_dashboard_id=target_dashboard_id,
        target_chart_id=target_chart_id,
    )
    return resolve_delivery_intent(user_text or default_text, context).to_dict()


def _normalized_request(
    request: str | NormalizedUserRequest,
    context: DeliveryContext | dict[str, Any] | None,
) -> NormalizedUserRequest:
    if isinstance(request, NormalizedUserRequest):
        return request
    ctx = _context_dict(context)
    return normalize_user_request(
        str(request or ""),
        approval_sources=_approval_sources_from_context(ctx),
        context={
            "target_workbook_id": ctx.get("target_workbook_id") or ctx.get("workbook_id") or "",
            "target_dashboard_id": ctx.get("target_dashboard_id") or ctx.get("dashboard_id") or "",
            "target_chart_id": ctx.get("target_chart_id") or ctx.get("chart_id") or "",
        },
    )


def _inputs_from_request(
    normalized: NormalizedUserRequest,
    context: DeliveryContext | dict[str, Any] | None,
) -> DeliveryIntentInputs:
    ctx = _context_dict(context)
    publish_enabled_raw = ctx.get("publish_enabled")
    publish_enabled = bool(
        not bool(ctx.get("publish_disabled_by_policy", False)) if publish_enabled_raw is None else publish_enabled_raw
    )
    save_enabled_raw = ctx.get("save_enabled")
    save_enabled = bool(ctx.get("writes_enabled", False) if save_enabled_raw is None else save_enabled_raw)
    safe_apply_approved = bool(ctx.get("safe_apply_approved", False))
    approval_sources = _approval_sources_from_context(ctx, normalized.approval_sources)
    approval_source = _default_approval_source(safe_apply_approved, str(ctx.get("approval_source") or ""), approval_sources)
    target_known = bool(ctx.get("target_known")) or _target_lock_known(ctx.get("target_lock")) or normalized.target_known
    saved_readback_available = bool(ctx.get("saved_readback_available", False))
    saved_readback_fresh_raw = ctx.get("saved_readback_fresh", None)
    saved_readback_fresh = bool(saved_readback_available if saved_readback_fresh_raw is None else saved_readback_fresh_raw)
    opt_outs = []
    if normalized.publish_override in {"draft", "save_only", "no_publish"}:
        opt_outs.append(normalized.publish_override)
    return DeliveryIntentInputs(
        task_intent=normalized.task_intent,
        publish_override=normalized.publish_override,
        target_known=target_known,
        target_lock_status=str(ctx.get("target_lock_status") or _target_lock_value(ctx.get("target_lock"), "status") or ""),
        target_lock_hash=str(ctx.get("target_lock_hash") or _target_lock_value(ctx.get("target_lock"), "lock_hash") or ""),
        writes_enabled=bool(ctx.get("writes_enabled", False)),
        save_enabled=save_enabled,
        publish_enabled=publish_enabled,
        safe_apply_approved=safe_apply_approved,
        approval_source=approval_source,
        approval_sources=approval_sources,
        user_opt_out_phrases=opt_outs,
        workbook_id=str(ctx.get("target_workbook_id") or normalized.target_workbook_id or ""),
        dashboard_id=str(ctx.get("target_dashboard_id") or normalized.target_dashboard_id or ""),
        chart_id=str(ctx.get("target_chart_id") or normalized.target_chart_id or ""),
        fresh_readback_available=bool(ctx.get("fresh_readback_available", False)),
        revision_preservation_available=bool(ctx.get("revision_preservation_available", False)),
        saved_readback_available=saved_readback_available,
        saved_readback_fresh=saved_readback_fresh,
        destructive_operation=bool(ctx.get("destructive_operation", False) or normalized.destructive_actions),
        proof_path=str(ctx.get("proof_path") or ""),
    )


def _decision(
    *,
    state: DeliveryState,
    intent: Intent,
    inputs: DeliveryIntentInputs,
    reason: str,
    required_gates: list[str] | None = None,
    satisfied_gates: list[str] | None = None,
    blocked_reasons: list[str] | None = None,
    publish_expected: bool = False,
    writes_expected: bool = False,
    default_delivery: list[str] | None = None,
    next_action: str = "",
) -> DeliveryIntentDecision:
    return DeliveryIntentDecision(
        state=state,
        intent=intent,
        reason=reason,
        required_gates=required_gates or [],
        satisfied_gates=satisfied_gates or [],
        blocked_reasons=blocked_reasons or [],
        publish_expected=publish_expected,
        writes_expected=writes_expected,
        approval_reuse_for_publish=bool(state in {"save_then_publish", "publish_from_saved"} and inputs.has_approval),
        default_delivery=default_delivery or [],
        next_action=next_action,
        proof_path=inputs.proof_path,
        task_intent=inputs.task_intent,
        approval_source=inputs.approval_source,
        target_lock_status=inputs.target_lock_status,
        target_lock_hash=inputs.target_lock_hash,
        workbook_id=inputs.workbook_id,
        dashboard_id=inputs.dashboard_id,
        chart_id=inputs.chart_id,
        user_opt_out_phrases=inputs.user_opt_out_phrases,
        saved_readback_fresh=inputs.saved_readback_fresh,
    )


def _satisfied_gates(inputs: DeliveryIntentInputs, *, include_publish: bool) -> list[str]:
    checks = {
        "target_lock": inputs.target_known,
        "writes_enabled": inputs.writes_enabled,
        "save_enabled": inputs.save_enabled,
        "safe_apply_session_approval": inputs.has_approval,
        "fresh_readback": inputs.fresh_readback_available,
        "revision_preservation": inputs.revision_preservation_available,
        "saved_readback": inputs.saved_readback_available,
        "saved_readback_fresh": inputs.saved_readback_fresh,
    }
    if include_publish:
        checks["publish_enabled"] = inputs.publish_enabled
    return [name for name, ok in checks.items() if ok]


def _context_dict(context: DeliveryContext | dict[str, Any] | None) -> dict[str, Any]:
    if context is None:
        return {}
    if isinstance(context, DeliveryContext):
        return asdict(context)
    return dict(context)


def _approval_sources_from_context(ctx: dict[str, Any], base: list[str] | None = None) -> list[str]:
    sources = list(base or [])
    raw = ctx.get("approval_sources") or []
    if isinstance(raw, str):
        raw = [raw]
    for source in raw:
        if source and source not in sources:
            sources.append(str(source))
    approval_source = str(ctx.get("approval_source") or "").strip()
    if approval_source and approval_source not in sources:
        sources.append(approval_source)
    return sources


def _default_approval_source(approved: bool, approval_source: str, approval_sources: list[str]) -> str:
    if approval_source:
        return approval_source
    for source in SUFFICIENT_APPROVAL_SOURCES:
        if source in approval_sources:
            return source
    if approved:
        return "codex_tool_approval"
    return ""


def _target_lock_known(lock: TargetLock | dict[str, Any] | None) -> bool:
    if isinstance(lock, TargetLock):
        return lock.known
    if isinstance(lock, dict):
        return str(lock.get("status") or "") == "locked"
    return False


def _target_lock_value(lock: TargetLock | dict[str, Any] | None, key: str) -> str:
    if isinstance(lock, TargetLock):
        return str(lock.to_dict().get(key) or "")
    if isinstance(lock, dict):
        return str(lock.get(key) or "")
    return ""
