from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.route_contract import normalize_route
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


def resolve_authoring_profile(
    *,
    project_root: str | Path = ".",
    requested_profile: str = "",
) -> dict[str, Any]:
    declaration: Any = str(requested_profile or "").strip()
    selection_origin = "tool_argument" if declaration else ""
    manifest_path = ""
    if not declaration:
        declaration, manifest_path = _project_profile_declaration(Path(project_root).expanduser().resolve())
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
            "unknown_authoring_profile",
            f"unknown authoring_profile {profile_id!r}; available profiles: {', '.join(sorted(profiles))}",
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
        family_registry = resource_json(family_registry_path)
    except RuntimeResourceError as exc:
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
        },
    }


def validate_authoring_profile_declaration(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [] if value.strip() else ["authoring_profile must not be blank"]
    if not isinstance(value, dict):
        return ["authoring_profile must be a profile id string or an object"]
    unknown = sorted(set(value) - {"id"})
    issues = [f"authoring_profile has unsupported fields: {', '.join(unknown)}"] if unknown else []
    if not str(value.get("id") or "").strip():
        issues.append("authoring_profile.id is required")
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
