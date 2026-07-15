from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from datalens_dev_mcp.pipeline.target_lock import TargetLock, validate_readback_target_lock, validate_target_delivery_trace
from datalens_dev_mcp.pipeline.visual_quality import validate_visual_readback_quality


@dataclass(frozen=True)
class FinalNoGapFinding:
    rule: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FinalNoGapResult:
    ok: bool
    findings: list[FinalNoGapFinding] = field(default_factory=list)
    schema_version: str = "2026-06-30.final_no_gap_validator.v1"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "findings": [finding.to_dict() for finding in self.findings]}


def validate_final_no_gap_report(report: dict[str, Any], *, target_lock: TargetLock | dict[str, Any]) -> FinalNoGapResult:
    findings: list[FinalNoGapFinding] = []
    trace = {
        "target_lock": target_lock.to_dict() if isinstance(target_lock, TargetLock) else target_lock,
        "actions": report.get("actions") or [],
        "saved_readback": report.get("saved_readback") or {},
        "published_readback": report.get("published_readback") or report.get("final_target_readback") or {},
        "final_report": report,
        "generated_widget_count": report.get("generated_widget_count") or report.get("planned_widget_count") or 0,
    }
    target_result = validate_target_delivery_trace(trace)
    for item in target_result["findings"]:
        findings.append(_finding(str(item.get("rule") or "target_mismatch"), str(item.get("message") or item)))
    publish_required = bool(report.get("publish_required") or report.get("publish_expected"))
    if publish_required and not report.get("publish_executed"):
        findings.append(_finding("publish_required_but_not_executed", "publish was required but final report did not execute it"))
    saved = report.get("saved_readback") if isinstance(report.get("saved_readback"), dict) else {}
    published = report.get("published_readback") if isinstance(report.get("published_readback"), dict) else {}
    if publish_required and not saved:
        findings.append(_finding("missing_saved_readback", "saved readback is required before publish"))
    if publish_required and not published:
        findings.append(_finding("missing_published_readback", "published readback is required after publish"))
    for branch, readback in (("saved", saved), ("published", published)):
        if readback:
            result = validate_readback_target_lock(target_lock, readback)
            if not result["ok"]:
                findings.append(_finding(f"{branch}_readback_target_mismatch", "; ".join(result["findings"])))
    visual_result = validate_visual_readback_quality(
        report.get("published_readback") or report,
        expected_active_widgets=int(report.get("expected_active_widgets") or 0),
    )
    for item in visual_result.findings:
        findings.append(_finding(item.rule, item.message))
    external_blockers = report.get("external_blockers") or []
    for blocker in external_blockers:
        if isinstance(blocker, dict) and not blocker.get("evidence"):
            findings.append(_finding("external_blocker_missing_evidence", "external blockers must include exact evidence"))
    return FinalNoGapResult(ok=not findings, findings=findings)


class FinalNoGapValidator:
    def validate(self, report: dict[str, Any], *, target_lock: TargetLock | dict[str, Any]) -> FinalNoGapResult:
        return validate_final_no_gap_report(report, target_lock=target_lock)


def _finding(rule: str, message: str, *, severity: str = "error") -> FinalNoGapFinding:
    return FinalNoGapFinding(rule=rule, severity=severity, message=message)
