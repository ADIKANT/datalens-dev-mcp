from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


BrowserQaStatus = Literal[
    "browser_pass",
    "browser_fail",
    "browser_auth_required",
    "browser_tool_timeout",
    "browser_not_authorized_by_user",
    "not_checked",
]

RUNTIME_ERROR_MARKERS = [
    "ERR.DS_API.FIELD.NOT_FOUND",
    "FIELD.NOT_FOUND",
    "UNKNOWN_IDENTIFIER",
    "DB::Exception",
    "502 Bad Gateway",
    "Using non-existent field",
    "Unknown field",
    "Data fetching error",
]


def browser_qa_evidence(
    *,
    status: str = "not_checked",
    artifact_paths: list[str] | None = None,
    message: str = "",
    checked_url: str = "",
) -> dict[str, Any]:
    normalized = _normalize_status(status)
    paths = [str(path) for path in artifact_paths or [] if str(path)]
    blocked_reasons: list[str] = []
    if normalized == "browser_pass" and not paths:
        normalized = "not_checked"
        blocked_reasons.append("browser_pass_requires_rendered_artifact")
    elif normalized in {"browser_auth_required", "browser_tool_timeout", "browser_not_authorized_by_user", "not_checked"}:
        blocked_reasons.append(normalized)
    return {
        "schema_version": "datalens.browser-runtime-qa.v1",
        "status": normalized,
        "proof_level": "browser_rendered" if normalized in {"browser_pass", "browser_fail"} else "source_static",
        "browser_verified": normalized == "browser_pass",
        "checked_url": checked_url,
        "artifact_paths": paths,
        "artifact_hashes": {path: _file_sha256(path) for path in paths if Path(path).is_file()},
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "message": message,
        "blocked_reasons": blocked_reasons,
    }


def build_runtime_publish_gate(
    *,
    status: str = "not_run",
    dashboard_id: str,
    tab_id: str = "",
    dashboard_url: str = "",
    changed_object_ids: list[str] | None = None,
    checked_error_markers: list[str] | None = None,
    proof_artifacts: list[str] | None = None,
    runtime_messages: list[str] | None = None,
    visible_object_ids: list[str] | None = None,
    selector_statuses: list[dict[str, Any]] | None = None,
    blocked_reason: str = "",
) -> dict[str, Any]:
    normalized = _normalize_gate_status(status)
    changed = [str(item) for item in changed_object_ids or [] if str(item)]
    markers = checked_error_markers or RUNTIME_ERROR_MARKERS
    artifacts = [str(path) for path in proof_artifacts or [] if str(path)]
    blocking_errors = _runtime_blocking_errors(runtime_messages or [], markers)
    visible_missing = (
        sorted(set(changed) - {str(item) for item in visible_object_ids or [] if str(item)})
        if visible_object_ids is not None
        else []
    )
    selector_errors = _selector_blocking_errors(selector_statuses or [])
    blocking_errors.extend(selector_errors)
    if visible_missing:
        blocking_errors.extend(
            {
                "marker": "changed_object_not_visible",
                "message": f"changed object {object_id} was not visible in runtime",
                "object_id": object_id,
            }
            for object_id in visible_missing
        )
    if normalized == "passed" and blocking_errors:
        normalized = "failed"
    if normalized == "passed" and not artifacts:
        normalized = "blocked"
        blocked_reason = blocked_reason or "runtime proof artifact is required"
    if normalized == "not_run" and blocked_reason:
        normalized = "blocked"
    return {
        "schema_version": "datalens.runtime-publish-gate.delta-v6",
        "status": normalized,
        "dashboard_id": dashboard_id,
        "tab_id": tab_id,
        "dashboard_url": dashboard_url,
        "changed_object_ids": changed,
        "checked_error_markers": markers,
        "blocking_errors": blocking_errors,
        "visible_assertions": [
            {"object_id": object_id, "visible": object_id not in visible_missing}
            for object_id in changed
        ],
        "selector_statuses": selector_statuses or [],
        "proof_artifacts": artifacts,
        "blocked_reason": blocked_reason if normalized in {"blocked", "not_run"} else "",
    }


def delivery_status_from_runtime_gate(runtime_gate: dict[str, Any]) -> str:
    status = str(runtime_gate.get("status") or "").strip()
    if status == "passed":
        return "done"
    if status in {"blocked", "not_run", ""}:
        return "runtime_not_verified"
    return "blocked"


def write_timestamped_evidence(root: str | Path, subdir: str, payload: dict[str, Any]) -> dict[str, Any]:
    base = Path(root) / "artifacts" / subdir
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), "sha256": _file_sha256(path)}


def _normalize_status(status: str) -> BrowserQaStatus:
    normalized = str(status or "not_checked").strip().lower()
    aliases = {
        "pass": "browser_pass",
        "passed": "browser_pass",
        "fail": "browser_fail",
        "failed": "browser_fail",
        "auth": "browser_auth_required",
        "auth_required": "browser_auth_required",
        "timeout": "browser_tool_timeout",
        "tool_timeout": "browser_tool_timeout",
        "not_authorized": "browser_not_authorized_by_user",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {
        "browser_pass",
        "browser_fail",
        "browser_auth_required",
        "browser_tool_timeout",
        "browser_not_authorized_by_user",
        "not_checked",
    }:
        return normalized  # type: ignore[return-value]
    return "not_checked"


def _normalize_gate_status(status: str) -> str:
    normalized = str(status or "not_run").strip().lower()
    aliases = {
        "pass": "passed",
        "browser_pass": "passed",
        "ok": "passed",
        "fail": "failed",
        "browser_fail": "failed",
        "auth": "blocked",
        "auth_required": "blocked",
        "browser_auth_required": "blocked",
        "timeout": "blocked",
        "browser_tool_timeout": "blocked",
        "not_checked": "not_run",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"passed", "failed", "blocked", "not_run"}:
        return normalized
    return "not_run"


def _runtime_blocking_errors(messages: list[str], markers: list[str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for message in messages:
        text = str(message)
        lowered = text.lower()
        for marker in markers:
            if str(marker).lower() in lowered:
                errors.append({"marker": str(marker), "message": text[:500]})
                break
    return errors


def _selector_blocking_errors(selector_statuses: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for selector in selector_statuses:
        status = str(selector.get("status") or "").strip().lower()
        if status in {"", "passed", "loaded", "ok"}:
            continue
        selector_id = str(selector.get("selector_id") or selector.get("id") or "")
        errors.append(
            {
                "marker": "selector_load_status",
                "message": f"selector {selector_id or '<unknown>'} runtime status is {status}",
                "object_id": selector_id,
            }
        )
    return errors


def _file_sha256(path: str | Path) -> str:
    target = Path(path)
    if not target.is_file():
        return ""
    return hashlib.sha256(target.read_bytes()).hexdigest()
