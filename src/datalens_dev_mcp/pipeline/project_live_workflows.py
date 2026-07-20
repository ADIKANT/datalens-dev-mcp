from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.project_adapters import (
    MIGRATION_SUMMARY_REQUIRED_FIELDS,
    REQUIRED_MIGRATION_MANIFEST_FIELDS,
    detect_project_adapter,
)
from datalens_dev_mcp.validators.dashboard_payload import validate_dashboard_payload
from datalens_dev_mcp.validators.editor_sql_lint import lint_editor_sql_file
from datalens_dev_mcp.validators.redaction import (
    is_sensitive_key,
    looks_like_secret_value,
    redact_text,
    secret_values_from_mapping,
)

MANIFEST_NAMES = (".datalens-mcp.json", "datalens-mcp.project.json", ".datalens-mcp.yaml", ".datalens-mcp.yml")
SCRIPT_PATTERNS = (
    "scripts/*datalens*.py",
    "scripts/*dashboard*.py",
    "scripts/*publish*.py",
    "scripts/*apply*.py",
    "scripts/*update*.py",
)
BLOCKED_COMMAND_TERMS = {
    "cat",
    "env",
    "printenv",
    "set",
    "export",
    "curl",
    "wget",
    "rm",
    "mv",
}
SHELL_META_RE = re.compile(r"[;&|`$<>]")
RETIRE_ACTION = "retire_legacy_objects"
NORMAL_PROJECT_LIVE_ACTIONS = {"validate", "dry_run", "apply", "publish", "readback"}
PROJECT_LIVE_ACTIONS = {*NORMAL_PROJECT_LIVE_ACTIONS, RETIRE_ACTION}
RETIRE_LIFECYCLE_STATES = (
    "requested",
    "dry_run_planned",
    "relation_checked",
    "approved",
    "executed",
    "readback_verified",
    "failed_or_rolled_back_not_available",
)
RETIRE_REQUIRED_EVIDENCE_CHECKS = (
    "relation_graph_proof",
    "saved_no_reference_proof",
    "published_no_reference_proof",
    "dry_run_retire_plan",
    "approval_provenance",
    "execution_summary",
    "post_retire_readback",
)
RETIRE_REQUIRED_PATH_FIELDS = {
    "relation_graph_proof": ("relation_graph_proof_path", "relation_graph_proof_paths", "relation_proof_path"),
    "saved_no_reference_proof": (
        "saved_no_reference_proof_path",
        "saved_no_reference_proof_paths",
        "saved_no_reference_paths",
    ),
    "published_no_reference_proof": (
        "published_no_reference_proof_path",
        "published_no_reference_proof_paths",
        "published_no_reference_paths",
    ),
    "dry_run_retire_plan": ("dry_run_retire_plan_path", "dry_run_retire_plan_paths", "retire_plan_path"),
    "approval_provenance": ("approval_provenance_path", "approval_provenance_paths", "approval_path"),
    "execution_summary": ("execution_summary_path", "execution_summary_paths", "summary_path", "summary_json_path"),
    "post_retire_readback": ("post_retire_readback_path", "post_retire_readback_paths", "post_delete_readback_path"),
}
DESTRUCTIVE_CONSTRAINT_KEYS = {
    "allow_delete",
    "allow_deletes",
    "allow_destructive_operations",
    "allow_move",
    "allow_moves",
    "allow_permission_mutations",
    "delete_legacy",
    "delete_move_permission_operations",
    "delete_move_permissions_allowed",
    "destructive_operations",
    "move_operations",
    "permission_mutations",
}
PERMISSION_MUTATION_TOKENS = {
    "addpermission",
    "deletepermission",
    "deleteworkbookpermission",
    "grant",
    "grantpermission",
    "setaccessbindings",
    "setiampolicy",
    "updateaccessbindings",
    "updatepermission",
    "updatepermissions",
    "updateworkbookpermission",
    "revoke",
    "revokepermission",
}
MOVE_OPERATION_TOKENS = {
    "move",
    "moveentry",
    "moveworkbookentry",
    "relocate",
    "relocateentry",
}
REQUIRED_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,95}$")
SUSPICIOUS_REQUIRED_ENV_NAME_RE = re.compile(
    r"(?:^|_)(?:TOKEN|AUTH|PASSWORD|PASS|SECRET|COOKIE|SESSION|CREDENTIAL|PRIVATE|"
    r"API_KEY|APIKEY|ACCESS_KEY|KEY|IAM|DSN|CONNECTION_STRING)(?:$|_)",
    re.IGNORECASE,
)
BASE_PROJECT_ENV_NAMES = ("PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LANGUAGE")
BASE_PROJECT_ENV_PREFIXES = ("LC_",)
RESERVED_PARENT_ENV_PREFIXES = (
    "ANTHROPIC_",
    "AWS_",
    "AZURE_",
    "CODEX_",
    "GITHUB_",
    "GITLAB_",
    "GOOGLE_",
    "OPENAI_",
    "YC_",
    "YDB_",
)
INJECTED_DATALENS_ENV_NAMES = (
    "DATALENS_API_BASE_URL",
    "DATALENS_API_VERSION",
    "DATALENS_IAM_TOKEN",
    "DATALENS_ORG_ID",
    "DATALENS_YC_BINARY",
    "YC_IAM_TOKEN",
)
SENSITIVE_ENV_ALLOWLIST_KEYS = (
    "allow_sensitive_required_env_names",
    "allowed_sensitive_env_names",
    "required_sensitive_env_names",
)
EVIDENCE_CHECK_ORDER = (
    "dashboard_payload_preflight",
    "static_sql_lint",
    "semantic_sql",
    "readback",
    "target_evidence",
    *RETIRE_REQUIRED_EVIDENCE_CHECKS,
)
EVIDENCE_CHECK_ALIASES = {
    "dashboard_payload_preflight": {
        "dashboard_payload",
        "dashboard_payload_preflight",
        "dashboard_payload_preflight_ok",
        "dashboard_preflight",
    },
    "static_sql_lint": {
        "editor_sql_lint",
        "sql_lint",
        "static_sql",
        "static_sql_lint",
    },
    "semantic_sql": {
        "semantic_sql",
        "semantic_sql_diagnostics",
        "semantic_sql_validation",
        "sql_semantic",
    },
    "readback": {
        "published_readback",
        "readback",
        "readback_evidence",
        "saved_readback",
    },
    "target_evidence": {
        "target_evidence",
        "target_lock",
        "target_lock_evidence",
        "target_readback",
    },
    "relation_graph_proof": {
        "relation_graph",
        "relation_graph_proof",
        "relations_proof",
    },
    "saved_no_reference_proof": {
        "saved_no_reference",
        "saved_no_reference_proof",
        "saved_no_refs",
    },
    "published_no_reference_proof": {
        "published_no_reference",
        "published_no_reference_proof",
        "published_no_refs",
    },
    "dry_run_retire_plan": {
        "dry_run_retire_plan",
        "retire_dry_run_plan",
        "retire_plan",
    },
    "approval_provenance": {
        "approval",
        "approval_provenance",
        "approval_record",
    },
    "execution_summary": {
        "execution_summary",
        "retire_execution_summary",
        "summary",
    },
    "post_retire_readback": {
        "post_delete_readback",
        "post_retire_readback",
        "retire_readback",
    },
}
EVIDENCE_PAYLOAD_PATH_KEYS = {
    "dashboard_payload_preflight": (
        "dashboard_payload_paths",
        "dashboard_payload_preflight_paths",
        "dashboard_paths",
    ),
    "static_sql_lint": (
        "editor_sql_paths",
        "static_sql_paths",
        "sql_lint_paths",
        "source_paths",
    ),
    "semantic_sql": (
        "semantic_sql_paths",
        "semantic_sql_evidence_paths",
        "semantic_sql_artifact_paths",
        "sql_semantic_paths",
    ),
    "readback": (
        "readback_evidence_paths",
        "readback_paths",
        "saved_readback_paths",
        "published_readback_paths",
        "evidence_paths",
    ),
    "target_evidence": (
        "target_evidence_paths",
        "target_lock_paths",
        "target_paths",
    ),
    "relation_graph_proof": RETIRE_REQUIRED_PATH_FIELDS["relation_graph_proof"],
    "saved_no_reference_proof": RETIRE_REQUIRED_PATH_FIELDS["saved_no_reference_proof"],
    "published_no_reference_proof": RETIRE_REQUIRED_PATH_FIELDS["published_no_reference_proof"],
    "dry_run_retire_plan": RETIRE_REQUIRED_PATH_FIELDS["dry_run_retire_plan"],
    "approval_provenance": RETIRE_REQUIRED_PATH_FIELDS["approval_provenance"],
    "execution_summary": RETIRE_REQUIRED_PATH_FIELDS["execution_summary"],
    "post_retire_readback": RETIRE_REQUIRED_PATH_FIELDS["post_retire_readback"],
}
EVIDENCE_ARTIFACT_KEYWORDS = {
    "dashboard_payload_preflight": ("dashboard", "payload", "preflight"),
    "static_sql_lint": ("sql", "source", "lint"),
    "semantic_sql": ("semantic", "diagnose", "diagnostic"),
    "readback": ("readback",),
    "target_evidence": ("target", "lock"),
    "relation_graph_proof": ("relation", "graph"),
    "saved_no_reference_proof": ("saved", "no_reference"),
    "published_no_reference_proof": ("published", "no_reference"),
    "dry_run_retire_plan": ("retire", "plan"),
    "approval_provenance": ("approval",),
    "execution_summary": ("execution", "summary"),
    "post_retire_readback": ("retire", "readback"),
}
DEFAULT_MIGRATION_EVIDENCE_CHECKS = (
    "dashboard_payload_preflight",
    "static_sql_lint",
    "readback",
    "target_evidence",
)
ACTION_BRANCH_STATUS = {
    "validate": "validated",
    "dry_run": "dry_run",
    "apply": "saved",
    "publish": "published",
    "readback": "saved_readback",
}
TRACKED_SOURCE_MUTATION_GUARDED_ACTIONS = {"read", "sync", "validate", "dry_run", "readback"}


def detect_project_live_workflows(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest_info = _load_manifest(root)
    if manifest_info["ok"]:
        manifest = manifest_info["manifest"]
        workflows = _workflow_names(manifest)
        return {
            "ok": True,
            "status": "manifest_detected",
            "adapter": "repo_live_workflow_manifest",
            "project_root": str(root),
            "manifest_path": str(manifest_info["path"]),
            "manifest": _safe_manifest_summary(manifest),
            "workflows": workflows,
            "workflow_summaries": [
                _workflow_summary(workflow)
                for workflow in manifest.get("workflows") or []
                if isinstance(workflow, dict)
            ],
            "recommended_next_actions": [
                "Run dl_plan_project_live_workflow for the selected workflow.",
                "Run dl_run_project_live_dry_run with execute_now=true only when the manifest command is reviewed.",
                "Run dl_run_project_live_apply only after approval, write flags, and dry-run summary review.",
                "Read summary/readback evidence with dl_read_project_live_summary.",
            ],
        }
    if manifest_info.get("path") and manifest_info.get("errors"):
        return {
            "ok": False,
            "status": "invalid_manifest",
            "project_root": str(root),
            "manifest_path": str(manifest_info["path"]),
            "errors": manifest_info["errors"],
            "recommended_next_actions": ["Fix the project live workflow manifest before planning live operations."],
        }
    detected_scripts = _detect_script_patterns(root)
    adapter_guidance = detect_project_adapter(root)
    return {
        "ok": False,
        "status": "adapter_required",
        "adapter": adapter_guidance.get("adapter") or "unknown_custom_layout",
        "adapter_status": adapter_guidance.get("status") or "adapter_required",
        "project_root": str(root),
        "detected_script_patterns": detected_scripts,
        "adapter_guidance": adapter_guidance.get("migration_guidance") or {},
        "blocked_operations": adapter_guidance.get("blocked_operations") or [],
        "suggested_manifest": _suggested_manifest(root, detected_scripts),
        "recommended_next_actions": [
            "Add .datalens-mcp.json or datalens-mcp.project.json to declare dry-run/apply/readback commands.",
            "Keep commands as argv arrays and summary/readback paths inside the project root.",
            "Keep may_execute_command=false until dry-run summaries and evidence paths are reviewed.",
            "Do not treat a custom layout as an empty successful safe-apply plan.",
        ],
    }


def plan_project_manifest(
    project_root: str | Path = ".",
    *,
    write_manifest: bool = False,
    approved: bool | None = None,
    overwrite_existing: bool = False,
    target_workbook_id: str = "",
    dashboard_id: str = "",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    detected_scripts = _detect_script_patterns(root)
    existing = _load_manifest(root)
    manifest_path = root / ".datalens-mcp.json"
    if existing.get("path"):
        manifest_path = Path(existing["path"])
    proposed = _suggested_manifest(root, detected_scripts)
    proposed["schema_version"] = "2026-07-01.project_live_workflow_manifest.v4"
    proposed["workbook_id"] = target_workbook_id or proposed.get("workbook_id") or "<workbook_id>"
    proposed["dashboard_ids"] = [dashboard_id] if dashboard_id else proposed.get("dashboard_ids", ["<dashboard_id>"])
    proposed["target"] = {
        "workbook_id": proposed["workbook_id"],
        "dashboard_ids": proposed["dashboard_ids"],
    }
    proposed["local_object_registry"] = _local_object_registry(root)
    proposed["source_paths"] = _manifest_source_paths(root)
    proposed["lifecycle_policy"] = {
        "default": "read_only",
        "writes": "safe_apply_only",
        "fresh_read_required": True,
        "save_first_for_publish": True,
        "delete_move_permission_operations": f"{RETIRE_ACTION}_only_for_explicit_user_requested_removal",
    }
    proposed["artifact_roots"] = ["artifacts", "artifacts/readback", "artifacts/safe_apply", "reports"]
    proposed["selector_parameter_contracts"] = _selector_parameter_contracts(root)
    proposed["allowed_live_operations"] = {
        "read": True,
        "validate": True,
        "dry_run": True,
        "save": False,
        "publish": False,
    }
    blocked: list[str] = []
    if existing.get("ok") and not overwrite_existing:
        blocked.append("manifest already exists; set overwrite_existing=true and write_manifest=true to replace it")
    written = False
    should_write = bool(write_manifest or approved is True)
    if should_write and not blocked:
        manifest_path.write_text(json.dumps(proposed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written = True
    return {
        "ok": not blocked,
        "status": "written" if written else ("blocked" if blocked else "preview"),
        "project_root": str(root),
        "manifest_path": str(manifest_path),
        "write_manifest": should_write,
        "approved": approved,
        "overwrite_existing": overwrite_existing,
        "written": written,
        "existing_manifest": bool(existing.get("path")),
        "blocked_reasons": blocked,
        "detected_script_patterns": detected_scripts,
        "proposed_manifest": proposed,
        "preview": not written,
    }


def plan_project_live_workflow(
    project_root: str | Path = ".",
    *,
    workflow_name: str = "",
    action: str = "dry_run",
    publish: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    loaded = _require_manifest(root)
    manifest = loaded["manifest"]
    workflow = _select_workflow(manifest, workflow_name)
    normalized_action = _normalize_action(action)
    action_spec = _action_spec(workflow, normalized_action, publish=publish)
    command = _command_from_spec(action_spec)
    required_env_validation = _required_env_validation(manifest, workflow, action_spec)
    validation = [
        *_validate_action_spec_shape(normalized_action, action_spec),
        *_validate_command(root, command),
        *_validate_action_safety(root, manifest, workflow, action_spec, normalized_action, publish=publish),
        *required_env_validation["issues"],
    ]
    summary_paths = _summary_candidates(root, workflow, action_spec)
    retire_lifecycle = _retire_lifecycle_summary(manifest, workflow, action_spec) if normalized_action == RETIRE_ACTION else {}
    return {
        "ok": not validation,
        "status": "planned" if not validation else "blocked",
        "project_root": str(root),
        "manifest_path": str(loaded["path"]),
        "project_name": manifest.get("project_name") or manifest.get("name") or root.name,
        "workflow_name": workflow["name"],
        "action": normalized_action,
        "publish_requested": publish,
        "workbook_id": manifest.get("workbook_id") or "",
        "dashboard_ids": manifest.get("dashboard_ids") or [],
        "command": command,
        "summary_candidates": [str(path) for path in summary_paths],
        "expected_changed_object_groups": workflow.get("expected_changed_object_groups") or [],
        "required_env_names": required_env_validation["allowed_env_names"],
        "rejected_required_env_names": required_env_validation["rejected_env_names"],
        "required_env_validation": required_env_validation,
        "affected_objects": workflow.get("affected_objects") or action_spec.get("affected_objects") or [],
        "expected_artifacts": _expected_artifacts(workflow, action_spec),
        "evidence_checks": workflow.get("evidence_checks") or action_spec.get("evidence_checks") or [],
        "safe_constraints": workflow.get("safe_constraints") or workflow.get("write_safety_constraints") or {},
        "workflow_modes": _workflow_modes(workflow),
        "readback_evidence_paths": workflow.get("readback_evidence_paths") or action_spec.get("readback_evidence_paths") or [],
        "summary_requirements": _summary_requirements_from_action(action_spec),
        "may_execute_command": bool(workflow.get("may_execute_command", workflow.get("may_execute", False))),
        "allow_publish": bool(workflow.get("allow_publish", False)),
        "retire_lifecycle": retire_lifecycle,
        "hidden_destructive_semantics_policy": (
            "normal validate/dry_run/apply/publish/readback actions block delete, move, and permission mutation tokens; "
            "explicit removal must use retire_legacy_objects with declared proofs"
        ),
        "blocked_reasons": validation,
    }


def run_project_live_dry_run(
    project_root: str | Path = ".",
    *,
    workflow_name: str = "",
    execute_now: bool = False,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    return _run_project_live_action(
        project_root=project_root,
        workflow_name=workflow_name,
        action="dry_run",
        execute_now=execute_now,
        timeout_sec=timeout_sec,
        approved=False,
        publish=False,
    )


def run_project_live_apply(
    project_root: str | Path = ".",
    *,
    workflow_name: str = "",
    execute_now: bool = False,
    approved: bool | None = None,
    confirm_delete: bool = False,
    publish: bool = False,
    action: str = "apply",
    timeout_sec: int = 120,
) -> dict[str, Any]:
    return _run_project_live_action(
        project_root=project_root,
        workflow_name=workflow_name,
        action=action,
        execute_now=execute_now,
        timeout_sec=timeout_sec,
        approved=approved,
        confirm_delete=confirm_delete,
        publish=publish,
    )


def read_project_live_summary(
    project_root: str | Path = ".",
    *,
    workflow_name: str = "",
    action: str = "dry_run",
    publish: bool = False,
    summary_path: str = "",
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    loaded = _require_manifest(root)
    manifest = loaded["manifest"]
    workflow = _select_workflow(manifest, workflow_name)
    summary_action = _summary_action_label(action, publish=publish)
    action_spec = _summary_action_spec(workflow, summary_action)
    candidates = [Path(summary_path)] if summary_path else _summary_candidates(root, workflow, action_spec)
    for candidate in candidates:
        resolved = _resolve_inside(root, candidate)
        if resolved.is_file():
            return _parse_summary(
                root=root,
                manifest=manifest,
                workflow=workflow,
                action_spec=action_spec,
                action=summary_action,
                publish_requested=summary_action == "publish",
                summary_path=resolved,
            )
    return {
        "ok": False,
        "status": "summary_not_found",
        "project_root": str(root),
        "workflow_name": workflow["name"],
        "action": summary_action,
        "publish_requested": summary_action == "publish",
        "summary_candidates": [str(_resolve_inside(root, candidate)) for candidate in candidates],
    }


def _run_project_live_action(
    *,
    project_root: str | Path,
    workflow_name: str,
    action: str,
    execute_now: bool,
    timeout_sec: int,
    approved: bool | None,
    confirm_delete: bool = False,
    publish: bool,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    plan = plan_project_live_workflow(root, workflow_name=workflow_name, action=action, publish=publish)
    if not execute_now:
        return {**plan, "executed": False, "status": "planned_not_executed"}
    if not plan["ok"]:
        return {**plan, "executed": False}
    loaded = _require_manifest(root)
    manifest = loaded["manifest"]
    workflow = _select_workflow(manifest, workflow_name)
    normalized_action = _normalize_action(action)
    action_spec = _action_spec(workflow, normalized_action, publish=publish)
    blocked = _runtime_blocks(
        workflow=workflow,
        action=action,
        approved=approved,
        confirm_delete=confirm_delete,
        publish=publish,
    )
    if blocked:
        return {**plan, "executed": False, "status": "blocked", "blocked_reasons": blocked}
    command = plan["command"]
    env, env_summary, secret_values = _safe_project_env(manifest, workflow, action_spec)
    mutation_guard_before = (
        _tracked_source_snapshot(root)
        if normalized_action in TRACKED_SOURCE_MUTATION_GUARDED_ACTIONS
        else {"available": False, "files": {}}
    )
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(1, int(timeout_sec)),
        )
    except subprocess.TimeoutExpired as exc:
        mutation_guard = _tracked_source_mutation_result(root, mutation_guard_before)
        return {
            **plan,
            "ok": False,
            "executed": True,
            "status": "tracked_source_mutation_blocked" if mutation_guard["mutated"] else "timeout",
            "returncode": None,
            "stdout": redact_text(exc.stdout or "", secret_values=secret_values),
            "stderr": redact_text(exc.stderr or "", secret_values=secret_values),
            "env_summary": env_summary,
            "tracked_source_mutation_guard": mutation_guard,
        }
    stdout = redact_text(completed.stdout, secret_values=secret_values)
    stderr = redact_text(completed.stderr, secret_values=secret_values)
    summary = {}
    if completed.returncode == 0:
        summary = read_project_live_summary(
            root,
            workflow_name=workflow["name"],
            action=_summary_action_label(action, publish=publish),
        )
    mutation_guard = _tracked_source_mutation_result(root, mutation_guard_before)
    summary_required = normalized_action in {"apply", "publish", RETIRE_ACTION} or publish
    summary_ok = not summary_required or summary.get("ok") is True
    summary_blocked_reasons = _summary_validation_blockers(summary) if summary_required and not summary_ok else []
    command_ok = completed.returncode == 0
    return {
        **plan,
        "ok": command_ok and summary_ok and not mutation_guard["mutated"],
        "executed": True,
        "status": (
            "tracked_source_mutation_blocked"
            if mutation_guard["mutated"]
            else "command_failed"
            if not command_ok
            else "summary_blocked"
            if not summary_ok
            else "completed"
        ),
        "returncode": completed.returncode,
        "stdout": stdout[:4000],
        "stderr": stderr[:4000],
        "env_summary": env_summary,
        "summary": summary,
        "blocked_reasons": summary_blocked_reasons,
        "tracked_source_mutation_guard": mutation_guard,
    }


def _summary_validation_blockers(summary: dict[str, Any]) -> list[str]:
    status = str(summary.get("status") or "").strip()
    if status == "summary_not_found":
        return ["project live action summary was not found"]
    issues = summary.get("blocking_issues")
    messages: list[str] = []
    if isinstance(issues, list):
        messages = [
            str(issue.get("message") or issue.get("rule") or "").strip()
            for issue in issues
            if isinstance(issue, dict)
        ]
    blockers = [message for message in messages if message]
    return blockers or ["project live action summary did not pass validation"]


def _tracked_source_snapshot(root: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "files": {}, "contents": {}, "modes": {}}
    if completed.returncode != 0:
        return {"available": False, "files": {}, "contents": {}, "modes": {}}
    files: dict[str, str] = {}
    contents: dict[str, bytes | None] = {}
    modes: dict[str, int] = {}
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative = raw_path.decode("utf-8", errors="surrogateescape")
        path = root / relative
        if not path.is_file():
            files[relative] = "<missing>"
            contents[relative] = None
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256()
        digest.update(raw)
        files[relative] = digest.hexdigest()
        contents[relative] = raw
        modes[relative] = path.stat().st_mode
    return {"available": True, "files": files, "contents": contents, "modes": modes}


def _tracked_source_mutation_result(root: Path, before: dict[str, Any]) -> dict[str, Any]:
    if not before.get("available"):
        return {
            "available": False,
            "mutated": False,
            "changed_paths": [],
            "policy": "tracked_source_guard_unavailable_outside_git_worktree",
        }
    after = _tracked_source_snapshot(root)
    if not after.get("available"):
        return {
            "available": False,
            "mutated": True,
            "changed_paths": [],
            "policy": "post_command_tracked_source_snapshot_failed",
        }
    before_files = before.get("files") or {}
    after_files = after.get("files") or {}
    changed = sorted(
        path
        for path in set(before_files) | set(after_files)
        if before_files.get(path) != after_files.get(path)
    )
    restore_failed: list[str] = []
    before_contents = before.get("contents") or {}
    before_modes = before.get("modes") or {}
    for relative in changed:
        path = root / relative
        try:
            original = before_contents.get(relative)
            if original is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
                if relative in before_modes:
                    path.chmod(int(before_modes[relative]) & 0o7777)
        except OSError:
            restore_failed.append(relative)
    return {
        "available": True,
        "mutated": bool(changed),
        "changed_paths": changed,
        "restored": bool(changed) and not restore_failed,
        "restore_failed_paths": restore_failed,
        "policy": "read_sync_validate_dry_run_must_not_mutate_tracked_sources",
    }


def _load_manifest(root: Path) -> dict[str, Any]:
    for name in MANIFEST_NAMES:
        path = root / name
        if not path.is_file():
            continue
        try:
            if path.suffix in {".yaml", ".yml"}:
                try:
                    import yaml  # type: ignore[import-not-found]
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "path": path, "errors": [f"{path.name}: PyYAML is not available: {exc}"]}
                manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            else:
                manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "path": path, "errors": [f"{path.name}: invalid manifest: {exc}"]}
        errors = _validate_manifest(manifest)
        return {"ok": not errors, "path": path, "manifest": manifest, "errors": errors}
    return {"ok": False, "path": None, "errors": []}


def _require_manifest(root: Path) -> dict[str, Any]:
    loaded = _load_manifest(root)
    if not loaded["ok"]:
        errors = loaded.get("errors") or ["project live workflow manifest is required"]
        raise ValueError("; ".join(errors))
    return loaded


def _validate_manifest(manifest: Any) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest root must be an object"]
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        return ["manifest requires a non-empty workflows list"]
    errors: list[str] = []
    for index, workflow in enumerate(workflows):
        if not isinstance(workflow, dict):
            errors.append(f"workflows[{index}] must be an object")
            continue
        if not str(workflow.get("name") or "").strip():
            errors.append(f"workflows[{index}].name is required")
        legacy_command_keys = [
            key
            for key in workflow
            if key in {"validate_command", "dry_run_command", "apply_command", "publish_command", "readback_command"}
        ]
        for key in legacy_command_keys:
            errors.append(f"workflows[{index}].{key} is not allowed; use action-specific {{command: [...]}} metadata")
        if not any(key in workflow for key in PROJECT_LIVE_ACTIONS):
            errors.append(
                f"workflows[{index}] requires at least one validate/dry_run/apply/publish/readback/"
                f"{RETIRE_ACTION} action metadata"
            )
        for action in sorted(PROJECT_LIVE_ACTIONS):
            if action not in workflow:
                continue
            spec = workflow.get(action)
            if not isinstance(spec, dict):
                errors.append(f"workflows[{index}].{action} must be an object")
                continue
            errors.extend(_manifest_action_step_errors(index, action, spec))
    return errors


def _workflow_names(manifest: dict[str, Any]) -> list[str]:
    return [str(workflow.get("name")) for workflow in manifest.get("workflows") or [] if workflow.get("name")]


def _select_workflow(manifest: dict[str, Any], workflow_name: str) -> dict[str, Any]:
    workflows = [item for item in manifest.get("workflows") or [] if isinstance(item, dict)]
    if not workflows:
        raise ValueError("manifest has no workflows")
    if not workflow_name:
        return workflows[0]
    for workflow in workflows:
        if workflow.get("name") == workflow_name:
            return workflow
    raise ValueError(f"workflow {workflow_name!r} was not found in manifest")


def _normalize_action(action: str) -> str:
    normalized = (action or "dry_run").strip().lower().replace("-", "_")
    if normalized not in PROJECT_LIVE_ACTIONS:
        raise ValueError(f"action must be validate, dry_run, apply, publish, readback, or {RETIRE_ACTION}")
    return normalized


def _action_spec(workflow: dict[str, Any], action: str, *, publish: bool) -> dict[str, Any]:
    if action == RETIRE_ACTION:
        spec = workflow.get(RETIRE_ACTION)
        return spec if isinstance(spec, dict) else {}
    key = "publish" if publish else action
    if key == "publish" and not isinstance(workflow.get("publish"), dict):
        key = "apply"
    spec = workflow.get(key)
    if not isinstance(spec, dict):
        command_key = f"{key}_command"
        spec = {"command": workflow.get(command_key)}
    if publish and key != "publish" and isinstance(workflow.get("publish"), dict):
        spec = {**spec, **workflow["publish"]}
    return spec if isinstance(spec, dict) else {}


def _summary_action_label(action: str, *, publish: bool) -> str:
    normalized = _normalize_action(action)
    if publish or normalized == "publish":
        return "publish"
    return normalized


def _summary_action_spec(workflow: dict[str, Any], action: str) -> dict[str, Any]:
    if action == "publish":
        return _action_spec(workflow, "apply", publish=True)
    return _action_spec(workflow, action, publish=False)


def _command_from_spec(spec: dict[str, Any]) -> list[str]:
    command = spec.get("command") or spec.get("argv")
    if isinstance(command, list):
        return [str(item) for item in command]
    return []


def _manifest_action_step_errors(workflow_index: int, action: str, spec: dict[str, Any]) -> list[str]:
    prefix = f"workflows[{workflow_index}].{action}"
    issues = _validate_action_spec_shape(action, spec)
    return [f"{prefix}: {issue}" for issue in issues]


def _validate_action_spec_shape(action: str, action_spec: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    command = action_spec.get("command") if "command" in action_spec else action_spec.get("argv")
    if command is None:
        issues.append("command is required")
    elif not isinstance(command, list):
        issues.append("command must be an argv array, not a shell/string command")
    elif not command:
        issues.append("command argv array must not be empty")
    elif not all(isinstance(item, str) and item.strip() for item in command):
        issues.append("command argv items must be non-empty strings")
    if not _summary_path_declared(action_spec):
        issues.append("summary_path or summary_glob is required for every action command")
    if action == RETIRE_ACTION:
        issues.extend(_validate_retire_contract_fields({}, {}, action_spec, include_workbook=False))
    return issues


def _summary_path_declared(action_spec: dict[str, Any]) -> bool:
    return bool(action_spec.get("summary_path") or action_spec.get("summary_json_path") or action_spec.get("summary_glob"))


def _validate_command(root: Path, command: list[str]) -> list[str]:
    issues: list[str] = []
    if not command:
        return ["workflow command is missing"]
    blocked_token = _blocked_token(command)
    if blocked_token:
        issues.append(f"workflow command token is not allowed: {blocked_token}")
    for token in command:
        if SHELL_META_RE.search(token):
            issues.append(f"workflow command token contains shell metacharacters: {token}")
        if token in {"-c", "--command"}:
            issues.append("inline interpreter commands are not allowed in live workflow manifests")
    executable = command[0]
    if "/" in executable:
        exe_path = Path(executable)
        if exe_path.name.startswith("python"):
            pass
        elif not _is_inside(root, exe_path):
            issues.append("absolute executable paths must be Python or stay inside project_root")
    for token in command[1:]:
        if token.endswith((".py", ".sh", ".json")) or "/" in token:
            candidate = Path(token)
            if candidate.is_absolute() and not _is_inside(root, candidate):
                issues.append(f"command path must stay inside project_root: {token}")
    return issues


def _blocked_token(command: list[str]) -> str:
    for token in command:
        lowered = Path(token).name.lower()
        if lowered in BLOCKED_COMMAND_TERMS:
            return token
    return ""


def _validate_action_safety(
    root: Path,
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
    action: str,
    *,
    publish: bool,
) -> list[str]:
    if action == RETIRE_ACTION:
        return _validate_retire_lifecycle(root, manifest, workflow, action_spec)
    return _normal_destructive_semantics_issues(workflow, action_spec, action=action, publish=publish)


def _normal_destructive_semantics_issues(
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
    *,
    action: str,
    publish: bool,
) -> list[str]:
    issues: list[str] = []
    command = _command_from_spec(action_spec)
    for token in command:
        rejection = _destructive_token_rejection(token)
        if rejection:
            issues.append(
                f"normal project-live {action} command contains hidden destructive token {token!r} "
                f"({rejection}); use {RETIRE_ACTION} for explicit user-requested removal"
            )
    for issue in _destructive_constraint_issues(workflow, action_spec):
        issues.append(f"normal project-live {action} declares destructive semantics ({issue}); use {RETIRE_ACTION}")
    if publish:
        for token in command:
            rejection = _destructive_token_rejection(token)
            if rejection:
                issues.append(
                    f"manifest publish cannot smuggle destructive token {token!r}; use {RETIRE_ACTION}"
                )
    return _unique_strings(issues)


def _destructive_token_rejection(token: Any) -> str:
    normalized = _operation_token(str(token))
    if not normalized:
        return ""
    if normalized in {"delete", "deletelegacy", "delete_legacy", "deleteeditorchart", "deletedashboard"}:
        return "delete operation"
    if normalized.startswith("delete_") or normalized.startswith("delete"):
        return "delete operation"
    if normalized in MOVE_OPERATION_TOKENS or normalized.startswith("move_") or normalized.startswith("move"):
        return "move operation"
    if normalized in PERMISSION_MUTATION_TOKENS or "permission" in normalized or "accessbinding" in normalized:
        return "permission mutation"
    if normalized in {"setiampolicy", "set_iam_policy"}:
        return "permission mutation"
    return ""


def _operation_token(token: str) -> str:
    value = Path(token).name.strip().strip("'\"").lower()
    value = value.lstrip("-")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def _destructive_constraint_issues(workflow: dict[str, Any], action_spec: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for constraints in _safe_constraint_objects({}, workflow, action_spec):
        for path, value in _walk_scalar_items(constraints):
            key = _operation_token(path.split(".")[-1])
            if key not in DESTRUCTIVE_CONSTRAINT_KEYS:
                continue
            if value in (False, None, "", "false", "False", "disabled", "none"):
                continue
            issues.append(f"{path}={value!r}")
    return issues


def _walk_scalar_items(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_walk_scalar_items(item, child))
        return rows
    if isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{prefix}[{index}]"
            rows.extend(_walk_scalar_items(item, child))
        return rows
    rows.append((prefix, value))
    return rows


def _validate_retire_lifecycle(
    root: Path,
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
) -> list[str]:
    issues = _validate_retire_contract_fields(manifest, workflow, action_spec, include_workbook=True)
    for proof_name, keys in RETIRE_REQUIRED_PATH_FIELDS.items():
        paths = _retire_declared_paths(workflow, action_spec, keys)
        if not paths:
            issues.append(f"{RETIRE_ACTION} requires declared {proof_name} path")
            continue
        if proof_name in {"relation_graph_proof", "dry_run_retire_plan", "approval_provenance"}:
            # These proofs are pre-execution gates. They must already exist before a retire command can be planned.
            missing = [str(_resolve_inside(root, Path(path))) for path in paths if not _resolve_inside(root, Path(path)).is_file()]
            if missing:
                issues.append(f"{RETIRE_ACTION} missing {proof_name} artifact(s): {', '.join(missing)}")
    return issues


def _validate_retire_contract_fields(
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
    *,
    include_workbook: bool,
) -> list[str]:
    issues: list[str] = []
    state = str(action_spec.get("lifecycle_state") or action_spec.get("state") or "requested").strip()
    if state not in RETIRE_LIFECYCLE_STATES:
        issues.append(f"{RETIRE_ACTION}.lifecycle_state must be one of {', '.join(RETIRE_LIFECYCLE_STATES)}")
    if include_workbook:
        workbook_id = str(action_spec.get("workbook_id") or workflow.get("workbook_id") or manifest.get("workbook_id") or "").strip()
        if not workbook_id or workbook_id.startswith("<"):
            issues.append(f"{RETIRE_ACTION} requires exact workbook_id")
    objects = _retire_objects(action_spec)
    if not objects:
        issues.append(f"{RETIRE_ACTION} requires exact objects with id and type")
    for index, item in enumerate(objects):
        object_id = str(item.get("id") or item.get("object_id") or item.get("entry_id") or "").strip()
        object_type = str(item.get("type") or item.get("object_type") or "").strip()
        if not object_id or object_id.startswith("<"):
            issues.append(f"{RETIRE_ACTION}.objects[{index}] requires exact object id")
        if not object_type or object_type.startswith("<"):
            issues.append(f"{RETIRE_ACTION}.objects[{index}] requires object type")
    if not str(action_spec.get("reason") or workflow.get("retire_reason") or "").strip():
        issues.append(f"{RETIRE_ACTION} requires reason")
    if not _retire_user_decision_provenance(workflow, action_spec):
        issues.append(f"{RETIRE_ACTION} requires user_request_quote or decision_id")
    for proof_name, keys in RETIRE_REQUIRED_PATH_FIELDS.items():
        if not _retire_declared_paths(workflow, action_spec, keys):
            issues.append(f"{RETIRE_ACTION} requires declared {proof_name} path")
    return _unique_strings(issues)


def _retire_lifecycle_summary(
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
) -> dict[str, Any]:
    objects = _retire_objects(action_spec)
    proof_paths = {
        proof_name: _retire_declared_paths(workflow, action_spec, keys)
        for proof_name, keys in RETIRE_REQUIRED_PATH_FIELDS.items()
    }
    return {
        "action": RETIRE_ACTION,
        "lifecycle_state": action_spec.get("lifecycle_state") or action_spec.get("state") or "requested",
        "allowed_lifecycle_states": list(RETIRE_LIFECYCLE_STATES),
        "workbook_id": action_spec.get("workbook_id") or workflow.get("workbook_id") or manifest.get("workbook_id") or "",
        "objects": objects,
        "object_count": len(objects),
        "reason": action_spec.get("reason") or workflow.get("retire_reason") or "",
        "user_request_quote": action_spec.get("user_request_quote") or workflow.get("user_request_quote") or "",
        "decision_id": action_spec.get("decision_id") or workflow.get("decision_id") or "",
        "required_proof_paths": proof_paths,
        "rollback_restore_note": (
            "DataLens delete/retire has no automatic MCP rollback; restoration requires separate "
            "operator-owned recovery evidence."
        ),
    }


def _retire_objects(action_spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw = action_spec.get("objects") or action_spec.get("target_objects") or action_spec.get("legacy_objects") or []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _retire_user_decision_provenance(workflow: dict[str, Any], action_spec: dict[str, Any]) -> bool:
    for container in (action_spec, workflow):
        if str(container.get("user_request_quote") or container.get("decision_id") or "").strip():
            return True
        provenance = container.get("approval_provenance")
        if isinstance(provenance, dict) and str(provenance.get("decision_id") or provenance.get("user_request_quote") or "").strip():
            return True
    return False


def _retire_declared_paths(
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
    keys: tuple[str, ...],
) -> list[str]:
    paths: list[str] = []
    for container in (workflow, action_spec):
        for key in keys:
            paths.extend(_path_values(container.get(key)))
    return _unique_strings(paths)


def _runtime_blocks(
    *,
    workflow: dict[str, Any],
    action: str,
    approved: bool | None,
    confirm_delete: bool,
    publish: bool,
) -> list[str]:
    cfg = DataLensConfig.from_env().reload_canonical_env(reload_state="reloaded_before_project_live_write")
    normalized_action = _normalize_action(action)
    blocked: list[str] = []
    if not workflow.get("may_execute_command", workflow.get("may_execute", False)):
        blocked.append("workflow manifest does not allow command execution")
    if normalized_action in {"apply", RETIRE_ACTION}:
        if normalized_action == RETIRE_ACTION and not confirm_delete:
            blocked.append("delete confirmation is required; repeat with confirm_delete=true for the unchanged plan")
        if not cfg.write_enabled:
            blocked.append("write mode is disabled; set DATALENS_MCP_ENABLE_WRITES=1")
        if not cfg.save_enabled:
            blocked.append("save execution is disabled; set DATALENS_MCP_LIVE_ALLOW_SAVE=1")
    if normalized_action == RETIRE_ACTION and publish:
        blocked.append(f"{RETIRE_ACTION} does not use publish=true; publish no-reference proof is evidence, not a publish request")
    if publish:
        if not workflow.get("allow_publish", False):
            blocked.append("workflow manifest does not allow publish")
        if not cfg.publish_enabled:
            blocked.append("publish execution is disabled; set DATALENS_MCP_LIVE_ALLOW_PUBLISH=1")
    return blocked


def _safe_project_env(
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
) -> tuple[dict[str, str], dict[str, Any], list[str]]:
    required_env_validation = _required_env_validation(manifest, workflow, action_spec)
    if not required_env_validation["ok"]:
        raise ValueError(
            "invalid project live required_env_names: " + "; ".join(required_env_validation["issues"])
        )
    cfg = DataLensConfig.from_env()
    token = cfg.iam_token
    if not token and cfg.token_refresh_enabled:
        token = refresh_iam_token_with_yc(yc_binary=cfg.yc_binary)
    yc_path = cfg.yc_binary if "/" in cfg.yc_binary else shutil.which(cfg.yc_binary) or cfg.yc_binary

    env = _base_project_env()
    parent_required_env_names: list[str] = []
    for name in required_env_validation["allowed_env_names"]:
        if name in INJECTED_DATALENS_ENV_NAMES or _is_base_project_env_name(name):
            continue
        if name in os.environ:
            env[name] = os.environ[name]
            parent_required_env_names.append(name)

    injected_env_names: list[str] = []
    if token:
        env["DATALENS_IAM_TOKEN"] = token
        env["YC_IAM_TOKEN"] = token
        injected_env_names.extend(["DATALENS_IAM_TOKEN", "YC_IAM_TOKEN"])
    if yc_path:
        env["DATALENS_YC_BINARY"] = yc_path
        injected_env_names.append("DATALENS_YC_BINARY")
    if cfg.org_id:
        env["DATALENS_ORG_ID"] = cfg.org_id
        injected_env_names.append("DATALENS_ORG_ID")
    if cfg.base_url:
        env["DATALENS_API_BASE_URL"] = cfg.base_url
        injected_env_names.append("DATALENS_API_BASE_URL")
    if cfg.api_version:
        env["DATALENS_API_VERSION"] = cfg.api_version
        injected_env_names.append("DATALENS_API_VERSION")

    allowed_env_names = required_env_validation["allowed_env_names"]
    missing_required_env_names = sorted(name for name in allowed_env_names if name not in env)
    secret_values = _unique_strings(
        [
            *secret_values_from_mapping(os.environ),
            *secret_values_from_mapping(env),
            token,
            os.getenv("DATALENS_IAM_TOKEN", ""),
            os.getenv("YC_IAM_TOKEN", ""),
        ]
    )
    return (
        env,
        {
            "ambient_env_inherited": False,
            "base_env_names": sorted(name for name in env if _is_base_project_env_name(name)),
            "manifest_required_env_names": allowed_env_names,
            "parent_required_env_names": sorted(parent_required_env_names),
            "missing_required_env_names": missing_required_env_names,
            "rejected_required_env_names": required_env_validation["rejected_env_names"],
            "injected_datalens_env_names": sorted(set(injected_env_names)),
            "token_present": bool(token),
            "org_id_set": bool(cfg.org_id),
            "api_base_url": cfg.base_url,
            "api_version": cfg.api_version,
            "yc_binary_resolved": bool(yc_path),
        },
        secret_values,
    )


def _base_project_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for name in BASE_PROJECT_ENV_NAMES:
        value = os.getenv(name)
        if value:
            env[name] = value
    env.setdefault("PATH", os.defpath)
    for name, value in os.environ.items():
        if name.startswith(BASE_PROJECT_ENV_PREFIXES) and value:
            env[name] = value
    return env


def _summary_candidates(root: Path, workflow: dict[str, Any], action_spec: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    for value in (
        action_spec.get("summary_path"),
        action_spec.get("summary_json_path"),
        workflow.get("summary_path"),
        workflow.get("summary_json_path"),
    ):
        if value:
            candidates.append(_resolve_inside(root, Path(str(value))))
    for pattern in (action_spec.get("summary_glob"), workflow.get("summary_glob"), workflow.get("summary_discovery_glob")):
        if not pattern:
            continue
        resolved_pattern = str(_resolve_inside(root, Path(str(pattern))))
        candidates.extend(Path(path) for path in sorted(glob.glob(resolved_pattern)))
    return candidates


def _parse_summary(
    *,
    root: Path,
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
    action: str,
    publish_requested: bool,
    summary_path: Path,
) -> dict[str, Any]:
    payload = read_json(summary_path, default={})
    if not isinstance(payload, dict):
        payload = {}
    artifact_validation = _validate_summary_artifacts(
        root,
        payload,
        workflow=workflow,
        action_spec=action_spec,
        action=action,
    )
    summary_requirements = _summary_requirements_from_action(action_spec)
    summary_requirements_validation = _validate_summary_requirements(
        payload,
        manifest=manifest,
        requirements=summary_requirements,
        action=action,
    )
    dashboard_payload_preflight = artifact_validation["checks"]["dashboard_payload_preflight"]
    sql_lint = artifact_validation["checks"]["static_sql_lint"]
    blocking_issues = [*artifact_validation["blocking_issues"], *summary_requirements_validation["blocking_issues"]]
    ok = bool(artifact_validation["ok"] and summary_requirements_validation["ok"])
    return {
        "ok": ok,
        "status": "summary_read" if ok else "summary_blocked",
        "project_root": str(root),
        "workflow_name": workflow["name"],
        "action": action,
        "publish_requested": publish_requested,
        "summary_path": str(summary_path),
        "branch_status": payload.get("branch_status") or payload.get("branch") or "",
        "workbook_id": payload.get("workbook_id") or manifest.get("workbook_id") or "",
        "dashboard_id": payload.get("dashboard_id") or _first(manifest.get("dashboard_ids")) or "",
        "dashboard_ids": payload.get("dashboard_ids") or manifest.get("dashboard_ids") or [],
        "target_ids": _summary_target_ids(payload, manifest),
        "saved": bool(payload.get("saved", payload.get("save_ok", False))),
        "published": bool(payload.get("published", payload.get("publish_ok", False))),
        "changed_object_counts": _changed_counts(payload),
        "evidence_paths": payload.get("evidence_paths") or payload.get("readback_evidence_paths") or [],
        "remaining_drift": payload.get("remaining_drift") or payload.get("drift") or [],
        "dashboard_payload_preflight": dashboard_payload_preflight,
        "static_sql_lint": sql_lint,
        "semantic_sql": artifact_validation["checks"]["semantic_sql"],
        "readback_evidence": artifact_validation["checks"]["readback"],
        "target_evidence": artifact_validation["checks"]["target_evidence"],
        "relation_graph_proof": artifact_validation["checks"]["relation_graph_proof"],
        "saved_no_reference_proof": artifact_validation["checks"]["saved_no_reference_proof"],
        "published_no_reference_proof": artifact_validation["checks"]["published_no_reference_proof"],
        "dry_run_retire_plan": artifact_validation["checks"]["dry_run_retire_plan"],
        "approval_provenance": artifact_validation["checks"]["approval_provenance"],
        "execution_summary": artifact_validation["checks"]["execution_summary"],
        "post_retire_readback": artifact_validation["checks"]["post_retire_readback"],
        "declared_evidence_checks": artifact_validation["declared_evidence_checks"],
        "checked_artifact_counts": artifact_validation["checked_artifact_counts"],
        "missing_declared_artifacts": artifact_validation["missing_declared_artifacts"],
        "summary_requirements": summary_requirements,
        "summary_requirements_validation": summary_requirements_validation,
        "blocking_issues": blocking_issues,
    }


def _validate_summary_artifacts(
    root: Path,
    payload: dict[str, Any],
    *,
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    declared = _declared_evidence_checks(workflow, action_spec, action=action)
    checks: dict[str, dict[str, Any]] = {}
    missing_declared_artifacts: list[dict[str, Any]] = []
    blocking_issues: list[dict[str, Any]] = []

    for check in EVIDENCE_CHECK_ORDER:
        expected_patterns = _expected_patterns_for_check(check, payload, workflow, action_spec)
        matched_paths, missing_patterns = _matching_artifact_paths(root, expected_patterns)
        declaration = declared.get(check, {"optional": False})
        declared_check = check in declared
        optional = bool(declaration.get("optional"))
        missing = [
            {
                "check": check,
                "action": action,
                "path_pattern": pattern,
            }
            for pattern in missing_patterns
        ]
        missing_declared_artifacts.extend(missing)

        if check == "dashboard_payload_preflight":
            summary = _validate_dashboard_artifacts(root, matched_paths)
        elif check == "static_sql_lint":
            summary = _validate_sql_lint_artifacts(matched_paths)
        elif check in {"saved_no_reference_proof", "published_no_reference_proof"}:
            summary = _validate_no_reference_artifacts(matched_paths, check=check)
        else:
            summary = _plain_artifact_summary(matched_paths)

        zero_issue = None
        if declared_check and not optional and summary["checked_count"] == 0:
            zero_issue = {
                "severity": "error",
                "rule": "zero_coverage",
                "check": check,
                "action": action,
                "blocking": True,
                "checked_count": 0,
                "expected_path_patterns": expected_patterns,
                "message": f"{check} is declared for {action} but no matching artifacts were checked.",
            }
            blocking_issues.append(zero_issue)

        check_ok = bool(summary["ok"]) and zero_issue is None
        checks[check] = {
            **summary,
            "ok": check_ok,
            "declared": declared_check,
            "optional": optional,
            "expected_path_patterns": expected_patterns,
            "missing_declared_artifacts": missing,
        }

    checked_counts = {check: checks[check]["checked_count"] for check in EVIDENCE_CHECK_ORDER}
    return {
        "ok": not blocking_issues and all(checks[check]["ok"] for check in EVIDENCE_CHECK_ORDER),
        "checks": checks,
        "declared_evidence_checks": [
            {"check": check, "optional": bool(value.get("optional"))}
            for check, value in declared.items()
        ],
        "checked_artifact_counts": checked_counts,
        "missing_declared_artifacts": missing_declared_artifacts,
        "blocking_issues": blocking_issues,
    }


def _validate_dashboard_artifacts(root: Path, paths: list[Path]) -> dict[str, Any]:
    results = []
    for path in paths:
        payload = read_json(path, default={})
        if not isinstance(payload, dict):
            payload = {}
        result = validate_dashboard_payload(payload)
        results.append({"path": str(path), "checked_paths": [str(path)], **result.to_dict()})
    return {
        "ok": bool(results) and all(item.get("ok", True) for item in results) if results else True,
        "checked_count": len(results),
        "checked_paths": [str(path) for path in paths],
        "results": results,
    }


def _validate_sql_lint_artifacts(paths: list[Path]) -> dict[str, Any]:
    results = []
    for path in paths:
        result = lint_editor_sql_file(path)
        results.append({"path": str(path), **result.to_dict()})
    return {
        "ok": bool(results) and all(item.get("ok", True) for item in results) if results else True,
        "checked_count": len(results),
        "checked_paths": [str(path) for path in paths],
        "results": results,
    }


def _plain_artifact_summary(paths: list[Path]) -> dict[str, Any]:
    return {
        "ok": True,
        "checked_count": len(paths),
        "checked_paths": [str(path) for path in paths],
        "results": [{"path": str(path)} for path in paths],
    }


def _validate_no_reference_artifacts(paths: list[Path], *, check: str) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for path in paths:
        payload = read_json(path, default={})
        if not isinstance(payload, dict):
            results.append(
                {
                    "path": str(path),
                    "ok": False,
                    "rule": "invalid_no_reference_proof",
                    "message": f"{check} proof must be a JSON object",
                }
            )
            continue
        proof = _no_reference_status(payload)
        results.append({"path": str(path), **proof})
    return {
        "ok": bool(results) and all(item.get("ok", False) for item in results) if results else True,
        "checked_count": len(results),
        "checked_paths": [str(path) for path in paths],
        "results": results,
    }


def _no_reference_status(payload: dict[str, Any]) -> dict[str, Any]:
    references = payload.get("references")
    referenced_by = payload.get("referenced_by")
    ref_count = payload.get("reference_count", payload.get("references_count", payload.get("linked_reference_count")))
    if isinstance(references, list) and references:
        return {"ok": False, "rule": "references_still_present", "reference_count": len(references)}
    if isinstance(referenced_by, list) and referenced_by:
        return {"ok": False, "rule": "references_still_present", "reference_count": len(referenced_by)}
    if isinstance(ref_count, int | float) and int(ref_count) != 0:
        return {"ok": False, "rule": "references_still_present", "reference_count": int(ref_count)}
    if payload.get("has_references") is True or payload.get("referenced") is True:
        return {"ok": False, "rule": "references_still_present", "reference_count": ref_count or 1}
    explicit_no_ref = (
        payload.get("no_references") is True
        or payload.get("no_reference") is True
        or payload.get("has_references") is False
        or payload.get("referenced") is False
        or ref_count == 0
        or references == []
        or referenced_by == []
    )
    if not explicit_no_ref:
        return {
            "ok": False,
            "rule": "missing_explicit_no_reference_assertion",
            "message": "No-reference proof must explicitly assert zero saved/published references.",
        }
    return {"ok": True, "rule": "no_references_verified", "reference_count": 0}


def _declared_evidence_checks(
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
    *,
    action: str,
) -> dict[str, dict[str, Any]]:
    declared: dict[str, dict[str, Any]] = {}
    for raw in [*(workflow.get("evidence_checks") or []), *(action_spec.get("evidence_checks") or [])]:
        parsed = _parse_evidence_check(raw)
        if not parsed:
            continue
        name, optional = parsed
        previous = declared.get(name)
        if previous:
            optional = bool(previous.get("optional")) and optional
        declared[name] = {"optional": optional}
    if action == RETIRE_ACTION:
        for name in RETIRE_REQUIRED_EVIDENCE_CHECKS:
            declared.setdefault(name, {"optional": False})
    return declared


def _parse_evidence_check(raw: Any) -> tuple[str, bool] | None:
    optional = False
    name = ""
    if isinstance(raw, str):
        name = raw
    elif isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("check") or raw.get("type") or raw.get("rule") or "")
        optional = bool(raw.get("optional") or raw.get("required") is False)
    canonical = _canonical_evidence_check(name)
    if not canonical:
        return None
    return canonical, optional


def _canonical_evidence_check(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    for canonical, aliases in EVIDENCE_CHECK_ALIASES.items():
        if normalized in aliases:
            return canonical
    return ""


def _expected_patterns_for_check(
    check: str,
    payload: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
) -> list[str]:
    patterns: list[str] = []
    for key in EVIDENCE_PAYLOAD_PATH_KEYS[check]:
        patterns.extend(_path_values(payload.get(key)))
        patterns.extend(_path_values(workflow.get(key)))
        patterns.extend(_path_values(action_spec.get(key)))
    if check == "readback":
        patterns.extend(_path_values(workflow.get("readback_evidence_paths")))
        patterns.extend(_path_values(action_spec.get("readback_evidence_paths")))
    for value in [*(workflow.get("expected_artifacts") or []), *(action_spec.get("expected_artifacts") or [])]:
        text = str(value)
        if _artifact_matches_check(check, text):
            patterns.append(text)
    return _unique_strings(patterns)


def _artifact_matches_check(check: str, value: str) -> bool:
    lowered = value.lower()
    return any(keyword in lowered for keyword in EVIDENCE_ARTIFACT_KEYWORDS[check])


def _path_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        for key in ("path", "artifact_path", "summary_path", "file"):
            if str(value.get(key) or "").strip():
                return [str(value[key])]
        return []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_path_values(item))
        return values
    return []


def _matching_artifact_paths(root: Path, patterns: list[str]) -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    missing: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        resolved = _resolve_inside(root, Path(pattern))
        matches = sorted(Path(path).resolve() for path in glob.glob(str(resolved)))
        if not _has_glob(pattern):
            matches = [resolved] if resolved.is_file() else []
        file_matches = [path for path in matches if path.is_file()]
        if not file_matches:
            missing.append(str(resolved))
            continue
        for path in file_matches:
            path_key = str(path)
            if path_key not in seen:
                seen.add(path_key)
                paths.append(path)
    return paths, missing


def _has_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def _changed_counts(payload: dict[str, Any]) -> dict[str, int]:
    counts = payload.get("changed_object_counts") or payload.get("changed_counts") or {}
    if isinstance(counts, dict):
        return {str(key): int(value) for key, value in counts.items() if isinstance(value, int | float)}
    changed = payload.get("changed_objects") or {}
    if isinstance(changed, dict):
        return {str(key): len(value) for key, value in changed.items() if isinstance(value, list)}
    return {}


def _summary_requirements_from_action(action_spec: dict[str, Any]) -> dict[str, Any]:
    raw = action_spec.get("summary_requirements") or action_spec.get("summary_contract") or {}
    if not isinstance(raw, dict) or not raw:
        return {}
    required_fields = raw.get("required_fields") or raw.get("fields") or []
    if isinstance(required_fields, str):
        required_fields = [required_fields]
    return {
        "required_fields": [str(field) for field in required_fields if str(field).strip()],
        "branch_status": str(raw.get("branch_status") or raw.get("expected_branch_status") or "").strip(),
        "changed_counts_required": bool(raw.get("changed_counts_required", True)),
        "target_ids_required": bool(raw.get("target_ids_required", True)),
        "evidence_paths_required": bool(raw.get("evidence_paths_required", True)),
    }


def _validate_summary_requirements(
    payload: dict[str, Any],
    *,
    manifest: dict[str, Any],
    requirements: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    if not requirements:
        return {"ok": True, "blocking_issues": [], "checked_fields": []}
    blocking_issues: list[dict[str, Any]] = []
    checked_fields: list[str] = []
    required_fields = requirements.get("required_fields") or MIGRATION_SUMMARY_REQUIRED_FIELDS
    for field in required_fields:
        checked_fields.append(str(field))
        if _summary_requirement_present(str(field), payload, manifest):
            continue
        blocking_issues.append(
            {
                "severity": "error",
                "rule": "missing_summary_required_field",
                "check": "summary_requirements",
                "action": action,
                "field": str(field),
                "blocking": True,
                "message": f"summary_requirements declares {field!r}, but the summary did not provide it.",
            }
        )
    expected_branch_status = str(requirements.get("branch_status") or "").strip()
    actual_branch_status = str(payload.get("branch_status") or payload.get("branch") or "").strip()
    if expected_branch_status and actual_branch_status and actual_branch_status != expected_branch_status:
        blocking_issues.append(
            {
                "severity": "error",
                "rule": "unexpected_branch_status",
                "check": "summary_requirements",
                "action": action,
                "expected": expected_branch_status,
                "actual": actual_branch_status,
                "blocking": True,
                "message": f"summary branch_status must be {expected_branch_status!r}.",
            }
        )
    return {"ok": not blocking_issues, "blocking_issues": blocking_issues, "checked_fields": checked_fields}


def _summary_requirement_present(field: str, payload: dict[str, Any], manifest: dict[str, Any]) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", field.lower()).strip("_")
    if normalized == "workbook_id":
        return _exact_id(payload.get("workbook_id"))
    if normalized in {"dashboard_id", "dashboard_ids"}:
        if _exact_id(payload.get("dashboard_id")):
            return True
        ids = payload.get("dashboard_ids")
        return isinstance(ids, list) and any(_exact_id(item) for item in ids)
    if normalized == "target_ids":
        target_ids = payload.get("target_ids")
        return (isinstance(target_ids, dict) and bool(target_ids)) or isinstance(
            payload.get("object_ids") or payload.get("changed_object_ids"),
            dict,
        )
    if normalized == "branch_status":
        return bool(str(payload.get("branch_status") or payload.get("branch") or "").strip())
    if normalized in {"changed_counts", "changed_count", "changed_object_counts"}:
        return any(key in payload for key in ("changed_object_counts", "changed_counts", "changed_objects"))
    if normalized in {"evidence_paths", "evidence"}:
        return bool(_path_values(payload.get("evidence_paths") or payload.get("readback_evidence_paths") or []))
    return normalized in payload and payload.get(normalized) not in (None, "", [])


def _summary_target_ids(payload: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    target_ids = payload.get("target_ids")
    if isinstance(target_ids, dict) and target_ids:
        return target_ids
    ids: dict[str, Any] = {}
    if _exact_id(payload.get("workbook_id")):
        ids["workbook_id"] = payload.get("workbook_id")
    dashboard_ids = payload.get("dashboard_ids")
    if isinstance(dashboard_ids, list) and any(_exact_id(item) for item in dashboard_ids):
        ids["dashboard_ids"] = [str(item) for item in dashboard_ids if _exact_id(item)]
    elif _exact_id(payload.get("dashboard_id")):
        ids["dashboard_ids"] = [payload.get("dashboard_id")]
    object_ids = payload.get("object_ids") or payload.get("changed_object_ids")
    if isinstance(object_ids, dict) and object_ids:
        ids["object_ids"] = object_ids
    if not ids and _exact_id(manifest.get("workbook_id")):
        ids["workbook_id"] = manifest.get("workbook_id")
    return ids


def _exact_id(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and not text.startswith("<"))


def _safe_manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    required_env_validation = _validate_required_env_name_list(
        manifest.get("required_env_names") or [],
        allowed_sensitive_names=_allowed_sensitive_required_env_names(manifest, {}, {}),
    )
    return {
        "schema_version": manifest.get("schema_version") or "",
        "project_name": manifest.get("project_name") or manifest.get("name") or "",
        "workbook_id": manifest.get("workbook_id") or "",
        "dashboard_ids": manifest.get("dashboard_ids") or [],
        "workflow_count": len(manifest.get("workflows") or []),
        "required_env_names": required_env_validation["allowed_env_names"],
        "rejected_required_env_names": required_env_validation["rejected_env_names"],
    }


def _workflow_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": workflow.get("name") or "",
        "modes": _workflow_modes(workflow),
        "may_execute_command": bool(workflow.get("may_execute_command", workflow.get("may_execute", False))),
        "allow_publish": bool(workflow.get("allow_publish", False)),
        "affected_objects": workflow.get("affected_objects") or [],
        "expected_artifacts": _expected_artifacts(workflow, {}),
        "evidence_checks": workflow.get("evidence_checks") or [],
        "safe_constraints": workflow.get("safe_constraints") or workflow.get("write_safety_constraints") or {},
        "summary_requirements_by_action": {
            action: _summary_requirements_from_action(spec)
            for action, spec in workflow.items()
            if action in PROJECT_LIVE_ACTIONS and isinstance(spec, dict) and _summary_requirements_from_action(spec)
        },
    }


def _workflow_modes(workflow: dict[str, Any]) -> list[str]:
    modes = []
    for mode in ("validate", "dry_run", "apply", "publish", "readback", RETIRE_ACTION):
        if isinstance(workflow.get(mode), dict) or workflow.get(f"{mode}_command"):
            modes.append(mode)
    if workflow.get("dry_run_command") and "dry_run" not in modes:
        modes.append("dry_run")
    return modes


def _required_env_names(manifest: dict[str, Any], workflow: dict[str, Any], action_spec: dict[str, Any]) -> list[str]:
    return _required_env_validation(manifest, workflow, action_spec)["allowed_env_names"]


def _required_env_validation(manifest: dict[str, Any], workflow: dict[str, Any], action_spec: dict[str, Any]) -> dict[str, Any]:
    names = _declared_required_env_names(manifest, workflow, action_spec)
    return _validate_required_env_name_list(
        names,
        allowed_sensitive_names=_allowed_sensitive_required_env_names(manifest, workflow, action_spec),
    )


def _declared_required_env_names(manifest: dict[str, Any], workflow: dict[str, Any], action_spec: dict[str, Any]) -> list[str]:
    names = [
        *(manifest.get("required_env_names") or []),
        *(workflow.get("required_env_names") or []),
        *(action_spec.get("required_env_names") or []),
    ]
    return sorted({str(name) for name in names if str(name).strip()})


def _validate_required_env_name_list(
    names: list[str],
    *,
    allowed_sensitive_names: set[str],
) -> dict[str, Any]:
    allowed_env_names: list[str] = []
    rejected_env_names: list[dict[str, str]] = []
    issues: list[str] = []
    for raw_name in names:
        name = str(raw_name or "").strip()
        rejection = _required_env_name_rejection(name, allowed_sensitive_names)
        if rejection:
            display = _display_required_env_name(name)
            rejected_env_names.append({"name": display, "reason": rejection})
            issues.append(f"required env name is not allowed ({rejection}): {display}")
            continue
        allowed_env_names.append(name)
    allowed_env_names = sorted(dict.fromkeys(allowed_env_names))
    return {
        "ok": not rejected_env_names,
        "allowed_env_names": allowed_env_names,
        "rejected_env_names": rejected_env_names,
        "allowed_sensitive_env_names": sorted(allowed_sensitive_names),
        "issues": issues,
    }


def _required_env_name_rejection(name: str, allowed_sensitive_names: set[str]) -> str:
    if not REQUIRED_ENV_NAME_RE.fullmatch(name):
        return "invalid_format"
    if name in INJECTED_DATALENS_ENV_NAMES or _is_base_project_env_name(name):
        return ""
    if _is_sensitive_required_env_name(name):
        if name in allowed_sensitive_names:
            return ""
        return "sensitive_name_requires_safe_constraints"
    if name.startswith(RESERVED_PARENT_ENV_PREFIXES):
        if name in allowed_sensitive_names:
            return ""
        return "reserved_parent_env_prefix_requires_safe_constraints"
    value = os.getenv(name)
    if value and looks_like_secret_value(value) and name not in allowed_sensitive_names:
        return "secret_like_value_requires_safe_constraints"
    return ""


def _is_sensitive_required_env_name(name: str) -> bool:
    return is_sensitive_key(name) or bool(SUSPICIOUS_REQUIRED_ENV_NAME_RE.search(name))


def _display_required_env_name(name: str) -> str:
    return "<redacted-env-name>" if _is_sensitive_required_env_name(name) else name


def _allowed_sensitive_required_env_names(
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
) -> set[str]:
    allowed: set[str] = set()
    for constraints in _safe_constraint_objects(manifest, workflow, action_spec):
        for key in SENSITIVE_ENV_ALLOWLIST_KEYS:
            value = constraints.get(key)
            if isinstance(value, str):
                allowed.add(value.strip())
            elif isinstance(value, list):
                allowed.update(str(item).strip() for item in value if str(item).strip())
    return {name for name in allowed if REQUIRED_ENV_NAME_RE.fullmatch(name)}


def _safe_constraint_objects(
    manifest: dict[str, Any],
    workflow: dict[str, Any],
    action_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for container in (manifest, workflow, action_spec):
        for key in ("safe_constraints", "write_safety_constraints"):
            value = container.get(key)
            if isinstance(value, dict):
                objects.append(value)
    return objects


def _is_base_project_env_name(name: str) -> bool:
    return name in BASE_PROJECT_ENV_NAMES or name.startswith(BASE_PROJECT_ENV_PREFIXES)


def _expected_artifacts(workflow: dict[str, Any], action_spec: dict[str, Any]) -> list[str]:
    values = [
        *(workflow.get("expected_artifacts") or []),
        *(action_spec.get("expected_artifacts") or []),
        *(workflow.get("readback_evidence_paths") or []),
        *(action_spec.get("readback_evidence_paths") or []),
    ]
    for key in ("summary_path", "summary_json_path"):
        if workflow.get(key):
            values.append(workflow[key])
        if action_spec.get(key):
            values.append(action_spec[key])
    return [str(value) for value in values if str(value).strip()]


def _detect_script_patterns(root: Path) -> list[str]:
    detected: list[str] = []
    for pattern in SCRIPT_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                detected.append(str(path.relative_to(root)))
    return detected[:50]


def _suggested_manifest(root: Path, detected_scripts: list[str]) -> dict[str, Any]:
    if detected_scripts:
        script_path = detected_scripts[0]
    else:
        script_path = "scripts/datalens_live_workflow.py"
    affected_objects = [
        {"type": "workbook", "id": "<workbook_id>"},
        {"type": "dashboard", "id": "<dashboard_id>"},
    ]
    return {
        "path": str(root / ".datalens-mcp.json"),
        "schema_version": "2026-07-01.project_live_workflow_manifest.v4",
        "project_name": root.name,
        "workbook_id": "<workbook_id>",
        "dashboard_ids": ["<dashboard_id>"],
        "target": {"workbook_id": "<workbook_id>", "dashboard_ids": ["<dashboard_id>"]},
        "manifest_requirements": REQUIRED_MIGRATION_MANIFEST_FIELDS,
        "summary_required_fields": MIGRATION_SUMMARY_REQUIRED_FIELDS,
        "allowed_live_operations": {
            "validate": True,
            "dry_run": True,
            "save": False,
            "publish": False,
        },
        "workflows": [
            {
                "name": "default_live_workflow",
                "may_execute_command": False,
                "allow_publish": False,
                "affected_objects": affected_objects,
                "expected_changed_object_groups": ["dashboards", "editor_charts"],
                "safe_constraints": {
                    "save_first": True,
                    "publish_default": False,
                    "delete_move_permission_operations": False,
                },
                "validate": _migration_action_step(
                    command=["python3", script_path, "--validate"],
                    summary_path="reports/datalens_validate_summary.json",
                    branch_status="validated",
                    expected_artifacts=["artifacts/validation/dashboard_payload_preflight.json"],
                ),
                "dry_run": _migration_action_step(
                    command=["python3", script_path, "--dry-run"],
                    summary_path="reports/datalens_dry_run_summary.json",
                    branch_status="dry_run",
                    expected_artifacts=[
                        "artifacts/validation/dashboard_payload_preflight.json",
                        "artifacts/validation/editor_sql_lint.json",
                        "artifacts/target_lock.json",
                    ],
                ),
                "apply": _migration_action_step(
                    command=["python3", script_path, "--save"],
                    summary_path="reports/datalens_save_summary.json",
                    branch_status="saved",
                    expected_artifacts=[
                        "artifacts/readback/dashboard.saved.latest.json",
                        "artifacts/safe_apply/save_report.json",
                    ],
                ),
                "readback": _migration_action_step(
                    command=["python3", script_path, "--readback", "--branch", "saved"],
                    summary_path="reports/datalens_saved_readback_summary.json",
                    branch_status="saved_readback",
                    expected_artifacts=["artifacts/readback/dashboard.saved.latest.json"],
                ),
                "publish": _migration_action_step(
                    command=["python3", script_path, "--publish-from-saved"],
                    summary_path="reports/datalens_publish_summary.json",
                    branch_status="published",
                    expected_artifacts=[
                        "artifacts/readback/dashboard.saved.latest.json",
                        "artifacts/readback/dashboard.published.latest.json",
                    ],
                ),
            }
        ],
    }


def _migration_action_step(
    *,
    command: list[str],
    summary_path: str,
    branch_status: str,
    expected_artifacts: list[str],
) -> dict[str, Any]:
    return {
        "command": command,
        "summary_path": summary_path,
        "expected_artifacts": expected_artifacts,
        "evidence_checks": list(DEFAULT_MIGRATION_EVIDENCE_CHECKS),
        "summary_requirements": {
            "branch_status": branch_status,
            "required_fields": list(MIGRATION_SUMMARY_REQUIRED_FIELDS),
            "changed_counts_required": True,
            "target_ids_required": True,
            "evidence_paths_required": True,
        },
    }


def _local_object_registry(root: Path) -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    payload_plan = root / "artifacts" / "payload_plan.json"
    if payload_plan.is_file():
        try:
            payloads = json.loads(payload_plan.read_text(encoding="utf-8")).get("payloads") or []
        except Exception:  # noqa: BLE001
            payloads = []
        for item in payloads:
            if isinstance(item, dict):
                registry.append(
                    {
                        "local_id": str(item.get("widget_id") or item.get("object_id") or ""),
                        "method": str(item.get("method") or ""),
                        "payload_path": str(item.get("payload_path") or ""),
                    }
                )
    for bundle in sorted(root.glob("dashboard/*/bundle.json"))[:50]:
        registry.append({"local_id": bundle.parent.name, "object_type": "editor_chart", "source_path": str(bundle.relative_to(root))})
    return registry[:100]


def _manifest_source_paths(root: Path) -> list[str]:
    candidates = [
        "README.md",
        "requirements",
        "dashboard",
        "artifacts/payload_plan.json",
        "artifacts/dashboard_object_relations.json",
        "datalens_mapping",
    ]
    return [item for item in candidates if (root / item).exists()]


def _selector_parameter_contracts(root: Path) -> list[dict[str, Any]]:
    relations_path = root / "artifacts" / "dashboard_object_relations.json"
    if not relations_path.is_file():
        return []
    try:
        relations = json.loads(relations_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    contracts = []
    for item in relations.get("relations") or relations.get("links") or []:
        if isinstance(item, dict):
            contracts.append(
                {
                    "source": str(item.get("source") or item.get("from") or ""),
                    "target": str(item.get("target") or item.get("to") or ""),
                    "parameter": str(item.get("param") or item.get("parameter") or ""),
                }
            )
    return contracts[:100]


def _resolve_inside(root: Path, path: Path) -> Path:
    resolved = path if path.is_absolute() else root / path
    resolved = resolved.resolve()
    if not _is_inside(root, resolved):
        raise ValueError(f"path must stay inside project_root: {path}")
    return resolved


def _is_inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _first(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return ""
