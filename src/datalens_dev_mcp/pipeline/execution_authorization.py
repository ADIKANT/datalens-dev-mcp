from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


def resolve_execution_authorization(contract: dict[str, Any]) -> dict[str, Any]:
    delivery = contract.get("delivery") or {}
    write_requested = bool(delivery.get("save") or delivery.get("publish"))
    destructive = bool(delivery.get("destructive"))
    confirmation_required = bool((contract.get("confirmation") or {}).get("required"))
    mode = "read_only"
    if destructive:
        mode = "destructive_exact_token"
    elif write_requested:
        mode = "pending_confirmation" if confirmation_required else "automatic_from_explicit_request"
    payload = {
        "schema_id": "datalens_execution_authorization",
        "authorization_version": 1,
        "mode": mode,
        "source": "current_user_request",
        "authorized_delivery": {
            "save": bool(delivery.get("save")) and not destructive and not confirmation_required,
            "publish": bool(delivery.get("publish")) and not destructive and not confirmation_required,
            "destructive": False,
        },
        "request_hash": str(contract.get("raw_request_hash") or ""),
        "contract_hash": str(contract.get("contract_hash") or ""),
        "confirmation": {
            "required": confirmation_required,
            "confirmed": False,
        },
    }
    payload["authorization_hash"] = canonical_hash(payload)
    return payload


def confirm_execution_authorization(
    contract: dict[str, Any],
    *,
    plan_hash: str,
    source_turn_hash: str,
) -> dict[str, Any]:
    delivery = contract.get("delivery") or {}
    target = contract.get("target") or {}
    payload = {
        "schema_id": "datalens_execution_authorization",
        "authorization_version": 1,
        "mode": "confirmed_plan",
        "source": "explicit_confirmation_turn",
        "authorized_delivery": {
            "save": bool(delivery.get("save")) and not bool(delivery.get("destructive")),
            "publish": bool(delivery.get("publish")) and not bool(delivery.get("destructive")),
            "destructive": False,
        },
        "request_hash": str(contract.get("raw_request_hash") or ""),
        "contract_hash": str(contract.get("contract_hash") or ""),
        "confirmation": {
            "required": True,
            "confirmed": True,
            "task_id": str(contract.get("task_id") or ""),
            "contract_revision": int(contract.get("contract_revision") or 1),
            "plan_hash": str(plan_hash),
            "target_hash": canonical_hash(target),
            "scope_hash": canonical_hash(contract.get("scope") or {}),
            "technology": str(target.get("technology") or contract.get("route") or ""),
            "delivery_hash": canonical_hash(delivery),
            "source_turn_hash": str(source_turn_hash),
        },
    }
    payload["authorization_hash"] = canonical_hash(payload)
    return payload


def validate_execution_authorization(
    authorization: dict[str, Any],
    contract: dict[str, Any],
    *,
    plan_hash: str = "",
) -> tuple[str, ...]:
    issues: list[str] = []
    if authorization.get("schema_id") != "datalens_execution_authorization":
        issues.append("execution authorization is missing")
    if authorization.get("contract_hash") != contract.get("contract_hash"):
        issues.append("execution authorization contract_hash mismatch")
    value = dict(authorization)
    digest = str(value.pop("authorization_hash", ""))
    if not digest or digest != canonical_hash(value):
        issues.append("execution authorization hash mismatch")
    confirmation_required = bool((contract.get("confirmation") or {}).get("required"))
    confirmation = authorization.get("confirmation") or {}
    if confirmation_required and confirmation.get("confirmed"):
        target = contract.get("target") or {}
        delivery = contract.get("delivery") or {}
        expected = {
            "task_id": str(contract.get("task_id") or ""),
            "contract_revision": int(contract.get("contract_revision") or 1),
            "target_hash": canonical_hash(target),
            "scope_hash": canonical_hash(contract.get("scope") or {}),
            "technology": str(target.get("technology") or contract.get("route") or ""),
            "delivery_hash": canonical_hash(delivery),
        }
        for key, expected_value in expected.items():
            if confirmation.get(key) != expected_value:
                issues.append(f"execution confirmation {key} mismatch")
        if plan_hash and confirmation.get("plan_hash") != plan_hash:
            issues.append("execution confirmation plan_hash mismatch")
    return tuple(issues)


def authorizes_write(authorization: dict[str, Any], *, publish: bool = False) -> bool:
    delivery = authorization.get("authorized_delivery") or {}
    return bool(delivery.get("publish" if publish else "save"))
