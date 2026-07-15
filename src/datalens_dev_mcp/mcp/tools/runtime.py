from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.methods import compiled_api_version, openapi_lock_summary
from datalens_dev_mcp.config import DataLensConfig, env_flag
from datalens_dev_mcp.local_config import load_local_config
from datalens_dev_mcp.mcp.tool_registry_policy import tool_registry_env_status
from datalens_dev_mcp.knowledge.reference import build_reference_response
from datalens_dev_mcp.runtime_resources import declared_resource_manifest, resource_manifest
from datalens_dev_mcp.validators.advanced_editor_validator import validate_editor_runtime_contract
from datalens_dev_mcp.validators.source_diagnostics import classify_datalens_source_error


def dl_runtime_status(project_root: str = ".", local_config_path: str = "") -> dict[str, Any]:
    initial_env = dict(os.environ)
    cfg = DataLensConfig.from_env()
    yc_binary_path = _yc_binary_path(cfg.yc_binary)
    local_config = _safe_load_local_config(project_root=project_root, local_config_path=local_config_path)
    config_defaults = _config_defaults(local_config)
    refresh_available = bool(cfg.token_refresh_enabled and yc_binary_path)
    credential_report = cfg.credential_report()
    api_lock = openapi_lock_summary()
    declared_resources = _resource_status()
    api_version_status = _api_version_status(cfg)
    tool_registry = tool_registry_env_status(initial_env)
    diagnostics = _runtime_diagnostics(
        cfg=cfg,
        yc_binary_path=yc_binary_path,
        config_defaults=config_defaults,
        refresh_available=refresh_available,
        tool_registry=tool_registry,
        api_version_status=api_version_status,
    )
    return {
        "ok": True,
        "allow_writes": cfg.write_enabled,
        "allow_save": env_flag("DATALENS_MCP_LIVE_ALLOW_SAVE", False),
        "allow_publish": env_flag("DATALENS_MCP_LIVE_ALLOW_PUBLISH", False),
        "expert_rpc_enabled": cfg.expert_rpc_enabled,
        "token_present": bool(cfg.iam_token),
        "token_refresh_on_401": cfg.token_refresh_enabled,
        "yc_binary_configured": bool(os.getenv("DATALENS_YC_BINARY") or yc_binary_path),
        "yc_binary_path": yc_binary_path,
        "org_id_set": bool(cfg.org_id),
        "api_base_url": cfg.base_url,
        "api_version": cfg.api_version,
        "selected_api_version": api_version_status["selected_api_version"],
        "api_version_selection": api_version_status,
        "write_compatible": api_version_status["write_compatible"],
        "write_block_reason": api_version_status["write_block_reason"],
        "openapi_lock": api_lock,
        "runtime_resources": declared_resources,
        "project_root": str(Path(project_root)),
        "local_config_path": local_config_path,
        "runtime_env": {
            "write_flags": {
                "allow_writes": cfg.write_enabled,
                "allow_save": env_flag("DATALENS_MCP_LIVE_ALLOW_SAVE", False),
                "allow_publish": env_flag("DATALENS_MCP_LIVE_ALLOW_PUBLISH", False),
                "expert_rpc_enabled": cfg.expert_rpc_enabled,
            },
            "auth": {
                "token_present": bool(cfg.iam_token),
                "token_source": cfg.credential_source,
                "org_id_set": bool(cfg.org_id),
                "org_id_source": cfg.org_id_source,
                "refresh_on_401": cfg.token_refresh_enabled,
                "refresh_available": refresh_available,
                "env_file": credential_report["env_file"],
            },
            "api": {
                "base_url": cfg.base_url,
                "base_url_source": _first_env_source(("DATALENS_BASE_URL", "DATALENS_API_BASE_URL"), initial_env)
                or "default",
                "api_version": cfg.api_version,
                "selected_api_version": api_version_status["selected_api_version"],
                "compiled_api_version": api_version_status["compiled_api_version"],
                "explicit_version_mismatch": api_version_status["explicit_version_mismatch"],
                "write_compatible": api_version_status["write_compatible"],
                "write_block_reason": api_version_status["write_block_reason"],
                "request_timeout_sec": cfg.request_timeout_sec,
                "openapi_lock_sha256": api_lock["openapi_sha256"],
                "api_version_source": _env_source("DATALENS_API_VERSION", initial_env, default_label="default"),
            },
            "resources": declared_resources,
            "yc": {
                "configured_value_present": bool(os.getenv("DATALENS_YC_BINARY")),
                "configured_source": _env_source("DATALENS_YC_BINARY", initial_env, default_label="default_path"),
                "resolved": bool(yc_binary_path),
                "path": yc_binary_path,
            },
            "env_file": {
                "configured": bool(os.getenv("DATALENS_ENV_FILE")),
                "source": _env_source("DATALENS_ENV_FILE", initial_env, default_label="none"),
            },
            "tool_registry": tool_registry,
        },
        "config_defaults": config_defaults,
        "diagnostics": diagnostics,
        "route_policy": {
            "supported": [
                "wizard_native",
                "editor_advanced",
                "editor_table",
                "editor_markdown",
                "editor_js_control",
                "wizard_map_native (geolayer compatibility alias)",
                "ql_explicit",
            ],
            "ql_behavior": "read_create_update_only_when_explicitly_requested; never automatic",
            "default_publish_policy": (
                "known-target implementation/fix/enhancement delivery may publish after guarded save, "
                "fresh saved readback, and selected evidence-mode gates"
            ),
            "forbidden": [
                "automatic_ql_selection",
                "d3_node",
                "regular_editor_chart",
                "gravity_ui_charts",
                "runtime_route_fallback_after_transport_failure",
                "hidden_delete_move_permission_operations_in_normal_workflows",
                "blind_writes",
                "blind_publish_without_evidence",
            ],
            "explicit_retire_lifecycle": "retire_legacy_objects",
        },
}


def _resource_status() -> dict[str, Any]:
    manifest = declared_resource_manifest()
    current = resource_manifest()
    declared = manifest.get("resources") or []
    return {
        "schema_version": manifest.get("schema_version"),
        "declared_resource_count": len(declared),
        "current_resource_count": len(current),
        "manifest_matches_current": declared == current,
    }


def dl_auth_probe(client: Any | None = None) -> dict[str, Any]:
    cfg = DataLensConfig.from_env()
    active_client = client or DataLensApiClient(cfg)
    refresh_available = _token_refresh_available(cfg, active_client)
    try:
        response = active_client.rpc("getWorkbooksList", {"page": 1, "pageSize": 1})
        return {
            "ok": True,
            "method": "getWorkbooksList",
            "auth_mode": cfg.credential_source,
            "refresh_on_401": cfg.token_refresh_enabled,
            "token_refresh_available": refresh_available,
            "selected_api_version": getattr(active_client, "_selected_api_version", "") or cfg.api_version,
            "api_version_selection_reason": getattr(active_client, "_api_version_selection_reason", ""),
            "openapi_lock": openapi_lock_summary(),
            "credential": cfg.credential_report(),
            "response_keys": sorted(response) if isinstance(response, dict) else [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "method": "getWorkbooksList",
            "auth_mode": cfg.credential_source,
            "refresh_on_401": cfg.token_refresh_enabled,
            "token_refresh_available": refresh_available,
            "selected_api_version": getattr(active_client, "_selected_api_version", "") or cfg.api_version,
            "api_version_selection_reason": getattr(active_client, "_api_version_selection_reason", ""),
            "openapi_lock": openapi_lock_summary(),
            "credential": cfg.credential_report(),
            "error": {"category": "auth_failure", "message": _sanitize_runtime_error(str(exc) or exc.__class__.__name__)},
        }


def dl_validate_editor_runtime_contract(
    entry: dict[str, Any] | None = None,
    sections: dict[str, Any] | None = None,
    source: str = "<memory>",
    allow_unknown_warnings: bool = False,
) -> dict[str, Any]:
    payload = entry if isinstance(entry, dict) and entry else sections or {}
    result = validate_editor_runtime_contract(
        payload,
        source=source,
        allow_unknown_warnings=allow_unknown_warnings,
    )
    references = build_reference_response(
        mode="source_trace",
        query="Editor.wrapFn Editor.generateHtml sanitizer methods",
        limit=4,
        max_chars=4000,
    )
    result["corpus_references"] = references.get("results") or []
    return result


def dl_classify_source_error(error_payload: dict[str, Any]) -> dict[str, Any]:
    return classify_datalens_source_error(error_payload)


def _yc_binary_path(yc_binary: str) -> str:
    configured = str(yc_binary or "").strip()
    if not configured:
        return ""
    if "/" in configured:
        return configured if os.access(configured, os.X_OK) else ""
    return shutil.which(configured) or ""


def _token_refresh_available(cfg: DataLensConfig, client: Any) -> bool:
    if getattr(client, "token_refresher", None) is not None:
        return True
    return bool(cfg.token_refresh_enabled and _yc_binary_path(cfg.yc_binary))


def _api_version_status(cfg: DataLensConfig) -> dict[str, Any]:
    configured = str(cfg.api_version or "auto").strip() or "auto"
    current = compiled_api_version()
    if configured.lower() == "auto":
        return {
            "configured_api_version": "auto",
            "compiled_api_version": current,
            "selected_api_version": current,
            "selection_policy": "auto_pinned_to_compiled_v2_without_implicit_fallback",
            "explicit_version_mismatch": False,
            "write_compatible": True,
            "write_block_reason": "",
        }
    normalized = configured.lower()
    write_compatible = normalized == current.lower()
    if write_compatible:
        selection_policy = "explicit_compiled_version"
        write_block_reason = ""
    elif normalized == "1":
        selection_policy = "explicit_v1_readonly_compatibility"
        write_block_reason = "api_version_mismatch_for_write: explicit_v1_readonly_compatibility_only"
    elif normalized == "latest":
        selection_policy = "explicit_latest_readonly_only"
        write_block_reason = "api_version_mismatch_for_write: unlocked_api_version_for_write"
    else:
        selection_policy = "explicit_uncompiled_readonly_only"
        write_block_reason = "api_version_mismatch_for_write: explicit_version_differs_from_compiled_contract"
    return {
        "configured_api_version": configured,
        "compiled_api_version": current,
        "selected_api_version": configured,
        "selection_policy": selection_policy,
        "explicit_version_mismatch": configured != current,
        "write_compatible": write_compatible,
        "write_block_reason": write_block_reason,
    }


def _auth_mode() -> str:
    if os.getenv("DATALENS_IAM_TOKEN", "").strip():
        return "datalens_iam_token"
    if os.getenv("YC_IAM_TOKEN", "").strip():
        return "yc_iam_token"
    return "none"


def _safe_load_local_config(*, project_root: str, local_config_path: str) -> dict[str, Any]:
    try:
        return load_local_config(local_config_path or None, project_root=project_root)
    except Exception as exc:  # noqa: BLE001
        return {
            "_meta": {
                "config_path": local_config_path,
                "loaded_from_file": False,
                "load_error": _sanitize_runtime_error(str(exc) or exc.__class__.__name__),
            }
        }


def _config_defaults(local_config: dict[str, Any]) -> dict[str, Any]:
    meta = local_config.get("_meta") or {}
    safe_mode = local_config.get("safe_mode") or {}
    approval = local_config.get("approval_gates") or {}
    readback = local_config.get("readback") or {}
    routing = local_config.get("routing") or {}
    return {
        "loaded_from_file": bool(meta.get("loaded_from_file")),
        "config_path": str(meta.get("config_path") or ""),
        "load_error": str(meta.get("load_error") or ""),
        "safe_mode_default": str(safe_mode.get("default") or ""),
        "safe_mode_allow_writes": bool(safe_mode.get("allow_writes", False)),
        "publish_default": bool(approval.get("publish_default", False)),
        "require_safe_apply_plan": bool(safe_mode.get("require_safe_apply_plan", True)),
        "require_fresh_read": bool(safe_mode.get("require_fresh_read", True)),
        "preserve_revision": bool(safe_mode.get("preserve_revision", True)),
        "readback_mode": str(readback.get("mode") or ""),
        "chart_creation_routes": list(routing.get("chart_creation_routes") or []),
        "ql_behavior": str(routing.get("ql_behavior") or ""),
    }


def _runtime_diagnostics(
    *,
    cfg: DataLensConfig,
    yc_binary_path: str,
    config_defaults: dict[str, Any],
    refresh_available: bool,
    tool_registry: dict[str, object],
    api_version_status: dict[str, Any],
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    if config_defaults.get("load_error"):
        diagnostics.append(
            {
                "severity": "error",
                "category": "local_config_load_error",
                "message": "Local MCP config could not be loaded; runtime env is still reported separately.",
                "suggested_action": "Fix the local config JSON or pass a valid local_config_path.",
            }
        )
    if cfg.write_enabled and not config_defaults.get("safe_mode_allow_writes", False):
        diagnostics.append(
            {
                "severity": "info",
                "category": "runtime_env_overrides_plan_only_config",
                "message": "Runtime env allows writes while local config defaults remain plan-only/read-only.",
                "suggested_action": "Treat env flags as the live execution gate; keep using approved safe apply before writes.",
            }
        )
    if api_version_status.get("explicit_version_mismatch"):
        diagnostics.append(
            {
                "severity": "error",
                "category": "explicit_api_version_mismatch",
                "message": (
                    "The configured explicit DataLens API version differs from the version required by the compiled "
                    "OpenAPI contract."
                ),
                "suggested_action": (
                    "Set DATALENS_API_VERSION=auto or "
                    f"DATALENS_API_VERSION={api_version_status['compiled_api_version']}, then restart the MCP server."
                ),
            }
        )
    if tool_registry.get("hidden_tool_calls_enabled"):
        diagnostics.append(
            {
                "severity": "warning",
                "category": "test_only_hidden_tool_calls_enabled",
                "message": "Hidden/internal compatibility tools are callable in this process.",
                "suggested_action": "Use this only in tests; unset hidden-tool env flags for normal Codex runtime.",
            }
        )
    elif tool_registry.get("hidden_tool_calls_env_ignored"):
        diagnostics.append(
            {
                "severity": "warning",
                "category": "hidden_tool_calls_env_ignored",
                "message": "A hidden-tool env flag is present but ignored because the test-only registry marker is absent.",
                "suggested_action": "Remove the hidden-tool env flag from normal runtime configuration.",
            }
        )
    if tool_registry.get("test_only_registry_enabled") and not tool_registry.get("hidden_tool_calls_enabled"):
        diagnostics.append(
            {
                "severity": "warning",
                "category": "test_only_registry_marker_enabled",
                "message": "The test-only registry marker is present in this process.",
                "suggested_action": "Unset the marker for normal Codex runtime.",
            }
        )
    if tool_registry.get("internal_profile_env_vars_present"):
        diagnostics.append(
            {
                "severity": "warning",
                "category": "internal_tool_profile_env_ignored",
                "message": "Legacy tool profile env vars are present; normal runtime still uses the standard surface.",
                "suggested_action": "Remove profile env vars from user-facing runtime configuration.",
            }
        )
    if cfg.token_refresh_enabled and not refresh_available:
        diagnostics.append(
            {
                "severity": "warning",
                "category": "token_refresh_unavailable",
                "message": "Refresh-on-401 is enabled but no executable yc binary is resolved.",
                "suggested_action": "Set DATALENS_YC_BINARY to an executable yc path or add yc to PATH.",
            }
        )
    if not cfg.iam_token and not refresh_available:
        diagnostics.append(
            {
                "severity": "error",
                "category": "missing_auth",
                "message": "No IAM token is present and token refresh is unavailable.",
                "suggested_action": "Launch through scripts/codex_mcp_launch.sh or set local auth env outside reports.",
            }
        )
    diagnostics.append(
        {
            "severity": "info",
            "category": "standalone_script_env_mismatch",
            "message": (
                "If MCP auth succeeds but a standalone project script fails, the likely cause is a different shell/env "
                "or yc resolution path, not a DataLens object-state issue."
            ),
            "suggested_action": (
                "Prefer the MCP live transport or rerun the script with launcher-resolved env names and yc path; "
                "do not print or copy credential values into reports."
            ),
        }
    )
    return diagnostics


def _env_source(name: str, initial_env: dict[str, str], *, default_label: str = "unset") -> str:
    if initial_env.get(name, "").strip():
        return "process_env"
    if os.getenv(name, "").strip():
        return "env_file"
    return default_label


def _first_env_source(names: tuple[str, ...], initial_env: dict[str, str]) -> str:
    for name in names:
        source = _env_source(name, initial_env)
        if source != "unset":
            return source
    return ""


def _sanitize_runtime_error(message: str) -> str:
    sanitized = message
    for key in ("DATALENS_IAM_TOKEN", "YC_IAM_TOKEN", "Authorization", "x-yacloud-subjecttoken"):
        sanitized = sanitized.replace(key, "<redacted-key>")
    for value in (os.getenv("DATALENS_IAM_TOKEN", ""), os.getenv("YC_IAM_TOKEN", "")):
        if value:
            sanitized = sanitized.replace(value, "<redacted>")
    sanitized = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=\-]+", "Bearer <redacted>", sanitized)
    return sanitized[:1000]
