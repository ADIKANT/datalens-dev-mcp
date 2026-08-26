from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


MATCH_PRIORITY = {
    "exact_object": 1,
    "explicit_reference": 2,
    "local_style_family": 3,
    "generic_cookbook": 4,
    "new_design": 5,
}


def load_style_registry(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    issues = validate_style_registry(payload)
    if issues:
        raise ValueError("invalid portfolio style registry: " + "; ".join(issues))
    return payload


def validate_style_registry(registry: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if registry.get("schema_id") != "portfolio_style_registry":
        issues.append("schema_id must be portfolio_style_registry")
    profiles = registry.get("profiles")
    if not isinstance(profiles, list):
        issues.append("profiles must be an array")
        return issues
    if registry.get("profile_count") != len(profiles):
        issues.append("profile_count does not match profiles")
    seen: set[str] = set()
    for index, profile in enumerate(profiles):
        profile_id = str(profile.get("id") or "") if isinstance(profile, dict) else ""
        if not profile_id:
            issues.append(f"profiles[{index}].id is required")
        elif profile_id in seen:
            issues.append(f"profiles[{index}].id is duplicated")
        seen.add(profile_id)
        source_hash = str((profile.get("source") or {}).get("source_hash") or "") if isinstance(profile, dict) else ""
        if len(source_hash) != 64:
            issues.append(f"profiles[{index}].source.source_hash must be sha256")
    return issues


def select_style_profile(registry: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    profiles = [item for item in registry.get("profiles") or [] if isinstance(item, dict)]
    exact_path = _normalized_path(context.get("existing_object_path"))
    explicit_path = _normalized_path(context.get("explicit_reference_path"))
    if exact_path:
        profile = _by_path(profiles, exact_path)
        if profile:
            return _selection("exact_object", profile, "saved object bundle matches exactly")
    if explicit_path:
        profile = _by_path(profiles, explicit_path)
        if profile:
            return _selection("explicit_reference", profile, "explicit reference matches a scanned bundle")
    ranked = sorted(
        ((_family_score(profile, context), profile) for profile in profiles),
        key=lambda item: (-item[0], str(item[1].get("id") or "")),
    )
    if ranked and ranked[0][0] > 0:
        return _selection("local_style_family", ranked[0][1], f"local family score {ranked[0][0]}")
    if context.get("cookbook_available", True):
        return _selection("generic_cookbook", None, "no compatible local family")
    return _selection("new_design", None, "no compatible local or cookbook family")


def profile_identity(profile: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _selection(origin: str, profile: dict[str, Any] | None, reason: str) -> dict[str, Any]:
    return {
        "origin": origin,
        "priority": MATCH_PRIORITY[origin],
        "matched": profile is not None,
        "profile_id": str((profile or {}).get("id") or ""),
        "profile_sha256": profile_identity(profile) if profile else "",
        "reason": reason,
        "profile": profile,
    }


def _by_path(profiles: list[dict[str, Any]], expected: str) -> dict[str, Any] | None:
    for profile in profiles:
        source = profile.get("source") or {}
        if expected in {
            _normalized_path(source.get("relative_path")),
            _normalized_path(source.get("absolute_path")),
        }:
            return profile
    return None


def _family_score(profile: dict[str, Any], context: dict[str, Any]) -> int:
    score = 0
    pairs = (
        ("technology", 32),
        ("visualization_kind", 24),
        ("layout_family", 8),
        ("selector_family", 8),
    )
    for key, weight in pairs:
        requested = str(context.get(key) or "")
        actual = str(profile.get(key) or "")
        if requested and actual == requested:
            score += weight
        elif requested and actual and key == "technology":
            return -1
    requested_tabs = list(context.get("tab_order") or [])
    if requested_tabs and requested_tabs == list(profile.get("tab_order") or []):
        score += 16
    requested_aliases = set(context.get("dataset_aliases") or [])
    actual_aliases = set(profile.get("dataset_aliases") or [])
    if requested_aliases and requested_aliases == actual_aliases:
        score += 8
    renderer = str(context.get("renderer_sha256") or "")
    if renderer and renderer == str((profile.get("renderer_fingerprint") or {}).get("sha256") or ""):
        score += 64
    return score


def _normalized_path(value: Any) -> str:
    return str(value or "").strip().rstrip("/")
