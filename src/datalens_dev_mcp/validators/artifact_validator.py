from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.validators.route_validator import ValidationResult


def validate_schema_file(schema_path: str | Path) -> ValidationResult:
    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(False, [f"{schema_path}: invalid JSON schema: {exc}"])
    if schema.get("$schema") is None:
        return ValidationResult(False, [f"{schema_path}: missing $schema"])
    if schema.get("type") != "object":
        return ValidationResult(False, [f"{schema_path}: root type must be object"])
    return ValidationResult(True, [])


def validate_required(payload: dict[str, Any], required: list[str]) -> ValidationResult:
    issues = [f"{field} is required" for field in required if field not in payload]
    return ValidationResult(not issues, issues)
