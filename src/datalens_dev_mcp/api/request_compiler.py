from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

from datalens_dev_mcp.runtime_resources import resource_json
from datalens_dev_mcp.pipeline.route_registry import (
    QL_EXPLICIT_ROUTE,
    WIZARD_MAP_ALIAS,
    WIZARD_NATIVE_ROUTE,
    is_supported_wizard_visualization,
    normalize_creation_route,
)

SCHEMA_BUNDLE_RESOURCE = "schemas/datalens-api/closed-schema-bundle.json"
OPERATION_INDEX_RESOURCE = "schemas/datalens-api/operation-schema-index.json"


DATASET_ID_KEYS = ("datasetId", "dataset_id", "id")
CONNECTION_ID_KEYS = ("connectionId", "connection_id", "id")
CREATE_ENTRY_LOCATION_METHODS = {
    "createDashboard",
    "createEditorChart",
    "createWizardChart",
    "createReport",
    "createQLChart",
}
GUARDED_RPC_ALLOWED_METHODS = frozenset(
    {
        "createConnection",
        "updateConnection",
        "createDashboard",
        "updateDashboard",
        "createDataset",
        "updateDataset",
        "validateDataset",
        "createEditorChart",
        "updateEditorChart",
        "createWizardChart",
        "updateWizardChart",
        "createQLChart",
        "updateQLChart",
    }
)


@lru_cache(maxsize=1)
def _schema_bundle() -> dict[str, Any]:
    return resource_json(SCHEMA_BUNDLE_RESOURCE)["schemas"]


@lru_cache(maxsize=1)
def _operation_index() -> dict[str, Any]:
    return resource_json(OPERATION_INDEX_RESOURCE)


def method_request_schema_ref(method: str) -> str:
    return str((_operation_index().get(method) or {}).get("request_schema_ref") or "")


def method_schema_defines_mode(method: str) -> bool:
    schema = _schema_for_method(method)
    return _schema_has_property(schema, "mode")


def compile_method_request(
    method: str,
    value: dict[str, Any] | None,
    *,
    object_type: str = "",
    operation: str = "",
    object_id: str = "",
    workbook_id: str = "",
    mode: str = "save",
) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return _error("missing_input", "payload is required")
    payload = _adapt_method_payload(
        method,
        value,
        object_type=object_type,
        operation=operation,
        object_id=object_id,
        workbook_id=workbook_id,
        mode=mode,
    )
    validation = validate_method_request(method, payload)
    if not validation["ok"]:
        return {
            "ok": False,
            "error": {"category": "datalens_validation_error", "message": "; ".join(validation["issues"])},
            "method": method,
            "schema_ref": validation["schema_ref"],
            "payload": payload,
            "issues": validation["issues"],
        }
    return {"ok": True, "method": method, "schema_ref": validation["schema_ref"], "payload": payload, "issues": []}


def compile_guarded_rpc_request(
    method: str,
    value: dict[str, Any] | None,
    *,
    object_type: str = "",
    operation: str = "",
    object_id: str = "",
    workbook_id: str = "",
    mode: str = "save",
    base_revision: str = "",
    fresh_read_artifact_path: str = "",
    expected_readback_branch: str = "",
    publish_source_artifact: str = "",
    changed_sections: list[str] | None = None,
    approval_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compiled = compile_method_request(
        method,
        value,
        object_type=object_type,
        operation=operation,
        object_id=object_id,
        workbook_id=workbook_id,
        mode=mode,
    )
    payload = compiled.get("payload") if isinstance(compiled.get("payload"), dict) else {}
    blocked_reasons = [] if compiled.get("ok") else [str((compiled.get("error") or {}).get("message") or "request_compile_failed")]
    if method not in GUARDED_RPC_ALLOWED_METHODS:
        blocked_reasons.append("method_not_allowed_by_guarded_rpc_policy")
    if method == "createWizardChart":
        wizard_issue = _wizard_create_policy_issue(value)
        if wizard_issue:
            blocked_reasons.append(wizard_issue)
    if method in {"createQLChart", "updateQLChart"}:
        ql_issue = _ql_write_policy_issue(value, approval_provenance)
        if ql_issue:
            blocked_reasons.append(ql_issue)
    normalized_mode = _guarded_mode(method, mode)
    resolved_object_id = object_id or _object_id_from_payload(method, payload)
    revision = base_revision or _revision_from_payload(payload)
    create_methods = {
        "createConnection",
        "createDataset",
        "createEditorChart",
        "createWizardChart",
        "createQLChart",
        "createDashboard",
    }
    if normalized_mode in {"save", "publish", "validate"} and method not in create_methods:
        if not revision and normalized_mode == "save":
            blocked_reasons.append("base_revision_required_for_guarded_update")
    if normalized_mode == "publish" and not publish_source_artifact:
        blocked_reasons.append("publish_source_artifact_required")
    readback_branch = expected_readback_branch or ("published" if normalized_mode == "publish" else "saved")
    return {
        "ok": not blocked_reasons,
        "schema_version": "datalens.delta_v7.guarded_rpc_request.v1",
        "method": method,
        "object_type": object_type or _object_type_from_method(method),
        "object_id": resolved_object_id,
        "mode": normalized_mode,
        "base_revision": revision,
        "payload_sha256": _payload_sha256(payload),
        "payload": payload,
        "fresh_read": {
            "required": normalized_mode in {"save", "publish", "validate"},
            "artifact_path": fresh_read_artifact_path,
        },
        "readback": {
            "required": normalized_mode in {"save", "publish"},
            "expected_branch": readback_branch,
        },
        "publish_source_artifact": publish_source_artifact,
        "changed_sections": [str(item) for item in changed_sections or [] if str(item)],
        "blocked_reasons": blocked_reasons,
        "request_schema_ref": compiled.get("schema_ref", ""),
        "issues": compiled.get("issues") or [],
        "approval_provenance": _safe_approval_provenance(approval_provenance),
    }


def validate_method_request(method: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "method": method,
            "schema_ref": method_request_schema_ref(method),
            "issues": ["request payload must be an object"],
        }
    schema_ref = method_request_schema_ref(method)
    if not schema_ref:
        return {"ok": True, "method": method, "schema_ref": "", "issues": []}
    schema = _schema_for_method(method)
    issues = _validate_value(payload, schema, path="$", method=method, depth=0)
    issues.extend(_method_semantic_issues(method, payload))
    return {"ok": not issues, "method": method, "schema_ref": schema_ref, "issues": issues}


def _method_semantic_issues(method: str, payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if method in CREATE_ENTRY_LOCATION_METHODS:
        location = payload.get("entry") if method in {"createDashboard", "createEditorChart"} else payload
        if not isinstance(location, dict) or not _valid_create_entry_location(location):
            path = "$.entry" if method in {"createDashboard", "createEditorChart"} else "$"
            issues.append(
                f"{path}: invalid create location; use non-empty `key` without `workbookId`/`name`, "
                "or non-empty `workbookId` and `name` without `key`"
            )
    if method == "getEntries" and "page" in payload:
        issues.append("$.page: removed in API v2; use `pageToken`")
    return issues


def _valid_create_entry_location(value: dict[str, Any]) -> bool:
    has_key = "key" in value
    has_workbook_id = "workbookId" in value
    has_name = "name" in value
    key_location = _is_nonempty_string(value.get("key")) and not has_workbook_id and not has_name
    workbook_location = (
        _is_nonempty_string(value.get("workbookId"))
        and _is_nonempty_string(value.get("name"))
        and not has_key
    )
    return key_location or workbook_location


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _wizard_create_policy_issue(value: Any) -> str:
    visualization_id = _wizard_visualization_token(value)
    if not visualization_id:
        return "wizard_visualization_id_required"
    if not is_supported_wizard_visualization(visualization_id):
        return "unknown_wizard_visualization_id"
    route = _route_token(value)
    if route == WIZARD_MAP_ALIAS and visualization_id != "geolayer":
        return "wizard_map_native_alias_requires_geolayer"
    if route and normalize_creation_route(route) != WIZARD_NATIVE_ROUTE:
        return "wizard_create_requires_wizard_native_route"
    return ""


def _ql_write_policy_issue(value: Any, approval_provenance: dict[str, Any] | None) -> str:
    route = normalize_creation_route(_route_token(value))
    if route != QL_EXPLICIT_ROUTE:
        return "ql_write_requires_route_ql_explicit"
    provenance = approval_provenance or (
        value.get("approval_provenance") if isinstance(value, dict) and isinstance(value.get("approval_provenance"), dict) else {}
    )
    if provenance.get("selection_origin") != "explicit_user_request":
        return "ql_write_requires_explicit_user_request_provenance"
    evidence = (
        provenance.get("user_request_excerpt")
        or provenance.get("request_digest")
        or provenance.get("decision_id")
        or provenance.get("approval_sources")
    )
    if not evidence:
        return "ql_write_requires_user_request_evidence"
    return ""


def _route_token(value: Any) -> str:
    if isinstance(value, dict):
        route = str(value.get("route") or "").strip()
        if route:
            return route
        for child in value.values():
            token = _route_token(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _route_token(child)
            if token:
                return token
    return ""


def _wizard_visualization_token(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("visualizationId", "visualization_id"):
            token = str(value.get(key) or "").strip()
            if token:
                return token
        visualization = value.get("visualization")
        if isinstance(visualization, str) and visualization.strip():
            return visualization.strip()
        if isinstance(visualization, dict):
            token = str(visualization.get("id") or "").strip()
            if token:
                return token
        for child in value.values():
            token = _wizard_visualization_token(child)
            if token:
                return token
    elif isinstance(value, list):
        for child in value:
            token = _wizard_visualization_token(child)
            if token:
                return token
    return ""


def _safe_approval_provenance(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key]
        for key in ("selection_origin", "selection_reason", "request_digest", "decision_id", "approval_sources")
        if value.get(key) not in (None, "")
    }


def _guarded_mode(method: str, mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized in {"read", "validate", "save", "publish", "plan"}:
        return normalized
    if method == "validateDataset":
        return "validate"
    return "save" if method.startswith("update") else "plan"


def _object_type_from_method(method: str) -> str:
    if "Dataset" in method:
        return "dataset"
    if "WizardChart" in method:
        return "wizard_chart"
    if "QLChart" in method:
        return "ql_chart"
    if "Dashboard" in method:
        return "dashboard"
    if "EditorChart" in method:
        return "editor_chart"
    if "Connection" in method:
        return "connection"
    return "object"


def _object_id_from_payload(method: str, payload: dict[str, Any]) -> str:
    keys = ("datasetId", "entryId", "dashboardId", "chartId", "connectionId", "id")
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    for key in keys:
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _revision_from_payload(payload: dict[str, Any]) -> str:
    for key in ("revId", "rev_id", "revisionId", "versionId"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
    for key in ("revId", "rev_id", "revisionId", "versionId"):
        value = entry.get(key)
        if value not in (None, ""):
            return str(value)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    dataset = data.get("dataset") if isinstance(data.get("dataset"), dict) else {}
    for key in ("revId", "rev_id", "revisionId", "versionId"):
        value = dataset.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _payload_sha256(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _schema_for_method(method: str) -> dict[str, Any]:
    schema_ref = method_request_schema_ref(method)
    return _resolve_schema({"$ref": f"#/components/schemas/{schema_ref}"}) if schema_ref else {}


def _adapt_method_payload(
    method: str,
    value: dict[str, Any],
    *,
    object_type: str,
    operation: str,
    object_id: str,
    workbook_id: str,
    mode: str,
) -> dict[str, Any]:
    if method == "createDataset":
        return _adapt_dataset_create(value, workbook_id=workbook_id)
    if method == "updateDataset":
        return _adapt_dataset_update(value, dataset_id=object_id, workbook_id=workbook_id)
    if method == "validateDataset":
        return _adapt_dataset_validate(value, dataset_id=object_id, workbook_id=workbook_id)
    if method == "createConnection":
        return dict(value)
    if method == "updateConnection":
        return _adapt_connection_update(value, connection_id=object_id)
    if method in {"createDashboard", "updateDashboard", "createEditorChart", "updateEditorChart"}:
        return _adapt_entry_envelope(method, value, mode=mode)
    if method in {"createWizardChart", "updateWizardChart"}:
        return _adapt_wizard_envelope(method, value, mode=mode, chart_id=object_id)
    if method in {"createQLChart", "updateQLChart"}:
        return _adapt_ql_envelope(method, value, mode=mode, chart_id=object_id)
    payload = dict(value)
    if method_schema_defines_mode(method) and "mode" not in payload and operation != "create":
        payload["mode"] = mode
    return payload


def _adapt_dataset_create(value: dict[str, Any], *, workbook_id: str) -> dict[str, Any]:
    payload = dict(value)
    if "dataset" not in payload:
        payload = {"dataset": payload}
    if workbook_id and "workbook_id" not in payload and "workbookId" not in payload:
        payload["workbook_id"] = workbook_id
    return payload


def _adapt_dataset_update(value: dict[str, Any], *, dataset_id: str, workbook_id: str) -> dict[str, Any]:
    payload = dict(value)
    if "datasetId" in payload and isinstance(payload.get("data"), dict) and "dataset" in payload["data"]:
        return payload
    resolved_id = dataset_id or _first_string(payload, DATASET_ID_KEYS)
    dataset = _strip_keys(payload, DATASET_ID_KEYS + ("workbookId", "workbook_id", "data"))
    if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("dataset"), dict):
        dataset = payload["data"]["dataset"]
    body: dict[str, Any] = {"datasetId": resolved_id, "data": {"dataset": dataset}}
    resolved_workbook = workbook_id or str(payload.get("workbookId") or payload.get("workbook_id") or "")
    if resolved_workbook:
        body["workbookId"] = resolved_workbook
    return body


def _adapt_dataset_validate(value: dict[str, Any], *, dataset_id: str, workbook_id: str) -> dict[str, Any]:
    payload = _adapt_dataset_update(value, dataset_id=dataset_id, workbook_id=workbook_id)
    if isinstance(value.get("updates"), list):
        payload.setdefault("data", {})["updates"] = value["updates"]
    return payload


def _adapt_connection_update(value: dict[str, Any], *, connection_id: str) -> dict[str, Any]:
    payload = dict(value)
    if "connectionId" in payload and "data" in payload:
        return payload
    resolved_id = connection_id or _first_string(payload, CONNECTION_ID_KEYS)
    data = _strip_keys(payload, CONNECTION_ID_KEYS + ("data",))
    if isinstance(payload.get("data"), dict):
        data = payload["data"]
    return {"connectionId": resolved_id, "data": data}


def _adapt_entry_envelope(method: str, value: dict[str, Any], *, mode: str) -> dict[str, Any]:
    payload = dict(value) if "entry" in value else {"entry": dict(value)}
    if isinstance(payload.get("entry"), dict):
        payload["entry"] = _strip_readback_only_entry_fields(payload["entry"])
    if method_schema_defines_mode(method) and "mode" not in payload:
        payload["mode"] = mode
    return payload


def _adapt_wizard_envelope(method: str, value: dict[str, Any], *, mode: str, chart_id: str) -> dict[str, Any]:
    raw = dict(value.get("entry") if isinstance(value.get("entry"), dict) else value)
    raw = _strip_readback_only_entry_fields(raw)
    data = raw.get("data") if isinstance(raw.get("data"), dict) else _strip_keys(
        raw,
        ("entryId", "chartId", "id", "mode", "template", "route", "chart_type", "type", "workbookId", "name", "key"),
    )
    if method == "createWizardChart":
        payload: dict[str, Any] = {"template": raw.get("template") or "datalens", "data": data}
        for key in ("key", "workbookId", "name", "annotation"):
            if raw.get(key) not in (None, ""):
                payload[key] = raw[key]
        return payload
    entry_id = chart_id or _first_string(raw, ("entryId", "chartId", "id"))
    return {
        "entryId": entry_id,
        "template": raw.get("template") or "datalens",
        "mode": mode,
        "data": data,
    }


def _adapt_ql_envelope(method: str, value: dict[str, Any], *, mode: str, chart_id: str) -> dict[str, Any]:
    raw = dict(value.get("entry") if isinstance(value.get("entry"), dict) else value)
    raw = _strip_readback_only_entry_fields(raw)
    data = raw.get("data") if isinstance(raw.get("data"), dict) else _strip_keys(
        raw,
        (
            "entryId",
            "chartId",
            "id",
            "mode",
            "template",
            "route",
            "approval_provenance",
            "workbookId",
            "name",
            "key",
        ),
    )
    if method == "createQLChart":
        payload: dict[str, Any] = {"template": "ql", "data": data}
        for key in ("key", "workbookId", "name", "annotation"):
            if raw.get(key) not in (None, ""):
                payload[key] = raw[key]
        return payload
    entry_id = chart_id or _first_string(raw, ("entryId", "chartId", "id"))
    return {"entryId": entry_id, "template": "ql", "mode": mode, "data": data}


def _strip_readback_only_entry_fields(entry: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "createdAt",
        "updatedAt",
        "createdBy",
        "updatedBy",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "permissions",
        "relations",
        "isLocked",
        "lock",
    }
    return {key: value for key, value in entry.items() if key not in blocked}


def _validate_value(value: Any, schema: dict[str, Any], *, path: str, method: str, depth: int) -> list[str]:
    schema = _resolve_schema(schema)
    if not schema:
        return []
    if "allOf" in schema:
        issues: list[str] = []
        for item in schema["allOf"]:
            issues.extend(_validate_value(value, item, path=path, method=method, depth=depth))
        return issues
    if "oneOf" in schema or "anyOf" in schema:
        if method in {"createConnection"}:
            return []
        options = schema.get("oneOf") or schema.get("anyOf") or []
        option_results = [
            _validate_value(value, item, path=path, method=method, depth=depth + 1)
            for item in options
        ]
        if any(not result for result in option_results):
            return []
        return [f"{path}: does not match any supported schema branch"]

    issues = _validate_type(value, schema, path=path)
    if issues:
        return issues
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for required in schema.get("required") or []:
            if required not in value:
                issues.append(f"{path}: missing required field `{required}`")
        if schema.get("additionalProperties") is False:
            for key in sorted(value):
                if key not in properties:
                    issues.append(f"{path}: unsupported additional property `{key}`")
        for key, subschema in properties.items():
            if key in value:
                if _skip_deep_entry_validation(method, path, key, depth):
                    continue
                issues.extend(_validate_value(value[key], subschema, path=f"{path}.{key}", method=method, depth=depth + 1))
    elif isinstance(value, list):
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            issues.append(f"{path}: has more than {max_items} items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value[:50]):
                issues.extend(_validate_value(item, item_schema, path=f"{path}[{index}]", method=method, depth=depth + 1))
    enum = schema.get("enum")
    if enum and value not in enum:
        issues.append(f"{path}: value is not one of {enum}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            issues.append(f"{path}: must be greater than or equal to {minimum}")
        if isinstance(maximum, (int, float)) and value > maximum:
            issues.append(f"{path}: must be less than or equal to {maximum}")
    return issues


def _skip_deep_entry_validation(method: str, path: str, key: str, depth: int) -> bool:
    if method in {"updateDataset", "validateDataset"} and path == "$.data" and key == "dataset":
        return True
    if method == "updateConnection" and path == "$" and key == "data":
        return True
    if method in {"createDashboard", "updateDashboard"} and path == "$.entry" and key in {"data", "meta", "annotation"}:
        return True
    if method == "createConnection":
        return True
    if key != "entry":
        return False
    if method in {"createEditorChart", "updateEditorChart"}:
        return True
    return False


def _validate_type(value: Any, schema: dict[str, Any], *, path: str) -> list[str]:
    expected = schema.get("type")
    if not expected:
        return []
    expected_types = expected if isinstance(expected, list) else [expected]
    if "null" in expected_types and value is None:
        return []
    checks = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if any(checks.get(item, True) for item in expected_types if item != "null"):
        return []
    return [f"{path}: expected type {expected}"]


def _resolve_schema(schema: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return _schema_bundle().get(ref.rsplit("/", 1)[-1], {})
    return schema


def _schema_has_property(schema: dict[str, Any], key: str) -> bool:
    schema = _resolve_schema(schema)
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    if key in properties:
        return True
    for child_key in ("allOf", "oneOf", "anyOf"):
        for item in schema.get(child_key) or []:
            if _schema_has_property(item, key):
                return True
    return False


def _first_string(value: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if item not in (None, ""):
            return str(item)
    return ""


def _strip_keys(value: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    blocked = set(keys)
    return {key: item for key, item in value.items() if key not in blocked}


def _error(category: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"category": category, "message": message}}
