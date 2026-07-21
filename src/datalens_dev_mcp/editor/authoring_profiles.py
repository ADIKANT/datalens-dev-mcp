from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from datalens_dev_mcp.pipeline.chart_taxonomy import resolve_chart_family
from datalens_dev_mcp.pipeline.route_contract import normalize_route
from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_json, resource_text


AUTHORING_PROFILE_RESOURCE = "config/editor_authoring_profiles.json"
PROJECT_MANIFEST_NAMES = (".datalens-mcp.json", "datalens-mcp.project.json")


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
        "runtime_asset": str(selected.get("runtime_asset") or ""),
        "runtime_sha256": str(selected.get("runtime_sha256") or ""),
        "adapter_asset": str(selected.get("adapter_asset") or ""),
        "adapter_sha256": str(selected.get("adapter_sha256") or ""),
        "family_adapters": dict(selected.get("family_adapters") or {}),
        "style_contract": dict(selected.get("style_contract") or {}),
        "registry_schema_version": str(registry.get("schema_version") or ""),
    }


def authoring_profile_route_decision(
    *,
    profile: dict[str, Any],
    family: str,
    explicit_route: str = "",
) -> dict[str, Any]:
    if not profile.get("active"):
        return {"ok": True, "active": False, "route": normalize_route(explicit_route) if explicit_route else ""}
    resolution = resolve_chart_family(family)
    if resolution.status == "reference_only":
        return _route_error(
            profile,
            "reference_only_chart_family",
            f"{resolution.requested} is reference-only; use {resolution.approved_alternative}",
            family=resolution.approved_alternative,
        )
    resolved_family = resolution.approved_alternative
    family_adapters = profile.get("family_adapters") if isinstance(profile.get("family_adapters"), dict) else {}
    adapter = str(family_adapters.get(resolved_family) or "")
    if not adapter:
        return _route_error(
            profile,
            "exact_template_not_registered",
            (
                f"profile {profile['id']} has no exact Charging adapter for {resolved_family}; "
                "approximate or generic-template generation was refused"
            ),
            family=resolved_family,
        )
    registered_route = "editor_advanced"
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
                    f"explicit route {requested_route} would bypass exact template reuse"
                ),
                family=resolved_family,
            )
    return {
        "ok": True,
        "active": True,
        "profile_id": profile["id"],
        "family": resolved_family,
        "route": registered_route,
        "adapter": adapter,
        "source_template": f"{profile.get('adapter_asset')}#{resolved_family}",
        "runtime_asset": profile.get("runtime_asset"),
        "runtime_sha256": profile.get("runtime_sha256"),
        "adapter_asset": profile.get("adapter_asset"),
        "adapter_sha256": profile.get("adapter_sha256"),
        "template_policy": profile.get("template_policy"),
        "fallback_policy": profile.get("fallback_policy"),
        "selection_origin": profile.get("selection_origin"),
    }


def apply_authoring_profile_bundle(
    *,
    bundle: dict[str, Any],
    profile: dict[str, Any],
    route_decision: dict[str, Any],
    title: str,
) -> dict[str, Any]:
    if not route_decision.get("active"):
        return bundle
    runtime_asset = str(route_decision.get("runtime_asset") or "")
    adapter_asset = str(route_decision.get("adapter_asset") or "")
    try:
        runtime = resource_text(runtime_asset)
        adapter_template = resource_text(adapter_asset)
    except RuntimeResourceError as exc:
        return _compiled_profile_error(
            profile,
            route_decision,
            "authoring_profile_asset_unavailable",
            str(exc),
        )
    runtime_sha256 = hashlib.sha256(runtime.encode("utf-8")).hexdigest()
    adapter_sha256 = hashlib.sha256(adapter_template.encode("utf-8")).hexdigest()
    expected_runtime_sha256 = str(route_decision.get("runtime_sha256") or "")
    expected_adapter_sha256 = str(route_decision.get("adapter_sha256") or "")
    if runtime_sha256 != expected_runtime_sha256 or adapter_sha256 != expected_adapter_sha256:
        return _compiled_profile_error(
            profile,
            route_decision,
            "authoring_profile_asset_hash_mismatch",
            (
                f"profile {profile.get('id')} asset fingerprint changed; "
                "refusing to compile an unversioned Charging runtime"
            ),
        )
    spec_placeholder = "__DATALENS_PROFILE_SPEC__"
    runtime_placeholder = "/* __DATALENS_CHARGING_RUNTIME__ */"
    if adapter_template.count(spec_placeholder) != 1 or adapter_template.count(runtime_placeholder) != 1:
        return _compiled_profile_error(
            profile,
            route_decision,
            "authoring_profile_adapter_marker_mismatch",
            "exact Charging adapter markers changed; approximate compilation was refused",
        )
    profile_spec = json.dumps(
        {
            "profile_id": profile.get("id"),
            "family": route_decision.get("family"),
            "adapter": route_decision.get("adapter"),
            "title": title,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    prepare = adapter_template.replace(spec_placeholder, profile_spec).replace(runtime_placeholder, runtime)
    if runtime not in prepare or prepare.count(runtime) != 1:
        return _compiled_profile_error(
            profile,
            route_decision,
            "canonical_runtime_not_embedded_verbatim",
            "the canonical Charging runtime was not embedded exactly once",
        )
    tabs = dict(bundle.get("tabs") or {})
    tabs["prepare.js"] = prepare
    asset_rows = [
        {"path": runtime_asset, "sha256": runtime_sha256},
        {"path": adapter_asset, "sha256": adapter_sha256},
    ]
    asset_canonical = json.dumps(asset_rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    tabs_canonical = json.dumps(tabs, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    source_template = str(route_decision.get("source_template") or adapter_asset)
    return {
        **bundle,
        "route": str(route_decision.get("route") or bundle.get("route") or ""),
        "family": str(route_decision.get("family") or bundle.get("family") or ""),
        "source_template": source_template,
        "source_gallery": source_template,
        "tabs": tabs,
        "template_provenance": {
            "policy": "exact_registered_asset",
            "approximate_fallback_used": False,
            "source_template": source_template,
            "original_source_template": bundle.get("source_template") or "",
            "asset_count": len(asset_rows),
            "template_asset_sha256": hashlib.sha256(asset_canonical.encode("utf-8")).hexdigest(),
            "compiled_tabs_sha256": hashlib.sha256(tabs_canonical.encode("utf-8")).hexdigest(),
            "canonical_runtime_asset": runtime_asset,
            "canonical_runtime_sha256": runtime_sha256,
            "canonical_runtime_bytes": len(runtime.encode("utf-8")),
            "canonical_runtime_embedded_verbatim": True,
            "adapter_asset": adapter_asset,
            "adapter_sha256": adapter_sha256,
            "adapter": route_decision.get("adapter"),
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
