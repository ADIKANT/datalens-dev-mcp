from __future__ import annotations

from typing import Any


CHANGE_CLASS_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "source_labels_only": ("static_validation", "data_assertions", "saved_readback"),
    "selector_behavior": ("static_validation", "data_assertions", "contract_harness", "saved_readback"),
    "renderer_logic": ("static_validation", "contract_harness", "saved_readback"),
    "dashboard_layout": ("static_validation", "composition_validation", "saved_readback"),
    "publish_only": ("saved_readback",),
}


def build_evidence_matrix(
    *,
    change_class: str,
    browser_policy: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    stage: str = "before_publish",
) -> dict[str, Any]:
    normalized_change = str(change_class or "").strip().lower()
    if normalized_change not in CHANGE_CLASS_REQUIREMENTS:
        normalized_change = "renderer_logic"
    policy = normalize_browser_policy(browser_policy, change_class=normalized_change)
    required = list(CHANGE_CLASS_REQUIREMENTS[normalized_change])
    if normalized_change == "publish_only" and stage == "completion":
        required.append("published_readback")
    final_visual = policy["purpose"] == "final_visual_acceptance"
    browser_required = policy["mode"] == "required" and (
        not final_visual or stage == "completion"
    )
    if browser_required:
        required.append("browser_attestation")
    observed = _normalize_evidence(evidence or {})
    missing = [name for name in required if not observed.get(name, False)]
    claims = _claims_from_observed(observed)
    return {
        "schema_id": "evidence_matrix",
        "change_class": normalized_change,
        "stage": stage,
        "browser_policy": policy,
        "required_evidence": required,
        "observed_evidence": observed,
        "missing_evidence": missing,
        "browser_adapter_allowed": (
            policy["mode"] != "forbidden"
            and policy["applicability"] == "applicable"
            and not (final_visual and stage != "completion")
        ),
        "browser_adapter_required": browser_required,
        "should_call_browser": browser_required and not observed.get("browser_attestation", False),
        "can_publish": not missing,
        "proof_claims": claims,
    }


def normalize_browser_policy(
    policy: dict[str, Any] | None,
    *,
    change_class: str = "renderer_logic",
) -> dict[str, Any]:
    value = policy if isinstance(policy, dict) else {}
    mode = str(value.get("mode") or "").strip().lower()
    source = str(value.get("source") or "").strip().lower()
    if mode not in {"forbidden", "optional", "required"}:
        mode = "optional"
        source = "compiled_default"
    if source not in {"explicit_user", "compiled_default", "workspace_policy"}:
        source = "compiled_default"
    applicability = str(value.get("applicability") or "applicable")
    if applicability not in {"applicable", "not_applicable"}:
        applicability = "applicable"
    purpose = str(value.get("purpose") or "runtime_visual_evidence")
    final_visual = purpose == "final_visual_acceptance"
    return {
        "mode": mode,
        "source": source,
        "applicability": applicability,
        "change_class": change_class,
        "purpose": purpose,
        "read_only": True,
        "mutation_allowed": False,
        "earliest_stage": str(value.get("earliest_stage") or (
            "published_readback_and_api_diagnostics_complete" if final_visual else "qa"
        )),
        "calls_before_earliest_stage_allowed": bool(
            value.get("calls_before_earliest_stage_allowed", not final_visual)
        ),
        "allowed_interactions": [
            str(item) for item in value.get("allowed_interactions") or [] if str(item)
        ],
        "target": dict(value.get("target") or {}),
    }


def browser_policy_from_legacy_flag(
    browser_runtime_required: bool | None,
    *,
    maintenance_mode: str,
    supplied_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(supplied_policy, dict) and supplied_policy:
        return normalize_browser_policy(supplied_policy)
    if browser_runtime_required is True:
        return normalize_browser_policy(
            {"mode": "required", "source": "compiled_default"},
            change_class="renderer_logic",
        )
    if browser_runtime_required is False:
        return normalize_browser_policy(
            {"mode": "forbidden", "source": "compiled_default"},
            change_class="source_labels_only",
        )
    data_only = maintenance_mode in {"dataset_sql_patch", "source_availability_patch"}
    return normalize_browser_policy(
        {"mode": "optional" if data_only else "required", "source": "compiled_default"},
        change_class="source_labels_only" if data_only else "renderer_logic",
    )


def _normalize_evidence(evidence: dict[str, Any]) -> dict[str, bool]:
    aliases = {
        "static_validation": ("static_validation", "static", "static_ok"),
        "data_assertions": ("data_assertions", "data", "live_data_verified"),
        "contract_harness": ("contract_harness", "render_contract_harness", "contract_runtime"),
        "composition_validation": ("composition_validation", "composition", "layout_validation"),
        "saved_readback": ("saved_readback", "saved"),
        "published_readback": ("published_readback", "published"),
        "browser_attestation": ("browser_attestation", "browser", "qa_attestation"),
    }
    return {
        name: any(_evidence_passes(evidence.get(alias)) for alias in names)
        for name, names in aliases.items()
    }


def _evidence_passes(value: Any) -> bool:
    if value is True:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("ok") is True:
        return True
    return str(value.get("status") or "").lower() in {"passed", "pass", "completed", "attested"}


def _claims_from_observed(observed: dict[str, bool]) -> list[str]:
    claims: list[str] = []
    if observed.get("static_validation"):
        claims.append("source_static_validated")
    if observed.get("data_assertions"):
        claims.append("live_data_verified")
    if observed.get("contract_harness"):
        claims.append("editor_contract_runtime_validated")
    if observed.get("saved_readback"):
        claims.append("saved_revision_read_back")
    if observed.get("published_readback"):
        claims.append("published_revision_read_back")
    if observed.get("browser_attestation"):
        claims.append("browser_rendered_revision_attested")
    return claims
