from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from datalens_dev_mcp.editor.protected_regions import validate_protected_regions
from datalens_dev_mcp.editor.semantic_slots import apply_semantic_slot_updates, bounded_slot_projection, source_aliases
from datalens_dev_mcp.editor.style_registry import profile_identity, select_style_profile
from datalens_dev_mcp.editor.style_scanner import TAB_ORDER


def bind_style_profile(registry: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    selection = select_style_profile(registry, context)
    profile = selection.get("profile")
    binding = {
        "schema_id": "style_binding",
        "selection_origin": selection["origin"],
        "selection_priority": selection["priority"],
        "reason": selection["reason"],
        "profile_id": selection["profile_id"],
        "profile_sha256": selection["profile_sha256"],
        "registry_identity_sha256": str((registry.get("source") or {}).get("identity_sha256") or ""),
        "source_hash": str(((profile or {}).get("source") or {}).get("source_hash") or ""),
        "technology": str((profile or {}).get("technology") or ""),
        "immutable": bool(profile),
    }
    binding["binding_sha256"] = _sha256_json(binding)
    return binding


def materialize_style_bundle(
    registry: dict[str, Any],
    binding: dict[str, Any],
    *,
    updates: dict[str, Any] | None = None,
    template_migration: bool = False,
) -> dict[str, Any]:
    profile = _bound_profile(registry, binding)
    if profile is None:
        raise ValueError("style binding does not reference a local profile")
    root = Path(str((registry.get("source") or {}).get("root") or "")).resolve()
    source = Path(str((profile.get("source") or {}).get("absolute_path") or "")).resolve()
    if root not in source.parents and source != root:
        raise ValueError("style profile source is outside the registry root")
    tabs = {name: (source / name).read_text(encoding="utf-8") for name in TAB_ORDER if (source / name).is_file()}
    actual_source_hash = _sha256_json({name: tabs[name] for name in [item for item in TAB_ORDER if item in tabs]})
    if actual_source_hash != str((profile.get("source") or {}).get("source_hash") or ""):
        raise ValueError("style profile is stale; rebuild the local registry")
    before_aliases = source_aliases(tabs.get("sources.js", ""))
    changed = apply_semantic_slot_updates(tabs, list(profile.get("semantic_slots") or []), updates or {})
    after_aliases = source_aliases(changed.get("sources.js", ""))
    validate_source_alias_coordination(
        before_aliases,
        after_aliases,
        prepare_changed=changed.get("prepare.js") != tabs.get("prepare.js"),
    )
    protection = validate_protected_regions(
        tabs,
        changed,
        list(profile.get("protected_regions") or []),
        template_migration=template_migration,
    )
    if not protection["ok"]:
        raise ValueError("protected style regions changed; use an explicit template migration plan")
    return {
        "tabs": changed,
        "style_binding": dict(binding),
        "protected_region_validation": protection,
        "style_profile_summary": bounded_profile_projection(
            profile,
            changed,
            resource_uri=(
                "datalens://style-registry/profiles/"
                f"{profile['id']}/tabs/prepare.js"
            ),
        ),
    }


def validate_bound_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    binding = bundle.get("style_binding")
    if not isinstance(binding, dict):
        return {"ok": True, "status": "not_bound", "issues": []}
    issues: list[str] = []
    expected = str(binding.get("binding_sha256") or "")
    identity = dict(binding)
    identity.pop("binding_sha256", None)
    if expected != _sha256_json(identity):
        issues.append("style binding hash mismatch")
    if binding.get("immutable") and not binding.get("profile_sha256"):
        issues.append("immutable style binding is missing profile_sha256")
    protection = bundle.get("protected_region_validation") or {}
    if protection and not protection.get("ok"):
        issues.append("protected style region validation failed")
    return {"ok": not issues, "status": "valid" if not issues else "blocked", "issues": issues}


def assert_technology_preserved(binding: dict[str, Any], requested_route: str) -> None:
    technology = str(binding.get("technology") or "")
    if technology and technology != requested_route:
        raise ValueError(f"style-bound technology change is blocked: {technology} -> {requested_route}")


def validate_source_alias_coordination(
    before_aliases: list[str],
    after_aliases: list[str],
    *,
    prepare_changed: bool,
) -> None:
    if before_aliases != after_aliases and not prepare_changed:
        raise ValueError("dataset alias rename requires a coordinated prepare.js update")


def bounded_profile_projection(
    profile: dict[str, Any],
    tabs: dict[str, str],
    *,
    resource_uri: str = "datalens://style-profile/full",
) -> dict[str, Any]:
    slots = list(profile.get("semantic_slots") or [])
    return {
        "profile_id": profile.get("id"),
        "technology": profile.get("technology"),
        "visualization_kind": profile.get("visualization_kind"),
        "tab_order": list(profile.get("tab_order") or []),
        "protected_region_count": len(profile.get("protected_regions") or []),
        "slot_projection": bounded_slot_projection(tabs, slots, resource_uri=resource_uri),
    }


def _bound_profile(registry: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any] | None:
    profile_id = str(binding.get("profile_id") or "")
    for profile in registry.get("profiles") or []:
        if str(profile.get("id") or "") != profile_id:
            continue
        if profile_identity(profile) != str(binding.get("profile_sha256") or ""):
            raise ValueError("style profile hash no longer matches the immutable binding")
        return profile
    return None


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
