#!/usr/bin/env python3
"""Run the installed public-only autonomous workflow against one dedicated canary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

try:
    from public_stdio_client import PublicStdioClient, PublicStdioError
except ModuleNotFoundError:  # Imported as scripts.run_public_autonomy_canary in tests.
    from scripts.public_stdio_client import PublicStdioClient, PublicStdioError


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TOOLS = {
    "dl_task_start",
    "dl_task_resume",
    "dl_task_status",
    "dl_inspect",
    "dl_plan",
    "dl_execute",
    "dl_verify",
    "dl_evidence",
}


class CanaryFailure(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an installed public-only DataLens autonomy canary.")
    parser.add_argument("--python", required=True, help="Python executable from the isolated installed-wheel environment.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--object-id", required=True)
    parser.add_argument("--tab-id", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--marker", default="Public autonomy controlled canary")
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-live-writes", action="store_true")
    parser.add_argument("--confirm-dedicated-target", action="store_true")
    args = parser.parse_args()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        receipt = run_canary(args, out=out)
    except (CanaryFailure, PublicStdioError, OSError, subprocess.SubprocessError) as exc:
        receipt = {
            "schema_id": "datalens_public_autonomy_canary",
            "status": "blocked",
            "ok": False,
            "live_verified": False,
            "error": {"category": exc.__class__.__name__, "message": str(exc)[:1000]},
        }
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt.get("ok"), "status": receipt.get("status"), "receipt": str(out)}, sort_keys=True))
    return 0 if receipt.get("ok") else 1


def run_canary(args: argparse.Namespace, *, out: Path) -> dict[str, Any]:
    if not args.allow_live_writes or not args.confirm_dedicated_target:
        raise CanaryFailure("live writes require explicit approval and confirmation of the dedicated target")
    env_file = Path(args.env_file).expanduser().resolve()
    if not env_file.is_file():
        raise CanaryFailure("canonical env file is missing")
    if _git("rev-parse", "HEAD") != args.expected_head:
        raise CanaryFailure("current source head does not match expected frozen head")
    if _git("status", "--porcelain"):
        raise CanaryFailure("source tree is not frozen and clean")
    source_tree_hash = _publication_tree_hash()
    python = Path(args.python).expanduser().absolute()
    if not python.is_file():
        raise CanaryFailure("installed Python executable is missing")
    installed = _installed_identity(python)
    if installed.get("version") != "0.5.0" or not installed.get("isolated"):
        raise CanaryFailure("installed package identity is not isolated version 0.5.0")

    project_root = Path(args.project_root).resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "DATALENS_ENV_FILE": str(env_file),
            "DATALENS_MCP_TOOL_SURFACE": "autonomous-v2",
            "DATALENS_MCP_ENABLE_EXPERT_RPC": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    command = [
        str(python),
        "-I",
        "-m",
        "datalens_dev_mcp.server",
        "--project-root",
        str(project_root),
    ]
    client_args = {
        "cwd": project_root,
        "env": env,
        "timeout": 120.0,
    }
    stale_marker = f"{args.marker} stale-negative"
    main_context = _semantic_context(args.object_id, args.tab_id, args.marker)
    stale_context = _semantic_context(args.object_id, args.tab_id, stale_marker)

    with PublicStdioClient(command, stderr_path=out.with_suffix(".phase1.stderr.log"), **client_args) as client:
        initialize = client.initialize()
        tool_list = client.list_tools()
        _assert_public_surface(tool_list)
        stale = _start_plan(client, args, project_root, stale_context, suffix="stale-negative")
        planned = _start_plan(client, args, project_root, main_context, suffix="main")
        _write_checkpoint(
            project_root,
            {
                "state": "planned",
                "main_task_id": planned["task_id"],
                "main_plan_hash": planned["plan_hash"],
                "stale_task_id": stale["task_id"],
                "stale_plan_hash": stale["plan_hash"],
            },
        )
        evidence = client.call_tool(
            "dl_evidence",
            {
                "task_id": planned["task_id"],
                "project_root": str(project_root),
                "resource_uri": planned["plan_resource_uri"],
                "limit": 4_000,
            },
        )
        if not evidence.get("returned_chars"):
            raise CanaryFailure("public plan evidence is empty")
        saved = client.call_tool(
            "dl_execute",
            {
                "task_id": planned["task_id"],
                "plan_hash": planned["plan_hash"],
                "project_root": str(project_root),
                "stop_after": "saved",
            },
        )
        if saved.get("state") != "SAVED" or _fact_count(saved, "write count=1") != 1:
            raise CanaryFailure("main canary did not produce exactly one saved write")
        _write_checkpoint(
            project_root,
            {
                "state": "saved",
                "main_task_id": planned["task_id"],
                "main_plan_hash": planned["plan_hash"],
                "saved_state_etag": saved["state_etag"],
                "stale_task_id": stale["task_id"],
                "stale_plan_hash": stale["plan_hash"],
            },
        )

    with PublicStdioClient(command, stderr_path=out.with_suffix(".phase2.stderr.log"), **client_args) as client:
        client.initialize()
        _assert_public_surface(client.list_tools())
        status = client.call_tool(
            "dl_task_status",
            {"task_id": planned["task_id"], "project_root": str(project_root)},
        )
        if status.get("state") != "SAVED" or status.get("state_etag") != saved.get("state_etag"):
            raise CanaryFailure("new process did not recover the exact SAVED checkpoint")
        completed = client.call_tool(
            "dl_task_resume",
            {
                "task_id": planned["task_id"],
                "project_root": str(project_root),
                "expected_state": "SAVED",
                "expected_hash": saved["state_etag"],
                "run_until": "completed",
            },
        )
        if completed.get("state") != "COMPLETED":
            raise CanaryFailure("main canary did not complete after restart")
        if "VALIDATED -> SAVED" in completed.get("performed", []):
            raise CanaryFailure("save was repeated after restart")
        if _fact_count(completed, "write count=1") != 1:
            raise CanaryFailure("resume did not report exactly one publish write")
        if _fact_count(completed, "browser calls=0") != 1:
            raise CanaryFailure("forbidden browser policy did not prove zero calls")
        verified = client.call_tool(
            "dl_verify",
            {"task_id": planned["task_id"], "project_root": str(project_root)},
        )
        if not verified.get("ok") or verified.get("highest_proof_level") != "publish_readback":
            raise CanaryFailure("completion verification is not publish-readback complete")
        inspection = client.call_tool(
            "dl_inspect",
            {"task_id": planned["task_id"], "project_root": str(project_root)},
        )
        context = inspection.get("data_context") if isinstance(inspection.get("data_context"), dict) else {}
        profile_evidence = client.call_tool(
            "dl_evidence",
            {
                "task_id": planned["task_id"],
                "project_root": str(project_root),
                "resource_uri": str(context.get("resource_uri") or ""),
                "limit": 12_000,
            },
        )
        stale_result = client.call_tool(
            "dl_execute",
            {
                "task_id": stale["task_id"],
                "plan_hash": stale["plan_hash"],
                "project_root": str(project_root),
                "stop_after": "saved",
            },
        )
        if stale_result.get("state") in {"SAVED", "COMPLETED"}:
            raise CanaryFailure("stale revision negative unexpectedly wrote")
        if "VALIDATED -> SAVED" in stale_result.get("performed", []):
            raise CanaryFailure("stale revision negative reports a save transition")

    evidence_hashes = verified.get("evidence_hashes") if isinstance(verified.get("evidence_hashes"), dict) else {}
    typed_data_verified = bool(
        evidence_hashes.get("fresh_data_proof")
        and context.get("proof_level") == "live_read_only_api"
        and context.get("raw_rows_inline") is False
    )
    if not typed_data_verified:
        raise CanaryFailure("fresh typed data proof was not verified")
    if _git("rev-parse", "HEAD") != args.expected_head or _publication_tree_hash() != source_tree_hash:
        raise CanaryFailure("source changed during the controlled canary")
    artifact_values = {
        "installed_identity": installed,
        "initialize": initialize,
        "plan_evidence": evidence,
        "context_profile": profile_evidence,
        "completion": verified,
        "stale_negative": stale_result,
    }
    return {
        "schema_id": "datalens_public_autonomy_canary",
        "status": "completed",
        "surface": "autonomous-v2",
        "public_tools_only": True,
        "public_tool_count": 8,
        "installed_package": True,
        "package_version": installed["version"],
        "build_identity_hash": _hash({"installed": installed, "head": args.expected_head, "tree": source_tree_hash}),
        "exact_head": args.expected_head,
        "source_tree_sha256": source_tree_hash,
        "source_unchanged": True,
        "task_id": planned["task_id"],
        "contract_hash": verified["contract_hash"],
        "target_binding_hash": planned["target_binding_hash"],
        "style_binding_hash": planned["style_binding_hash"],
        "plan_hash": planned["plan_hash"],
        "save_write_count": 1,
        "publish_write_count": 1,
        "process_restart_after_save": True,
        "saved_readback_verified": bool(evidence_hashes.get("saved_readback_receipt")),
        "published_readback_verified": bool(evidence_hashes.get("published_readback_receipt")),
        "typed_data_verified": typed_data_verified,
        "dataset_data_semantics": context.get("dataset_data_semantics"),
        "raw_rows_inline": False,
        "browser_policy": "forbidden",
        "browser_call_count": 0,
        "stale_revision_write_count": 0,
        "completion_verified": True,
        "cleanup": {"executed": False, "policy": "dedicated canary retained in sandbox"},
        "artifact_hashes": {key: _hash(value) for key, value in sorted(artifact_values.items())},
        "live_verified": True,
        "ok": True,
    }


def _start_plan(
    client: PublicStdioClient,
    args: argparse.Namespace,
    project_root: Path,
    context: dict[str, Any],
    *,
    suffix: str,
) -> dict[str, Any]:
    result = client.call_tool(
        "dl_task_start",
        {
            "request": (
                f"Update the dedicated controlled dashboard {args.target_url} for the {suffix} canary, "
                "save and publish it without browser."
            ),
            "project_root": str(project_root),
            "context": context,
            "run_until": "plan_ready",
        },
    )
    if result.get("state") != "PLAN_VALIDATED" or not result.get("plan_hash"):
        raise CanaryFailure(f"{suffix} task did not reach a validated immutable plan")
    for key in ("target_binding_hash", "style_binding_hash", "plan_resource_uri"):
        if not result.get(key):
            raise CanaryFailure(f"{suffix} task is missing {key}")
    return result


def _semantic_context(object_id: str, tab_id: str, value: str) -> dict[str, Any]:
    return {
        "semantic_changes": [
            {
                "target_id": object_id,
                "tab": tab_id,
                "anchor": {"kind": "json_pointer", "pointer": "/data/supportDescription"},
                "value": value,
            }
        ]
    }


def _assert_public_surface(tool_list: dict[str, Any]) -> None:
    names = {str(item.get("name") or "") for item in tool_list.get("tools") or [] if isinstance(item, dict)}
    if tool_list.get("tool_surface") != "autonomous-v2" or names != PUBLIC_TOOLS:
        raise CanaryFailure(f"installed stdio surface is not the exact 8-tool autonomous-v2 surface: {sorted(names)}")


def _installed_identity(python: Path) -> dict[str, Any]:
    probe = subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            (
                "import datalens_dev_mcp,json,pathlib,sys;"
                "print(json.dumps({'module':datalens_dev_mcp.__file__,'version':datalens_dev_mcp.__version__,"
                "'prefix':sys.prefix},sort_keys=True))"
            ),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if probe.returncode:
        raise CanaryFailure("installed package identity probe failed")
    value = json.loads(probe.stdout)
    module = Path(str(value.get("module") or "")).resolve()
    prefix = Path(str(value.get("prefix") or "")).resolve()
    return {
        "module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "version": str(value.get("version") or ""),
        "isolated": module.is_relative_to(prefix) and not module.is_relative_to(ROOT),
    }


def _publication_tree_hash() -> str:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if listed.returncode:
        raise CanaryFailure("cannot enumerate frozen publication tree")
    digest = hashlib.sha256()
    for raw in sorted(item for item in listed.stdout.split(b"\0") if item):
        relative = Path(raw.decode("utf-8"))
        path = ROOT / relative
        if path.is_file() and not path.is_symlink():
            digest.update(relative.as_posix().encode("utf-8") + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise CanaryFailure(f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _fact_count(payload: dict[str, Any], fact: str) -> int:
    return sum(str(item) == fact for item in payload.get("observed_facts") or [])


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_checkpoint(project_root: Path, value: dict[str, Any]) -> None:
    path = project_root / "public-autonomy-canary-checkpoint.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
