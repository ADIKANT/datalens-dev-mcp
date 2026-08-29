from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.request_compiler import project_method_request
from datalens_dev_mcp.pipeline.baseline_preservation import build_object_reuse_decision
from datalens_dev_mcp.pipeline.safe_apply import create_safe_apply_plan
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

CREATE_BUNDLE_SCHEMA_ID = "datalens_public_create_bundle"
CREATE_MANIFEST_SCHEMA_ID = "datalens_public_create_manifest"
OBJECT_LIFECYCLES = frozenset({"persistent", "temporary"})
WORKBOOK_LIFECYCLES = frozenset({"persistent", "persistent_anchor", "disposable_sibling"})
CLEANUP_ROUTES = frozenset(
    {
        "direct_object_delete",
        "semantic_inverse_update",
        "whole_disposable_workbook_delete",
        "approved_retained_fixture",
    }
)
PLACEHOLDER_RE = re.compile(r"\$\{object:([A-Za-z][A-Za-z0-9._-]{0,63})\}")
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
ROUTES: dict[str, dict[str, Any]] = {
    "dataset": {
        "route": "dataset",
        "create": "createDataset",
        "read": "getDataset",
        "id_key": "datasetId",
        "publishable": False,
    },
    "wizard_chart": {
        "route": "wizard_native",
        "create": "createWizardChart",
        "read": "getWizardChart",
        "id_key": "chartId",
        "publishable": True,
    },
    "editor_chart": {
        "route": "editor_advanced",
        "create": "createEditorChart",
        "read": "getEditorChart",
        "id_key": "chartId",
        "publishable": True,
    },
    "editor_markdown": {
        "route": "editor_markdown",
        "create": "createHtmlPage",
        "read": "getHtmlPage",
        "id_key": "entryId",
        "publishable": True,
    },
    "dashboard": {
        "route": "dashboard",
        "create": "createDashboard",
        "read": "getDashboard",
        "id_key": "dashboardId",
        "publishable": True,
    },
    "ql_chart": {
        "route": "ql_explicit",
        "create": "createQLChart",
        "read": "getQLChart",
        "id_key": "chartId",
        "publishable": True,
    },
}


class CreateManifestError(ValueError):
    pass


def load_create_bundle(
    project_root: str | Path,
    manifest_locator: str,
    *,
    workbook_id: str = "",
    direct_ql_requested: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest_path = _inside_project(root, manifest_locator, label="create manifest")
    manifest = _read_json(manifest_path, label="create manifest")
    issues = list(validate_create_manifest(manifest))
    resolved_workbook = str(manifest.get("workbook_id") or workbook_id or "").strip()
    run_id = str(manifest.get("run_id") or "").strip()
    workbook_lifecycle = str(manifest.get("workbook_lifecycle") or "persistent").strip()
    if not resolved_workbook:
        issues.append("workbook_id is required")
    if workbook_id and manifest.get("workbook_id") and str(manifest["workbook_id"]) != workbook_id:
        issues.append("manifest workbook_id does not match the requested workbook")
    objects: list[dict[str, Any]] = []
    for item in manifest.get("objects") or []:
        if not isinstance(item, dict):
            continue
        object_type = str(item.get("object_type") or "")
        route = ROUTES.get(object_type) or {}
        object_lifecycle = str(item.get("lifecycle") or "persistent").strip()
        cleanup_route = str(item.get("cleanup_route") or "").strip()
        if object_lifecycle == "temporary":
            if not run_id:
                issues.append("run_id is required before temporary create")
            if not cleanup_route:
                issues.append("cleanup_route is required before temporary create")
        if cleanup_route == "whole_disposable_workbook_delete" and workbook_lifecycle != "disposable_sibling":
            issues.append(
                f"object {item.get('key')} whole_disposable_workbook_delete requires "
                "workbook_lifecycle=disposable_sibling"
            )
        if object_type == "ql_chart" and object_lifecycle == "temporary":
            if cleanup_route in {"direct_object_delete", "semantic_inverse_update"}:
                issues.append(
                    f"object {item.get('key')} QL temporary create requires a disposable sibling "
                    "workbook or approved_retained_fixture"
                )
            if workbook_lifecycle == "persistent_anchor" and cleanup_route != "approved_retained_fixture":
                issues.append(
                    f"object {item.get('key')} QL temporary create in a persistent anchor "
                    "requires approved_retained_fixture"
                )
        if object_type == "ql_chart" and not direct_ql_requested:
            issues.append("ql_chart requires a direct QL request")
        requested_route = str(item.get("route") or route.get("route") or "")
        if route and requested_route != route.get("route"):
            issues.append(f"object {item.get('key')} route does not match object_type")
        try:
            payload_path = _inside_project(root, str(item.get("payload_path") or ""), label="create payload")
            payload = _read_json(payload_path, label="create payload")
        except CreateManifestError as exc:
            issues.append(str(exc))
            continue
        placeholders = sorted(set(_collect_placeholders(payload)))
        declared_dependencies = sorted({str(value) for value in item.get("dependencies") or []})
        if placeholders != declared_dependencies:
            issues.append(
                f"object {item.get('key')} placeholder dependencies do not match declared dependencies"
            )
        writable_payload = payload
        if route:
            projected = project_method_request(
                str(route["create"]),
                payload,
                object_type=object_type,
                operation="create",
                workbook_id=resolved_workbook,
                mode="save",
            )
            if not projected.get("ok"):
                issues.append(
                    f"object {item.get('key')} payload is invalid: "
                    + "; ".join(projected.get("issues") or [])
                )
            elif isinstance(projected.get("payload"), dict):
                # Create manifests commonly originate from a fresh saved
                # readback.  Persist the schema-projected writable request in
                # the immutable bundle, not the read model: otherwise fields
                # marked readOnly are validated away here but reintroduced
                # later when the create action is compiled.
                writable_payload = projected["payload"]
        canonical_payload = deepcopy(writable_payload)
        objects.append(
            {
                "key": str(item.get("key") or ""),
                "object_type": object_type,
                "route": requested_route,
                "name": str(item.get("name") or ""),
                "dependencies": declared_dependencies,
                "payload": canonical_payload,
                "payload_hash": canonical_hash(canonical_payload),
                "lifecycle": object_lifecycle,
                "cleanup_route": cleanup_route,
                "inverse_or_recreate_plan": _cleanup_plan(
                    cleanup_route,
                    workbook_id=resolved_workbook,
                    object_type=object_type,
                ),
            }
        )
    issues.extend(_dependency_issues(objects))
    if issues:
        raise CreateManifestError("invalid create manifest: " + "; ".join(dict.fromkeys(issues)))
    source = deepcopy(manifest)
    bundle = {
        "schema_id": CREATE_BUNDLE_SCHEMA_ID,
        "bundle_version": 1,
        "run_id": run_id,
        "workbook_id": resolved_workbook,
        "workbook_lifecycle": workbook_lifecycle,
        "manifest_hash": canonical_hash(source),
        "object_count": len(objects),
        "objects": objects,
    }
    bundle["bundle_hash"] = create_bundle_hash(bundle)
    return bundle


def validate_create_manifest(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != CREATE_MANIFEST_SCHEMA_ID:
        issues.append(f"schema_id must be {CREATE_MANIFEST_SCHEMA_ID}")
    if value.get("manifest_version") != 1:
        issues.append("manifest_version must equal 1")
    objects = value.get("objects")
    if not isinstance(objects, list) or not objects:
        issues.append("objects must be a non-empty array")
        return tuple(issues)
    if len(objects) > 25:
        issues.append("objects exceeds the maximum of 25")
    keys: list[str] = []
    for index, item in enumerate(objects):
        if not isinstance(item, dict):
            issues.append(f"objects[{index}] must be an object")
            continue
        key = str(item.get("key") or "")
        keys.append(key)
        if not KEY_RE.fullmatch(key):
            issues.append(f"objects[{index}].key is invalid")
        if str(item.get("object_type") or "") not in ROUTES:
            issues.append(f"objects[{index}].object_type is unsupported")
        if not str(item.get("name") or "").strip():
            issues.append(f"objects[{index}].name is required")
        if not str(item.get("payload_path") or "").strip():
            issues.append(f"objects[{index}].payload_path is required")
        lifecycle = str(item.get("lifecycle") or "persistent").strip()
        if lifecycle not in OBJECT_LIFECYCLES:
            issues.append(f"objects[{index}].lifecycle is invalid")
        cleanup_route = str(item.get("cleanup_route") or "").strip()
        if cleanup_route and cleanup_route not in CLEANUP_ROUTES:
            issues.append(f"objects[{index}].cleanup_route is invalid")
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies):
            issues.append(f"objects[{index}].dependencies must be an array of keys")
    if len(keys) != len(set(keys)):
        issues.append("object keys must be unique")
    workbook_lifecycle = str(value.get("workbook_lifecycle") or "persistent").strip()
    if workbook_lifecycle not in WORKBOOK_LIFECYCLES:
        issues.append("workbook_lifecycle is invalid")
    return tuple(issues)


def validate_create_bundle(value: dict[str, Any]) -> tuple[str, ...]:
    issues: list[str] = []
    if value.get("schema_id") != CREATE_BUNDLE_SCHEMA_ID:
        issues.append("create bundle schema_id is invalid")
    if value.get("bundle_version") != 1:
        issues.append("create bundle version is invalid")
    if value.get("bundle_hash") != create_bundle_hash(value):
        issues.append("create bundle hash mismatch")
    objects = value.get("objects") or []
    if value.get("object_count") != len(objects) or not objects:
        issues.append("create bundle object count is invalid")
    for item in objects:
        if not isinstance(item, dict) or item.get("payload_hash") != canonical_hash(item.get("payload")):
            issues.append("create bundle payload hash mismatch")
    issues.extend(_dependency_issues([item for item in objects if isinstance(item, dict)]))
    return tuple(dict.fromkeys(issues))


def create_bundle_hash(value: dict[str, Any]) -> str:
    material = deepcopy(value)
    material.pop("bundle_hash", None)
    return canonical_hash(material)


def create_template_actions(bundle: dict[str, Any], *, baseline_artifact: str) -> list[dict[str, Any]]:
    issues = validate_create_bundle(bundle)
    if issues:
        raise CreateManifestError("invalid persisted create bundle: " + "; ".join(issues))
    workbook_id = str(bundle["workbook_id"])
    actions: list[dict[str, Any]] = []
    for item in bundle["objects"]:
        spec = ROUTES[str(item["object_type"])]
        proof = {
            "schema_id": "datalens.object-creation-necessity",
            "status": "validated",
            "update_insufficient_reason": "the requested manifest declares a new workbook-scoped object role",
            "existing_readback_checked": True,
            "preserve_existing_ids_default": True,
            "cleanup_report_required_if_created": True,
        }
        lifecycle = {
            "mode": "created_object_registry",
            "owner_workflow": "public_create_manifest",
            "active_graph_check": True,
            "run_id": str(bundle.get("run_id") or ""),
            "object_lifecycle": str(item.get("lifecycle") or "persistent"),
            "workbook_lifecycle": str(bundle.get("workbook_lifecycle") or "persistent"),
            "parent_workbook": workbook_id,
            "cleanup_route": str(item.get("cleanup_route") or ""),
            "inverse_or_recreate_plan": deepcopy(item.get("inverse_or_recreate_plan") or {}),
        }
        reuse = build_object_reuse_decision(
            desired_role=str(item["key"]),
            target_object_type=str(item["object_type"]),
            existing_object_found=False,
            target_scope={"workbook_id": workbook_id},
            selected_action="create",
            create_necessity_proof=proof,
            cleanup_lifecycle=lifecycle,
            baseline_proof_artifact=baseline_artifact,
        )
        actions.append(
            {
                "action": f"create_{item['object_type']}",
                "action_type": "create",
                "object_key": item["key"],
                "object_type": item["object_type"],
                "route": item["route"],
                "dependencies": list(item["dependencies"]),
                "method": spec["create"],
                "payload": deepcopy(item["payload"]),
                "payload_template_hash": item["payload_hash"],
                "fresh_read_method": "getWorkbookEntries",
                "fresh_read_payload": {"workbookId": workbook_id},
                "readback_method": spec["read"],
                "readback_payload": {"workbookId": workbook_id},
                "readback_mode": "full",
                "requires_fresh_read": True,
                "preserve_unknown_fields": True,
                "publishable": bool(spec["publishable"]),
                "creation_necessity_proof": proof,
                "object_reuse_decision": reuse,
                "cleanup_lifecycle": lifecycle,
                "changed": True,
            }
        )
    return actions


def create_safe_apply_template(
    bundle: dict[str, Any],
    *,
    project_root: str,
    task_contract_hash: str,
    baseline_artifact: str,
) -> dict[str, Any]:
    return create_safe_apply_plan(
        project_root=project_root,
        actions=create_template_actions(bundle, baseline_artifact=baseline_artifact),
        approved=True,
        approval_note="authorized by immutable public create task contract",
        user_request_text="create declared workbook objects and save",
        task_contract_hash=task_contract_hash,
    )


def resolve_object_placeholders(value: Any, identities: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_object_placeholders(item, identities) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_object_placeholders(item, identities) for item in value]
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in identities:
                raise CreateManifestError(f"unresolved create dependency: {key}")
            return identities[key]

        return PLACEHOLDER_RE.sub(replace, value)
    return value


def _dependency_issues(objects: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    keys = [str(item.get("key") or "") for item in objects]
    positions = {key: index for index, key in enumerate(keys)}
    for index, item in enumerate(objects):
        key = str(item.get("key") or "")
        for dependency in item.get("dependencies") or []:
            if dependency not in positions:
                issues.append(f"object {key} has unknown dependency {dependency}")
            elif positions[dependency] >= index:
                issues.append(f"object {key} dependency {dependency} must appear earlier")
    return issues


def _cleanup_plan(cleanup_route: str, *, workbook_id: str, object_type: str) -> dict[str, Any]:
    if cleanup_route == "whole_disposable_workbook_delete":
        return {"strategy": "delete_workbook_and_verify_absent", "workbook_id": workbook_id}
    if cleanup_route == "direct_object_delete":
        return {"strategy": "delete_object_and_verify_absent", "object_type": object_type}
    if cleanup_route == "semantic_inverse_update":
        return {"strategy": "restore_baseline_and_verify_equivalent"}
    if cleanup_route == "approved_retained_fixture":
        return {"strategy": "retained_fixture_with_named_approval"}
    return {"strategy": "not_applicable_persistent_object"}


def _collect_placeholders(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [found for item in value.values() for found in _collect_placeholders(item)]
    if isinstance(value, list):
        return [found for item in value for found in _collect_placeholders(item)]
    if isinstance(value, str):
        return PLACEHOLDER_RE.findall(value)
    return []


def _inside_project(root: Path, locator: str, *, label: str) -> Path:
    if not locator:
        raise CreateManifestError(f"{label} path is required")
    candidate = Path(locator)
    if candidate.is_absolute():
        raise CreateManifestError(f"{label} path must be relative to project_root")
    path = (root / candidate).resolve()
    if root not in path.parents:
        raise CreateManifestError(f"{label} path escapes project_root")
    if not path.is_file():
        raise CreateManifestError(f"{label} file is missing")
    return path


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CreateManifestError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise CreateManifestError(f"{label} must contain a JSON object")
    return value
