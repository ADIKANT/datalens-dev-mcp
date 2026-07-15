from __future__ import annotations

from pathlib import Path
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SourceRouteStatus = Literal["supported", "manual_handoff", "blocked", "static_embedded"]


@dataclass(frozen=True)
class SourceRouteDecision:
    status: SourceRouteStatus
    selected_route: str
    reason: str
    embedded_fallback_allowed: bool
    required_evidence: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    manual_upload_handoff: dict[str, Any] = field(default_factory=dict)
    dataset_field_contract: dict[str, Any] = field(default_factory=dict)
    accepted_degraded: bool = False
    accepted_degraded_artifact_required: bool = False
    static_fallback_label: str = ""
    field_mappings: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = "2026-07-02.source_route_policy.v2"

    @property
    def ok(self) -> bool:
        return self.status in {"supported", "manual_handoff", "static_embedded"} and not self.findings

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceRouteResolver:
    """Resolve dataset/file sources before Advanced Editor embedded fallback."""

    def resolve(
        self,
        request: dict[str, Any],
        *,
        available_datasets: list[dict[str, Any]] | None = None,
        available_connections: list[dict[str, Any]] | None = None,
    ) -> SourceRouteDecision:
        datasets = available_datasets or request.get("available_datasets") or []
        connections = available_connections or request.get("available_connections") or []
        explicit_dataset_id = str(request.get("dataset_id") or request.get("existing_dataset_id") or "").strip()
        explicit_connection_id = str(request.get("connection_id") or request.get("existing_connection_id") or "").strip()
        static_approved = bool(request.get("explicit_static_embedded_approval") or request.get("static_embedded_mode"))
        user_uploaded_file = bool(
            request.get("user_uploaded_file")
            or request.get("file_uploaded")
            or request.get("source_file_name")
            or request.get("source_file_path")
            or _requirement_mentions_file_or_dataset(request)
        )
        source_limited = _source_limited(request)
        accepted_degraded = bool(request.get("accepted_degraded"))
        if source_limited and not accepted_degraded:
            return SourceRouteDecision(
                status="blocked",
                selected_route="",
                reason="required source fields are missing or empty; publish would require guessed mappings",
                embedded_fallback_allowed=False,
                required_evidence=["source_field_evidence", "accepted_degraded_decision"],
                dataset_field_contract=_dataset_field_contract(request),
                findings=["source_fields_missing_or_empty"],
            )
        if source_limited and accepted_degraded:
            return SourceRouteDecision(
                status="supported",
                selected_route="accepted_degraded_source_limited",
                reason="source limitation was explicitly accepted; no guessed field mappings are generated",
                embedded_fallback_allowed=False,
                required_evidence=["accepted_degraded_decision", "publish_report_caveat"],
                dataset_field_contract=_dataset_field_contract(request),
                accepted_degraded=True,
                accepted_degraded_artifact_required=True,
                field_mappings=[],
            )
        matching_dataset = _matching_dataset(request, datasets)
        if explicit_dataset_id or matching_dataset:
            dataset_id = explicit_dataset_id or str(matching_dataset.get("id") or matching_dataset.get("dataset_id") or "")
            return SourceRouteDecision(
                status="supported",
                selected_route="dataset_backed",
                reason=f"dataset-backed route selected for dataset {dataset_id}",
                embedded_fallback_allowed=False,
                required_evidence=["workbook_entries_readback", "dataset_schema_readback"],
                dataset_field_contract=_dataset_field_contract(request, dataset_id=dataset_id),
            )
        if explicit_connection_id or connections:
            return SourceRouteDecision(
                status="supported",
                selected_route="connection_plus_dataset_plan",
                reason="connection exists; build a dataset plan before chart payloads",
                embedded_fallback_allowed=False,
                required_evidence=["connection_readback", "dataset_plan"],
                dataset_field_contract=_dataset_field_contract(request),
            )
        if user_uploaded_file and not static_approved:
            return SourceRouteDecision(
                status="manual_handoff",
                selected_route="manual_upload_handoff",
                reason="uploaded/local file has no confirmed DataLens dataset; embedded final fallback is blocked",
                embedded_fallback_allowed=False,
                required_evidence=["manual_upload_or_dataset_schema_readback"],
                manual_upload_handoff=_manual_upload_handoff(request),
                dataset_field_contract=_dataset_field_contract(request),
            )
        if static_approved:
            return SourceRouteDecision(
                status="static_embedded",
                selected_route="explicit_static_embedded_mode",
                reason="embedded static mode was explicitly approved",
                embedded_fallback_allowed=True,
                required_evidence=["bounded_static_data_size", "deployment_report_source_mode"],
                dataset_field_contract=_dataset_field_contract(request),
                static_fallback_label="static_reference_mock",
            )
        return SourceRouteDecision(
            status="blocked",
            selected_route="",
            reason="no dataset, connection, manual upload handoff, or explicit static embedded approval is present",
            embedded_fallback_allowed=False,
            required_evidence=["source_route_decision"],
            findings=["source_route_missing"],
        )


def resolve_source_route(
    request: dict[str, Any],
    *,
    available_datasets: list[dict[str, Any]] | None = None,
    available_connections: list[dict[str, Any]] | None = None,
) -> SourceRouteDecision:
    return SourceRouteResolver().resolve(
        request,
        available_datasets=available_datasets,
        available_connections=available_connections,
    )


def validate_source_route_decision(payload: dict[str, Any]) -> dict[str, Any]:
    decision = resolve_source_route(payload)
    source_mode = str(payload.get("source_mode") or payload.get("selected_source_route") or "").strip()
    findings = list(decision.findings)
    if source_mode == "embedded" and not decision.embedded_fallback_allowed:
        findings.append("embedded_fallback_without_explicit_static_mode")
    return {
        "ok": decision.ok and not findings,
        "decision": decision.to_dict(),
        "findings": findings,
    }


def render_manual_upload_handoff(decision: SourceRouteDecision | dict[str, Any]) -> str:
    payload = decision.to_dict() if isinstance(decision, SourceRouteDecision) else decision
    handoff = payload.get("manual_upload_handoff") or {}
    if not handoff:
        return ""
    lines = [
        "# Manual Upload Handoff",
        "",
        f"- Processed file path: `{handoff.get('processed_file_path') or '<missing>'}`",
        f"- Expected dataset name: `{handoff.get('expected_dataset_name') or '<missing>'}`",
        f"- Required workbook id: `{handoff.get('required_workbook_id') or '<missing>'}`",
        "- Expected schema:",
    ]
    schema = handoff.get("expected_schema") or []
    if schema:
        for field in schema:
            if isinstance(field, dict):
                lines.append(f"  - `{field.get('name')}`: `{field.get('type') or 'unknown'}`")
            else:
                lines.append(f"  - `{field}`")
    else:
        lines.append("  - `<schema evidence required>`")
    lines.extend(
        [
            "- Resume steps:",
            "  - Upload/connect the file in DataLens UI or through a supported connector.",
            "  - Read back the created connection/dataset id in the target workbook.",
            "  - Rerun planning with `existing_dataset_id` or `existing_connection_id`.",
            "  - Publish only after saved and published readback prove the dataset-backed route.",
            "",
        ]
    )
    return "\n".join(lines)


def _matching_dataset(request: dict[str, Any], datasets: list[dict[str, Any]]) -> dict[str, Any]:
    wanted = str(request.get("source_file_name") or request.get("dataset_name") or "").strip().lower()
    if not wanted:
        return datasets[0] if datasets else {}
    for dataset in datasets:
        haystack = " ".join(str(dataset.get(key) or "") for key in ("name", "title", "source_file_name", "id", "dataset_id")).lower()
        if wanted in haystack:
            return dataset
    return {}


def _requirement_mentions_file_or_dataset(request: dict[str, Any]) -> bool:
    text = " ".join(
        str(request.get(key) or "")
        for key in ("requirements_text", "source_description", "source_requirement", "source_kind")
    ).lower()
    return any(
        token in text
        for token in (
            "excel",
            "xlsx",
            "csv",
            "file upload",
            "upload file",
            "uploaded file",
            "file connection",
            "dataset-backed",
            "dataset backed",
            "datalens dataset",
            "existing dataset",
            "загруженный файл",
            "датасет",
        )
    )


def _source_limited(request: dict[str, Any]) -> bool:
    if request.get("source_empty") or request.get("source_missing"):
        return True
    required_fields = [str(item) for item in request.get("required_fields") or []]
    source_fields = {str(item) for item in request.get("source_fields") or request.get("available_fields") or []}
    return bool(required_fields and not source_fields)


def _dataset_field_contract(request: dict[str, Any], *, dataset_id: str = "") -> dict[str, Any]:
    fields = request.get("expected_schema") or request.get("fields") or request.get("required_fields") or []
    normalized_fields: list[dict[str, Any]] = []
    if isinstance(fields, list):
        for item in fields:
            if isinstance(item, dict):
                normalized_fields.append(
                    {
                        "name": str(item.get("name") or item.get("field") or ""),
                        "type": str(item.get("type") or "unknown"),
                    }
                )
            else:
                normalized_fields.append({"name": str(item), "type": "unknown"})
    return {
        "dataset_id": dataset_id or str(request.get("dataset_id") or request.get("existing_dataset_id") or ""),
        "expected_dataset_name": _expected_dataset_name(request),
        "fields": [field for field in normalized_fields if field["name"]],
        "field_mappings": [],
        "mapping_policy": "no_guessed_mappings_without_source_evidence",
    }


def _manual_upload_handoff(request: dict[str, Any]) -> dict[str, Any]:
    path = str(request.get("processed_file_path") or request.get("source_file_path") or request.get("source_file_name") or "")
    return {
        "processed_file_path": path,
        "expected_dataset_name": _expected_dataset_name(request),
        "expected_schema": _dataset_field_contract(request).get("fields") or [],
        "required_workbook_id": str(request.get("workbook_id") or request.get("target_workbook_id") or ""),
        "resume_with": {
            "existing_dataset_id": "<created_dataset_id>",
            "existing_connection_id": "<created_connection_id_if_applicable>",
        },
        "resume_steps": [
            "upload_or_connect_file_in_datalens",
            "read_back_dataset_or_connection_id",
            "rerun_planning_with_existing_dataset_id_or_existing_connection_id",
            "publish_only_after_dataset_backed_readback",
        ],
    }


def _expected_dataset_name(request: dict[str, Any]) -> str:
    explicit = str(request.get("expected_dataset_name") or request.get("dataset_name") or "").strip()
    if explicit:
        return explicit
    file_name = str(request.get("source_file_name") or request.get("source_file_path") or "").strip()
    if file_name:
        return Path(file_name).stem
    return ""
