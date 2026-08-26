from __future__ import annotations

import hashlib
import json
from typing import Any


BREAKING_OPERATION_FIELDS = {
    "http_method",
    "path",
    "request_required",
    "security",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def semantic_openapi_snapshot(
    spec: dict[str, Any],
    *,
    docs_by_operation: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Project an OpenAPI document into a byte-stable semantic snapshot."""
    docs_by_operation = docs_by_operation or {}
    operations: dict[str, dict[str, Any]] = {}
    for path, path_item in sorted((spec.get("paths") or {}).items()):
        if not isinstance(path_item, dict):
            continue
        for http_method, operation in sorted(path_item.items()):
            if http_method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            operation_id = str(operation.get("operationId") or path.rsplit("/", 1)[-1]).strip()
            if not operation_id:
                continue
            request_schema = _json_schema(operation, direction="request")
            response_schema = _json_schema(operation, direction="response")
            operations[operation_id] = {
                "operation": operation_id,
                "path": str(path),
                "http_method": http_method.upper(),
                "security": _normalized_security(operation.get("security")),
                "request_required": _required_fields(request_schema),
                "request_schema_hash": sha256_json(_strip_annotations(request_schema)),
                "response_schema_hash": sha256_json(_strip_annotations(response_schema)),
                "docs_ref": str(docs_by_operation.get(operation_id) or ""),
                "experimental": "experimental" in str(operation.get("summary") or "").lower(),
            }
    schemas = {
        str(name): sha256_json(_strip_annotations(schema))
        for name, schema in sorted((((spec.get("components") or {}).get("schemas") or {}).items()))
        if isinstance(schema, dict)
    }
    snapshot = {
        "openapi_version": str(spec.get("openapi") or ""),
        "operations": operations,
        "schemas": schemas,
    }
    return {**snapshot, "snapshot_hash": sha256_json(snapshot)}


def classify_api_delta(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    support_classification: dict[str, str] | None = None,
) -> dict[str, Any]:
    baseline_operations = _mapping(baseline.get("operations"))
    candidate_operations = _mapping(candidate.get("operations"))
    baseline_names = set(baseline_operations)
    candidate_names = set(candidate_operations)

    changed_operations: list[dict[str, Any]] = []
    relocated_docs: list[dict[str, str]] = []
    breaking_changes: list[dict[str, Any]] = []
    for name in sorted(baseline_names & candidate_names):
        before = _mapping(baseline_operations[name])
        after = _mapping(candidate_operations[name])
        changed_fields = sorted(
            field
            for field in set(before) | set(after)
            if field not in {"docs_ref"} and before.get(field) != after.get(field)
        )
        if changed_fields:
            item = {"operation": name, "changed_fields": changed_fields}
            changed_operations.append(item)
            breaking_fields = sorted(set(changed_fields) & BREAKING_OPERATION_FIELDS)
            if breaking_fields:
                breaking_changes.append({"operation": name, "changed_fields": breaking_fields})
        old_docs = str(before.get("docs_ref") or "")
        new_docs = str(after.get("docs_ref") or "")
        if old_docs and new_docs and old_docs != new_docs:
            relocated_docs.append({"operation": name, "old": old_docs, "new": new_docs})

    baseline_schemas = _mapping(baseline.get("schemas"))
    candidate_schemas = _mapping(candidate.get("schemas"))
    baseline_schema_names = set(baseline_schemas)
    candidate_schema_names = set(candidate_schemas)
    schema_delta = {
        "added": sorted(candidate_schema_names - baseline_schema_names),
        "removed": sorted(baseline_schema_names - candidate_schema_names),
        "changed": sorted(
            name
            for name in baseline_schema_names & candidate_schema_names
            if baseline_schemas[name] != candidate_schemas[name]
        ),
    }
    removed_operations = sorted(baseline_names - candidate_names)
    return {
        "schema_id": "datalens_api_delta_report",
        "policy_version": "api_delta_policy_v1",
        "baseline_hash": str(baseline.get("snapshot_hash") or sha256_json(baseline)),
        "candidate_hash": str(candidate.get("snapshot_hash") or sha256_json(candidate)),
        "added_operations": sorted(candidate_names - baseline_names),
        "removed_operations": removed_operations,
        "changed_operations": changed_operations,
        "relocated_docs": relocated_docs,
        "schema_delta": schema_delta,
        "support_classification": dict(sorted((support_classification or {}).items())),
        "breaking_changes": breaking_changes,
        "breaking": bool(removed_operations or schema_delta["removed"] or breaking_changes),
    }


def reclassify_delta_report(report: dict[str, Any]) -> dict[str, Any]:
    """Apply the current blocker policy to a persisted semantic delta."""
    normalized = dict(report)
    normalized["schema_id"] = "datalens_api_delta_report"
    breaking_changes: list[dict[str, Any]] = []
    for item in report.get("changed_operations") or []:
        if not isinstance(item, dict):
            continue
        fields = sorted(set(item.get("changed_fields") or []) & BREAKING_OPERATION_FIELDS)
        if fields:
            breaking_changes.append({"operation": str(item.get("operation") or ""), "changed_fields": fields})
    schema_delta = _mapping(report.get("schema_delta"))
    normalized["policy_version"] = "api_delta_policy_v1"
    normalized["breaking_changes"] = breaking_changes
    normalized["breaking"] = bool(
        report.get("removed_operations") or schema_delta.get("removed") or breaking_changes
    )
    return normalized


def semantic_compiled_snapshot(
    catalog: dict[str, Any],
    schemas: dict[str, Any],
) -> dict[str, Any]:
    """Build the same semantic comparison surface from compiled assets."""
    operations: dict[str, dict[str, Any]] = {}
    for item in sorted(catalog.get("methods") or [], key=lambda value: str(value.get("method") or "")):
        if not isinstance(item, dict):
            continue
        name = str(item.get("method") or "").strip()
        if not name:
            continue
        request_ref = str(item.get("request_schema_ref") or "")
        response_ref = str(item.get("response_schema_ref") or "")
        request_schema = _mapping(schemas.get(request_ref))
        response_schema = _mapping(schemas.get(response_ref))
        operations[name] = {
            "operation": name,
            "path": str(item.get("path") or ""),
            "http_method": str(item.get("http_method") or "POST").upper(),
            "security": _normalized_security_from_auth(item.get("auth")),
            "request_required": _required_fields(request_schema),
            "request_schema_hash": sha256_json(_strip_annotations(request_schema)),
            "response_schema_hash": sha256_json(_strip_annotations(response_schema)),
            "docs_ref": str(item.get("markdown_ref") or item.get("doc_url") or ""),
            "experimental": bool(item.get("experimental")),
        }
    normalized_schemas = {
        str(name): sha256_json(_strip_annotations(schema))
        for name, schema in sorted(schemas.items())
        if isinstance(schema, dict)
    }
    snapshot = {
        "openapi_version": str(catalog.get("openapi_version") or ""),
        "operations": operations,
        "schemas": normalized_schemas,
    }
    return {**snapshot, "snapshot_hash": sha256_json(snapshot)}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_schema(operation: dict[str, Any], *, direction: str) -> dict[str, Any]:
    if direction == "request":
        content = _mapping(_mapping(operation.get("requestBody")).get("content"))
    else:
        responses = _mapping(operation.get("responses"))
        response = _mapping(responses.get("200") or responses.get("201") or responses.get("default"))
        content = _mapping(response.get("content"))
    media = _mapping(content.get("application/json"))
    if not media and content:
        media = _mapping(next(iter(content.values())))
    return _mapping(media.get("schema"))


def _required_fields(schema: dict[str, Any]) -> list[str]:
    required = schema.get("required") or []
    return sorted(str(item) for item in required if str(item).strip())


def _normalized_security(value: Any) -> list[list[str]]:
    result: list[list[str]] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                result.append(sorted(str(key) for key in item))
    return sorted(result)


def _normalized_security_from_auth(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    names = sorted(
        str(item).split(":", 1)[0].strip()
        for item in value
        if str(item).strip() and not str(item).lower().startswith("x-dl-api-version")
    )
    return [[name] for name in names]


def _strip_annotations(value: Any) -> Any:
    ignored = {"description", "title", "summary", "example", "examples", "externalDocs"}
    if isinstance(value, dict):
        return {
            key: _strip_annotations(nested)
            for key, nested in sorted(value.items())
            if key not in ignored
        }
    if isinstance(value, list):
        return [_strip_annotations(item) for item in value]
    return value
