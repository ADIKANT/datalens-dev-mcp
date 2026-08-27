from __future__ import annotations

from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


def resolve_execution_authorization(contract: dict[str, Any]) -> dict[str, Any]:
    delivery = contract.get("delivery") or {}
    write_requested = bool(delivery.get("save") or delivery.get("publish"))
    destructive = bool(delivery.get("destructive"))
    mode = "read_only"
    if destructive:
        mode = "destructive_exact_token"
    elif write_requested:
        mode = "automatic_from_explicit_request"
    payload = {
        "schema_id": "datalens_execution_authorization",
        "authorization_version": 1,
        "mode": mode,
        "source": "current_user_request",
        "authorized_delivery": {
            "save": bool(delivery.get("save")) and not destructive,
            "publish": bool(delivery.get("publish")) and not destructive,
            "destructive": False,
        },
        "request_hash": str(contract.get("raw_request_hash") or ""),
        "contract_hash": str(contract.get("contract_hash") or ""),
    }
    payload["authorization_hash"] = canonical_hash(payload)
    return payload


def validate_execution_authorization(authorization: dict[str, Any], contract: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if authorization.get("schema_id") != "datalens_execution_authorization":
        issues.append("execution authorization is missing")
    if authorization.get("contract_hash") != contract.get("contract_hash"):
        issues.append("execution authorization contract_hash mismatch")
    value = dict(authorization)
    digest = str(value.pop("authorization_hash", ""))
    if not digest or digest != canonical_hash(value):
        issues.append("execution authorization hash mismatch")
    return tuple(issues)


def authorizes_write(authorization: dict[str, Any], *, publish: bool = False) -> bool:
    delivery = authorization.get("authorized_delivery") or {}
    return bool(delivery.get("publish" if publish else "save"))
