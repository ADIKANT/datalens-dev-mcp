from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.mcp.task_projection import compact_task_status
from datalens_dev_mcp.pipeline.artifacts import read_json
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal

TASK_URI_PREFIX = "datalens://tasks/"
DEFAULT_EVIDENCE_LIMIT = 4_000
MAX_EVIDENCE_LIMIT = 20_000


def task_resource_uri(task_id: str, suffix: str = "") -> str:
    base = f"{TASK_URI_PREFIX}{task_id}"
    return f"{base}/{suffix.lstrip('/')}" if suffix else base


def list_task_resources(project_root: str | Path) -> list[dict[str, str]]:
    tasks_root = ProjectJournal(project_root, "resource-discovery").storage_root
    if not tasks_root.is_dir():
        return []
    resources: list[dict[str, str]] = []
    for task_root in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        resources.append(
            {
                "uri": task_resource_uri(task_root.name),
                "name": f"Task {task_root.name}",
                "title": "DataLens Task Status",
                "mimeType": "application/json",
            }
        )
    return resources


def read_task_resource(uri: str, *, project_root: str | Path = ".") -> dict[str, Any]:
    task_id, suffix = _parse_task_uri(uri)
    journal = ProjectJournal(project_root, task_id)
    contract = journal.load_contract()
    state, _ = journal.replay()
    if not suffix:
        payload = compact_task_status(
            contract,
            state,
            resource_uri=task_resource_uri(task_id),
            target_binding=read_json(journal.target_binding_path, {}) or {},
            style_binding=read_json(journal.style_binding_path, {}) or {},
        )
        return {"uri": uri, "mimeType": "application/json", "text": json.dumps(payload, indent=2, sort_keys=True)}
    fixed = {
        "contract": journal.contract_path,
        "state": journal.state_path,
        "checkpoint": journal.checkpoint_path,
        "target-binding": journal.target_binding_path,
        "target-graph": journal.target_graph_path,
        "reference-binding": journal.reference_binding_path,
        "style-binding": journal.style_binding_path,
        "data/context-profile.json": journal.root / "data" / "context-profile.json",
        "delivery/save-stage-receipt.json": journal.save_stage_receipt_path,
        "delivery/saved-readback-receipt.json": journal.saved_readback_receipt_path,
        "delivery/publish-stage-receipt.json": journal.publish_stage_receipt_path,
        "delivery/published-readback-receipt.json": journal.published_readback_receipt_path,
    }
    if suffix in fixed:
        path = fixed[suffix]
    else:
        path = _bounded_artifact_path(journal.root, suffix)
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    mime = "application/json" if path.suffix in {".json", ".jsonl"} else "text/markdown" if path.suffix == ".md" else "text/plain"
    return {"uri": uri, "mimeType": mime, "text": text}


def read_task_evidence(
    *,
    project_root: str | Path,
    task_id: str,
    resource_uri: str = "",
    section: str = "",
    offset: int = 0,
    limit: int = DEFAULT_EVIDENCE_LIMIT,
) -> dict[str, Any]:
    uri = resource_uri or task_resource_uri(task_id, "checkpoint")
    if not uri.startswith(task_resource_uri(task_id)):
        raise ValueError("resource_uri must belong to the requested task")
    resource = read_task_resource(uri, project_root=project_root)
    text = str(resource.get("text") or "")
    if section:
        text = _markdown_section(text, section)
    start = max(0, int(offset or 0))
    bounded_limit = min(MAX_EVIDENCE_LIMIT, max(1, int(limit or DEFAULT_EVIDENCE_LIMIT)))
    excerpt = text[start : start + bounded_limit]
    return {
        "task_id": task_id,
        "resource_uri": uri,
        "section": section,
        "offset": start,
        "returned_chars": len(excerpt),
        "total_chars": len(text),
        "truncated": start + len(excerpt) < len(text),
        "text": excerpt,
    }


def _parse_task_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith(TASK_URI_PREFIX):
        raise KeyError(f"Unknown task resource {uri}")
    remainder = uri.removeprefix(TASK_URI_PREFIX).strip("/")
    task_id, _, suffix = remainder.partition("/")
    if not task_id:
        raise KeyError("task resource requires a task id")
    return task_id, suffix


def _bounded_artifact_path(task_root: Path, suffix: str) -> Path:
    relative = Path(suffix)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise KeyError("task resource path is unsafe")
    if relative.parts[0] not in {"plans", "receipts", "snapshots", "evidence"}:
        raise KeyError("task resource exposes only bounded plans, receipts, snapshots, or evidence")
    target = (task_root / relative).resolve()
    if not target.is_relative_to(task_root.resolve()):
        raise KeyError("task resource escapes the task journal")
    return target


def _markdown_section(text: str, section: str) -> str:
    wanted = section.strip().lower()
    if not wanted:
        return text
    lines = text.splitlines()
    selected: list[str] = []
    collecting = False
    level = 0
    for line in lines:
        if line.startswith("#"):
            hashes = len(line) - len(line.lstrip("#"))
            title = line[hashes:].strip().lower()
            if collecting and hashes <= level:
                break
            if title == wanted:
                collecting = True
                level = hashes
        if collecting:
            selected.append(line)
    return "\n".join(selected) + ("\n" if selected else "")
