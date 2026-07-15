from __future__ import annotations

from typing import Any

from datalens_dev_mcp.validators.route_validator import ValidationResult, validate_route_payload


def validate_editor_bundle(bundle: dict[str, Any]) -> ValidationResult:
    return validate_route_payload(bundle)
