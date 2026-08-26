from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def attempt_signature(
    *,
    target_revision: Any,
    plan_hash: str,
    failure_class: str,
    resulting_hash: str,
) -> dict[str, str]:
    fields = {
        "target_revision": str(target_revision),
        "plan_hash": str(plan_hash),
        "failure_class": str(failure_class),
        "resulting_hash": str(resulting_hash),
    }
    fields["signature"] = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return fields


def evaluate_noop_attempt(history: list[dict[str, Any]], current: dict[str, Any]) -> dict[str, Any]:
    signature = str(current.get("signature") or "")
    repeated = bool(signature) and any(str(item.get("signature") or "") == signature for item in history)
    return {
        "ok": not repeated,
        "status": "NO_PROGRESS" if repeated else "PROGRESS_POSSIBLE",
        "repeat_write_allowed": not repeated,
        "signature": signature,
        "root_cause_review_required": repeated,
    }


def record_noop_attempt(path: str | Path, current: dict[str, Any], *, max_entries: int = 32) -> dict[str, Any]:
    target = Path(path)
    history: list[dict[str, Any]] = []
    if target.is_file():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            history = list(payload.get("attempts") or []) if isinstance(payload, dict) else []
        except (OSError, json.JSONDecodeError):
            history = []
    decision = evaluate_noop_attempt(history, current)
    if decision["ok"]:
        history.append(dict(current))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"schema_id": "semantic_patch_attempts", "attempts": history[-max_entries:]}, indent=2) + "\n",
            encoding="utf-8",
        )
    return decision
