from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from datalens_dev_mcp.pipeline.user_request import NormalizedUserRequest, normalize_user_request


TargetSource = Literal["user_url", "manifest", "workbook_entry", "goal_objective", "manual"]
TargetStatus = Literal["locked", "ambiguous", "missing", "mismatch"]


@dataclass(frozen=True)
class TargetLock:
    target_source: TargetSource
    target_workbook_id: str
    lock_hash: str
    status: TargetStatus
    target_url: str = ""
    target_dashboard_id: str = ""
    target_chart_id: str = ""
    target_object_type: str = ""
    target_object_key: str = ""
    target_objects: list[dict[str, str]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return self.status == "locked"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_target_lock(
    request: str | NormalizedUserRequest | dict[str, Any],
    *,
    target_source: TargetSource | str = "manual",
    target_workbook_id: str = "",
    target_dashboard_id: str = "",
    target_chart_id: str = "",
    target_url: str = "",
    target_object_type: str = "",
    target_object_key: str = "",
    target_objects: list[dict[str, Any]] | None = None,
) -> TargetLock:
    if isinstance(request, NormalizedUserRequest):
        normalized = request
    elif isinstance(request, dict):
        normalized = normalize_user_request("", context=request)
    else:
        normalized = normalize_user_request(str(request))

    workbook_id = target_workbook_id or normalized.target_workbook_id
    dashboard_id = target_dashboard_id or normalized.target_dashboard_id
    chart_id = target_chart_id or normalized.target_chart_id
    object_type = target_object_type or normalized.target_object_type or ("dashboard" if dashboard_id else "chart" if chart_id else "")
    object_key = str(target_object_key or "").strip()
    normalized_target_objects, target_objects_valid = _normalize_target_objects(target_objects or [])
    url = target_url or normalized.target_url
    source = _target_source(target_source, url=url, normalized=normalized)
    evidence = list(normalized.evidence)
    if workbook_id:
        evidence.append(f"target_workbook_id:{workbook_id}")
    if dashboard_id:
        evidence.append(f"target_dashboard_id:{dashboard_id}")
    if chart_id:
        evidence.append(f"target_chart_id:{chart_id}")
    if object_key:
        evidence.append(f"target_object_key:{object_key}")
    evidence.extend(
        f"action_target:{item['method']}:{item['object_id']}"
        for item in normalized_target_objects
    )
    status = _target_status(
        workbook_id=workbook_id,
        dashboard_id=dashboard_id,
        chart_id=chart_id,
        object_type=object_type,
        object_key=object_key,
        target_objects=normalized_target_objects,
        target_objects_valid=target_objects_valid,
    )
    payload = {
        "target_source": source,
        "target_url": url,
        "target_workbook_id": workbook_id,
        "target_dashboard_id": dashboard_id,
        "target_chart_id": chart_id,
        "target_object_type": object_type,
        "target_object_key": object_key,
        "target_objects": normalized_target_objects,
    }
    return TargetLock(
        target_source=source,
        target_url=url,
        target_workbook_id=workbook_id,
        target_dashboard_id=dashboard_id,
        target_chart_id=chart_id,
        target_object_type=object_type,
        target_object_key=object_key,
        target_objects=normalized_target_objects,
        lock_hash=_hash_payload(payload),
        status=status,
        evidence=sorted(dict.fromkeys(evidence)),
    )


def validate_action_target_lock(lock: TargetLock | dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    lock_obj = _lock_obj(lock)
    observed = _extract_action_ids(action)
    findings: list[str] = []
    if not lock_obj.known:
        findings.append(f"target lock is not locked: {lock_obj.status}")
    if lock_obj.target_objects:
        expected_targets = {
            (item["method"], item["object_id"])
            for item in lock_obj.target_objects
        }
        observed_target = (observed.get("method", ""), observed.get("object_id", ""))
        if observed_target not in expected_targets:
            findings.append(
                "action target is outside the locked action set: "
                f"{observed_target[0]}:{observed_target[1]}"
            )
    else:
        for key, expected in (
            ("workbook_id", lock_obj.target_workbook_id),
            ("dashboard_id", lock_obj.target_dashboard_id),
            ("chart_id", lock_obj.target_chart_id),
        ):
            if not expected:
                continue
            actual = observed.get(key)
            if actual and actual != expected:
                findings.append(f"{key} mismatch: expected {expected}, got {actual}")
        if lock_obj.target_dashboard_id and not observed.get("dashboard_id") and not observed.get("chart_id"):
            findings.append("action does not carry dashboard_id or chart_id target evidence")
    return {
        "ok": not findings,
        "target_lock_hash": lock_obj.lock_hash,
        "expected": lock_obj.to_dict(),
        "observed": observed,
        "findings": findings,
    }


def validate_readback_target_lock(lock: TargetLock | dict[str, Any], readback: dict[str, Any]) -> dict[str, Any]:
    lock_obj = _lock_obj(lock)
    observed = _extract_readback_ids(readback)
    findings: list[str] = []
    expected_object_ids = {
        item["object_id"]
        for item in lock_obj.target_objects
        if item.get("object_id")
    }
    observed_object_ids = set(observed.get("object_ids") or [])
    if expected_object_ids:
        if not observed_object_ids:
            findings.append("readback does not expose an action-set object identity")
        extra = sorted(observed_object_ids - expected_object_ids)
        if extra:
            findings.append("readback exposes objects outside target lock: " + ", ".join(extra))
    if lock_obj.target_dashboard_id and not lock_obj.target_objects:
        actual_dashboard = observed.get("dashboard_id")
        if actual_dashboard and actual_dashboard != lock_obj.target_dashboard_id:
            findings.append(f"dashboard_id mismatch: expected {lock_obj.target_dashboard_id}, got {actual_dashboard}")
        elif observed_object_ids and lock_obj.target_dashboard_id not in observed_object_ids and not lock_obj.target_objects:
            findings.append(
                f"dashboard_id mismatch: expected {lock_obj.target_dashboard_id}, "
                f"got {', '.join(sorted(observed_object_ids))}"
            )
    if lock_obj.target_chart_id and not lock_obj.target_objects:
        actual_chart = observed.get("chart_id")
        if actual_chart and actual_chart != lock_obj.target_chart_id:
            findings.append(f"chart_id mismatch: expected {lock_obj.target_chart_id}, got {actual_chart}")
        elif observed_object_ids and lock_obj.target_chart_id not in observed_object_ids and not lock_obj.target_objects:
            findings.append(
                f"chart_id mismatch: expected {lock_obj.target_chart_id}, "
                f"got {', '.join(sorted(observed_object_ids))}"
            )
    if not observed.get("dashboard_id") and not observed.get("chart_id") and not observed_object_ids:
        findings.append("readback does not expose a dashboard or chart identity")
    return {
        "ok": not findings,
        "target_lock_hash": lock_obj.lock_hash,
        "expected": lock_obj.to_dict(),
        "observed": observed,
        "findings": findings,
    }


def validate_target_delivery_trace(trace: dict[str, Any]) -> dict[str, Any]:
    lock = _lock_obj(trace.get("target_lock") or {})
    findings: list[dict[str, Any]] = []
    if not lock.known:
        findings.append({"rule": "target_lock_not_locked", "message": f"target lock status is {lock.status}"})
    for index, action in enumerate(trace.get("actions") or []):
        result = validate_action_target_lock(lock, action)
        if not result["ok"]:
            findings.append({"rule": "action_target_mismatch", "index": index, "findings": result["findings"]})
    for branch in ("saved_readback", "published_readback", "final_report"):
        value = trace.get(branch)
        if not isinstance(value, dict) or not value:
            continue
        result = validate_readback_target_lock(lock, value)
        if not result["ok"]:
            findings.append({"rule": f"{branch}_target_mismatch", "findings": result["findings"]})
    active_widgets = _active_widget_count(trace.get("published_readback") or trace.get("final_report") or {})
    generated_widgets = int(trace.get("generated_widget_count") or 0)
    if lock.target_dashboard_id and active_widgets == 0 and generated_widgets > 0:
        findings.append(
            {
                "rule": "target_dashboard_has_zero_widgets",
                "message": "target dashboard has zero active widgets while generated layout has widgets",
            }
        )
    return {
        "ok": not findings,
        "target_lock_hash": lock.lock_hash,
        "findings": findings,
    }


def _target_source(source: str, *, url: str, normalized: NormalizedUserRequest) -> TargetSource:
    if source in {"user_url", "manifest", "workbook_entry", "goal_objective", "manual"}:
        return source  # type: ignore[return-value]
    if url:
        return "user_url"
    if normalized.target_url:
        return "user_url"
    return "manual"


def _target_status(
    *,
    workbook_id: str,
    dashboard_id: str,
    chart_id: str,
    object_type: str,
    object_key: str,
    target_objects: list[dict[str, str]],
    target_objects_valid: bool,
) -> TargetStatus:
    if target_objects:
        if not target_objects_valid:
            return "ambiguous"
        if not workbook_id:
            return "missing"
        return "locked"
    if dashboard_id and chart_id:
        return "ambiguous"
    if not (dashboard_id or chart_id) and not (object_type and object_key):
        return "missing"
    if not workbook_id:
        return "missing"
    return "locked"


def _hash_payload(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _lock_obj(lock: TargetLock | dict[str, Any]) -> TargetLock:
    if isinstance(lock, TargetLock):
        return lock
    status = str(lock.get("status") or "missing")
    if status not in {"locked", "ambiguous", "missing", "mismatch"}:
        status = "missing"
    source = str(lock.get("target_source") or "manual")
    if source not in {"user_url", "manifest", "workbook_entry", "goal_objective", "manual"}:
        source = "manual"
    payload = {
        "target_source": source,
        "target_url": str(lock.get("target_url") or ""),
        "target_workbook_id": str(lock.get("target_workbook_id") or ""),
        "target_dashboard_id": str(lock.get("target_dashboard_id") or ""),
        "target_chart_id": str(lock.get("target_chart_id") or ""),
        "target_object_type": str(lock.get("target_object_type") or ""),
        "target_object_key": str(lock.get("target_object_key") or ""),
        "target_objects": _normalize_target_objects(lock.get("target_objects") or [])[0],
    }
    return TargetLock(
        target_source=source,  # type: ignore[arg-type]
        target_url=payload["target_url"],
        target_workbook_id=payload["target_workbook_id"],
        target_dashboard_id=payload["target_dashboard_id"],
        target_chart_id=payload["target_chart_id"],
        target_object_type=payload["target_object_type"],
        target_object_key=payload["target_object_key"],
        target_objects=payload["target_objects"],
        lock_hash=str(lock.get("lock_hash") or _hash_payload(payload)),
        status=status,  # type: ignore[arg-type]
        evidence=list(lock.get("evidence") or []),
    )


def _extract_action_ids(action: dict[str, Any]) -> dict[str, str]:
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    fresh = action.get("fresh_read_payload") if isinstance(action.get("fresh_read_payload"), dict) else {}
    readback = action.get("readback_payload") if isinstance(action.get("readback_payload"), dict) else {}
    values = {**payload, **entry, **fresh, **readback, **action}
    dashboard_id = _first(values, "dashboardId", "dashboard_id")
    chart_id = _first(values, "chartId", "chart_id", "entryId", "object_id")
    return {
        "method": str(action.get("method") or ""),
        "object_id": dashboard_id or chart_id,
        "workbook_id": _first(values, "workbookId", "workbook_id"),
        "dashboard_id": dashboard_id,
        "chart_id": chart_id,
    }


def _extract_readback_ids(readback: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = dict(readback)
    object_ids: set[str] = set()
    for key in ("dashboard", "chart", "entry", "object", "summary", "response"):
        item = readback.get(key)
        if isinstance(item, dict):
            values.update(item)
            nested = item.get("entry")
            if isinstance(nested, dict):
                values.update(nested)
    for key in ("charts", "objects", "entries"):
        items = readback.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            nested = item.get("entry")
            if isinstance(nested, dict):
                item = nested
            response = item.get("response")
            if isinstance(response, dict) and isinstance(response.get("entry"), dict):
                item = response["entry"]
            object_id = _first(item, "entryId", "entry_id", "dashboardId", "dashboard_id", "chartId", "chart_id", "id")
            if object_id:
                object_ids.add(object_id)
    supplied_object_ids = readback.get("object_ids")
    if isinstance(supplied_object_ids, list):
        for item in supplied_object_ids:
            if isinstance(item, dict):
                object_id = _first(
                    item,
                    "entryId",
                    "entry_id",
                    "dashboardId",
                    "dashboard_id",
                    "chartId",
                    "chart_id",
                    "object_id",
                    "id",
                )
            else:
                object_id = str(item or "").strip()
            if object_id:
                object_ids.add(object_id)
    compact = readback.get("compact_graph")
    if isinstance(compact, dict):
        values.update(compact)
    branch_summary = readback.get("branch_summary")
    if isinstance(branch_summary, dict):
        values.update(branch_summary)
    dashboard_id = _first(values, "dashboardId", "dashboard_id")
    chart_id = _first(values, "chartId", "chart_id")
    direct_entry_id = _first(values, "entryId", "entry_id", "id")
    if dashboard_id:
        object_ids.add(dashboard_id)
    if chart_id:
        object_ids.add(chart_id)
    if direct_entry_id:
        object_ids.add(direct_entry_id)
    return {
        "workbook_id": _first(values, "workbookId", "workbook_id"),
        "dashboard_id": dashboard_id or (direct_entry_id if "dashboard" in readback else ""),
        "chart_id": chart_id,
        "object_ids": sorted(object_ids),
    }


def _normalize_target_objects(
    target_objects: Any,
) -> tuple[list[dict[str, str]], bool]:
    if not isinstance(target_objects, list):
        return [], False
    normalized: list[dict[str, str]] = []
    valid = True
    for item in target_objects:
        if not isinstance(item, dict):
            valid = False
            continue
        method = str(item.get("method") or "").strip()
        object_id = str(item.get("object_id") or item.get("id") or "").strip()
        if not method or not object_id:
            valid = False
            continue
        normalized.append({"method": method, "object_id": object_id})
    normalized.sort(key=lambda item: (item["method"], item["object_id"]))
    unique = {
        (item["method"], item["object_id"])
        for item in normalized
    }
    if len(unique) != len(normalized):
        valid = False
    return normalized, valid


def _first(values: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = values.get(key)
        if value:
            return str(value)
    return ""


def _active_widget_count(value: dict[str, Any]) -> int:
    for key in ("active_widget_count", "active_widgets", "widget_count"):
        raw = value.get(key)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, list):
            return len(raw)
    counts = value.get("counts_by_object_type")
    if isinstance(counts, dict):
        return int(counts.get("widget") or counts.get("widgets") or counts.get("chart") or counts.get("charts") or 0)
    compact = value.get("compact_graph")
    if isinstance(compact, dict):
        return _active_widget_count(compact)
    return 0
