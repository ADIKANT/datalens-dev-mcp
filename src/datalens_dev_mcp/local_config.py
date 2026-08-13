from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_LOCAL_CONFIG: dict[str, Any] = {
    "schema_id": "datalens_mcp_local_config",
    "defaults": {
        "workbook_id": "<WORKBOOK_ID>",
        "project_id": "<PROJECT_ID>",
        "dashboard_id": "<DASHBOARD_ID>",
        "project_workspace_path": ".",
    },
    "execution": {
        "default": "follow_user_request",
        "writes": True,
        "save": True,
        "publish": True,
        "delete_requires_confirmation": True,
    },
    "safe_apply": {
        "require_safe_apply_plan": True,
        "require_fresh_read": True,
        "preserve_revision": True,
        "require_save_mode_first": True,
        "require_readback_after_save": True,
    },
    "readback": {
        "mode": "minimal",
        "justification": (
            "Minimal saved readback is enough for local plan verification unless "
            "a live publish or debug task explicitly requires full/debug."
        ),
    },
    "validation": {
        "strictness": "strict",
        "fail_on_secret_scan": True,
        "require_route_validation": True,
        "require_template_validation": True,
        "require_relation_validation": True,
    },
    "live_testing": {
        "run_live_tests_by_default": False,
        "require_env_flag": "DATALENS_MCP_RUN_LIVE_TESTS=1",
        "require_disposable_targets": True,
        "allow_publish_checks": False,
    },
    "api_defaults": {
        "request_interval_sec": 1.05,
        "rate_limit_retries": 6,
        "request_timeout_sec": 30,
        "max_read_concurrency": 3,
        "read_transient_retries": 2,
    },
    "routing": {
        "chart_creation_routes": ["wizard_native", "advanced_editor_js", "ql_explicit"],
        "advanced_editor_js_routes": ["editor_advanced", "editor_table", "editor_markdown", "editor_js_control"],
        "wizard_native": {
            "enabled": True,
            "visualization_registry": "templates/datalens/wizard/wizard_template_registry.json",
            "seed_policy": "fresh_saved_same_visualization_then_committed_canonical",
            "geolayer_requires_geo_evidence": True,
        },
        "wizard_map_native_alias": {"enabled": True, "visualization_id": "geolayer"},
        "ql_behavior": "explicit_user_request_only",
        "forbidden_routes": [
            "d3_node",
            "regular_editor_chart",
            "gravity_ui_charts",
            "automatic_ql_selection",
            "runtime_route_fallback",
        ],
    },
    "style": {
        "style_guide_path": "config/datalens_style_guide.json",
        "chart_design_rules_path": "config/datalens_chart_design_rules.json",
        "theme_tokens_path": "templates/advanced/style-tokens.js",
        "theme_tokens": {
            "text_primary": "var(--g-color-text-primary)",
            "text_secondary": "var(--g-color-text-secondary)",
            "background": "var(--g-color-base-background)",
            "border": "var(--g-color-line-generic)",
            "accent": "var(--g-color-base-brand)",
        },
    },
    "naming": {
        "title_source": "role_based_contract",
        "hint_source": "role_based_contract",
        "duplicate_titles_inside_chart_body": False,
        "default_title_prefix": "js - ",
        "require_hint_when_enableHint": True,
    },
    "selectors": {
        "label_placement": "left",
        "width_mode": "percentage",
        "row_width_percent": 94,
        "default_selector_width_percent": 24,
        "min_selector_width_percent": 16,
        "max_selector_width_percent": 48,
        "target_binding_required": True,
    },
}

LOCAL_CONFIG_SCHEMA_ID = "datalens_mcp_local_config"
ALLOWED_EXECUTION_MODES = {"follow_user_request"}
ALLOWED_READBACK_MODES = {"none", "minimal", "full", "debug"}
ALLOWED_VALIDATION_STRICTNESS = {"permissive", "normal", "strict"}
ALLOWED_CHART_CREATION_ROUTES = {"wizard_native", "advanced_editor_js", "ql_explicit"}
TOP_LEVEL_KEYS = set(DEFAULT_LOCAL_CONFIG)


def load_local_config(config_path: str | Path | None = None, *, project_root: str | Path = ".") -> dict[str, Any]:
    path = _resolve_config_path(config_path, project_root=project_root)
    data: dict[str, Any] = {}
    project_manifest: dict[str, Any] = {}
    if path and path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if is_project_live_manifest_payload(data):
            project_manifest = data
            data = {}
    config = _deep_merge(DEFAULT_LOCAL_CONFIG, data)
    validate_local_config(config)
    requested_project_profile = project_manifest.get("authoring_profile") if project_manifest else ""
    normalized_project_profile = requested_project_profile
    if requested_project_profile:
        from datalens_dev_mcp.editor.authoring_profiles import resolve_authoring_profile

        resolved_profile = resolve_authoring_profile(
            project_root=project_root,
            requested_profile=requested_project_profile,
        )
        if resolved_profile.get("ok") and resolved_profile.get("active"):
            normalized_project_profile = {"id": str(resolved_profile.get("id") or "")}
    config["_meta"] = {
        "config_path": str(path) if path else "",
        "loaded_from_file": bool(path and path.is_file() and not project_manifest),
        "project_manifest_detected": bool(project_manifest),
        "project_manifest_path": str(path) if project_manifest and path else "",
        "project_authoring_profile": normalized_project_profile,
        "project_authoring_profile_requested": requested_project_profile,
    }
    return config


def is_project_live_manifest_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    workflows = value.get("workflows")
    project_named = bool(str(value.get("project_name") or value.get("name") or "").strip())
    target_declared = bool(
        str(value.get("workbook_id") or "").strip()
        or value.get("dashboard_ids")
        or isinstance(value.get("target"), dict)
    )
    return bool(isinstance(workflows, list) and workflows and project_named and target_declared)


def validate_local_config(config: dict[str, Any]) -> None:
    unknown_top_level = sorted(set(config) - TOP_LEVEL_KEYS - {"_meta"})
    if unknown_top_level:
        raise ValueError(f"unknown local config sections: {unknown_top_level}")

    if config.get("schema_id") != LOCAL_CONFIG_SCHEMA_ID:
        raise ValueError(f"schema_id must be {LOCAL_CONFIG_SCHEMA_ID}")

    execution = config.get("execution") or {}
    execution_mode = execution.get("default")
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        raise ValueError(f"execution.default must be one of {sorted(ALLOWED_EXECUTION_MODES)}")
    for key in ("writes", "save", "publish", "delete_requires_confirmation"):
        if execution.get(key) is not True:
            raise ValueError(f"execution.{key} must be true; use an explicit env value 0 as the runtime off switch")

    readback_mode = (config.get("readback") or {}).get("mode")
    if readback_mode not in ALLOWED_READBACK_MODES:
        raise ValueError(f"readback.mode must be one of {sorted(ALLOWED_READBACK_MODES)}")
    if readback_mode == "none" and not str((config.get("readback") or {}).get("justification") or "").strip():
        raise ValueError("readback.justification is required when readback.mode is none")

    strictness = (config.get("validation") or {}).get("strictness")
    if strictness not in ALLOWED_VALIDATION_STRICTNESS:
        raise ValueError(f"validation.strictness must be one of {sorted(ALLOWED_VALIDATION_STRICTNESS)}")

    routes = set((config.get("routing") or {}).get("chart_creation_routes") or [])
    if not routes or not routes <= ALLOWED_CHART_CREATION_ROUTES:
        raise ValueError("routing.chart_creation_routes must contain only wizard_native, advanced_editor_js, and ql_explicit")

    if (config.get("routing") or {}).get("ql_behavior") != "explicit_user_request_only":
        raise ValueError("routing.ql_behavior must be explicit_user_request_only")

    safe_apply = config.get("safe_apply") or {}
    for key in (
        "require_safe_apply_plan",
        "require_fresh_read",
        "preserve_revision",
        "require_save_mode_first",
        "require_readback_after_save",
    ):
        if safe_apply.get(key) is not True:
            raise ValueError(f"safe_apply.{key} must be true")

    live_testing = config.get("live_testing") or {}
    if live_testing.get("run_live_tests_by_default") is not False:
        raise ValueError("live_testing.run_live_tests_by_default must be false")
    if live_testing.get("allow_publish_checks") is not False:
        raise ValueError("live_testing.allow_publish_checks must be false")

    api_defaults = config.get("api_defaults") or {}
    if float(api_defaults.get("request_interval_sec", 0)) < 0:
        raise ValueError("api_defaults.request_interval_sec must be non-negative")
    if int(api_defaults.get("rate_limit_retries", 0)) < 0:
        raise ValueError("api_defaults.rate_limit_retries must be non-negative")
    if float(api_defaults.get("request_timeout_sec", 0)) <= 0:
        raise ValueError("api_defaults.request_timeout_sec must be positive")
    if not 1 <= int(api_defaults.get("max_read_concurrency", 0)) <= 3:
        raise ValueError("api_defaults.max_read_concurrency must be between 1 and 3")
    if not 0 <= int(api_defaults.get("read_transient_retries", 0)) <= 2:
        raise ValueError("api_defaults.read_transient_retries must be between 0 and 2")

    selectors = config.get("selectors") or {}
    if selectors.get("label_placement") != "left":
        raise ValueError("selectors.label_placement must be left")
    if selectors.get("width_mode") != "percentage":
        raise ValueError("selectors.width_mode must be percentage")
    if int(selectors.get("row_width_percent", 0)) != 94:
        raise ValueError("selectors.row_width_percent must be 94")
    default_width = int(selectors.get("default_selector_width_percent", 0))
    min_width = int(selectors.get("min_selector_width_percent", 0))
    max_width = int(selectors.get("max_selector_width_percent", 0))
    if not 1 <= min_width <= default_width <= max_width <= 94:
        raise ValueError("selector width defaults must satisfy 1 <= min <= default <= max <= 94")


def apply_tool_defaults(
    tool_name: str,
    arguments: dict[str, Any],
    config: dict[str, Any],
    *,
    project_root: str,
    supports_project_root: bool,
    supports_workbook_id: bool,
    supports_readback_mode: bool,
) -> dict[str, Any]:
    resolved = dict(arguments)
    defaults = config.get("defaults") or {}

    if supports_project_root and not resolved.get("project_root"):
        workspace = str(defaults.get("project_workspace_path") or "").strip()
        server_root = Path(project_root).expanduser().resolve()
        if workspace and not _is_placeholder(workspace):
            workspace_path = Path(workspace).expanduser()
            if not workspace_path.is_absolute():
                workspace_path = server_root / workspace_path
            resolved["project_root"] = str(workspace_path.resolve())
        else:
            resolved["project_root"] = str(server_root)

    workbook_id = str(defaults.get("workbook_id") or "").strip()
    if (
        supports_workbook_id
        and not resolved.get("workbook_id")
        and not resolved.get("workbook_ids")
        and workbook_id
        and not _is_placeholder(workbook_id)
    ):
        resolved["workbook_id"] = workbook_id

    if supports_readback_mode and not resolved.get("readback_mode"):
        resolved["readback_mode"] = (config.get("readback") or {}).get("mode", "minimal")

    if tool_name == "dl_publish_object_plan":
        resolved.setdefault("mode", "publish")
    return resolved


def _resolve_config_path(config_path: str | Path | None, *, project_root: str | Path) -> Path | None:
    raw = str(config_path or os.getenv("DATALENS_MCP_LOCAL_CONFIG") or "").strip()
    if raw:
        return Path(raw).expanduser()
    candidate = Path(project_root) / "config" / "datalens_mcp.local.json"
    return candidate if candidate.is_file() else None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _is_placeholder(value: str) -> bool:
    return value.startswith("<") and value.endswith(">")


def sanitize_local_config(config: dict[str, Any]) -> dict[str, Any]:
    return _redact_sensitive(copy.deepcopy(config))


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("token", "secret", "password", "authorization")):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value
