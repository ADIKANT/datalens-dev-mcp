from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from datalens_dev_mcp.pipeline.artifacts import write_json


SENSITIVE_FIELD_RE = re.compile(
    r"(^|[_\s-])(password|passwd|secret|token|authorization|cookie|email|phone|mobile|passport|snils|inn|name)([_\s-]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DataSampleBudget:
    max_rows: int = 5_000
    max_cells: int = 50_000
    max_bytes: int = 2_000_000
    inline_examples: int = 3
    inline_bytes: int = 8_000

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def enforce_sample_budget(
    rows: list[dict[str, Any]],
    *,
    schema: list[dict[str, Any]] | None = None,
    budget: DataSampleBudget | None = None,
) -> dict[str, Any]:
    active = budget or DataSampleBudget()
    row_count = len(rows)
    cell_count = sum(len(row) for row in rows)
    byte_count = len(json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
    issues: list[str] = []
    if row_count > active.max_rows:
        issues.append(f"sample row budget exceeded: {row_count} > {active.max_rows}")
    if cell_count > active.max_cells:
        issues.append(f"sample cell budget exceeded: {cell_count} > {active.max_cells}")
    if byte_count > active.max_bytes:
        issues.append(f"sample byte budget exceeded: {byte_count} > {active.max_bytes}")
    sensitive = sensitive_field_guids(schema or [])
    examples: list[dict[str, Any]] = []
    for row in rows[: active.inline_examples]:
        redacted = {key: ("[REDACTED]" if key in sensitive else value) for key, value in row.items()}
        if len(json.dumps(examples + [redacted], ensure_ascii=False, default=str).encode("utf-8")) > active.inline_bytes:
            break
        examples.append(redacted)
    return {
        "ok": not issues,
        "issues": issues,
        "budget": active.to_dict(),
        "observed": {"rows": row_count, "cells": cell_count, "bytes": byte_count},
        "sensitive_fields": sorted(sensitive),
        "redacted_examples": examples,
    }


def externalize_data_sample(
    *,
    project_root: str | Path,
    dataset_id: str,
    schema: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    artifact_name: str = "data-proof-sample",
) -> dict[str, Any]:
    safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in artifact_name)
    safe_name = safe_name.strip("-")[:80] or "data-proof-sample"
    fingerprint = hashlib.sha256(dataset_id.encode("utf-8")).hexdigest()[:12]
    path = Path(project_root) / "artifacts" / "data_samples" / f"{safe_name}-{fingerprint}.json"
    payload = {
        "schema_id": "data_sample_artifact",
        "dataset_fingerprint": fingerprint,
        "schema": schema,
        "rows": rows,
    }
    write_json(path, payload)
    return {
        "artifact_path": str(path),
        "sha256": hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest(),
    }


def sensitive_field_guids(schema: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for field in schema:
        if not isinstance(field, dict):
            continue
        guid = str(field.get("guid") or "")
        label = " ".join(str(field.get(key) or "") for key in ("guid", "name", "title"))
        if guid and (field.get("sensitive") is True or field.get("pii") is True or SENSITIVE_FIELD_RE.search(label)):
            result.add(guid)
    return result
