from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT, normalize_route


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: list[str]


def _scan_terms(value: Any, terms: tuple[str, ...], *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            hits.extend(_scan_terms(str(key), terms, path=f"{path}.{key}#key"))
            hits.extend(_scan_terms(item, terms, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_scan_terms(item, terms, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        lowered = value.lower()
        for term in terms:
            if term.lower() in lowered:
                hits.append(f"{path}: forbidden route/API term {term}")
    return hits


def validate_route_payload(payload: dict[str, Any]) -> ValidationResult:
    issues: list[str] = []
    raw_route = str(payload.get("route", ""))
    route = normalize_route(raw_route)
    if route not in ROUTE_CONTRACT.routes:
        issues.append(f"route must be one of {sorted(ROUTE_CONTRACT.routes)}")
    else:
        spec = ROUTE_CONTRACT.routes[route]
        entry_type = payload.get("entry_type")
        compatible_entry_types = {spec.entry_type}
        if raw_route == "wizard_map_native":
            compatible_entry_types.add("wizard_map_native")
        if entry_type and entry_type not in compatible_entry_types:
            issues.append(f"{route} must use entry_type {spec.entry_type}")
        if route not in {"wizard_native", "ql_explicit"}:
            tabs = payload.get("tabs", {})
            if not isinstance(tabs, dict):
                issues.append("editor route payload requires tabs object")
            else:
                missing = [tab for tab in spec.required_tabs if tab not in tabs]
                if missing:
                    issues.append(f"{route} is missing required tabs: {', '.join(missing)}")
                for tab, value in tabs.items():
                    if not isinstance(value, str):
                        issues.append(f"{tab} must be a string in API payload")
                if route != "editor_table" and "config.js" in tabs:
                    issues.append(f"{route} must not include config.js as a standard tab")
        elif route == "wizard_native" and (
            raw_route == "wizard_map_native" or _wizard_visualization_id(payload) == "geolayer"
        ):
            evidence = payload.get("geo_evidence")
            if not isinstance(evidence, dict) or evidence.get("status") != "validated":
                issues.append("wizard_map_native requires validated geo_evidence")
            elif evidence.get("kind") not in ROUTE_CONTRACT.valid_geo_evidence_kinds:
                issues.append("wizard_map_native geo_evidence.kind is unsupported")
        elif route == "ql_explicit":
            provenance = payload.get("approval_provenance")
            if not isinstance(provenance, dict) or provenance.get("selection_origin") != "explicit_user_request":
                issues.append("ql_explicit requires approval_provenance.selection_origin=explicit_user_request")
    issues.extend(_scan_terms(payload, ROUTE_CONTRACT.forbidden_terms))
    return ValidationResult(ok=not issues, issues=issues)


def _wizard_visualization_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("visualization_id", "visualizationId"):
            token = str(value.get(key) or "").strip()
            if token:
                return token
        visualization = value.get("visualization")
        if isinstance(visualization, dict):
            token = str(visualization.get("id") or visualization.get("type") or "").strip()
            if token:
                return token
        for child in value.values():
            token = _wizard_visualization_id(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _wizard_visualization_id(child)
            if token:
                return token
    return ""


def validate_route_contract_object(payload: dict[str, Any]) -> ValidationResult:
    if "routes" not in payload:
        return ValidationResult(False, ["route contract object must contain routes"])
    return ValidationResult(True, [])
