from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from datalens_dev_mcp.validators.redaction import redact_text


RUNTIME_GATE_SCHEMA_VERSION = "datalens.delta_v7.runtime_gate_evidence.v1"
BROWSER_RUNTIME_SMOKE_SCHEMA_VERSION = "datalens.delta_v8.browser_runtime_smoke.v1"
MAX_CAPTURE_IMAGE_DIMENSION = 65_535
MAX_CAPTURE_IMAGE_PIXELS = 50_000_000
MAX_CAPTURE_DECODED_BYTES = 256 * 1024 * 1024
SCROLL_BOTTOM_TOLERANCE_PX = 2.0

SELECTOR_NOT_APPLICABLE_CODES = {
    "no_selectors_in_scope",
    "selectors_not_affected_by_change",
    "target_is_non_interactive",
}

RUNTIME_GATE_MARKERS = [
    "Data fetching error",
    "Unknown field",
    "Using non-existent field",
    "DB::Exception",
    "ILLEGAL_AGGREGATION",
    "NO_COMMON_TYPE",
    "UNKNOWN_IDENTIFIER",
    "ERR.DS_API.FIELD.NOT_FOUND",
    "ERR.DS_API.DB.COLUMN_DOES_NOT_EXIST",
    "Too many series on the chart",
    "ERR.CK.TOOMANYLINES",
    "NOT_IMPLEMENTED",
    "Data source refused connection",
    "502 Bad Gateway",
    "UNKNOWN_TABLE",
]


def build_runtime_gate_evidence(
    *,
    status: str = "not_run",
    target_url: str = "",
    tab_id: str = "",
    changed_object_ids: list[str] | None = None,
    required_changed_object_ids: list[str] | None = None,
    required_target_url: str = "",
    required_tab_id: str = "",
    branch: str = "",
    revision_id: str = "",
    object_revisions: dict[str, str] | None = None,
    required_branch: str = "",
    required_revision_id: str = "",
    required_object_revisions: dict[str, str] | None = None,
    delivery_stage: str = "",
    checked_selectors: list[dict[str, Any]] | None = None,
    visible_widget_titles: list[str] | None = None,
    expected_titles: list[str] | None = None,
    body_text_excerpt: str = "",
    console_messages: list[str] | None = None,
    dom_error_texts: list[str] | None = None,
    marker_counts: dict[str, int] | None = None,
    console_error_count: int | None = None,
    extracted_error_details: list[dict[str, Any]] | None = None,
    screenshot_artifacts: list[str] | None = None,
    proof_artifacts: list[str] | None = None,
    proof_artifact_metadata: list[dict[str, Any]] | None = None,
    browser_capture_artifact: str = "",
    browser_capture_artifact_metadata: dict[str, Any] | None = None,
    artifact_root: str | Path | None = None,
    non_rendering_exemption: str = "",
    blocked_reason: str = "",
) -> dict[str, Any]:
    normalized = _normalize_runtime_status(status)
    capture_validation = validate_browser_capture_artifact(
        browser_capture_artifact,
        artifact_metadata=browser_capture_artifact_metadata,
        artifact_root=artifact_root,
    )
    capture = capture_validation.get("document") if isinstance(capture_validation.get("document"), dict) else {}
    rendering_pass = normalized == "passed" and not non_rendering_exemption.strip()
    selector_interaction: dict[str, Any] = {}
    scroll_check: dict[str, Any] = {}
    if rendering_pass and capture:
        target_url = str(capture.get("target_url") or "")
        tab_id = str(capture.get("tab_id") or "")
        changed_object_ids = [str(item) for item in capture.get("changed_object_ids") or []]
        checked_selectors = (
            capture.get("checked_selectors") if isinstance(capture.get("checked_selectors"), list) else []
        )
        selector_interaction = (
            dict(capture.get("selector_interaction"))
            if isinstance(capture.get("selector_interaction"), dict)
            else {}
        )
        scroll_check = dict(capture.get("scroll_check")) if isinstance(capture.get("scroll_check"), dict) else {}
        visible_widget_titles = [str(item) for item in capture.get("visible_widget_titles") or []]
        body_text_excerpt = str(capture.get("body_text_excerpt") or "")
        console_messages = [str(item) for item in capture.get("console_messages") or []]
        dom_error_texts = [str(item) for item in capture.get("dom_error_texts") or []]
        marker_counts = capture.get("marker_counts") if isinstance(capture.get("marker_counts"), dict) else {}
        console_error_count = capture.get("console_error_count")
        branch = str(capture.get("branch") or "")
        revision_id = str(capture.get("revision_id") or "")
        object_revisions = (
            capture.get("object_revisions") if isinstance(capture.get("object_revisions"), dict) else {}
        )
    messages = [str(item) for item in console_messages or []]
    dom_messages = [str(item) for item in dom_error_texts or []]
    extracted = [
        _sanitize_detail(item)
        for item in extracted_error_details or []
        if isinstance(item, dict)
    ]
    if not extracted:
        extracted = extract_runtime_error_details(
            body_text_excerpt=body_text_excerpt,
            console_messages=messages,
            dom_error_texts=dom_messages,
        )
    counts = {marker: 0 for marker in RUNTIME_GATE_MARKERS}
    marker_count_issues: list[str] = []
    for key, value in (marker_counts or {}).items():
        marker = str(key)
        try:
            count = int(value)
        except (TypeError, ValueError):
            marker_count_issues.append(f"marker_counts[{marker}] must be a nonnegative integer")
            continue
        if count < 0:
            marker_count_issues.append(f"marker_counts[{marker}] must be a nonnegative integer")
            continue
        if marker not in RUNTIME_GATE_MARKERS:
            counts[marker] = count
    detail_texts = [
        str(detail.get("excerpt") or detail.get("text") or detail.get("message") or "")
        for detail in extracted
        if isinstance(detail, dict)
    ]
    for message in [*messages, *dom_messages, str(body_text_excerpt or ""), *detail_texts]:
        lowered = message.lower()
        for marker in RUNTIME_GATE_MARKERS:
            if marker.lower() in lowered:
                counts[marker] = counts.get(marker, 0) + 1
    blocking_markers = [marker for marker, count in counts.items() if count > 0]
    changed_ids = _unique_strings(changed_object_ids or [])
    required_changed_ids = _unique_strings(required_changed_object_ids or [])
    visible_titles = _unique_strings(visible_widget_titles or [])
    expected = _unique_strings(expected_titles or [])
    missing_titles = _missing_normalized_values(expected, visible_titles)
    missing_changed_ids = [item for item in required_changed_ids if item not in set(changed_ids)]
    normalized_branch = str(branch or "").strip().lower()
    normalized_required_branch = str(required_branch or "").strip().lower()
    normalized_revision_id = str(revision_id or "").strip()
    normalized_required_revision_id = str(required_revision_id or "").strip()
    normalized_object_revisions = {
        str(key).strip(): str(value).strip()
        for key, value in (object_revisions or {}).items()
        if str(key).strip() and str(value).strip()
    }
    if normalized_revision_id and len(changed_ids) == 1:
        normalized_object_revisions.setdefault(changed_ids[0], normalized_revision_id)
    normalized_required_object_revisions = {
        str(key).strip(): str(value).strip()
        for key, value in (required_object_revisions or {}).items()
        if str(key).strip() and str(value).strip()
    }
    revision_mismatch_object_ids = [
        object_id
        for object_id, required_revision in normalized_required_object_revisions.items()
        if normalized_object_revisions.get(object_id) != required_revision
    ]
    proof_paths = _unique_strings(proof_artifacts or [])
    screenshot_paths = _unique_strings(screenshot_artifacts or [])
    supplied_metadata = [item for item in proof_artifact_metadata or [] if isinstance(item, dict)]
    artifact_validation = verify_local_artifacts(
        [*proof_paths, *screenshot_paths, *supplied_metadata],
        artifact_root=artifact_root,
    )
    evidence_validation_issues: list[str] = list(marker_count_issues)
    evidence_mismatch = bool(marker_count_issues)
    normalized_console_error_count = _nonnegative_int(console_error_count)
    if console_error_count is not None and normalized_console_error_count is None:
        evidence_validation_issues.append("console_error_count must be a nonnegative integer")
        evidence_mismatch = True
    console_errors = normalized_console_error_count or 0

    if any(count > 0 for count in counts.values()) and normalized == "passed":
        normalized = "failed"
    if normalized == "passed" and not non_rendering_exemption.strip():
        if not browser_capture_artifact:
            evidence_validation_issues.append("machine-readable browser_capture_artifact is required")
        evidence_validation_issues.extend(str(item["message"]) for item in capture_validation["issues"])
        if capture_validation["issues"]:
            evidence_mismatch = True
        if not _valid_target_url(target_url):
            evidence_validation_issues.append("runtime target_url must be a nonempty http(s) URL")
        if not str(tab_id or "").strip():
            evidence_validation_issues.append("runtime tab_id is required")
        if required_target_url and _canonical_url(target_url) != _canonical_url(required_target_url):
            evidence_validation_issues.append("runtime target_url does not match the required target URL")
            evidence_mismatch = True
        if required_tab_id and str(tab_id).strip() != str(required_tab_id).strip():
            evidence_validation_issues.append("runtime tab_id does not match the required target tab")
            evidence_mismatch = True
        if normalized_required_branch and normalized_branch != normalized_required_branch:
            evidence_validation_issues.append(
                f"runtime browser capture must bind branch={normalized_required_branch}"
            )
            evidence_mismatch = True
        if normalized_required_revision_id and normalized_revision_id != normalized_required_revision_id:
            evidence_validation_issues.append("runtime browser capture revision_id does not match the required revision")
            evidence_mismatch = True
        if normalized_required_object_revisions and revision_mismatch_object_ids:
            evidence_validation_issues.append(
                "runtime browser capture object revisions do not match required revisions: "
                + ", ".join(revision_mismatch_object_ids)
            )
            evidence_mismatch = True
        if not changed_ids:
            evidence_validation_issues.append("runtime changed_object_ids must bind the checked objects")
        if missing_changed_ids:
            evidence_validation_issues.append(
                "runtime changed_object_ids omit required objects: " + ", ".join(missing_changed_ids)
            )
            evidence_mismatch = True
        if expected and not visible_titles:
            evidence_validation_issues.append("visible_widget_titles are required when expected_titles are supplied")
        elif missing_titles:
            evidence_validation_issues.append(
                "expected widget titles were not observed: " + ", ".join(missing_titles)
            )
            evidence_mismatch = True
        if console_errors > 0:
            evidence_validation_issues.append("browser capture reports console errors")
            evidence_mismatch = True
        if evidence_validation_issues:
            normalized = "failed" if evidence_mismatch else "blocked"
            blocked_reason = blocked_reason or evidence_validation_issues[0]
    if normalized == "not_run" and blocked_reason:
        normalized = "blocked"
    return {
        "schema_version": RUNTIME_GATE_SCHEMA_VERSION,
        "status": normalized,
        "target_url": target_url,
        "tab_id": tab_id,
        "branch": normalized_branch,
        "revision_id": normalized_revision_id,
        "object_revisions": normalized_object_revisions,
        "required_branch": normalized_required_branch,
        "required_revision_id": normalized_required_revision_id,
        "required_object_revisions": normalized_required_object_revisions,
        "revision_mismatch_object_ids": revision_mismatch_object_ids,
        "delivery_stage": str(delivery_stage or "").strip(),
        "changed_object_ids": changed_ids,
        "required_changed_object_ids": required_changed_ids,
        "missing_changed_object_ids": missing_changed_ids,
        "checked_selectors": checked_selectors or [],
        "selector_interaction": selector_interaction,
        "scroll_check": scroll_check,
        "visible_widget_titles": visible_titles,
        "expected_titles": expected,
        "missing_expected_titles": missing_titles,
        "body_text_excerpt": str(body_text_excerpt or "")[:2000],
        "console_messages": [redact_text(item)[:1000] for item in messages if item],
        "dom_error_texts": [redact_text(item)[:1000] for item in dom_messages if item],
        "checked_markers": list(RUNTIME_GATE_MARKERS),
        "blocking_markers_found": blocking_markers,
        "marker_counts": counts,
        "console_error_count": console_errors,
        "extracted_error_details": extracted,
        "detail_extraction_attempted": _should_attempt_detail_extraction(
            body_text_excerpt=body_text_excerpt,
            console_messages=messages,
            dom_error_texts=dom_messages,
        ),
        "detail_extraction_status": "found" if extracted else "details_unavailable",
        "screenshot_artifacts": capture_validation.get("image_artifacts") or screenshot_paths,
        "proof_artifacts": list(
            dict.fromkeys(
                [
                    *proof_paths,
                    *([browser_capture_artifact] if browser_capture_artifact else []),
                    *[str(item) for item in capture_validation.get("image_artifacts") or []],
                ]
            )
        ),
        "proof_artifact_metadata": [
            *capture_validation.get("verified_artifacts", []),
            *artifact_validation["verified_artifacts"],
        ],
        "artifact_validation_issues": [
            *capture_validation["issues"],
            *artifact_validation["issues"],
        ],
        "browser_capture_artifact": str(browser_capture_artifact or ""),
        "browser_capture_validation": {
            "ok": capture_validation["ok"],
            "verified_artifacts": capture_validation.get("verified_artifacts") or [],
            "image_details": capture_validation.get("image_details") or {},
            "issues": capture_validation["issues"],
        },
        "evidence_validation_issues": evidence_validation_issues,
        "non_rendering_exemption": str(non_rendering_exemption or "").strip(),
        "blocked_reason": blocked_reason if normalized in {"blocked", "not_run"} else "",
    }


def final_status_from_runtime_gate(
    runtime_gate: dict[str, Any] | None,
    *,
    browser_runtime_required: bool = True,
    non_rendering_exemption: str = "",
) -> str:
    if not browser_runtime_required and non_rendering_exemption:
        return "done"
    status = str((runtime_gate or {}).get("status") or "").strip().lower()
    if status == "passed":
        return "done"
    if status == "failed":
        return "blocked"
    return "runtime_not_verified"


def runtime_gate_has_blocking_markers(runtime_gate: dict[str, Any] | None) -> bool:
    counts = (runtime_gate or {}).get("marker_counts")
    if not isinstance(counts, dict):
        return False
    return any(_int_value(value) > 0 for value in counts.values())


def build_browser_runtime_smoke(
    *,
    status: str = "not_run",
    target_url: str = "",
    tab_id: str = "",
    changed_chart_ids: list[str] | None = None,
    required_changed_chart_ids: list[str] | None = None,
    required_target_url: str = "",
    required_tab_id: str = "",
    branch: str = "",
    revision_id: str = "",
    object_revisions: dict[str, str] | None = None,
    required_branch: str = "",
    required_revision_id: str = "",
    required_object_revisions: dict[str, str] | None = None,
    delivery_stage: str = "",
    checked_selectors: list[dict[str, Any]] | None = None,
    visible_widget_titles: list[str] | None = None,
    expected_titles: list[str] | None = None,
    body_text_excerpt: str = "",
    console_messages: list[str] | None = None,
    dom_error_texts: list[str] | None = None,
    marker_counts: dict[str, int] | None = None,
    console_error_count: int | None = None,
    extracted_error_details: list[dict[str, Any]] | None = None,
    screenshot_artifacts: list[str] | None = None,
    proof_artifacts: list[str] | None = None,
    proof_artifact_metadata: list[dict[str, Any]] | None = None,
    browser_capture_artifact: str = "",
    browser_capture_artifact_metadata: dict[str, Any] | None = None,
    artifact_root: str | Path | None = None,
    non_rendering_exemption: str = "",
    blocked_reason: str = "",
) -> dict[str, Any]:
    """Build the v8 targeted browser/runtime smoke contract from observed text."""

    gate = build_runtime_gate_evidence(
        status=status,
        target_url=target_url,
        tab_id=tab_id,
        changed_object_ids=changed_chart_ids,
        required_changed_object_ids=required_changed_chart_ids,
        required_target_url=required_target_url,
        required_tab_id=required_tab_id,
        branch=branch,
        revision_id=revision_id,
        object_revisions=object_revisions,
        required_branch=required_branch,
        required_revision_id=required_revision_id,
        required_object_revisions=required_object_revisions,
        delivery_stage=delivery_stage,
        checked_selectors=checked_selectors,
        visible_widget_titles=visible_widget_titles,
        expected_titles=expected_titles,
        body_text_excerpt=body_text_excerpt,
        console_messages=console_messages,
        dom_error_texts=dom_error_texts,
        marker_counts=marker_counts,
        console_error_count=console_error_count,
        extracted_error_details=extracted_error_details,
        screenshot_artifacts=screenshot_artifacts,
        proof_artifacts=proof_artifacts,
        proof_artifact_metadata=proof_artifact_metadata,
        browser_capture_artifact=browser_capture_artifact,
        browser_capture_artifact_metadata=browser_capture_artifact_metadata,
        artifact_root=artifact_root,
        non_rendering_exemption=non_rendering_exemption,
        blocked_reason=blocked_reason,
    )
    return {
        "schema_version": BROWSER_RUNTIME_SMOKE_SCHEMA_VERSION,
        "status": gate["status"],
        "target_url": gate["target_url"],
        "tab_id": gate["tab_id"],
        "branch": gate["branch"],
        "revision_id": gate["revision_id"],
        "object_revisions": gate["object_revisions"],
        "required_branch": gate["required_branch"],
        "required_revision_id": gate["required_revision_id"],
        "required_object_revisions": gate["required_object_revisions"],
        "revision_mismatch_object_ids": gate["revision_mismatch_object_ids"],
        "delivery_stage": gate["delivery_stage"],
        "changed_chart_ids": gate["changed_object_ids"],
        "required_changed_chart_ids": gate["required_changed_object_ids"],
        "missing_changed_chart_ids": gate["missing_changed_object_ids"],
        "checked_selectors": gate["checked_selectors"],
        "selector_interaction": gate["selector_interaction"],
        "scroll_check": gate["scroll_check"],
        "visible_widget_titles": gate["visible_widget_titles"],
        "expected_titles": gate["expected_titles"],
        "missing_expected_titles": gate["missing_expected_titles"],
        "checked_markers": gate["checked_markers"],
        "blocking_markers_found": gate["blocking_markers_found"],
        "marker_counts": gate["marker_counts"],
        "console_error_count": gate["console_error_count"],
        "console_messages": gate["console_messages"],
        "dom_error_texts": gate["dom_error_texts"],
        "extracted_error_details": gate["extracted_error_details"],
        "detail_extraction_attempted": gate["detail_extraction_attempted"],
        "detail_extraction_status": gate["detail_extraction_status"],
        "screenshot_artifacts": gate["screenshot_artifacts"],
        "proof_artifacts": gate["proof_artifacts"],
        "proof_artifact_metadata": gate["proof_artifact_metadata"],
        "artifact_validation_issues": gate["artifact_validation_issues"],
        "browser_capture_artifact": gate["browser_capture_artifact"],
        "browser_capture_validation": gate["browser_capture_validation"],
        "evidence_validation_issues": gate["evidence_validation_issues"],
        "non_rendering_exemption": gate["non_rendering_exemption"],
        "blocked_reason": gate["blocked_reason"],
    }


def verify_local_artifacts(
    artifacts: Iterable[str | dict[str, Any]],
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify local proof files and compute content metadata without trusting caller claims."""

    root = Path(artifact_root).resolve() if artifact_root is not None else Path.cwd().resolve()
    verified: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    by_path: dict[str, dict[str, Any]] = {}
    for item in artifacts:
        supplied = item if isinstance(item, dict) else {"path": item}
        raw_path = str(supplied.get("path") or "").strip()
        if not raw_path:
            continue
        if raw_path not in by_path:
            by_path[raw_path] = {"path": raw_path}
        if isinstance(item, dict):
            by_path[raw_path].update(item)
    for raw_path, supplied in by_path.items():
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = root / path
        resolved = path.resolve()
        if not resolved.is_file():
            issues.append(
                {
                    "rule": "artifact_missing",
                    "path": raw_path,
                    "message": f"runtime proof artifact does not exist: {raw_path}",
                }
            )
            continue
        digest = _sha256_file(resolved)
        expected_digest = str(supplied.get("sha256") or "").strip().lower()
        if expected_digest and expected_digest != digest:
            issues.append(
                {
                    "rule": "artifact_sha256_mismatch",
                    "path": raw_path,
                    "message": f"runtime proof artifact sha256 does not match: {raw_path}",
                }
            )
            continue
        stat = resolved.stat()
        verified.append(
            {
                "path": raw_path,
                "resolved_path": str(resolved),
                "sha256": digest,
                "serialized_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return {"ok": not issues and bool(verified), "verified_artifacts": verified, "issues": issues}


def validate_browser_capture_artifact(
    artifact_path: str,
    *,
    artifact_metadata: dict[str, Any] | None = None,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    if not str(artifact_path or "").strip():
        return {
            "ok": False,
            "document": {},
            "verified_artifacts": [],
            "image_artifacts": [],
            "image_details": {},
            "issues": [],
        }
    item = dict(artifact_metadata or {})
    item["path"] = str(artifact_path)
    sidecar_validation = verify_local_artifacts([item], artifact_root=artifact_root)
    issues = list(sidecar_validation["issues"])
    if not sidecar_validation["verified_artifacts"]:
        return {
            "ok": False,
            "document": {},
            "verified_artifacts": [],
            "image_artifacts": [],
            "image_details": {},
            "issues": issues,
        }
    sidecar_path = Path(sidecar_validation["verified_artifacts"][0]["resolved_path"])
    if sidecar_path.suffix.lower() != ".json":
        issues.append(
            {
                "rule": "browser_capture_not_json",
                "path": str(sidecar_path),
                "message": "browser capture sidecar must be a JSON file",
            }
        )
        return {
            "ok": False,
            "document": {},
            "verified_artifacts": sidecar_validation["verified_artifacts"],
            "image_artifacts": [],
            "image_details": {},
            "issues": issues,
        }
    try:
        document = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        document = {}
    if not isinstance(document, dict):
        document = {}
    if not document:
        issues.append(
            {
                "rule": "browser_capture_invalid_json",
                "path": str(sidecar_path),
                "message": "browser capture sidecar must contain one JSON object",
            }
        )
    if document and document.get("schema_version") != "datalens.browser_capture.v1":
        issues.append(
            {
                "rule": "browser_capture_schema_version",
                "path": str(sidecar_path),
                "message": "browser capture sidecar has an unsupported schema_version",
            }
        )
    if document and str(document.get("status") or "").strip().lower() != "passed":
        issues.append(
            {
                "rule": "browser_capture_status",
                "path": str(sidecar_path),
                "message": "browser capture sidecar status must be passed",
            }
        )
    required_fields = {
        "captured_at": str,
        "target_url": str,
        "tab_id": str,
        "branch": str,
        "object_revisions": dict,
        "changed_object_ids": list,
        "checked_selectors": list,
        "selector_interaction": dict,
        "scroll_check": dict,
        "visible_widget_titles": list,
        "console_messages": list,
        "dom_error_texts": list,
        "console_error_count": int,
    }
    for field, expected_type in required_fields.items():
        value = document.get(field) if document else None
        valid = isinstance(value, expected_type) and not isinstance(value, bool)
        if expected_type is str:
            valid = valid and bool(str(value).strip())
        if not valid:
            issues.append(
                {
                    "rule": "browser_capture_required_field",
                    "path": str(sidecar_path),
                    "message": f"browser capture sidecar requires {field} as {expected_type.__name__}",
                }
            )
    if document and _nonnegative_int(document.get("console_error_count")) is None:
        issues.append(
            {
                "rule": "browser_capture_console_error_count",
                "path": str(sidecar_path),
                "message": "browser capture console_error_count must be a nonnegative integer",
            }
        )
    if document:
        branch = str(document.get("branch") or "").strip().lower()
        if branch not in {"saved", "published"}:
            issues.append(
                {
                    "rule": "browser_capture_branch_binding",
                    "path": str(sidecar_path),
                    "message": "browser capture branch must be saved or published",
                }
            )
        changed_ids = _unique_strings(document.get("changed_object_ids") or [])
        revisions = document.get("object_revisions") if isinstance(document.get("object_revisions"), dict) else {}
        missing_revisions = [item for item in changed_ids if not str(revisions.get(item) or "").strip()]
        if missing_revisions:
            issues.append(
                {
                    "rule": "browser_capture_revision_binding",
                    "path": str(sidecar_path),
                    "message": "browser capture omits revisions for changed objects: " + ", ".join(missing_revisions),
                }
            )
    if document:
        issues.extend(_browser_interaction_issues(document, path=sidecar_path))
    capture_time_issue = _capture_time_issue(str(document.get("captured_at") or "")) if document else ""
    if capture_time_issue:
        issues.append(
            {
                "rule": "browser_capture_freshness",
                "path": str(sidecar_path),
                "message": capture_time_issue,
            }
        )
    image = document.get("image_artifact") if isinstance(document.get("image_artifact"), dict) else {}
    image_path_value = str(image.get("path") or "").strip()
    image_sha = str(image.get("sha256") or "").strip().lower()
    image_validation = {"verified_artifacts": [], "issues": []}
    image_details: dict[str, Any] = {}
    if not image_path_value or not image_sha:
        issues.append(
            {
                "rule": "browser_capture_image_binding",
                "path": str(sidecar_path),
                "message": "browser capture sidecar requires image_artifact.path and sha256",
            }
        )
    else:
        image_path = Path(image_path_value)
        if not image_path.is_absolute():
            image_path = sidecar_path.parent / image_path
        image_validation = verify_local_artifacts(
            [{"path": str(image_path), "sha256": image_sha}],
            artifact_root=sidecar_path.parent,
        )
        issues.extend(image_validation["issues"])
        if image_validation["verified_artifacts"]:
            resolved_image = Path(image_validation["verified_artifacts"][0]["resolved_path"])
            image_details, image_issue = _decode_image_metadata(resolved_image)
            if image_issue:
                issues.append(
                    {
                        "rule": "browser_capture_image_invalid",
                        "path": str(resolved_image),
                        "message": f"browser capture image is not decodable: {image_issue}",
                    }
                )
    verified_artifacts = [
        *sidecar_validation["verified_artifacts"],
        *image_validation.get("verified_artifacts", []),
    ]
    image_artifacts = [
        str(item.get("resolved_path") or item.get("path") or "")
        for item in image_validation.get("verified_artifacts", [])
        if item.get("resolved_path") or item.get("path")
    ]
    return {
        "ok": not issues and bool(document) and bool(image_artifacts),
        "document": document,
        "verified_artifacts": verified_artifacts,
        "image_artifacts": image_artifacts,
        "image_details": image_details,
        "issues": issues,
    }


def runtime_first_status_from_runtime_gate(
    runtime_gate: dict[str, Any] | None,
    *,
    browser_runtime_required: bool = True,
    non_rendering_exemption: str = "",
) -> str:
    if not browser_runtime_required and non_rendering_exemption:
        return "structural_ok_runtime_not_checked"
    if runtime_gate_has_blocking_markers(runtime_gate):
        return "runtime_failed"
    status = str((runtime_gate or {}).get("status") or "").strip().lower()
    if status == "passed":
        return "runtime_passed"
    if status == "failed":
        return "runtime_failed"
    return "runtime_not_verified"


def extract_runtime_error_details(
    *,
    body_text_excerpt: str = "",
    console_messages: list[str] | None = None,
    dom_error_texts: list[str] | None = None,
) -> list[dict[str, Any]]:
    texts = [
        str(body_text_excerpt or ""),
        *[str(item) for item in console_messages or []],
        *[str(item) for item in dom_error_texts or []],
    ]
    details: list[dict[str, Any]] = []
    for source, text in enumerate(texts):
        sanitized = redact_text(text)
        if not sanitized.strip():
            continue
        lowered = sanitized.lower()
        if not _contains_runtime_detail_signal(lowered):
            continue
        details.append(
            {
                "source": "body" if source == 0 else "console_or_dom",
                "detail_type": _detail_type(lowered),
                "excerpt": sanitized[:1200],
            }
        )
    return details[:10]


def merge_runtime_messages(*groups: Iterable[str]) -> list[str]:
    messages: list[str] = []
    for group in groups:
        for item in group:
            text = str(item).strip()
            if text:
                messages.append(text[:500])
    return messages


def _should_attempt_detail_extraction(
    *,
    body_text_excerpt: str,
    console_messages: list[str],
    dom_error_texts: list[str],
) -> bool:
    text = "\n".join([str(body_text_excerpt or ""), *console_messages, *dom_error_texts]).lower()
    return any(
        token in text
        for token in (
            "data fetching error",
            "data source refused connection",
            "database response",
            "sent query",
            "more",
            "debug",
        )
    )


def _contains_runtime_detail_signal(text: str) -> bool:
    return any(
        token in text
        for token in (
            "database response",
            "sent query",
            "db::exception",
            "err.ds_api",
            "illegal_aggregation",
            "no_common_type",
            "unknown_identifier",
            "unknown_table",
            "not_implemented",
            "data source refused connection",
        )
    )


def _detail_type(text: str) -> str:
    if "database response" in text or "db::exception" in text:
        return "database_response"
    if "sent query" in text:
        return "sent_query"
    if "debug" in text:
        return "debug"
    return "runtime_error_text"


def _sanitize_detail(item: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): redact_text(str(value))[:1200] if isinstance(value, str) else value
        for key, value in item.items()
    }


def _normalize_runtime_status(status: str) -> str:
    normalized = str(status or "not_run").strip().lower()
    aliases = {
        "pass": "passed",
        "ok": "passed",
        "browser_pass": "passed",
        "fail": "failed",
        "browser_fail": "failed",
        "error": "failed",
        "auth": "blocked",
        "auth_required": "blocked",
        "browser_auth_required": "blocked",
        "browser_auth_blocked": "blocked",
        "timeout": "blocked",
        "tool_timeout": "blocked",
        "browser_tool_timeout": "blocked",
        "not_checked": "not_run",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"passed", "failed", "blocked", "not_run"}:
        return normalized
    return "not_run"


def _unique_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _normalized_visible_text(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _missing_normalized_values(expected: list[str], observed: list[str]) -> list[str]:
    observed_normalized = {_normalized_visible_text(item) for item in observed}
    return [item for item in expected if _normalized_visible_text(item) not in observed_normalized]


def _browser_interaction_issues(document: dict[str, Any], *, path: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    changed_ids = _unique_strings(document.get("changed_object_ids") or [])
    checked_selectors = document.get("checked_selectors")
    selector_contract = document.get("selector_interaction")
    scroll_contract = document.get("scroll_check")
    if isinstance(selector_contract, dict):
        issues.extend(
            _selector_interaction_issues(
                selector_contract,
                checked_selectors=checked_selectors if isinstance(checked_selectors, list) else [],
                changed_ids=changed_ids,
                path=path,
            )
        )
    if isinstance(scroll_contract, dict):
        issues.extend(_scroll_check_issues(scroll_contract, changed_ids=changed_ids, path=path))
    return issues


def _selector_interaction_issues(
    contract: dict[str, Any],
    *,
    checked_selectors: list[Any],
    changed_ids: list[str],
    path: Path,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    status = str(contract.get("status") or "").strip().lower()
    scope_ids = _unique_strings(contract.get("scope_object_ids") or [])
    issues.extend(_scope_binding_issues("selector_interaction", scope_ids, changed_ids, path=path))
    if status == "passed":
        if not checked_selectors:
            issues.append(
                _capture_issue(
                    "browser_capture_selector_interaction",
                    path,
                    "selector_interaction.status=passed requires at least one checked selector",
                )
            )
        for index, item in enumerate(checked_selectors):
            if not isinstance(item, dict):
                issues.append(
                    _capture_issue(
                        "browser_capture_selector_interaction",
                        path,
                        f"checked_selectors[{index}] must be an object",
                    )
                )
                continue
            selector_id = str(item.get("selector_id") or "").strip()
            interaction = str(item.get("interaction") or "").strip()
            item_status = str(item.get("status") or "").strip().lower()
            affected_ids = _unique_strings(item.get("affected_object_ids") or [])
            if not selector_id or not interaction or item_status != "passed" or not affected_ids:
                issues.append(
                    _capture_issue(
                        "browser_capture_selector_interaction",
                        path,
                        (
                            f"checked_selectors[{index}] requires selector_id, interaction, status=passed, "
                            "and affected_object_ids"
                        ),
                    )
                )
                continue
            if not set(affected_ids).issubset(set(scope_ids)):
                issues.append(
                    _capture_issue(
                        "browser_capture_selector_scope",
                        path,
                        f"checked_selectors[{index}] affected_object_ids must stay inside the declared scope",
                    )
                )
            elif changed_ids and not set(affected_ids).intersection(changed_ids):
                issues.append(
                    _capture_issue(
                        "browser_capture_selector_scope",
                        path,
                        f"checked_selectors[{index}] must affect at least one changed object",
                    )
                )
    elif status == "not_applicable":
        if checked_selectors:
            issues.append(
                _capture_issue(
                    "browser_capture_selector_interaction",
                    path,
                    "selector_interaction.status=not_applicable requires checked_selectors to be empty",
                )
            )
        reason = contract.get("reason") if isinstance(contract.get("reason"), dict) else {}
        code = str(reason.get("code") or "").strip()
        detail = str(reason.get("detail") or "").strip()
        if code not in SELECTOR_NOT_APPLICABLE_CODES or not detail:
            issues.append(
                _capture_issue(
                    "browser_capture_selector_not_applicable",
                    path,
                    "selector not_applicable evidence requires a supported reason code and nonempty detail",
                )
            )
    else:
        issues.append(
            _capture_issue(
                "browser_capture_selector_interaction",
                path,
                "selector_interaction.status must be passed or not_applicable",
            )
        )
    return issues


def _scroll_check_issues(
    contract: dict[str, Any],
    *,
    changed_ids: list[str],
    path: Path,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    status = str(contract.get("status") or "").strip().lower()
    scope_ids = _unique_strings(contract.get("scope_object_ids") or [])
    issues.extend(_scope_binding_issues("scroll_check", scope_ids, changed_ids, path=path))
    document_height = _finite_number(contract.get("document_height"))
    viewport_height = _finite_number(contract.get("viewport_height"))
    if document_height is None or document_height <= 0 or viewport_height is None or viewport_height <= 0:
        issues.append(
            _capture_issue(
                "browser_capture_scroll_dimensions",
                path,
                "scroll_check requires positive finite document_height and viewport_height",
            )
        )
        return issues
    if status == "passed":
        start_scroll_y = _finite_number(contract.get("start_scroll_y"))
        end_scroll_y = _finite_number(contract.get("end_scroll_y"))
        if (
            start_scroll_y is None
            or end_scroll_y is None
            or start_scroll_y < 0
            or end_scroll_y <= start_scroll_y
            or document_height <= viewport_height + SCROLL_BOTTOM_TOLERANCE_PX
            or contract.get("bottom_reached") is not True
            or end_scroll_y + viewport_height + SCROLL_BOTTOM_TOLERANCE_PX < document_height
        ):
            issues.append(
                _capture_issue(
                    "browser_capture_scroll_bottom",
                    path,
                    "long-form scroll proof must move down and measurably reach the document bottom",
                )
            )
    elif status == "not_applicable":
        reason = contract.get("reason") if isinstance(contract.get("reason"), dict) else {}
        if (
            str(reason.get("code") or "").strip() != "content_fits_viewport"
            or not str(reason.get("detail") or "").strip()
            or document_height > viewport_height + SCROLL_BOTTOM_TOLERANCE_PX
        ):
            issues.append(
                _capture_issue(
                    "browser_capture_scroll_not_applicable",
                    path,
                    "scroll not_applicable requires measured content_fits_viewport evidence and nonempty detail",
                )
            )
    else:
        issues.append(
            _capture_issue(
                "browser_capture_scroll_status",
                path,
                "scroll_check.status must be passed or not_applicable",
            )
        )
    return issues


def _scope_binding_issues(
    label: str,
    scope_ids: list[str],
    changed_ids: list[str],
    *,
    path: Path,
) -> list[dict[str, str]]:
    if not scope_ids:
        return [_capture_issue(f"browser_capture_{label}_scope", path, f"{label} requires scope_object_ids")]
    missing = [item for item in changed_ids if item not in set(scope_ids)]
    if missing:
        return [
            _capture_issue(
                f"browser_capture_{label}_scope",
                path,
                f"{label}.scope_object_ids omit changed objects: {', '.join(missing)}",
            )
        ]
    return []


def _capture_issue(rule: str, path: Path, message: str) -> dict[str, str]:
    return {"rule": rule, "path": str(path), "message": message}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_target_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _canonical_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_image_metadata(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {}, f"cannot read image bytes: {exc}"
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            details = _decode_png_metadata(data)
        elif data.startswith(b"\xff\xd8"):
            details = _decode_jpeg_metadata(data)
        elif data.startswith((b"GIF87a", b"GIF89a")):
            details = _decode_gif_metadata(data)
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            details = _decode_webp_metadata(data)
        else:
            return {}, "unsupported image signature"
        width = int(details.get("width") or 0)
        height = int(details.get("height") or 0)
        if width <= 0 or height <= 0:
            return {}, "decoded dimensions must be positive"
        if width > MAX_CAPTURE_IMAGE_DIMENSION or height > MAX_CAPTURE_IMAGE_DIMENSION:
            return {}, "decoded dimensions exceed the capture limit"
        if width * height > MAX_CAPTURE_IMAGE_PIXELS:
            return {}, "decoded pixel count exceeds the capture limit"
        return {**details, "serialized_bytes": len(data)}, ""
    except (IndexError, ValueError, struct.error, zlib.error) as exc:
        return {}, str(exc)


def _decode_png_metadata(data: bytes) -> dict[str, Any]:
    offset = 8
    ihdr: bytes | None = None
    idat_parts: list[bytes] = []
    saw_iend = False
    chunk_index = 0
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk header")
        length = struct.unpack_from(">I", data, offset)[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise ValueError("truncated PNG chunk payload")
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"PNG chunk {chunk_type!r} has an invalid CRC")
        if chunk_index == 0 and chunk_type != b"IHDR":
            raise ValueError("PNG IHDR must be the first chunk")
        if chunk_type == b"IHDR":
            if ihdr is not None or length != 13:
                raise ValueError("PNG requires exactly one 13-byte IHDR")
            ihdr = chunk_data
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0:
                raise ValueError("PNG IEND must be empty")
            saw_iend = True
            offset = chunk_end
            if offset != len(data):
                raise ValueError("PNG has trailing bytes after IEND")
            break
        offset = chunk_end
        chunk_index += 1
    if ihdr is None or not idat_parts or not saw_iend:
        raise ValueError("PNG requires IHDR, IDAT, and IEND chunks")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if (
        width <= 0
        or height <= 0
        or width > MAX_CAPTURE_IMAGE_DIMENSION
        or height > MAX_CAPTURE_IMAGE_DIMENSION
        or width * height > MAX_CAPTURE_IMAGE_PIXELS
    ):
        raise ValueError("PNG dimensions are outside the capture limit")
    valid_depths = {
        0: {1, 2, 4, 8, 16},
        2: {8, 16},
        3: {1, 2, 4, 8},
        4: {8, 16},
        6: {8, 16},
    }
    if bit_depth not in valid_depths.get(color_type, set()):
        raise ValueError("PNG bit depth and color type are incompatible")
    if compression != 0 or filter_method != 0 or interlace not in {0, 1}:
        raise ValueError("PNG uses an unsupported compression, filter, or interlace method")
    samples_per_pixel = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    row_layouts = _png_row_layouts(width, height, samples_per_pixel, bit_depth, interlace)
    expected_decoded_bytes = sum((row_bytes + 1) * row_count for row_bytes, row_count in row_layouts)
    if expected_decoded_bytes <= 0 or expected_decoded_bytes > MAX_CAPTURE_DECODED_BYTES:
        raise ValueError("PNG decoded byte count is outside the capture limit")
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(b"".join(idat_parts), expected_decoded_bytes + 1)
    if decoder.unconsumed_tail or len(decoded) > expected_decoded_bytes:
        raise ValueError("PNG IDAT expands beyond the decoded image dimensions")
    decoded += decoder.flush()
    if not decoder.eof or decoder.unused_data or len(decoded) != expected_decoded_bytes:
        raise ValueError("PNG IDAT does not decode to the declared image dimensions")
    cursor = 0
    for row_bytes, row_count in row_layouts:
        for _ in range(row_count):
            if decoded[cursor] > 4:
                raise ValueError("PNG scanline has an invalid filter byte")
            cursor += row_bytes + 1
    return {"format": "png", "width": width, "height": height, "decoded_bytes": len(decoded)}


def _png_row_layouts(
    width: int,
    height: int,
    samples_per_pixel: int,
    bit_depth: int,
    interlace: int,
) -> list[tuple[int, int]]:
    passes = [(0, 0, 1, 1)]
    if interlace == 1:
        passes = [
            (0, 0, 8, 8),
            (4, 0, 8, 8),
            (0, 4, 4, 8),
            (2, 0, 4, 4),
            (0, 2, 2, 4),
            (1, 0, 2, 2),
            (0, 1, 1, 2),
        ]
    layouts: list[tuple[int, int]] = []
    for start_x, start_y, step_x, step_y in passes:
        pass_width = max(0, (width - start_x + step_x - 1) // step_x)
        pass_height = max(0, (height - start_y + step_y - 1) // step_y)
        if pass_width and pass_height:
            row_bits = pass_width * samples_per_pixel * bit_depth
            layouts.append(((row_bits + 7) // 8, pass_height))
    return layouts


def _decode_jpeg_metadata(data: bytes) -> dict[str, Any]:
    offset = 2
    width = 0
    height = 0
    saw_scan = False
    saw_eoi = False
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while offset < len(data):
        if data[offset] != 0xFF:
            raise ValueError("JPEG marker stream is malformed")
        marker_start = offset
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise ValueError("JPEG ends inside a marker")
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            saw_eoi = True
            if offset != len(data):
                raise ValueError("JPEG has trailing bytes after EOI")
            break
        if marker == 0x00 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if offset + 2 > len(data):
            raise ValueError("truncated JPEG segment length")
        segment_length = struct.unpack_from(">H", data, offset)[0]
        if segment_length < 2 or offset + segment_length > len(data):
            raise ValueError("invalid JPEG segment length")
        segment = data[offset + 2 : offset + segment_length]
        offset += segment_length
        if marker in sof_markers:
            if len(segment) < 6:
                raise ValueError("truncated JPEG frame header")
            height = struct.unpack_from(">H", segment, 1)[0]
            width = struct.unpack_from(">H", segment, 3)[0]
        if marker != 0xDA:
            continue
        saw_scan = True
        while offset < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            next_offset = offset + 1
            while next_offset < len(data) and data[next_offset] == 0xFF:
                next_offset += 1
            if next_offset >= len(data):
                raise ValueError("JPEG scan ends inside a marker")
            next_marker = data[next_offset]
            if next_marker == 0x00 or 0xD0 <= next_marker <= 0xD7:
                offset = next_offset + 1
                continue
            if next_marker == 0xD9:
                offset = next_offset + 1
                saw_eoi = True
                if offset != len(data):
                    raise ValueError("JPEG has trailing bytes after EOI")
                break
            offset = marker_start = next_offset - 1
            break
        if saw_eoi:
            break
        if offset == marker_start and data[offset] == 0xFF:
            continue
    if not (width and height and saw_scan and saw_eoi):
        raise ValueError("JPEG requires a frame header, image scan, and EOI marker")
    return {"format": "jpeg", "width": width, "height": height}


def _decode_gif_metadata(data: bytes) -> dict[str, Any]:
    if len(data) < 14:
        raise ValueError("truncated GIF logical screen descriptor")
    width, height = struct.unpack_from("<HH", data, 6)
    packed = data[10]
    offset = 13
    if packed & 0x80:
        offset += 3 * (2 ** ((packed & 0x07) + 1))
    saw_image = False
    saw_trailer = False
    while offset < len(data):
        marker = data[offset]
        offset += 1
        if marker == 0x3B:
            saw_trailer = True
            if offset != len(data):
                raise ValueError("GIF has trailing bytes after trailer")
            break
        if marker == 0x21:
            if offset >= len(data):
                raise ValueError("truncated GIF extension label")
            offset += 1
            offset = _skip_gif_subblocks(data, offset)
            continue
        if marker != 0x2C or offset + 9 > len(data):
            raise ValueError("GIF block stream is malformed")
        saw_image = True
        descriptor_packed = data[offset + 8]
        offset += 9
        if descriptor_packed & 0x80:
            offset += 3 * (2 ** ((descriptor_packed & 0x07) + 1))
        if offset >= len(data):
            raise ValueError("truncated GIF image data")
        lzw_minimum_code_size = data[offset]
        if lzw_minimum_code_size < 2 or lzw_minimum_code_size > 8:
            raise ValueError("GIF image has an invalid LZW code size")
        offset = _skip_gif_subblocks(data, offset + 1)
    if not (width and height and saw_image and saw_trailer):
        raise ValueError("GIF requires positive dimensions, image data, and a trailer")
    return {"format": "gif", "width": width, "height": height}


def _skip_gif_subblocks(data: bytes, offset: int) -> int:
    while True:
        if offset >= len(data):
            raise ValueError("truncated GIF data sub-block")
        length = data[offset]
        offset += 1
        if length == 0:
            return offset
        offset += length
        if offset > len(data):
            raise ValueError("truncated GIF data sub-block payload")


def _decode_webp_metadata(data: bytes) -> dict[str, Any]:
    if len(data) < 20 or struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
        raise ValueError("WebP RIFF length does not match the file")
    offset = 12
    width = 0
    height = 0
    image_chunk = ""
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("truncated WebP chunk header")
        chunk_type = data[offset : offset + 4]
        chunk_length = struct.unpack_from("<I", data, offset + 4)[0]
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_length
        if chunk_end > len(data):
            raise ValueError("truncated WebP chunk payload")
        chunk = data[chunk_start:chunk_end]
        if chunk_type == b"VP8X":
            if len(chunk) < 10:
                raise ValueError("truncated WebP VP8X header")
            width = 1 + int.from_bytes(chunk[4:7], "little")
            height = 1 + int.from_bytes(chunk[7:10], "little")
        elif chunk_type == b"VP8 ":
            if len(chunk) < 10 or chunk[3:6] != b"\x9d\x01\x2a":
                raise ValueError("invalid WebP VP8 frame header")
            width = struct.unpack_from("<H", chunk, 6)[0] & 0x3FFF
            height = struct.unpack_from("<H", chunk, 8)[0] & 0x3FFF
            image_chunk = "vp8"
        elif chunk_type == b"VP8L":
            if len(chunk) < 5 or chunk[0] != 0x2F:
                raise ValueError("invalid WebP VP8L frame header")
            bits = int.from_bytes(chunk[1:5], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            image_chunk = "vp8l"
        offset = chunk_end + (chunk_length % 2)
        if offset > len(data):
            raise ValueError("invalid WebP chunk padding")
    if offset != len(data) or not image_chunk or not width or not height:
        raise ValueError("WebP requires a decodable VP8X, VP8, or VP8L image chunk")
    return {"format": "webp", "width": width, "height": height, "encoding": image_chunk}


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _capture_time_issue(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "browser capture captured_at is required"
    try:
        captured = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "browser capture captured_at must be an ISO-8601 timestamp"
    if captured.tzinfo is None:
        return "browser capture captured_at must include a timezone"
    age_seconds = (datetime.now(timezone.utc) - captured.astimezone(timezone.utc)).total_seconds()
    if age_seconds < -300:
        return "browser capture captured_at is too far in the future"
    if age_seconds > 1800:
        return "browser capture is stale; captured_at must be within 30 minutes"
    return ""


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
