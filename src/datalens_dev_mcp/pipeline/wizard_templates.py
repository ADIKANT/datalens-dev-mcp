from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from datalens_dev_mcp.pipeline.route_registry import (
    WIZARD_MAP_ALIAS,
    WIZARD_NATIVE_ROUTE,
    is_supported_wizard_visualization,
    normalize_creation_route,
)
from datalens_dev_mcp.pipeline.wizard_contracts import (
    compact_wizard_dataset_readbacks,
    validate_wizard_field_binding_against_dataset_readback,
)
from datalens_dev_mcp.pipeline.wizard_role_types import binding_role_type_error
from datalens_dev_mcp.runtime_resources import resource_json


REGISTRY_RESOURCE = "templates/datalens/wizard/wizard_template_registry.json"
CANONICAL_TEMPLATES_RESOURCE = "templates/datalens/wizard/canonical_templates.json"
NATIVE_MAP_EXAMPLE_RESOURCE = "templates/datalens/wizard/native_map/example_input.json"
GEO_EVIDENCE_KINDS = {"geopoint", "geopolygon", "lat_lon", "validated_map_payload"}
IDENTITY_KEYS = {
    "entryId",
    "chartId",
    "dashboardId",
    "revId",
    "revisionId",
    "savedId",
    "publishedId",
    "workbookId",
    "key",
    "name",
    "location",
}


def load_wizard_template_registry() -> dict[str, Any]:
    return resource_json(REGISTRY_RESOURCE)


def load_canonical_wizard_templates() -> dict[str, Any]:
    return resource_json(CANONICAL_TEMPLATES_RESOURCE)


def default_native_map_config() -> dict[str, Any]:
    legacy = deepcopy(resource_json(NATIVE_MAP_EXAMPLE_RESOURCE))
    legacy["route"] = WIZARD_MAP_ALIAS
    legacy["visualization_id"] = "geolayer"
    return legacy


def validate_wizard_template_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_config(config)
    errors: list[str] = []
    warnings: list[str] = []
    route = normalize_creation_route(str(normalized.get("route") or WIZARD_NATIVE_ROUTE))
    if route != WIZARD_NATIVE_ROUTE:
        errors.append("route must be wizard_native; wizard_map_native is accepted only as the geolayer compatibility alias")
    visualization_id = str(normalized.get("visualization_id") or "")
    if not is_supported_wizard_visualization(visualization_id):
        errors.append(f"unknown or unsupported Wizard visualization_id: {visualization_id or '<missing>'}")
    if config.get("route") == WIZARD_MAP_ALIAS and visualization_id != "geolayer":
        errors.append("wizard_map_native compatibility alias is valid only for geolayer")
    location = normalized.get("location") if isinstance(normalized.get("location"), dict) else {}
    if location and not _valid_location(location):
        errors.append("location must use key XOR workbookId + name")
    if not str(normalized.get("dataset_id") or "").strip():
        errors.append("dataset is required")
    template_spec = (load_wizard_template_registry().get("templates") or {}).get(visualization_id) or {}
    bindings = normalized.get("field_bindings") if isinstance(normalized.get("field_bindings"), dict) else {}
    required_roles = list(template_spec.get("required_roles") or [])
    for role in required_roles:
        role_bindings = _binding_items(bindings.get(role))
        if not role_bindings:
            errors.append(f"field_bindings.{role} is required")
        elif any(not _binding_guid(item) for item in role_bindings):
            errors.append(f"field_bindings.{role} must contain saved dataset field GUIDs")
    for role, raw_values in bindings.items():
        for item in _binding_items(raw_values):
            type_error = binding_role_type_error(
                visualization_id=visualization_id,
                role=str(role),
                field_type=_binding_type(item),
            )
            if type_error:
                errors.append(f"field_bindings.{role} {type_error}")
    semantic_family = str(normalized.get("semantic_family") or "")
    if semantic_family == "bubble" and not _binding_items(bindings.get("size")):
        errors.append("bubble requires a non-empty size role")
    geo = normalized.get("geo") if isinstance(normalized.get("geo"), dict) else {}
    if visualization_id == "geolayer":
        evidence_kind = str(geo.get("evidence_kind") or "")
        if evidence_kind not in GEO_EVIDENCE_KINDS:
            errors.append("geolayer requires supported geo.evidence_kind")
    seed = normalized.get("saved_seed")
    if seed:
        seed_errors = _saved_seed_errors(seed, visualization_id)
        errors.extend(seed_errors)
    if not location:
        warnings.append("location is deferred; guarded create still requires key XOR workbookId + name")
    return {
        "ok": not errors,
        "visualization_id": visualization_id,
        "required_roles": required_roles,
        "errors": errors,
        "warnings": warnings,
    }


def build_wizard_payload_plan(config: dict[str, Any] | None = None) -> dict[str, Any]:
    active_config = deepcopy(config or default_native_map_config())
    normalized = _normalize_config(active_config)
    validation = validate_wizard_template_config(active_config)
    visualization_id = str(normalized.get("visualization_id") or "")
    if not validation["ok"]:
        return {
            "ok": False,
            "schema_version": "2026-07-13.wizard_payload_plan.v3",
            "route": WIZARD_NATIVE_ROUTE,
            "visualization_id": visualization_id,
            "status": "blocked_invalid_template_config",
            "validation": validation,
            "error": {
                "category": "datalens_validation_error",
                "message": "Wizard template config is incomplete, stale, or unsupported.",
            },
        }

    canonical = deepcopy((load_canonical_wizard_templates().get("templates") or {})[visualization_id])
    saved_seed = normalized.get("saved_seed") if isinstance(normalized.get("saved_seed"), dict) else None
    source_kind = "fresh_saved_seed" if saved_seed else "committed_canonical_template"
    sanitized_seed: dict[str, Any] = {}
    if saved_seed:
        sanitized_seed = _sanitize_saved_seed(saved_seed)
        seed_data = sanitized_seed.get("data") if isinstance(sanitized_seed.get("data"), dict) else {}
        canonical["data"] = seed_data
        canonical["template"] = str(sanitized_seed.get("template") or canonical.get("template") or "datalens")
    compiled_data = deepcopy(canonical.get("data") or {})
    _ensure_visualization_id(compiled_data, visualization_id)
    _clear_runtime_bindings(compiled_data)
    dataset_id = str(normalized["dataset_id"])
    bindings = normalized.get("field_bindings") or {}
    bound_fields = _bind_fields(compiled_data, bindings, dataset_id=dataset_id)
    compiled_data["datasetsIds"] = [dataset_id]
    compiled_data["datasetsPartialFields"] = _dedupe_fields(bound_fields)
    options = normalized.get("options") if isinstance(normalized.get("options"), dict) else {}
    for key, value in options.items():
        if key not in IDENTITY_KEYS:
            compiled_data[key] = deepcopy(value)
    payload: dict[str, Any] = {"template": str(canonical.get("template") or "datalens"), "data": compiled_data}
    location = normalized.get("location") or {}
    payload.update(location)
    if active_config.get("annotation") not in (None, ""):
        payload["annotation"] = deepcopy(active_config["annotation"])

    raw_dataset_readbacks = active_config.get("dataset_readbacks")
    dataset_readback_shape_valid = isinstance(raw_dataset_readbacks, list) and all(
        isinstance(item, dict) for item in raw_dataset_readbacks
    )
    dataset_readbacks = compact_wizard_dataset_readbacks(
        payload,
        raw_dataset_readbacks if dataset_readback_shape_valid else [],
    )
    dataset_readback_validation = validate_wizard_field_binding_against_dataset_readback(
        payload,
        dataset_readbacks,
        source="wizard_payload_plan",
        strict=True,
        enforce_role_types=True,
    )
    if raw_dataset_readbacks is not None and not dataset_readback_shape_valid:
        dataset_readback_validation["ok"] = False
        dataset_readback_validation["findings"].insert(
            0,
            {
                "severity": "error",
                "rule": "dataset_readbacks_shape_invalid",
                "path": "$.dataset_readbacks",
                "message": "dataset_readbacks must be an array of dataset readback objects",
            },
        )

    registry = load_wizard_template_registry()
    template_spec = (registry.get("templates") or {})[visualization_id]
    sanitized_hash = _sha256_json(sanitized_seed) if sanitized_seed else ""
    plan = {
        "ok": True,
        "schema_version": "2026-07-13.wizard_payload_plan.v3",
        "template_name": visualization_id,
        "widget_id": str(active_config.get("widget_id") or "wizard_widget"),
        "route": WIZARD_NATIVE_ROUTE,
        "compatibility_alias": WIZARD_MAP_ALIAS if visualization_id == "geolayer" else "",
        "entry_type": "wizard_chart",
        "visualization_id": visualization_id,
        "method": "createWizardChart",
        "status": "compiled_payload_ready",
        "payload_shape_status": "COMPILED_FROM_SANITIZED_TEMPLATE",
        "source_kind": source_kind,
        "seed_policy": registry.get("seed_policy"),
        "sanitized_seed": {
            "used": bool(saved_seed),
            "sha256": sanitized_hash,
            "branch": "saved" if saved_seed else "",
            "visualization_id": visualization_id if saved_seed else "",
        },
        "template_provenance": registry.get("template_provenance"),
        "semantic_families": list(template_spec.get("semantic_families") or []),
        "required_roles": list(template_spec.get("required_roles") or []),
        "optional_roles": list(template_spec.get("optional_roles") or []),
        "safe_apply_required": True,
        "execute_now": False,
        "live_verification": False,
        "live_execution_ready": bool(dataset_readback_validation["ok"]),
        "validation": validation,
        "dataset_readbacks": dataset_readbacks,
        "dataset_readback_validation": dataset_readback_validation,
        "compiled_payload": payload,
        "payload": payload,
        "compiled_payload_sha256": _sha256_json(payload),
    }
    if visualization_id == "geolayer":
        plan["geo_evidence"] = {
            "status": "validated",
            "kind": (normalized.get("geo") or {}).get("evidence_kind"),
        }
        plan["native_map_preserved"] = True
    if raw_dataset_readbacks is not None and not dataset_readback_validation["ok"]:
        plan["ok"] = False
        plan["status"] = "blocked_dataset_readback_validation"
        plan["validation"]["errors"].extend(
            finding["message"]
            for finding in dataset_readback_validation["findings"]
            if finding.get("severity") == "error"
        )
    return plan


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(config)
    route = str(result.get("route") or WIZARD_NATIVE_ROUTE)
    visualization_id = str(result.get("visualization_id") or result.get("visualizationId") or "")
    chart_type = str(result.get("chart_type") or "")
    if not visualization_id and route == WIZARD_MAP_ALIAS:
        visualization_id = "geolayer"
    if not visualization_id and chart_type in {"map", "geo_layer", "symbol_map"}:
        visualization_id = "geolayer"
    if not visualization_id and is_supported_wizard_visualization(chart_type):
        visualization_id = chart_type
    result["route"] = route
    result["visualization_id"] = visualization_id
    dataset = result.get("dataset")
    if isinstance(dataset, dict):
        dataset_id = dataset.get("dataset_id") or dataset.get("datasetId") or dataset.get("id")
    else:
        dataset_id = dataset
    result["dataset_id"] = str(dataset_id or result.get("dataset_ref") or result.get("dataset_id") or "")
    location = result.get("location") if isinstance(result.get("location"), dict) else {}
    if not location:
        if result.get("key") not in (None, ""):
            location = {"key": result["key"]}
        elif result.get("workbookId") not in (None, ""):
            location = {
                key: result[key]
                for key in ("workbookId", "name")
                if result.get(key) not in (None, "")
            }
    result["location"] = location
    bindings = deepcopy(result.get("field_bindings") or {})
    role_aliases = {
        "measure": "measures",
        "measure_role": "measures",
        "dimension": "dimensions",
        "dimension_role": "dimensions",
        "geo_role": "geo",
    }
    legacy_roles = result.get("data_roles") if isinstance(result.get("data_roles"), dict) else {}
    for key, value in legacy_roles.items():
        target = role_aliases.get(key, key)
        bindings.setdefault(target, value)
    dimensions = list(result.get("dimensions") or [])
    measures = list(result.get("measures") or [])
    if visualization_id == "flatTable" and dimensions + measures:
        bindings.setdefault("flat-table-columns", dimensions + measures)
    elif visualization_id == "pivotTable":
        if dimensions:
            bindings.setdefault("pivot-table-columns", dimensions[:1])
            bindings.setdefault("rows", dimensions[1:] or dimensions[:1])
        if measures:
            bindings.setdefault("measures", measures)
    else:
        if dimensions:
            bindings.setdefault("x", dimensions[:1])
            bindings.setdefault("dimensions", dimensions)
        if measures:
            bindings.setdefault("y", measures)
            bindings.setdefault("measures", measures)
    geo = result.get("geo") if isinstance(result.get("geo"), dict) else {}
    if visualization_id == "geolayer":
        geo_field = geo.get("field") or legacy_roles.get("geo_role")
        if geo_field:
            bindings.setdefault("geo", geo_field)
    result["field_bindings"] = bindings
    return result


def _valid_location(location: dict[str, Any]) -> bool:
    has_key = bool(str(location.get("key") or "").strip())
    has_workbook = bool(str(location.get("workbookId") or "").strip())
    has_name = bool(str(location.get("name") or "").strip())
    return (has_key and not has_workbook and not has_name) or (has_workbook and has_name and not has_key)


def _binding_items(value: Any) -> list[Any]:
    if value in (None, "", []):
        return []
    return value if isinstance(value, list) else [value]


def _binding_guid(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("guid") or value.get("field_guid") or value.get("id") or "").strip()
    return str(value or "").strip()


def _binding_type(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(
        value.get("data_type")
        or value.get("dataType")
        or value.get("field_type")
        or value.get("fieldType")
        or value.get("type")
        or ""
    ).strip()


def _field_item(value: Any, *, dataset_id: str) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {"guid": str(value)}
    guid = str(source.get("guid") or source.get("field_guid") or source.get("id") or "").strip()
    item: dict[str, Any] = {"guid": guid, "datasetId": str(source.get("datasetId") or source.get("dataset_id") or dataset_id)}
    for key in ("title", "type", "data_type", "dataType", "aggregation", "formula"):
        if source.get(key) not in (None, ""):
            item[key] = deepcopy(source[key])
    return item


def _placeholder_objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "items" in value and str(value.get("id") or value.get("name") or ""):
            found.append(value)
        for child in value.values():
            found.extend(_placeholder_objects(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_placeholder_objects(child))
    return found


def _bind_fields(data: dict[str, Any], bindings: dict[str, Any], *, dataset_id: str) -> list[dict[str, Any]]:
    all_fields: list[dict[str, Any]] = []
    placeholders = _placeholder_objects(data.get("visualization") or {})
    by_role = {str(item.get("id") or item.get("name")): item for item in placeholders}
    for role, raw_values in bindings.items():
        target = by_role.get(str(role))
        if target is None:
            continue
        fields = [_field_item(value, dataset_id=dataset_id) for value in _binding_items(raw_values)]
        target["items"] = fields
        all_fields.extend(fields)
    return all_fields


def _clear_runtime_bindings(data: dict[str, Any]) -> None:
    data["datasetsIds"] = []
    data["datasetsPartialFields"] = []
    for placeholder in _placeholder_objects(data.get("visualization") or {}):
        placeholder["items"] = []


def _dedupe_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for field in fields:
        key = (str(field.get("datasetId") or ""), str(field.get("guid") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(field)
    return result


def _saved_seed_errors(seed: Any, visualization_id: str) -> list[str]:
    if not isinstance(seed, dict):
        return ["saved_seed must be an object"]
    branch = str(seed.get("branch") or seed.get("source_branch") or "").strip().lower()
    if branch != "saved":
        return ["saved_seed must declare branch=saved"]
    if not _revision_token(seed):
        return ["saved_seed must include a fresh revision id"]
    seed_visualization = _visualization_token(seed)
    if seed_visualization != visualization_id:
        return [f"saved_seed visualization {seed_visualization or '<missing>'} does not match {visualization_id}"]
    return []


def _sanitize_saved_seed(seed: dict[str, Any]) -> dict[str, Any]:
    current = deepcopy(seed)
    for key in ("response", "result", "chart", "entry", "object"):
        nested = current.get(key)
        if isinstance(nested, dict):
            current = nested
    sanitized = {
        key: deepcopy(value)
        for key, value in current.items()
        if key not in IDENTITY_KEYS and key not in {"branch", "source_branch"}
    }
    data = sanitized.get("data") if isinstance(sanitized.get("data"), dict) else {}
    sanitized = {"template": str(sanitized.get("template") or "datalens"), "data": data}
    return sanitized


def _revision_token(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("revId", "revisionId", "revision_id", "versionId"):
            token = str(value.get(key) or "").strip()
            if token:
                return token
        for child in value.values():
            token = _revision_token(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _revision_token(child)
            if token:
                return token
    return ""


def _visualization_token(value: Any) -> str:
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
            token = _visualization_token(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _visualization_token(child)
            if token:
                return token
    return ""


def _ensure_visualization_id(data: dict[str, Any], visualization_id: str) -> None:
    visualization = data.get("visualization")
    if not isinstance(visualization, dict):
        visualization = {}
        data["visualization"] = visualization
    visualization["id"] = visualization_id


def _sha256_json(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()
