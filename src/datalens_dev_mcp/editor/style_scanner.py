from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from datalens_dev_mcp.editor.protected_regions import build_protected_regions, function_signatures
from datalens_dev_mcp.editor.semantic_slots import discover_semantic_slots, source_aliases


TAB_ORDER = ("meta.json", "params.js", "sources.js", "controls.js", "prepare.js", "config.js")
SKIP_PARTS = frozenset(
    {
        ".git",
        ".rollbacks",
        ".tmp_plugin_patch",
        "artifacts",
        "memory-bank",
        "node_modules",
        "__pycache__",
    }
)
MAX_TAB_BYTES = 2_000_000
FUNCTION_RE = re.compile(r"\b(?:function\s+|const\s+)([A-Za-z_$][A-Za-z0-9_$]*)")


def scan_portfolio_style_registry(
    portfolio_root: str | Path,
    *,
    max_profiles: int = 1024,
    max_tab_bytes: int = MAX_TAB_BYTES,
) -> dict[str, Any]:
    root = Path(portfolio_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"portfolio root is not a directory: {root}")
    commit_sha = _git_head(root)
    profiles: list[dict[str, Any]] = []
    truncated = False
    for directory in _candidate_directories(root):
        if len(profiles) >= max(1, int(max_profiles)):
            truncated = True
            break
        tabs = _read_tabs(directory, max_tab_bytes=max_tab_bytes)
        if not _is_editor_bundle(tabs):
            continue
        profiles.append(_build_profile(root, directory, tabs, commit_sha=commit_sha))
    profiles.sort(key=lambda item: str(item["source"]["relative_path"]))
    identity = _registry_identity(profiles)
    return {
        "schema_id": "portfolio_style_registry",
        "source_kind": "local_read_only_scan",
        "source": {
            "root": str(root),
            "commit_sha": commit_sha,
            "identity_sha256": identity,
        },
        "profile_count": len(profiles),
        "truncated": truncated,
        "profiles": profiles,
        "limits": {"max_profiles": max_profiles, "max_tab_bytes": max_tab_bytes},
    }


def public_safe_registry(registry: dict[str, Any]) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    for index, profile in enumerate(registry.get("profiles") or [], start=1):
        profiles.append(
            {
                "schema_id": "portfolio_style_profile",
                "id": f"family_{index:03d}",
                "technology": profile.get("technology"),
                "visualization_kind": profile.get("visualization_kind"),
                "tab_order": list(profile.get("tab_order") or []),
                "tab_hashes": dict(profile.get("tab_hashes") or {}),
                "renderer_fingerprint": {
                    "sha256": (profile.get("renderer_fingerprint") or {}).get("sha256"),
                    "function_count": (profile.get("renderer_fingerprint") or {}).get("function_count"),
                },
                "shared_helper_fingerprints": [
                    _sha256_text(str(value))[:16]
                    for value in profile.get("shared_helper_signatures") or []
                ],
                "layout_family": profile.get("layout_family"),
                "selector_family": profile.get("selector_family"),
                "protected_regions": [
                    {
                        **{key: value for key, value in region.items() if key not in {"id", "signature"}},
                        "id": f"region_{region_index:03d}",
                        "signature": "sha256:" + _sha256_text(str(region.get("signature") or "")),
                    }
                    for region_index, region in enumerate(profile.get("protected_regions") or [], start=1)
                ],
                "semantic_slots": [
                    {
                        **{key: value for key, value in slot.items() if key != "id"},
                        "id": f"slot_{slot_index:03d}",
                    }
                    for slot_index, slot in enumerate(profile.get("semantic_slots") or [], start=1)
                ],
                "visual_contracts": list(profile.get("visual_contracts") or []),
                "source": {"source_hash": (profile.get("source") or {}).get("source_hash")},
            }
        )
    safe = {
        "schema_id": "portfolio_style_registry",
        "source_kind": "public_safe_projection",
        "source": {"identity_sha256": (registry.get("source") or {}).get("identity_sha256")},
        "profile_count": len(profiles),
        "truncated": bool(registry.get("truncated")),
        "profiles": profiles,
    }
    safe["projection_sha256"] = _sha256_json(safe)
    return safe


def _candidate_directories(root: Path) -> Iterable[Path]:
    for meta in root.rglob("meta.json"):
        relative = meta.relative_to(root)
        if any(part.startswith(".") or part in SKIP_PARTS for part in relative.parts[:-1]):
            continue
        yield meta.parent


def _read_tabs(directory: Path, *, max_tab_bytes: int) -> dict[str, str]:
    tabs: dict[str, str] = {}
    for name in TAB_ORDER:
        path = directory / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > max_tab_bytes:
            continue
        tabs[name] = path.read_text(encoding="utf-8", errors="replace")
    return tabs


def _is_editor_bundle(tabs: dict[str, str]) -> bool:
    return "meta.json" in tabs and "sources.js" in tabs and bool({"prepare.js", "controls.js"} & tabs.keys())


def _build_profile(
    root: Path,
    directory: Path,
    tabs: dict[str, str],
    *,
    commit_sha: str,
) -> dict[str, Any]:
    relative = directory.relative_to(root).as_posix()
    profile_id = f"local_{hashlib.sha256(relative.encode()).hexdigest()[:16]}"
    tab_order = [name for name in TAB_ORDER if name in tabs]
    prepare = tabs.get("prepare.js", "")
    controls = tabs.get("controls.js", "")
    signatures = function_signatures(prepare)
    aliases = source_aliases(tabs.get("sources.js", ""))
    source_hash = _sha256_json({name: tabs[name] for name in tab_order})
    return {
        "schema_id": "portfolio_style_profile",
        "id": profile_id,
        "profile_id": profile_id,
        "technology": "editor_js_control" if controls and not prepare else "editor_advanced",
        "visualization_kind": _visualization_kind(prepare, controls),
        "tab_order": tab_order,
        "tabs": tab_order,
        "tab_hashes": {name: _sha256_text(tabs[name]) for name in tab_order},
        "renderer_fingerprint": {
            "sha256": _sha256_text(_normalized_code(prepare or controls)),
            "function_count": len(signatures),
            "function_signatures": signatures[:64],
        },
        "shared_helper_signatures": sorted(set(signatures))[:64],
        "layout_family": _layout_family(prepare),
        "selector_family": _selector_family(controls),
        "dataset_aliases": aliases,
        "protected_regions": build_protected_regions(tabs),
        "semantic_slots": discover_semantic_slots(tabs),
        "visual_contracts": _visual_contracts(tabs),
        "contracts": _fixture_contracts(directory),
        "source": {
            "relative_path": relative,
            "absolute_path": str(directory),
            "repository": root.name,
            "commit_sha": commit_sha,
            "source_hash": source_hash,
        },
    }


def _visualization_kind(prepare: str, controls: str) -> str:
    lowered = (prepare + controls).lower()
    for token, kind in (
        ("highcharts", "chart"),
        ("generatehtml", "html"),
        ("paginator", "table"),
        ("controls", "selector"),
    ):
        if token in lowered:
            return kind
    return "advanced"


def _layout_family(prepare: str) -> str:
    lowered = prepare.lower()
    if "display:grid" in lowered or "display: grid" in lowered:
        return "grid"
    if "display:flex" in lowered or "display: flex" in lowered:
        return "flex"
    return "runtime_defined"


def _selector_family(controls: str) -> str:
    if not controls:
        return "none"
    lowered = controls.lower()
    if "multiselect" in lowered or "multiple" in lowered:
        return "multi_select"
    if "select" in lowered:
        return "single_select"
    return "custom"


def _visual_contracts(tabs: dict[str, str]) -> list[str]:
    joined = "\n".join(tabs.values()).lower()
    checks = (
        ("font-family", "typography"),
        ("border-radius", "corner_radius"),
        ("color", "color_tokens"),
        ("tooltip", "tooltip"),
        ("legend", "legend"),
        ("responsive", "responsive_layout"),
        ("paginator", "pagination"),
        ("parameter", "selector_wiring"),
    )
    return [contract for token, contract in checks if token in joined]


def _fixture_contracts(directory: Path) -> dict[str, Any]:
    path = directory / "visual-contracts.json"
    if not path.is_file() or path.stat().st_size > 65_536:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _registry_identity(profiles: list[dict[str, Any]]) -> str:
    return _sha256_json([(item["source"]["relative_path"], item["source"]["source_hash"]) for item in profiles])


def _normalized_code(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", text)).strip()


def _git_head(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
