from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

GENERIC_DEFAULTS: dict[str, Any] = {
    "theme": "auto",
    "spacing": 8,
    "visible_title": {"owner": "widget", "visible": True},
    "hint": {"owner": "widget", "enabled": True},
    "labels": {"visible": True},
    "axes_gridlines": {"x_grid": False, "y_grid": False},
    "dashboard": {"hide_dash_title": True},
    "selector": {"title_placement": "left", "show_title": True},
}
FORBIDDEN_CONFIG_KEYS = {"workflow", "history", "messages", "memory", "task", "orchestrator"}


def get_authoring_defaults(
    project_root: str | Path | None = None,
    family: str | None = None,
    *,
    explicit: Mapping[str, Any] | None = None,
    reference: Mapping[str, Any] | None = None,
    user_config_path: str | Path | None = None,
) -> dict[str, Any]:
    user_path = Path(user_config_path).expanduser() if user_config_path else _user_config_path()
    project_path = Path(project_root).expanduser().resolve() / ".datalens/authoring.json" if project_root else None
    user = _read_config(user_path)
    project = _read_config(project_path) if project_path else {}
    # Family structure and reference technology are useful; reference styling is
    # not an override of the current installation's presentation policy.
    from datalens_dev_mcp.authoring.recipes import list_recipes

    recipe = list_recipes().get(family, {})
    values = normalize_presentation(recipe.get("visual_contract", {}))
    values["technology"] = recipe.get("technology", "wizard")
    sources = ["generic"]
    technology_source = "generic"
    conflicts: list[dict[str, Any]] = []
    overrides: dict[str, Any] = {}
    if reference:
        values = _deep_merge(values, normalize_presentation(reference))
        overrides = normalize_presentation(reference)
        sources.append("reference")
        if "technology" in reference:
            technology_source = "reference"
    policy = deepcopy(GENERIC_DEFAULTS)
    if family == "selector":
        policy["labels"]["visible"] = False
        policy["hint"]["enabled"] = False
    values = _merge_report(values, normalize_presentation(policy), "policy", conflicts)
    for source, config in (("user", user), ("project", project)):
        if config:
            configured = _config_values(config, family)
            values = _merge_report(values, configured, source, conflicts)
            overrides = _deep_merge(overrides, configured)
            if "technology" in configured:
                technology_source = source
            sources.append(source)
    if explicit:
        configured = normalize_presentation(explicit)
        values = _merge_report(values, configured, "explicit", conflicts)
        overrides = _deep_merge(overrides, configured)
        sources.append("explicit")
        if "technology" in configured:
            technology_source = "explicit"
    if family == "selector":
        if explicit and (explicit.get("labels") or {}).get("visible"):
            raise ValueError("presentation/labels: selector has no metric labels")
        values["labels"]["visible"] = False
    return {
        "ok": True,
        "family": family,
        "values": values,
        "profile_version": 2,
        "overrides": overrides,
        "precedence": ["generic", "reference", "policy", "user", "project", "explicit"],
        "conflicts": conflicts,
        "applied_sources": sources,
        "technology_source": technology_source,
        "config": {
            "user": str(user_path) if user else None,
            "project": str(project_path) if project and project_path else None,
        },
        "allowed_reference_files": [
            *_reference_files(user, user_path.parent),
            *_reference_files(project, project_path.parent if project_path else Path.cwd()),
        ],
    }


def _user_config_path() -> Path:
    base = (
        Path(os.environ["XDG_CONFIG_HOME"]).expanduser()
        if os.environ.get("XDG_CONFIG_HOME")
        else Path.home() / ".config"
    )
    return base / "datalens-dev-mcp/authoring.json"


def _read_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"authoring config must contain an object: {path}")
    forbidden = FORBIDDEN_CONFIG_KEYS.intersection(str(key).lower() for key in value)
    if forbidden:
        raise ValueError("authoring config cannot contain workflow, history, task, orchestrator, or memory state")
    return value


def _config_values(config: Mapping[str, Any], family: str | None) -> dict[str, Any]:
    values = normalize_presentation(config.get("defaults") or {})
    families = config.get("families")
    if family and isinstance(families, Mapping) and isinstance(families.get(family), Mapping):
        values = _deep_merge(values, normalize_presentation(families[family]))
    return values


def _reference_files(config: Mapping[str, Any], base: Path) -> list[str]:
    raw = config.get("reference_files")
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value).expanduser()
        result.append(str((base / path).resolve() if not path.is_absolute() else path.resolve()))
    return result


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def normalize_presentation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the historical title alias at its own precedence layer."""
    if not isinstance(value, Mapping):
        raise TypeError("presentation must be an object")
    result = deepcopy(dict(value))
    alias = result.pop("title", None)
    if alias is not None:
        if not isinstance(alias, Mapping):
            raise ValueError("presentation/title must be an object; object names belong in name")
        canonical = result.get("visible_title", {})
        if not isinstance(canonical, Mapping):
            raise ValueError("presentation/visible_title must be an object")
        for key in set(alias) & set(canonical):
            if alias[key] != canonical[key]:
                raise ValueError(f"presentation/title/{key} conflicts with visible_title/{key}")
        result["visible_title"] = _deep_merge(alias, canonical)
    if "theme" in result:
        result["states_theme"] = _deep_merge(result.get("states_theme", {}), {"theme": result["theme"]})
    if "spacing" in result:
        result["geometry"] = _deep_merge(result.get("geometry", {}), {"spacing": result["spacing"]})
    _validate_presentation(result)
    return result


def _validate_presentation(value: Mapping[str, Any]) -> None:
    # The complete family contract remains extensible only where the consumer
    # accepts business mappings (table columns, semantic legend items, etc.).
    from datalens_dev_mcp.authoring.recipes import _registry

    known = set(_registry()["base_visual_contract"]) | {"theme", "spacing", "technology", "dashboard"}
    for key in set(value) - known:
        raise ValueError(f"presentation/{key}: unsupported visual field")
    shapes = {
        "visible_title": {"owner", "visible", "text"},
        "hint": {"owner", "enabled", "text", "content"},
        "axes_gridlines": {"x_grid", "y_grid", "zero_baseline", "range", "ticks", "reason"},
        "labels": {"visible", "precision", "unit", "sign", "abbreviation", "collision", "position"},
        "dashboard": {"hide_dash_title"},
    }
    registry = _registry()
    for section in ("table", "geometry", "legend", "selector", "kpi", "states_theme", "tooltip", "object_name", "comparison", "heatmap"):
        fields = set(registry["base_visual_contract"].get(section, {}))
        for recipe in registry["recipes"].values():
            fields.update(recipe.get("visual_contract", {}).get(section, {}))
        fields.update({"table": {"totals_additive", "page_size", "size", "freeze_columns"},
                       "kpi": {"accent"}, "object_name": {"value"},
                       "selector": {"title_placement", "show_title", "empty_selection", "options"},
                       "comparison": {"field_guid", "label", "current_period", "previous_period", "cutoff", "periods_overlap"}}.get(section, set()))
        shapes[section] = fields
    for key, allowed in shapes.items():
        if key not in value:
            continue
        if not isinstance(value[key], Mapping):
            raise TypeError(f"presentation/{key}: expected an object")
        for extra in set(value[key]) - allowed:
            raise ValueError(f"presentation/{key}/{extra}: unsupported visual field")
    for key, field in (("visible_title", "visible"), ("hint", "enabled"), ("labels", "visible"),
                       ("axes_gridlines", "x_grid"), ("axes_gridlines", "y_grid"), ("dashboard", "hide_dash_title"),
                       ("tooltip", "hide_null"), ("tooltip", "hide_zero_multi"), ("legend", "hide_empty_series")):
        if field in value.get(key, {}) and type(value[key][field]) is not bool:
            raise ValueError(f"presentation/{key}/{field}: expected a boolean")
    enabled = value.get("comparison", {}).get("enabled")
    if enabled is not None and type(enabled) is not bool:
        raise ValueError("presentation/comparison/enabled: expected boolean or null")
    for key, owners in (("visible_title", {"widget", "chart", "body", "hidden"}), ("hint", {"widget", "body", "custom_hover", "hidden"})):
        if "owner" in value.get(key, {}) and value[key]["owner"] not in owners:
            raise ValueError(f"presentation/{key}/owner: unsupported owner")


def _merge_report(base: Mapping[str, Any], override: Mapping[str, Any], source: str,
                  conflicts: list[dict[str, Any]], path: str = "") -> dict[str, Any]:
    for key, value in override.items():
        previous = base.get(key)
        child = f"{path}/{key}"
        if isinstance(value, Mapping) and isinstance(previous, Mapping):
            _merge_report(previous, value, source, conflicts, child)
        elif key in base and previous != value:
            conflicts.append({"path": child, "source": source, "before": previous, "after": value})
    return _deep_merge(base, override)
