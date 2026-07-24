from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from datalens_dev_mcp.editor.standard_templates import build_dataset_source_binding
from datalens_dev_mcp.pipeline.chart_param_matrix import get_chart_param_spec
from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.route_contract import ROUTE_CONTRACT, normalize_route
from datalens_dev_mcp.runtime_resources import (
    RESOURCE_OVERRIDE_ENV,
    RuntimeResourceError,
    resource_json,
    resource_text,
)


AUTHORING_PROFILE_RESOURCE = "config/editor_authoring_profiles.json"
DEFAULT_TEMPLATE_REGISTRY_RESOURCE = "templates/datalens/standard_chart_templates.json"
PROJECT_MANIFEST_NAMES = (".datalens-mcp.json", "datalens-mcp.project.json")
SHARED_TEMPLATE_ASSETS = (
    "templates/datalens/advanced_editor/_shared/style_tokens.js",
    "templates/datalens/advanced_editor/_shared/render_helpers.js",
)
PROJECT_PROFILE_SCHEMA_VERSION = "2026-07-23.project_authoring_profile.v1"
PROJECT_PROFILE_MAX_BYTES = 1_048_576


def resolve_authoring_profile(
    *,
    project_root: str | Path = ".",
    requested_profile: Any = "",
) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    manifest_declaration, manifest_path = _project_profile_declaration(root)
    declaration: Any = requested_profile
    if isinstance(declaration, str):
        declaration = declaration.strip()
    selection_origin = "tool_argument" if declaration else ""
    if (
        isinstance(declaration, str)
        and isinstance(manifest_declaration, dict)
        and _profile_token(_profile_id(manifest_declaration)) == _profile_token(declaration)
    ):
        declaration = manifest_declaration
        selection_origin = "tool_argument_with_project_manifest_binding"
    if not declaration:
        declaration = manifest_declaration
        if declaration:
            selection_origin = "project_manifest"
    if not declaration:
        return {
            "ok": True,
            "active": False,
            "id": "",
            "selection_origin": "default_route_policy",
            "manifest_path": manifest_path,
        }

    profile_id = _profile_id(declaration)
    if not profile_id:
        return _profile_error(
            "invalid_authoring_profile",
            "authoring_profile must be a profile id string or an object containing a non-empty id",
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    if isinstance(declaration, dict) and declaration.get("descriptor_path"):
        return _resolve_project_local_profile(
            root=root,
            declaration=declaration,
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    try:
        registry = resource_json(AUTHORING_PROFILE_RESOURCE)
    except RuntimeResourceError as exc:
        return _profile_error(
            "authoring_profile_registry_unavailable",
            str(exc),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    profiles = registry.get("profiles") if isinstance(registry.get("profiles"), dict) else {}
    normalized_requested = _profile_token(profile_id)
    selected_id = ""
    selected: dict[str, Any] = {}
    for candidate_id, candidate in profiles.items():
        if not isinstance(candidate, dict):
            continue
        aliases = [candidate_id, *(candidate.get("aliases") or [])]
        if normalized_requested in {_profile_token(value) for value in aliases}:
            selected_id = str(candidate_id)
            selected = candidate
            break
    if not selected:
        return _profile_error(
            "reference_profile_required",
            (
                f"unknown authoring_profile {profile_id!r}; bind a hash-locked project descriptor "
                f"or use one of: {', '.join(sorted(profiles))}"
            ),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )

    family_registry = str(selected.get("family_registry") or DEFAULT_TEMPLATE_REGISTRY_RESOURCE)
    expected_template_set_sha256 = str(selected.get("template_set_sha256") or "")
    try:
        template_set = authoring_profile_template_set_identity(family_registry)
    except RuntimeResourceError as exc:
        return _profile_error(
            "authoring_profile_template_registry_unavailable",
            str(exc),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    if not _is_sha256(expected_template_set_sha256) or template_set["sha256"] != expected_template_set_sha256:
        return _profile_error(
            "authoring_profile_template_set_hash_mismatch",
            (
                f"profile {selected_id} template-set fingerprint changed; "
                "register a new reviewed profile version before generation"
            ),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    style_contract = dict(selected.get("style_contract") or {})
    style_contract_canonical = json.dumps(
        style_contract,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "ok": True,
        "active": True,
        "id": selected_id,
        "selection_origin": selection_origin,
        "manifest_path": manifest_path,
        "route_policy": str(selected.get("route_policy") or ""),
        "template_policy": str(selected.get("template_policy") or ""),
        "fallback_policy": str(selected.get("fallback_policy") or ""),
        "allowed_routes": list(selected.get("allowed_routes") or []),
        "family_registry": family_registry,
        "template_set_sha256": template_set["sha256"],
        "template_asset_count": template_set["asset_count"],
        "registered_family_count": template_set["family_count"],
        "style_contract": style_contract,
        "style_contract_sha256": hashlib.sha256(style_contract_canonical.encode("utf-8")).hexdigest(),
        "registry_schema_version": str(registry.get("schema_version") or ""),
        "source_kind": "packaged",
    }


def authoring_profile_template_set_identity(family_registry: str) -> dict[str, Any]:
    registry_path = str(family_registry or DEFAULT_TEMPLATE_REGISTRY_RESOURCE).strip()
    if os.getenv(RESOURCE_OVERRIDE_ENV, "").strip():
        identity = _calculate_template_set_identity(registry_path)
    else:
        identity = _packaged_template_set_identity(registry_path)
    return {
        "sha256": identity[0],
        "asset_count": identity[1],
        "family_count": identity[2],
    }


def _resolve_project_local_profile(
    *,
    root: Path,
    declaration: dict[str, Any],
    selection_origin: str,
    manifest_path: str,
) -> dict[str, Any]:
    declaration_issues = validate_authoring_profile_declaration(declaration)
    if declaration_issues:
        return _profile_error(
            "invalid_authoring_profile",
            "; ".join(declaration_issues),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    try:
        descriptor_path = _resolve_inside_project(root, str(declaration["descriptor_path"]))
        raw = descriptor_path.read_bytes()
    except (OSError, ValueError) as exc:
        return _profile_error(
            "authoring_profile_descriptor_unavailable",
            str(exc),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    if len(raw) > PROJECT_PROFILE_MAX_BYTES:
        return _profile_error(
            "authoring_profile_descriptor_too_large",
            f"project authoring profile descriptor exceeds {PROJECT_PROFILE_MAX_BYTES} bytes",
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    expected_descriptor_sha256 = str(declaration.get("descriptor_sha256") or "").lower()
    actual_descriptor_sha256 = hashlib.sha256(raw).hexdigest()
    if not _is_sha256(expected_descriptor_sha256) or expected_descriptor_sha256 != actual_descriptor_sha256:
        return _profile_error(
            "authoring_profile_descriptor_hash_mismatch",
            "project authoring profile descriptor hash does not match the manifest binding",
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    try:
        descriptor = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _profile_error(
            "invalid_authoring_profile_descriptor",
            f"project authoring profile descriptor is not valid UTF-8 JSON: {exc}",
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    if not isinstance(descriptor, dict):
        return _profile_error(
            "invalid_authoring_profile_descriptor",
            "project authoring profile descriptor must be an object",
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    allowed_descriptor_fields = {
        "schema_version",
        "id",
        "description",
        "route_policy",
        "template_policy",
        "fallback_policy",
        "allowed_routes",
        "family_registry",
        "template_set_sha256",
        "shared_assets",
        "style_contract",
    }
    unknown = sorted(set(descriptor) - allowed_descriptor_fields)
    profile_id = _profile_id(declaration)
    descriptor_id = str(descriptor.get("id") or "").strip()
    issues = []
    if descriptor.get("schema_version") != PROJECT_PROFILE_SCHEMA_VERSION:
        issues.append(f"schema_version must be {PROJECT_PROFILE_SCHEMA_VERSION}")
    if not descriptor_id or descriptor_id != profile_id:
        issues.append("descriptor id must exactly match authoring_profile.id")
    if unknown:
        issues.append(f"descriptor has unsupported fields: {', '.join(unknown)}")
    family_registry = str(descriptor.get("family_registry") or "").strip()
    if not family_registry:
        issues.append("descriptor family_registry is required")
    if str(descriptor.get("route_policy") or "project_registered_editor_family") != (
        "project_registered_editor_family"
    ):
        issues.append("project authoring profiles must use route_policy=project_registered_editor_family")
    if str(descriptor.get("template_policy") or "exact_registered_asset") != "exact_registered_asset":
        issues.append("project authoring profiles must use template_policy=exact_registered_asset")
    allowed_routes = [normalize_route(str(route)) for route in descriptor.get("allowed_routes") or []]
    if not allowed_routes or any(route not in ROUTE_CONTRACT.routes for route in allowed_routes):
        issues.append("descriptor allowed_routes must contain only supported Editor routes")
    if str(descriptor.get("fallback_policy") or "block") != "block":
        issues.append("project authoring profiles must use fallback_policy=block")
    shared_assets = descriptor.get("shared_assets") or []
    if not isinstance(shared_assets, list) or any(
        not isinstance(item, str) or not item.strip()
        for item in shared_assets
    ):
        issues.append("descriptor shared_assets must be an array of non-empty project-relative paths")
        shared_assets = []
    if not isinstance(descriptor.get("style_contract") or {}, dict):
        issues.append("descriptor style_contract must be an object")
    expected_template_sha256 = str(descriptor.get("template_set_sha256") or "").lower()
    if not _is_sha256(expected_template_sha256):
        issues.append("descriptor template_set_sha256 must be a lowercase SHA-256")
    if issues:
        return _profile_error(
            "invalid_authoring_profile_descriptor",
            "; ".join(issues),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    try:
        identity = _project_template_set_identity(
            root=root,
            family_registry=family_registry,
            shared_assets=[str(item) for item in shared_assets],
        )
    except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _profile_error(
            "authoring_profile_template_registry_unavailable",
            str(exc),
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    if expected_template_sha256 != identity["sha256"]:
        return _profile_error(
            "authoring_profile_template_set_hash_mismatch",
            f"profile {profile_id} template-set fingerprint changed; update the reviewed descriptor hash",
            selection_origin=selection_origin,
            manifest_path=manifest_path,
        )
    style_contract = dict(descriptor.get("style_contract") or {})
    style_canonical = json.dumps(style_contract, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "ok": True,
        "active": True,
        "id": profile_id,
        "selection_origin": selection_origin,
        "manifest_path": manifest_path,
        "source_kind": "project_local",
        "project_root": str(root),
        "descriptor_path": str(descriptor_path),
        "descriptor_sha256": actual_descriptor_sha256,
        "route_policy": str(descriptor.get("route_policy") or "project_registered_editor_family"),
        "template_policy": str(descriptor.get("template_policy") or "exact_registered_asset"),
        "fallback_policy": "block",
        "allowed_routes": allowed_routes,
        "family_registry": family_registry,
        "shared_assets": [str(item) for item in shared_assets],
        "template_set_sha256": identity["sha256"],
        "template_asset_count": identity["asset_count"],
        "registered_family_count": identity["family_count"],
        "style_contract": style_contract,
        "style_contract_sha256": hashlib.sha256(style_canonical.encode("utf-8")).hexdigest(),
        "registry_schema_version": PROJECT_PROFILE_SCHEMA_VERSION,
    }


def _project_template_set_identity(
    *,
    root: Path,
    family_registry: str,
    shared_assets: list[str],
) -> dict[str, Any]:
    root = root.resolve()
    registry_path = _resolve_inside_project(root, family_registry)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or not isinstance(registry.get("families"), dict):
        raise ValueError("project family registry must contain a families object")
    families = registry["families"]
    paths = {registry_path}
    for asset in shared_assets:
        paths.add(_resolve_inside_project(root, asset))
    for family, spec in families.items():
        if not isinstance(spec, dict):
            raise ValueError(f"project family {family!r} must be an object")
        template_dir = str(spec.get("template_dir") or "").strip().rstrip("/")
        required_files = spec.get("required_files")
        if not template_dir or not isinstance(required_files, list) or not required_files:
            raise ValueError(f"project family {family!r} requires template_dir and required_files")
        for file_name in required_files:
            paths.add(_resolve_inside_project(root, f"{template_dir}/{file_name}"))
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(paths)
    ]
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "asset_count": len(rows),
        "family_count": len(families),
    }


@lru_cache(maxsize=8)
def _packaged_template_set_identity(family_registry: str) -> tuple[str, int, int]:
    return _calculate_template_set_identity(family_registry)


def _calculate_template_set_identity(family_registry: str) -> tuple[str, int, int]:
    registry = resource_json(family_registry)
    families = registry.get("families") if isinstance(registry.get("families"), dict) else {}
    resource_paths = {family_registry, *SHARED_TEMPLATE_ASSETS}
    for spec in families.values():
        if not isinstance(spec, dict):
            continue
        template_dir = str(spec.get("template_dir") or "").strip().rstrip("/")
        if not template_dir:
            continue
        for file_name in spec.get("required_files") or []:
            resource_paths.add(f"{template_dir}/{file_name}")
    asset_rows = [
        {
            "path": path,
            "sha256": hashlib.sha256(resource_text(path).encode("utf-8")).hexdigest(),
        }
        for path in sorted(resource_paths)
    ]
    canonical = json.dumps(asset_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), len(asset_rows), len(families)


def authoring_profile_route_decision(
    *,
    profile: dict[str, Any],
    family: str,
    explicit_route: str = "",
) -> dict[str, Any]:
    if not profile.get("active"):
        return {"ok": True, "active": False, "route": normalize_route(explicit_route) if explicit_route else ""}
    resolution = resolve_chart_family(family)
    if resolution.status != "approved":
        message = (
            f"{resolution.requested} is reference-only; use {resolution.approved_alternative}"
            if resolution.status == "reference_only"
            else f"{resolution.requested or family} is not an approved registered family for exact profile reuse"
        )
        return _route_error(
            profile,
            "reference_only_chart_family" if resolution.status == "reference_only" else "profile_family_requires_review",
            message,
            family=resolution.approved_alternative,
        )
    resolved_family = resolution.approved_alternative
    family_registry_path = str(profile.get("family_registry") or DEFAULT_TEMPLATE_REGISTRY_RESOURCE)
    try:
        family_registry = _profile_family_registry(profile)
    except (RuntimeResourceError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _route_error(
            profile,
            "authoring_profile_template_registry_unavailable",
            str(exc),
            family=resolved_family,
        )
    families = family_registry.get("families") if isinstance(family_registry.get("families"), dict) else {}
    template_spec = families.get(resolved_family) if isinstance(families.get(resolved_family), dict) else {}
    registered_route = normalize_route(str(template_spec.get("route") or ""))
    source_template = str(template_spec.get("template_dir") or "").strip()
    if not registered_route or not source_template:
        return _route_error(
            profile,
            "exact_template_not_registered",
            (
                f"profile {profile['id']} has no registered template for {resolved_family}; "
                "approximate or prompt-generated output was refused"
            ),
            family=resolved_family,
        )
    allowed_routes = {normalize_route(str(value)) for value in profile.get("allowed_routes") or []}
    if registered_route not in allowed_routes:
        return _route_error(
            profile,
            "profile_route_not_allowed",
            f"registered route {registered_route} is outside profile {profile['id']}",
            family=resolved_family,
        )
    if explicit_route:
        requested_route = normalize_route(explicit_route)
        if requested_route != registered_route:
            return _route_error(
                profile,
                "authoring_profile_route_conflict",
                (
                    f"profile {profile['id']} requires {registered_route} for {resolved_family}; "
                    f"explicit route {requested_route} would bypass registered template reuse"
                ),
                family=resolved_family,
            )
    return {
        "ok": True,
        "active": True,
        "profile_id": profile["id"],
        "family": resolved_family,
        "route": registered_route,
        "source_template": source_template,
        "template_variant": str(template_spec.get("variant") or resolved_family),
        "family_registry": family_registry_path,
        "template_set_sha256": profile.get("template_set_sha256"),
        "style_contract_sha256": profile.get("style_contract_sha256"),
        "template_policy": profile.get("template_policy"),
        "fallback_policy": profile.get("fallback_policy"),
        "selection_origin": profile.get("selection_origin"),
        "source_kind": profile.get("source_kind") or "packaged",
        "descriptor_sha256": profile.get("descriptor_sha256") or "",
    }


def load_project_authoring_profile_bundle(
    *,
    profile: dict[str, Any],
    route_decision: dict[str, Any],
    widget_id: str,
    title: str,
    dataset_alias: str | None = None,
    columns: list[str] | None = None,
    visual_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile.get("source_kind") != "project_local":
        raise ValueError("load_project_authoring_profile_bundle requires a project-local profile")
    root = Path(str(profile.get("project_root") or "")).resolve()
    registry = _profile_family_registry(profile)
    families = registry.get("families") if isinstance(registry.get("families"), dict) else {}
    family = str(route_decision.get("family") or "")
    spec = families.get(family) if isinstance(families.get(family), dict) else {}
    route = normalize_route(str(route_decision.get("route") or ""))
    template_dir = str(spec.get("template_dir") or "").strip().rstrip("/")
    required_files = [str(item) for item in spec.get("required_files") or []]
    route_spec = ROUTE_CONTRACT.spec(route)
    tabs: dict[str, str] = {}
    asset_rows: list[dict[str, str]] = []
    substitutions = {
        "__WIDGET_ID_JSON__": json.dumps(widget_id, ensure_ascii=False),
        "__TITLE_JSON__": json.dumps(title, ensure_ascii=False),
        "__TEMPLATE_VARIANT__": str(spec.get("variant") or family),
        "__RENDERER_VISUAL_SPEC_JSON__": json.dumps(
            visual_spec or {},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    }
    for file_name in required_files:
        path = _resolve_inside_project(root, f"{template_dir}/{file_name}")
        text = path.read_text(encoding="utf-8")
        asset_rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        if file_name not in route_spec.required_tabs:
            continue
        for token, replacement in substitutions.items():
            text = text.replace(token, replacement)
        tabs[file_name] = text
    missing_tabs = [name for name in route_spec.required_tabs if name not in tabs]
    source_binding = str(spec.get("source_binding") or "template_complete")
    if source_binding == "caller_dataset":
        source_tabs, source_contract = build_dataset_source_binding(
            dataset_alias=dataset_alias,
            columns=columns,
            required_columns=tuple(str(item) for item in spec.get("required_columns") or []),
        )
        tabs.update(source_tabs)
    elif source_binding == "template_complete":
        source_contract = {
            "status": "ready",
            "production_ready": True,
            "binding": "project_hash_locked_template",
            "required_output_columns": [str(item) for item in spec.get("required_columns") or []],
            "issues": [],
        }
    else:
        source_contract = {
            "status": "blocked_missing_input",
            "production_ready": False,
            "binding": source_binding,
            "required_output_columns": [],
            "issues": [
                {
                    "code": "unsupported_project_profile_source_binding",
                    "message": "source_binding must be template_complete or caller_dataset",
                }
            ],
        }
    blocking_issues = list(source_contract.get("issues") or [])
    if missing_tabs:
        blocking_issues.append(
            {
                "code": "project_profile_required_tabs_missing",
                "message": f"project profile is missing route tabs: {', '.join(missing_tabs)}",
            }
        )
    asset_canonical = json.dumps(asset_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    tabs_canonical = json.dumps(tabs, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "schema_version": "2026-07-23.project_template_bundle.v1",
        "widget_id": widget_id,
        "name": f"{widget_id}_{route}",
        "display_title": title,
        "route": route,
        "entry_type": route_spec.entry_type,
        "family": family,
        "requested_family": family,
        "template_status": "PROJECT_REGISTERED",
        "parameter_spec": get_chart_param_spec(family).brief(),
        "renderer_visual_spec": visual_spec or {},
        "source_template": template_dir,
        "source_gallery": template_dir,
        "template_provenance": {
            "policy": "exact_registered_asset",
            "approximate_fallback_used": False,
            "source_template": template_dir,
            "asset_count": len(asset_rows),
            "template_asset_sha256": hashlib.sha256(asset_canonical.encode("utf-8")).hexdigest(),
            "compiled_tabs_sha256": hashlib.sha256(tabs_canonical.encode("utf-8")).hexdigest(),
            "descriptor_sha256": profile.get("descriptor_sha256"),
        },
        "generation_status": "ready" if not blocking_issues else "blocked_missing_input",
        "source_contract": source_contract,
        "blocking_issues": blocking_issues,
        "tabs": tabs,
    }


def apply_authoring_profile_bundle(
    *,
    bundle: dict[str, Any],
    profile: dict[str, Any],
    route_decision: dict[str, Any],
) -> dict[str, Any]:
    if not route_decision.get("active"):
        return bundle
    provenance = bundle.get("template_provenance") if isinstance(bundle.get("template_provenance"), dict) else {}
    tabs = bundle.get("tabs") if isinstance(bundle.get("tabs"), dict) else {}
    tabs_canonical = json.dumps(tabs, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    compiled_tabs_sha256 = hashlib.sha256(tabs_canonical.encode("utf-8")).hexdigest()
    mismatches = []
    if bundle.get("route") != route_decision.get("route"):
        mismatches.append("route")
    if bundle.get("family") != route_decision.get("family"):
        mismatches.append("family")
    if bundle.get("source_template") != route_decision.get("source_template"):
        mismatches.append("source_template")
    if provenance.get("policy") != "exact_registered_asset":
        mismatches.append("template_policy")
    if provenance.get("approximate_fallback_used") is not False:
        mismatches.append("fallback_policy")
    if not _is_sha256(str(provenance.get("template_asset_sha256") or "")):
        mismatches.append("template_asset_sha256")
    if provenance.get("compiled_tabs_sha256") != compiled_tabs_sha256:
        mismatches.append("compiled_tabs_sha256")
    if mismatches:
        return _compiled_profile_error(
            profile,
            route_decision,
            "exact_template_identity_mismatch",
            (
                f"profile {profile.get('id')} expected a registered deterministic template; "
                f"identity checks failed: {', '.join(mismatches)}"
            ),
        )
    return {
        **bundle,
        "template_provenance": {
            **provenance,
            "authoring_profile_id": profile.get("id"),
            "profile_template_set_sha256": profile.get("template_set_sha256"),
            "profile_style_contract_sha256": profile.get("style_contract_sha256"),
            "profile_descriptor_sha256": profile.get("descriptor_sha256") or "",
            "profile_source_kind": profile.get("source_kind") or "packaged",
        },
    }


def validate_authoring_profile_declaration(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [] if value.strip() else ["authoring_profile must not be blank"]
    if not isinstance(value, dict):
        return ["authoring_profile must be a profile id string or an object"]
    unknown = sorted(set(value) - {"id", "descriptor_path", "descriptor_sha256"})
    issues = [f"authoring_profile has unsupported fields: {', '.join(unknown)}"] if unknown else []
    if not str(value.get("id") or "").strip():
        issues.append("authoring_profile.id is required")
    descriptor_path = str(value.get("descriptor_path") or "").strip()
    descriptor_sha256 = str(value.get("descriptor_sha256") or "").strip().lower()
    if bool(descriptor_path) != bool(descriptor_sha256):
        issues.append("authoring_profile descriptor_path and descriptor_sha256 must be provided together")
    if descriptor_sha256 and not _is_sha256(descriptor_sha256):
        issues.append("authoring_profile.descriptor_sha256 must be a lowercase SHA-256")
    return issues


def _project_profile_declaration(root: Path) -> tuple[Any, str]:
    for name in PROJECT_MANIFEST_NAMES:
        path = root / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return "", str(path)
        if isinstance(payload, dict):
            return payload.get("authoring_profile") or "", str(path)
    return "", ""


def _profile_id(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("id") or "").strip()
    return ""


def _profile_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _profile_family_registry(profile: dict[str, Any]) -> dict[str, Any]:
    registry_path = str(profile.get("family_registry") or DEFAULT_TEMPLATE_REGISTRY_RESOURCE)
    if profile.get("source_kind") != "project_local":
        return resource_json(registry_path)
    root = Path(str(profile.get("project_root") or "")).resolve()
    path = _resolve_inside_project(root, registry_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("project family registry must be an object")
    return payload


def _resolve_inside_project(root: Path, value: str) -> Path:
    root = root.resolve()
    raw = Path(str(value or "").strip())
    if not str(raw):
        raise ValueError("project profile path must not be blank")
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"project profile path escapes project_root: {value}") from exc
    if not resolved.is_file():
        raise ValueError(f"project profile path is not a regular file: {value}")
    return resolved


def _is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _profile_error(category: str, message: str, *, selection_origin: str, manifest_path: str) -> dict[str, Any]:
    return {
        "ok": False,
        "active": True,
        "id": "",
        "selection_origin": selection_origin,
        "manifest_path": manifest_path,
        "status": "blocked_authoring_profile",
        "error": {"category": category, "message": message},
    }


def _route_error(profile: dict[str, Any], category: str, message: str, *, family: str) -> dict[str, Any]:
    return {
        "ok": False,
        "active": True,
        "profile_id": profile.get("id"),
        "family": family,
        "status": "blocked_authoring_profile",
        "error": {"category": category, "message": message},
    }


def _compiled_profile_error(
    profile: dict[str, Any],
    route_decision: dict[str, Any],
    category: str,
    message: str,
) -> dict[str, Any]:
    return {
        "ok": False,
        "active": True,
        "profile_id": profile.get("id"),
        "family": route_decision.get("family"),
        "status": "blocked_authoring_profile",
        "error": {"category": category, "message": message},
        "authoring_profile": profile,
        "profile_route_decision": route_decision,
    }
