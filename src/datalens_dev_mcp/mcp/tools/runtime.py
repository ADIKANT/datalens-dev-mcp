from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.auth import classify_auth_probe_failure
from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.methods import compiled_api_version, openapi_lock_summary
from datalens_dev_mcp.api.scheduler import record_cache_hit, scheduler_status
from datalens_dev_mcp.config import DataLensConfig, use_api_defaults
from datalens_dev_mcp.local_config import load_local_config
from datalens_dev_mcp.knowledge.reference import build_reference_response
from datalens_dev_mcp.mcp.response_projection import serialized_metadata, stable_json_text
from datalens_dev_mcp.pipeline.artifacts import ensure_project_dirs, write_json
from datalens_dev_mcp.runtime_resources import (
    RESOURCE_OVERRIDE_ENV,
    declared_resource_manifest,
    resource_manifest,
)
from datalens_dev_mcp.validators.advanced_editor_validator import (
    _EDITOR_VALIDATION_CACHE,
    validate_editor_runtime_contract,
)
from datalens_dev_mcp.validators.source_diagnostics import classify_datalens_source_error


EDITOR_ARTIFACT_MAX_COUNT = 100
EDITOR_ARTIFACT_MAX_BYTES = 2 * 1024 * 1024
EDITOR_ARTIFACT_TOTAL_MAX_BYTES = 10 * 1024 * 1024
EDITOR_TAB_FILE_NAMES = (
    "meta.json",
    "params.js",
    "sources.js",
    "prepare.js",
    "controls.js",
    "config.js",
)


def dl_runtime_status(project_root: str = ".", local_config_path: str = "") -> dict[str, Any]:
    initial_env = dict(os.environ)
    local_config = _safe_load_local_config(project_root=project_root, local_config_path=local_config_path)
    with use_api_defaults(local_config.get("api_defaults") or {}):
        cfg = DataLensConfig.from_env()
    yc_binary_path = _yc_binary_path(cfg.yc_binary)
    config_defaults = _config_defaults(local_config)
    local_meta = local_config.get("_meta") if isinstance(local_config.get("_meta"), dict) else {}
    refresh_available = bool(cfg.token_refresh_enabled and yc_binary_path)
    credential_report = cfg.credential_report()
    api_lock = openapi_lock_summary()
    declared_resources = _resource_status()
    api_version_status = _api_version_status(cfg)
    request_scheduler = scheduler_status()
    diagnostics = _runtime_diagnostics(
        cfg=cfg,
        yc_binary_path=yc_binary_path,
        config_defaults=config_defaults,
        refresh_available=refresh_available,
        api_version_status=api_version_status,
    )
    return {
        "ok": True,
        "allow_writes": cfg.write_enabled,
        "allow_save": cfg.save_enabled,
        "allow_publish": cfg.publish_enabled,
        "delete_requires_confirmation": cfg.delete_requires_confirmation,
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
        "request_scheduler": request_scheduler,
        "project_root": str(Path(project_root)),
        "local_config_path": local_config_path,
        "project_manifest": {
            "detected": bool(local_meta.get("project_manifest_detected")),
            "path": str(local_meta.get("project_manifest_path") or ""),
            "authoring_profile": local_meta.get("project_authoring_profile") or "",
            "used_as_runtime_config": False,
        },
        "runtime_env": {
            "write_flags": {
                "allow_writes": cfg.write_enabled,
                "allow_save": cfg.save_enabled,
                "allow_publish": cfg.publish_enabled,
                "delete_requires_confirmation": cfg.delete_requires_confirmation,
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
                "request_interval_sec": cfg.request_interval_sec,
                "max_read_concurrency": cfg.max_read_concurrency,
                "read_transient_retries": cfg.read_transient_retries,
                "rate_limit_retries": cfg.rate_limit_retries,
                "scheduler_scope": request_scheduler["scope"],
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
                "whole_object_delete_requires_confirmation",
                "move_permission_credential_mutations_unsupported",
                "blind_writes",
                "blind_publish_without_evidence",
            ],
            "whole_object_delete_confirmation": "confirm_delete",
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
    try:
        response = active_client.rpc("getWorkbooksList", {"page": 1, "pageSize": 1})
        effective_cfg = getattr(active_client, "config", cfg)
        return {
            "ok": True,
            "method": "getWorkbooksList",
            "auth_mode": effective_cfg.credential_source,
            "refresh_on_401": effective_cfg.token_refresh_enabled,
            "token_refresh_available": _token_refresh_available(effective_cfg, active_client),
            "initial_token_bootstrapped": bool(not cfg.iam_token and effective_cfg.iam_token),
            "selected_api_version": getattr(active_client, "_selected_api_version", "") or effective_cfg.api_version,
            "api_version_selection_reason": getattr(active_client, "_api_version_selection_reason", ""),
            "openapi_lock": openapi_lock_summary(),
            "credential": effective_cfg.credential_report(),
            "response_keys": sorted(response) if isinstance(response, dict) else [],
        }
    except Exception as exc:  # noqa: BLE001
        effective_cfg = getattr(active_client, "config", cfg)
        classified = classify_auth_probe_failure(exc)
        return {
            "ok": False,
            "method": "getWorkbooksList",
            "auth_mode": effective_cfg.credential_source,
            "refresh_on_401": effective_cfg.token_refresh_enabled,
            "token_refresh_available": _token_refresh_available(effective_cfg, active_client),
            "initial_token_bootstrapped": False,
            "selected_api_version": getattr(active_client, "_selected_api_version", "") or effective_cfg.api_version,
            "api_version_selection_reason": getattr(active_client, "_api_version_selection_reason", ""),
            "openapi_lock": openapi_lock_summary(),
            "credential": effective_cfg.credential_report(),
            "error": {
                **classified,
                "message": _sanitize_runtime_error(str(exc) or exc.__class__.__name__),
            },
        }


def dl_validate_editor_runtime_contract(
    entry: dict[str, Any] | None = None,
    sections: dict[str, Any] | None = None,
    source: str = "<memory>",
    allow_unknown_warnings: bool = False,
    project_root: str = ".",
    artifact_paths: list[str] | None = None,
    include_references: bool = False,
) -> dict[str, Any]:
    paths = list(artifact_paths or [])
    if paths:
        if entry or sections:
            raise ValueError("artifact_paths is mutually exclusive with entry and sections")
        return _validate_editor_artifacts(
            project_root=project_root,
            artifact_paths=paths,
            allow_unknown_warnings=allow_unknown_warnings,
            include_references=include_references,
        )
    payload = entry if isinstance(entry, dict) and entry else sections if isinstance(sections, dict) else None
    if payload is None:
        raise ValueError("one of entry, sections, or artifact_paths is required")
    result = _cached_editor_validation(
        payload,
        source=source,
        allow_unknown_warnings=allow_unknown_warnings,
    )
    result.update(_editor_reference_payload(include_references=include_references))
    return result


def _cached_editor_validation(
    payload: dict[str, Any],
    *,
    source: str,
    allow_unknown_warnings: bool,
) -> dict[str, Any]:
    return validate_editor_runtime_contract(
        payload,
        source=source,
        allow_unknown_warnings=allow_unknown_warnings,
    )


def _validate_editor_artifacts(
    *,
    project_root: str,
    artifact_paths: list[str],
    allow_unknown_warnings: bool,
    include_references: bool,
) -> dict[str, Any]:
    if not artifact_paths or len(artifact_paths) > EDITOR_ARTIFACT_MAX_COUNT:
        raise ValueError(
            f"artifact_paths must contain between 1 and {EDITOR_ARTIFACT_MAX_COUNT} JSON, JS, or widget-directory paths"
        )
    root = Path(project_root).expanduser().resolve()
    resolved: list[tuple[str, Path, str]] = []
    total_bytes = 0
    for raw_path in artifact_paths:
        candidate = Path(str(raw_path or "")).expanduser()
        candidate = candidate if candidate.is_absolute() else root / candidate
        try:
            path = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"Editor artifact does not exist: {raw_path}") from exc
        if not path.is_relative_to(root):
            raise ValueError(f"Editor artifact path escapes project_root: {raw_path}")
        if path.is_dir():
            tab_paths = [path / name for name in EDITOR_TAB_FILE_NAMES if (path / name).is_file()]
            if not tab_paths:
                raise ValueError(f"Editor widget directory contains no recognized tab files: {raw_path}")
            for tab_path in tab_paths:
                byte_count = tab_path.stat().st_size
                if byte_count > EDITOR_ARTIFACT_MAX_BYTES:
                    raise ValueError(f"Editor tab exceeds {EDITOR_ARTIFACT_MAX_BYTES} bytes: {tab_path}")
                total_bytes += byte_count
            kind = "widget_directory"
        elif path.is_file() and path.suffix.lower() in {".json", ".js"}:
            byte_count = path.stat().st_size
            if byte_count > EDITOR_ARTIFACT_MAX_BYTES:
                raise ValueError(f"Editor artifact exceeds {EDITOR_ARTIFACT_MAX_BYTES} bytes: {raw_path}")
            total_bytes += byte_count
            kind = "json" if path.suffix.lower() == ".json" else "javascript"
        else:
            raise ValueError(f"Editor artifact must be JSON, JavaScript, or a widget directory: {raw_path}")
        if total_bytes > EDITOR_ARTIFACT_TOTAL_MAX_BYTES:
            raise ValueError(f"Editor artifacts exceed {EDITOR_ARTIFACT_TOTAL_MAX_BYTES} total bytes")
        resolved.append((path.relative_to(root).as_posix(), path, kind))

    full_items: list[dict[str, Any]] = []
    compact_items: list[dict[str, Any]] = []
    aggregate_findings: list[dict[str, Any]] = []
    for relative, path, kind in resolved:
        payload = _load_editor_artifact_payload(path=path, relative=relative, kind=kind)
        result = _cached_editor_validation(
            payload,
            source=relative,
            allow_unknown_warnings=allow_unknown_warnings,
        )
        full_items.append({"path": relative, "result": result})
        compact_items.append(
            {
                "path": relative,
                "ok": result["ok"],
                "payload_sha256": result["payload_sha256"],
                "summary": result["summary"],
                "validation_cache": result["validation_cache"],
            }
        )
        aggregate_findings.extend(
            {"artifact_path": relative, **finding}
            for finding in result.get("findings") or []
            if isinstance(finding, dict)
        )
    summary = {
        "artifacts": len(full_items),
        "passed": sum(1 for item in full_items if item["result"]["ok"]),
        "failed": sum(1 for item in full_items if not item["result"]["ok"]),
        "findings": len(aggregate_findings),
        "errors": sum(1 for finding in aggregate_findings if finding.get("severity") == "error"),
        "warnings": sum(1 for finding in aggregate_findings if finding.get("severity") == "warning"),
        "input_bytes": total_bytes,
    }
    full_result = {
        "schema_version": "2026-07-20.editor_runtime_contract.batch.v1",
        "ok": summary["failed"] == 0,
        "summary": summary,
        "items": full_items,
        "findings": aggregate_findings,
        **_editor_reference_payload(include_references=include_references),
    }
    full_metadata = serialized_metadata(full_result)
    artifact_path = (
        ensure_project_dirs(root)
        / "artifacts"
        / "validation"
        / f"editor_runtime_batch.{full_metadata['sha256'][:12]}.json"
    )
    write_json(artifact_path, full_result)
    return {
        "ok": full_result["ok"],
        "schema_version": full_result["schema_version"],
        "mode": "artifact_paths",
        "summary": summary,
        "items": compact_items,
        "findings_preview": aggregate_findings[:50],
        "findings_truncated": len(aggregate_findings) > 50,
        "artifact": {
            "path": str(artifact_path),
            **full_metadata,
        },
        **_editor_reference_payload(include_references=include_references),
    }


def _load_editor_artifact_payload(*, path: Path, relative: str, kind: str) -> dict[str, Any]:
    try:
        if kind == "widget_directory":
            sections = {
                name: (path / name).read_text(encoding="utf-8")
                for name in EDITOR_TAB_FILE_NAMES
                if (path / name).is_file()
            }
            return {"sections": sections}
        text = path.read_text(encoding="utf-8")
        if kind == "javascript":
            return {"sections": {path.name: text}}
        payload = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        label = "UTF-8 JSON" if kind == "json" else "UTF-8 Editor tabs"
        raise ValueError(f"Editor artifact is not valid {label}: {relative}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Editor artifact root must be a JSON object: {relative}")
    return payload


def _editor_reference_payload(*, include_references: bool) -> dict[str, Any]:
    references = _editor_reference_rows()
    reference_set_id = hashlib.sha256(stable_json_text(references).encode("utf-8")).hexdigest()
    payload: dict[str, Any] = {
        "corpus_reference_set": {
            "id": reference_set_id,
            "count": len(references),
            "source_urls": list(
                dict.fromkeys(str(item.get("source_url") or "") for item in references if item.get("source_url"))
            ),
        }
    }
    if include_references:
        payload["corpus_references"] = references
    return payload


def _editor_reference_rows() -> list[dict[str, Any]]:
    if os.getenv(RESOURCE_OVERRIDE_ENV, "").strip():
        return _build_editor_reference_rows()
    hits_before = _packaged_editor_reference_rows.cache_info().hits
    rows = _packaged_editor_reference_rows()
    if _packaged_editor_reference_rows.cache_info().hits > hits_before:
        record_cache_hit("editor_source_trace")
    return [deepcopy(item) for item in rows]


@lru_cache(maxsize=1)
def _packaged_editor_reference_rows() -> tuple[dict[str, Any], ...]:
    return tuple(_build_editor_reference_rows())


def _build_editor_reference_rows() -> list[dict[str, Any]]:
    references = build_reference_response(
        mode="source_trace",
        query="Editor.wrapFn Editor.generateHtml sanitizer methods",
        limit=4,
        max_chars=4000,
    )
    return [item for item in references.get("results") or [] if isinstance(item, dict)]


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
    execution = local_config.get("execution") or {}
    safe_apply = local_config.get("safe_apply") or {}
    readback = local_config.get("readback") or {}
    routing = local_config.get("routing") or {}
    api_defaults = local_config.get("api_defaults") or {}
    return {
        "loaded_from_file": bool(meta.get("loaded_from_file")),
        "config_path": str(meta.get("config_path") or ""),
        "project_manifest_detected": bool(meta.get("project_manifest_detected")),
        "project_manifest_path": str(meta.get("project_manifest_path") or ""),
        "project_authoring_profile": meta.get("project_authoring_profile") or "",
        "load_error": str(meta.get("load_error") or ""),
        "execution_default": str(execution.get("default") or ""),
        "writes_default": bool(execution.get("writes", True)),
        "save_default": bool(execution.get("save", True)),
        "publish_default": bool(execution.get("publish", True)),
        "delete_requires_confirmation": bool(execution.get("delete_requires_confirmation", True)),
        "require_safe_apply_plan": bool(safe_apply.get("require_safe_apply_plan", True)),
        "require_fresh_read": bool(safe_apply.get("require_fresh_read", True)),
        "preserve_revision": bool(safe_apply.get("preserve_revision", True)),
        "readback_mode": str(readback.get("mode") or ""),
        "chart_creation_routes": list(routing.get("chart_creation_routes") or []),
        "ql_behavior": str(routing.get("ql_behavior") or ""),
        "api_defaults": {
            "request_interval_sec": float(api_defaults.get("request_interval_sec", 1.05)),
            "request_timeout_sec": float(api_defaults.get("request_timeout_sec", 30)),
            "rate_limit_retries": int(api_defaults.get("rate_limit_retries", 6)),
            "max_read_concurrency": int(api_defaults.get("max_read_concurrency", 3)),
            "read_transient_retries": int(api_defaults.get("read_transient_retries", 2)),
        },
    }


def _runtime_diagnostics(
    *,
    cfg: DataLensConfig,
    yc_binary_path: str,
    config_defaults: dict[str, Any],
    refresh_available: bool,
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
    if not (cfg.write_enabled and cfg.save_enabled and cfg.publish_enabled):
        diagnostics.append(
            {
                "severity": "info",
                "category": "runtime_write_switch_disabled",
                "message": "At least one write, save, or publish switch is disabled for this process.",
                "suggested_action": (
                    "Keep the switch disabled for read-only work, or set it to 1 in the canonical env file."
                ),
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
