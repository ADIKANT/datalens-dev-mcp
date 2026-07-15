#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "datalens_api_methods.json"
SCHEMA_BUNDLE_PATH = ROOT / "schemas" / "datalens-api" / "selected-openapi-schema-refs.json"
OPENAPI_LOCK_PATH = ROOT / "schemas" / "datalens-api" / "openapi.lock.json"
POLICY_PATH = ROOT / "config" / "datalens_api_operation_policy.json"
PACKAGE_POLICY_PATH = ROOT / "src" / "datalens_dev_mcp" / "assets" / "config" / "datalens_api_operation_policy.json"
DOC_PATH = ROOT / "docs" / "datalens" / "api_contract_coverage.md"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "api_contracts"
SCHEMA_VERSION = "2026-06-30.api_operation_policy.v1"
EXPECTED_OPERATIONS = 88
EXPECTED_PATHS = 88

VALID_STATUSES = {
    "supported_tool",
    "guarded_plan_only",
    "readonly_reference",
    "expert_only_disabled_by_default",
    "unsupported_explicit",
}

SUPPORT_STATUS_MAP = {
    "EXECUTABLE_TOOL_SUPPORTED": "supported_tool",
    "PLAN_ONLY_SUPPORTED": "guarded_plan_only",
    "READ_ONLY_REFERENCE": "readonly_reference",
    "UNSUPPORTED_NO_VALIDATED_METHOD": "unsupported_explicit",
}


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    import hashlib

    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_name(method: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in method)
    return f"{safe}.json"


def representative_response_payload(method: str) -> dict[str, Any]:
    if method == "getAuditEntriesUpdates":
        return {"entries": [{"entryId": "artifact_1", "scope": "artifact", "isDeleted": False}]}
    if method == "getEntriesRelations":
        return {"relations": [{"entryId": "compute_1", "scope": "compute", "type": ""}]}
    if method == "getWorkbookEntries":
        return {"entries": [{"entryId": "compute_1", "scope": "compute", "type": ""}]}
    if method == "getWorkbookExportStatus":
        return {
            "exportId": "export_1",
            "status": "pending",
            "progress": 0,
            "notifications": [{"entryId": "compute_1", "scope": "compute", "code": "pending", "level": "info"}],
        }
    if method == "getWorkbookImportStatus":
        return {
            "importId": "import_1",
            "workbookId": "workbook_1",
            "status": "pending",
            "progress": 0,
            "notifications": [{"entryId": "compute_1", "scope": "compute", "code": "pending", "level": "info"}],
        }
    return {}


def schema_hash(schema_ref: str, schemas: dict[str, Any]) -> str:
    if not schema_ref:
        return ""
    schema = schemas.get(schema_ref)
    if schema is None:
        return ""
    return sha256_json(schema)


def schema_closure(schema_ref: str, schemas: dict[str, Any]) -> dict[str, Any]:
    if not schema_ref or schema_ref not in schemas:
        return {}
    pending = [schema_ref]
    resolved: dict[str, Any] = {}
    while pending:
        name = pending.pop()
        if name in resolved:
            continue
        schema = schemas.get(name)
        if schema is None:
            continue
        resolved[name] = schema
        for reference in _schema_refs(schema):
            if reference not in resolved:
                pending.append(reference)
    return {name: resolved[name] for name in sorted(resolved)}


def schema_closure_hash(schema_ref: str, schemas: dict[str, Any]) -> str:
    closure = schema_closure(schema_ref, schemas)
    return sha256_json(closure) if closure else ""


def _schema_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
            refs.add(reference.rsplit("/", 1)[-1])
        for item in value.values():
            refs.update(_schema_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_schema_refs(item))
    return refs


def status_for_method(method: dict[str, Any]) -> str:
    support_status = str(method.get("support_status") or "")
    return SUPPORT_STATUS_MAP.get(support_status, "unsupported_explicit")


def live_probe_policy(status: str, method: dict[str, Any]) -> str:
    mode = str(method.get("mode") or "")
    tag = str(method.get("tag") or "")
    if status == "supported_tool" and mode == "readonly" and tag != "QL":
        return "optional_readonly_sanitized_probe"
    if status == "guarded_plan_only":
        return "offline_fixture_required_live_write_optional_approval_gated"
    if status == "readonly_reference":
        return "reference_only_no_mutation_probe"
    if status == "expert_only_disabled_by_default":
        return "disabled_unless_expert_flag_enabled"
    return "unsupported_no_live_probe"


def owning_tool(method: dict[str, Any], status: str) -> str:
    tool = str(method.get("mcp_tool") or "").strip()
    route = str(method.get("mcp_route") or "").strip()
    if status == "supported_tool" and tool:
        return tool
    if status == "guarded_plan_only":
        return tool or route or "safe_apply_plan"
    if status == "readonly_reference":
        return tool or "dl_reference"
    return "explicit_unavailable_method_spec"


def build_policy() -> tuple[dict[str, Any], dict[Path, dict[str, Any]]]:
    catalog = read_json(CATALOG_PATH)
    schemas = read_json(SCHEMA_BUNDLE_PATH)
    lock = read_json(OPENAPI_LOCK_PATH)
    records = []
    fixtures: dict[Path, dict[str, Any]] = {}
    for method in sorted(catalog.get("methods", []), key=lambda item: item["method"]):
        request_ref = str(method.get("request_schema_ref") or "")
        response_ref = str(method.get("response_schema_ref") or "")
        request_closure = schema_closure(request_ref, schemas)
        response_closure = schema_closure(response_ref, schemas)
        status = status_for_method(method)
        record = {
            "operation_id": method["method"],
            "method_name": method["method"],
            "http_method": method.get("http_method") or "POST",
            "path": method["path"],
            "tag": method.get("tag") or "",
            "request_schema_ref": request_ref,
            "request_schema_hash": schema_hash(request_ref, schemas),
            "request_schema_closure_hash": schema_closure_hash(request_ref, schemas),
            "request_schema_closure_refs": sorted(request_closure),
            "response_schema_ref": response_ref,
            "response_schema_hash": schema_hash(response_ref, schemas),
            "response_schema_closure_hash": schema_closure_hash(response_ref, schemas),
            "response_schema_closure_refs": sorted(response_closure),
            "status": status,
            "owning_mcp_tool": owning_tool(method, status),
            "unavailable_response": ""
            if status in {"supported_tool", "guarded_plan_only"}
            else "Return ok=false with error.category=unavailable_api_method or readonly/reference policy.",
            "fixture_path": f"tests/fixtures/api_contracts/{fixture_name(method['method'])}",
            "live_probe_policy": live_probe_policy(status, method),
            "source": {
                "openapi_sha256": lock.get("openapi_sha256") or "",
                "doc_url": method.get("doc_url") or "",
                "catalog": "config/datalens_api_methods.json",
            },
        }
        records.append(record)
        fixtures[ROOT / record["fixture_path"]] = {
            "schema_version": "2026-06-30.api_contract_fixture.v1",
            "operation_id": record["operation_id"],
            "method_name": record["method_name"],
            "path": record["path"],
            "status": record["status"],
            "request_schema_ref": request_ref,
            "request_schema_hash": record["request_schema_hash"],
            "request_schema_closure_hash": record["request_schema_closure_hash"],
            "request_schema_closure_refs": record["request_schema_closure_refs"],
            "response_schema_ref": response_ref,
            "response_schema_hash": record["response_schema_hash"],
            "response_schema_closure_hash": record["response_schema_closure_hash"],
            "response_schema_closure_refs": record["response_schema_closure_refs"],
            "fixture_mode": "offline_schema_contract",
            "request_payload": {},
            "response_payload": representative_response_payload(method["method"]),
        }
    policy = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "catalog": "config/datalens_api_methods.json",
            "schema_bundle": "schemas/datalens-api/selected-openapi-schema-refs.json",
            "openapi_lock": "schemas/datalens-api/openapi.lock.json",
            "openapi_sha256": lock.get("openapi_sha256") or "",
            "generated_at": catalog.get("generated_at") or lock.get("generated_at") or "",
        },
        "expected_counts": {
            "operations": EXPECTED_OPERATIONS,
            "paths": EXPECTED_PATHS,
            "catalog_operations": catalog.get("operation_count"),
            "lock_operations": lock.get("operation_count"),
        },
        "status_enum": sorted(VALID_STATUSES),
        "status_counts": _status_counts(records),
        "operations": records,
    }
    return policy, fixtures


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(VALID_STATUSES)}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    return {key: value for key, value in counts.items() if value}


def render_markdown(policy: dict[str, Any]) -> str:
    counts = policy["expected_counts"]
    lines = [
        "# DataLens API Contract Coverage",
        "",
        "This file is a distilled operation policy generated from the current OpenAPI catalog and compiled schema bundle.",
        "",
        "## Source",
        "",
        f"- OpenAPI SHA-256: `{policy['source']['openapi_sha256']}`.",
        f"- Operations: `{counts['operations']}`.",
        f"- Paths: `{counts['paths']}`.",
        f"- Generated at: `{policy['source']['generated_at']}`.",
        "",
        "## Status Counts",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in sorted(policy["status_counts"].items()))
    lines.extend(
        [
            "",
            "## Operation Matrix",
            "",
            "| Operation | Path | Status | Owner | Request closure hash | Response closure hash |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in policy["operations"]:
        lines.append(
            f"| `{record['operation_id']}` | `{record['path']}` | `{record['status']}` | "
            f"{record['owning_mcp_tool']} | `{record['request_schema_closure_hash']}` | "
            f"`{record['response_schema_closure_hash']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs() -> None:
    policy, fixtures = build_policy()
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PACKAGE_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    policy_text = json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    POLICY_PATH.write_text(policy_text, encoding="utf-8")
    PACKAGE_POLICY_PATH.write_text(policy_text, encoding="utf-8")
    DOC_PATH.write_text(render_markdown(policy), encoding="utf-8")
    expected_fixture_paths = set(fixtures)
    for stale in FIXTURE_DIR.glob("*.json"):
        if stale not in expected_fixture_paths:
            stale.unlink()
    for path, payload in fixtures.items():
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate(*, strict: bool = False) -> dict[str, Any]:
    issues: list[str] = []
    expected_policy, expected_fixtures = build_policy()
    if not POLICY_PATH.is_file():
        issues.append(f"missing {POLICY_PATH.relative_to(ROOT)}")
        actual_policy: dict[str, Any] = {}
    else:
        actual_policy = read_json(POLICY_PATH)
        if actual_policy != expected_policy:
            issues.append(f"changed {POLICY_PATH.relative_to(ROOT)}")
    if not PACKAGE_POLICY_PATH.is_file():
        issues.append(f"missing {PACKAGE_POLICY_PATH.relative_to(ROOT)}")
    elif read_json(PACKAGE_POLICY_PATH) != expected_policy:
        issues.append(f"changed {PACKAGE_POLICY_PATH.relative_to(ROOT)}")
    if not DOC_PATH.is_file():
        issues.append(f"missing {DOC_PATH.relative_to(ROOT)}")
    elif DOC_PATH.read_text(encoding="utf-8") != render_markdown(expected_policy):
        issues.append(f"changed {DOC_PATH.relative_to(ROOT)}")
    if len(expected_policy["operations"]) != EXPECTED_OPERATIONS:
        issues.append(f"operation count mismatch: {len(expected_policy['operations'])} != {EXPECTED_OPERATIONS}")
    path_count = len({record["path"] for record in expected_policy["operations"]})
    if path_count != EXPECTED_PATHS:
        issues.append(f"path count mismatch: {path_count} != {EXPECTED_PATHS}")
    for record in actual_policy.get("operations", []):
        status = record.get("status")
        if status not in VALID_STATUSES:
            issues.append(f"{record.get('operation_id')}: invalid status {status!r}")
        if not record.get("fixture_path"):
            issues.append(f"{record.get('operation_id')}: missing fixture_path")
        if record.get("request_schema_ref") and not record.get("request_schema_hash"):
            issues.append(f"{record.get('operation_id')}: missing request_schema_hash")
        if record.get("request_schema_ref") and not record.get("request_schema_closure_hash"):
            issues.append(f"{record.get('operation_id')}: missing request_schema_closure_hash")
        if record.get("response_schema_ref") and not record.get("response_schema_hash"):
            issues.append(f"{record.get('operation_id')}: missing response_schema_hash")
        if record.get("response_schema_ref") and not record.get("response_schema_closure_hash"):
            issues.append(f"{record.get('operation_id')}: missing response_schema_closure_hash")
    for path, payload in expected_fixtures.items():
        if not path.is_file():
            issues.append(f"missing {path.relative_to(ROOT)}")
        else:
            try:
                actual = read_json(path)
            except json.JSONDecodeError as exc:
                issues.append(f"{path.relative_to(ROOT)}: invalid JSON {exc}")
                continue
            if actual != payload:
                issues.append(f"changed {path.relative_to(ROOT)}")
    stale = sorted(path.relative_to(ROOT).as_posix() for path in FIXTURE_DIR.glob("*.json") if path not in expected_fixtures)
    if stale:
        issues.append("stale api fixtures: " + ", ".join(stale))

    return {
        "ok": not issues,
        "strict": strict,
        "issues": issues,
        "checked": {
            "policy": str(POLICY_PATH.relative_to(ROOT)),
            "doc": str(DOC_PATH.relative_to(ROOT)),
            "operation_count": len(expected_policy["operations"]),
            "path_count": path_count,
            "fixture_count": len(expected_fixtures),
            "status_counts": expected_policy["status_counts"],
            "openapi_sha256": expected_policy["source"]["openapi_sha256"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate current DataLens API operation coverage.")
    parser.add_argument("--write", action="store_true", help="Regenerate operation policy, docs, and fixtures.")
    parser.add_argument("--strict", action="store_true", help="Fail on any mismatch.")
    args = parser.parse_args(argv)
    try:
        if args.write:
            write_outputs()
        report = validate(strict=args.strict)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
