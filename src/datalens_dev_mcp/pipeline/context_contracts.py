from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_CONTEXT_SCHEMA = "project_context_ref.v1"
EVIDENCE_SCHEMA = "evidence_ref.v1"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

_CANONICAL_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "dl_start_pipeline": ("datalens_mapping/governance_memory_registry.json",),
    "dl_ingest_requirements": ("artifacts/requirements_s2t_bundle.json",),
    "dl_ingest_requirements_markdown": ("requirements/source_inputs.md",),
    "dl_build_dashboard_blueprint_plan": ("requirements/implementation_plan.md",),
    "dl_generate_editor_bundle": ("artifacts/dashboard_object_relations.json",),
    "dl_validate_project": ("artifacts/validation_report.json",),
    "dl_build_payload_plan": ("artifacts/payload_plan.json",),
    "dl_create_safe_apply_plan": ("artifacts/safe_apply_plan.json",),
    "dl_readback_and_report": ("artifacts/deployment_report.json",),
}
PROJECT_CONTEXT_AWARE_TOOLS = frozenset(_CANONICAL_ARTIFACTS)


def validate_project_contract_inputs(
    project_root: str | Path,
    context_ref: dict[str, Any] | None,
    evidence_refs: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    root = Path(project_root).expanduser().resolve()
    if context_ref is None:
        if evidence_refs:
            raise ValueError("evidence_refs require project_context_ref.v1")
        return None, []
    if not isinstance(context_ref, dict) or context_ref.get("schema_version") != PROJECT_CONTEXT_SCHEMA:
        raise ValueError("context_ref must use project_context_ref.v1")
    required = {"workspace_root", "workspace_id", "context_id", "index_sha256", "task", "issued_at"}
    missing = sorted(required - set(context_ref))
    if missing:
        raise ValueError(f"context_ref is missing fields: {missing}")
    workspace_root = Path(str(context_ref["workspace_root"])).expanduser().resolve()
    try:
        root.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("project_root must be contained by context_ref.workspace_root") from exc
    if not _SHA256_RE.fullmatch(str(context_ref["index_sha256"])):
        raise ValueError("context_ref.index_sha256 must be a lowercase SHA-256")
    for key in ("workspace_id", "context_id", "task", "issued_at"):
        if not str(context_ref[key]).strip():
            raise ValueError(f"context_ref.{key} must not be empty")
    normalized_context = {"schema_version": PROJECT_CONTEXT_SCHEMA, **{key: context_ref[key] for key in sorted(required)}}
    normalized_evidence = [_validate_evidence_ref(item, workspace_root) for item in evidence_refs or []]
    return normalized_context, normalized_evidence


def finalize_project_contract_result(
    tool_name: str,
    output: Any,
    *,
    project_root: str | Path,
    context_ref: dict[str, Any] | None,
    consumed_evidence: list[dict[str, Any]],
) -> Any:
    if context_ref is None or not isinstance(output, dict):
        return output
    root = Path(project_root).expanduser().resolve()
    workspace_root = Path(str(context_ref["workspace_root"])).expanduser().resolve()
    result = dict(output)
    result["project_context"] = {
        "schema_version": PROJECT_CONTEXT_SCHEMA,
        "workspace_id": context_ref["workspace_id"],
        "context_id": context_ref["context_id"],
        "index_sha256": context_ref["index_sha256"],
    }
    if consumed_evidence:
        result["consumed_evidence"] = [
            {
                "producer": item["producer"],
                "run_id": item["run_id"],
                "kind": item["kind"],
                "sha256": item["sha256"],
            }
            for item in consumed_evidence
        ]
    suggestions = _suggested_records(tool_name, output)
    evidence_refs = []
    for relative_path in _CANONICAL_ARTIFACTS.get(tool_name, ()):
        source = (root / relative_path).resolve()
        if source.is_file():
            evidence_refs.append(
                _snapshot_evidence(
                    tool_name,
                    source,
                    project_root=root,
                    workspace_root=workspace_root,
                    context_ref=context_ref,
                    suggested_records=suggestions,
                )
            )
    if evidence_refs:
        result["evidence_refs"] = evidence_refs
    if suggestions:
        result["suggested_records"] = suggestions
    return result


def _validate_evidence_ref(evidence: Any, workspace_root: Path) -> dict[str, Any]:
    if not isinstance(evidence, dict) or evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError("evidence_refs items must use evidence_ref.v1")
    required = {
        "producer",
        "workspace_root",
        "run_id",
        "kind",
        "scope",
        "artifact_path",
        "sha256",
        "generated_at",
        "freshness",
        "summary",
    }
    missing = sorted(required - set(evidence))
    if missing:
        raise ValueError(f"evidence_ref is missing fields: {missing}")
    declared_root = Path(str(evidence["workspace_root"])).expanduser().resolve()
    if declared_root != workspace_root:
        raise ValueError("evidence_ref.workspace_root does not match context_ref")
    artifact = Path(str(evidence["artifact_path"])).expanduser()
    if not artifact.is_absolute():
        artifact = workspace_root / artifact
    artifact = artifact.resolve()
    try:
        artifact.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("evidence_ref artifact escapes the owning workspace") from exc
    if not artifact.is_file():
        raise ValueError("evidence_ref artifact does not exist")
    digest = str(evidence["sha256"])
    if not _SHA256_RE.fullmatch(digest) or hashlib.sha256(artifact.read_bytes()).hexdigest() != digest:
        raise ValueError("evidence_ref artifact hash does not match")
    return {"schema_version": EVIDENCE_SCHEMA, **{key: evidence[key] for key in sorted(required)}}


def _snapshot_evidence(
    tool_name: str,
    source: Path,
    *,
    project_root: Path,
    workspace_root: Path,
    context_ref: dict[str, Any],
    suggested_records: list[dict[str, Any]],
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_bytes = source.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    run_id = "datalens_" + re.sub(r"[^a-z0-9_]+", "_", tool_name.removeprefix("dl_").lower()).strip("_")
    run_id += "_" + generated_at.replace(":", "").replace("-", "").replace(".", "_").replace("+", "")
    snapshot_dir = project_root / "artifacts" / "datalens_dev_mcp" / "evidence" / run_id
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    snapshot = snapshot_dir / source.name
    temp = snapshot.with_name(f".{snapshot.name}.tmp")
    temp.write_bytes(source_bytes)
    temp.replace(snapshot)
    relative_project = project_root.relative_to(workspace_root)
    scope = relative_project.as_posix() if relative_project.parts else project_root.name
    reference: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "producer": "datalens-dev-mcp",
        "workspace_root": str(workspace_root),
        "run_id": run_id,
        "kind": tool_name.removeprefix("dl_"),
        "scope": scope,
        "artifact_path": snapshot.relative_to(workspace_root).as_posix(),
        "sha256": digest,
        "generated_at": generated_at,
        "freshness": "current",
        "summary": _evidence_summary(tool_name, context_ref),
    }
    if suggested_records:
        reference["suggested_records"] = suggested_records
    return reference


def _evidence_summary(tool_name: str, context_ref: dict[str, Any]) -> str:
    return f"DataLens {tool_name.removeprefix('dl_')} evidence for context {context_ref['context_id']}."


def _suggested_records(tool_name: str, output: dict[str, Any]) -> list[dict[str, Any]]:
    if tool_name not in _CANONICAL_ARTIFACTS:
        return []
    status = str(output.get("status") or ("ok" if output.get("ok", True) else "blocked"))
    return [
        {
            "op": "upsert_entry",
            "path": "memory-bank/project.md",
            "heading": "Current State",
            "entry_id": f"datalens-{tool_name.removeprefix('dl_').replace('_', '-')}",
            "content": f"DataLens `{tool_name}` completed with status `{status}`; record the returned evidence reference if durable.",
        }
    ]
