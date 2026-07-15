#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "validation_profiles"
PROFILE_SCHEMA_VERSION = "2026-07-01.validation_profiles.v1"
PROFILE_NAMES = ("quick", "standard", "full")
CONTROLLED_LIVE_ENABLE_ENV = "DATALENS_MCP_RUN_CONTROLLED_LIVE_PROOF"
CONTROLLED_LIVE_APPROVAL_ENV = "DATALENS_MCP_APPROVED_CONTROLLED_LIVE_WRITES"
CONTROLLED_LIVE_APPROVAL_NOTE_ENV = "DATALENS_MCP_CONTROLLED_LIVE_APPROVAL_NOTE"


FOCUSED_UNIT_MODULES = [
    "tests.unit.test_local_config",
    "tests.unit.test_tool_schemas",
    "tests.unit.test_clean_repo_surface",
    "tests.unit.test_local_runtime_cleanup",
    "tests.unit.test_editor_bundle",
    "tests.unit.test_standard_chart_templates",
    "tests.unit.test_chart_routing_wizard_js_only",
    "tests.unit.test_template_quality_gate",
    "tests.unit.test_full_corpus_editor_recipes",
    "tests.unit.test_full_corpus_runtime_integration",
    "tests.unit.test_semantic_authoring_acceptance",
    "tests.unit.test_sql_semantics_performance",
]


def py(*parts: str) -> list[str]:
    return [sys.executable, *parts]


def command_step(
    name: str,
    command: list[str],
    timeout: int,
    *,
    proof_levels: list[str] | None = None,
    heavy_artifacts: bool = False,
) -> dict[str, Any]:
    return {
        "kind": "command",
        "name": name,
        "command": command,
        "timeout_sec": timeout,
        "proof_levels": proof_levels or ["source_static"],
        "heavy_artifacts": heavy_artifacts,
    }


def skip_step(name: str, reason: str) -> dict[str, Any]:
    return {
        "kind": "skip",
        "name": name,
        "skip_reason": reason,
        "timeout_sec": 0,
        "proof_levels": ["source_static"],
        "heavy_artifacts": False,
    }


def docs_corpus_available() -> bool:
    candidates: list[Path] = []
    env_value = os.environ.get("DATALENS_DOCS_CORPUS_ROOT", "").strip()
    if env_value:
        candidates.append(Path(env_value).expanduser())
    candidates.append(ROOT / ".external" / "datalens-docs-corpus")
    return any((candidate / "pages.jsonl").is_file() and (candidate / "reports" / "update_report.md").is_file() for candidate in candidates)


def static_policy_steps() -> list[dict[str, Any]]:
    steps = [
        command_step("clean_runtime_artifacts", py("scripts/clean_local_runtime_artifacts.py"), 60),
        command_step("lint_local", py("scripts/lint_local.py"), 120),
        command_step("schema_validation", py("scripts/validate_schemas.py"), 120),
        command_step("runtime_resource_manifest", py("scripts/build_runtime_resource_manifest.py", "--check"), 120),
        command_step("js_template_contracts", py("scripts/check_js_templates.py"), 120),
        command_step("docs_consistency", py("scripts/check_docs_consistency.py"), 120),
        command_step("api_contract_policy", py("scripts/validate_api_contract_coverage.py"), 120),
        command_step("public_release_surface", py("scripts/check_public_release.py"), 120),
    ]
    if docs_corpus_available():
        steps.append(command_step("current_docs_policy", py("scripts/validate_current_datalens_docs_reconciliation.py"), 180))
    else:
        steps.append(
            skip_step(
                "current_docs_policy",
                "compact docs corpus mirror is unavailable; docs/API policy still covers API policy and active docs consistency",
            )
        )
    steps.append(command_step("stdio_smoke", py("scripts/smoke_mcp_stdio.py"), 30, proof_levels=["source_static", "installed_static"]))
    return steps


def quick_profile_steps() -> list[dict[str, Any]]:
    return [
        *static_policy_steps(),
        command_step("focused_unit_subset", py("-m", "unittest", *FOCUSED_UNIT_MODULES, "-v"), 300),
    ]


def standard_profile_steps() -> list[dict[str, Any]]:
    return [
        *static_policy_steps(),
        command_step("unit_tests", py("-m", "unittest", "discover", "-s", "tests/unit", "-p", "test_*.py", "-v"), 360),
        command_step(
            "integration_offline_tests",
            py("-m", "unittest", "discover", "-s", "tests/integration_offline", "-p", "test_*.py", "-v"),
            240,
        ),
        command_step("repo_size_budget", py("scripts/check_repo_size_budget.py", "--strict"), 120),
        command_step("sensitive_artifact_scan", py("scripts/scan_sensitive_artifacts.py", "."), 120),
    ]


def full_profile_steps() -> list[dict[str, Any]]:
    return [
        *standard_profile_steps(),
        {
            "kind": "wheel_build",
            "name": "package_wheel_build",
            "timeout_sec": 180,
            "proof_levels": ["installed_static"],
            "heavy_artifacts": True,
        },
        {
            "kind": "wheel_smoke",
            "name": "portable_wheel_smoke",
            "timeout_sec": 180,
            "proof_levels": ["installed_static"],
            "heavy_artifacts": True,
        },
        command_step("golden_runtime_gallery_fixtures", py("scripts/build_golden_runtime_gallery.py", "--check"), 120),
        {
            "kind": "controlled_live_optional",
            "name": "controlled_live_proof",
            "timeout_sec": 900,
            "proof_levels": ["controlled_live_write"],
            "heavy_artifacts": True,
        },
    ]


def profile_steps(profile: str) -> list[dict[str, Any]]:
    normalized = profile.strip().lower()
    if normalized == "quick":
        return quick_profile_steps()
    if normalized == "standard":
        return standard_profile_steps()
    if normalized == "full":
        return full_profile_steps()
    raise ValueError(f"profile must be one of {PROFILE_NAMES}")


def git_status() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return [f"<git status failed: {result.stderr.strip()}>"]
    return result.stdout.splitlines()


def artifact_metadata(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": relative_path(path),
        "serialized_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def command_text(command: list[str]) -> str:
    return " ".join(command)


def base_env(run_dir: Path) -> dict[str, str]:
    env = {**os.environ}
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT / "src") if not existing_pythonpath else f"{ROOT / 'src'}{os.pathsep}{existing_pythonpath}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONFAULTHANDLER"] = "1"
    env["DATALENS_MCP_RUN_ARTIFACT_DIR"] = str(run_dir / "mcp_runs")
    env["DATALENS_VALIDATION_ARTIFACT_DIR"] = str(run_dir)
    return env


def run_command_step(step: dict[str, Any], *, env: dict[str, str], run_dir: Path, index: int, context: dict[str, Any]) -> dict[str, Any]:
    if step["kind"] == "skip":
        return {
            "name": step["name"],
            "status": "skipped",
            "duration_ms": 0,
            "returncode": 0,
            "skip_reason": step["skip_reason"],
            "proof_levels": step.get("proof_levels", []),
            "heavy_artifacts": False,
        }
    if step["kind"] == "wheel_build":
        wheelhouse = run_dir / "wheelhouse"
        wheelhouse.mkdir(parents=True, exist_ok=True)
        step = {**step, "kind": "command", "command": py("-m", "pip", "wheel", ".", "--no-deps", "--wheel-dir", str(wheelhouse))}
        result = run_subprocess_step(step, env=env, run_dir=run_dir, index=index)
        wheels = sorted(wheelhouse.glob("datalens_dev_mcp-*.whl"))
        if result["status"] == "passed" and wheels:
            context["wheel_path"] = str(wheels[-1])
            result["wheel_artifact"] = artifact_metadata(wheels[-1])
        elif result["status"] == "passed":
            result["status"] = "failed"
            result["returncode"] = 1
            result["stderr_tail"] = "wheel build passed but no datalens_dev_mcp wheel was produced"
        return result
    if step["kind"] == "wheel_smoke":
        wheel_path = context.get("wheel_path")
        if not wheel_path:
            return skipped_result(step, "package_wheel_build did not produce a wheel")
        out_path = run_dir / "portable_wheel_smoke.json"
        cwd = tempfile.mkdtemp(prefix="datalens-wheel-smoke-")
        command = py("scripts/run_portable_wheel_smoke.py", "--wheel", str(wheel_path), "--out", str(out_path), "--cwd", cwd)
        step = {**step, "kind": "command", "command": command}
        result = run_subprocess_step(step, env=env, run_dir=run_dir, index=index)
        if out_path.is_file():
            result["smoke_artifact"] = artifact_metadata(out_path)
        return result
    if step["kind"] == "controlled_live_optional":
        if os.environ.get(CONTROLLED_LIVE_ENABLE_ENV) != "1":
            return skipped_result(step, f"{CONTROLLED_LIVE_ENABLE_ENV}=1 is not set")
        if os.environ.get(CONTROLLED_LIVE_APPROVAL_ENV) != "1":
            return skipped_result(step, f"{CONTROLLED_LIVE_APPROVAL_ENV}=1 is not set")
        approval_note = os.environ.get(CONTROLLED_LIVE_APPROVAL_NOTE_ENV, "").strip()
        workbook_id = os.environ.get("DATALENS_MCP_TEST_WORKBOOK_ID", "").strip()
        if not approval_note or not workbook_id:
            return skipped_result(step, "approval note and DATALENS_MCP_TEST_WORKBOOK_ID are required")
        out_path = run_dir / "controlled_live_proof.json"
        command = py(
            "scripts/run_controlled_live_lifecycle.py",
            "--out",
            str(out_path),
            "--test-workbook-id",
            workbook_id,
            "--confirm-disposable-workbook",
            "--approved-live-writes",
            "--approval-note",
            approval_note,
        )
        step = {**step, "kind": "command", "command": command}
        result = run_subprocess_step(step, env=env, run_dir=run_dir, index=index)
        if out_path.is_file():
            result["controlled_live_artifact"] = artifact_metadata(out_path)
        return result
    return run_subprocess_step(step, env=env, run_dir=run_dir, index=index)


def skipped_result(step: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "name": step["name"],
        "status": "skipped",
        "duration_ms": 0,
        "returncode": 0,
        "skip_reason": reason,
        "proof_levels": step.get("proof_levels", []),
        "heavy_artifacts": bool(step.get("heavy_artifacts")),
    }


def run_subprocess_step(step: dict[str, Any], *, env: dict[str, str], run_dir: Path, index: int) -> dict[str, Any]:
    name = step["name"]
    command = step["command"]
    timeout = int(step.get("timeout_sec") or 120)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"{index:02d}_{name}.stdout.log"
    stderr_path = logs_dir / f"{index:02d}_{name}.stderr.log"
    print(f"+ [{name}] {command_text(command)}", file=sys.stderr, flush=True)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        returncode = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        stderr = f"{stderr}\ncommand timed out after {timeout}s"
        returncode = 124
        timed_out = True
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    status = "passed" if returncode == 0 else "failed"
    return {
        "name": name,
        "status": status,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
        "timeout_sec": timeout,
        "command": command,
        "proof_levels": step.get("proof_levels", []),
        "heavy_artifacts": bool(step.get("heavy_artifacts")),
        "log_artifacts": {
            "stdout": artifact_metadata(stdout_path),
            "stderr": artifact_metadata(stderr_path),
        },
        "stdout_tail": stdout[-2000:] if returncode != 0 else "",
        "stderr_tail": stderr[-2000:] if returncode != 0 else "",
    }


def status_delta(before: list[str], after: list[str]) -> dict[str, list[str]]:
    before_set = set(before)
    after_set = set(after)
    return {
        "added": sorted(after_set - before_set),
        "removed": sorted(before_set - after_set),
    }


def run_profile(profile: str, *, artifact_root: Path = DEFAULT_ARTIFACT_ROOT) -> dict[str, Any]:
    normalized = profile.strip().lower()
    steps = profile_steps(normalized)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{os.getpid()}"
    run_dir = artifact_root / normalized / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = base_env(run_dir)
    before_status = git_status()
    started = time.perf_counter()
    context: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    failed = False
    for index, step in enumerate(steps, start=1):
        result = run_command_step(step, env=env, run_dir=run_dir, index=index, context=context)
        results.append(result)
        if result["status"] == "failed":
            failed = True
            break
    after_status = git_status()
    delta = status_delta(before_status, after_status)
    clean_tree_safe = not delta["added"] and not delta["removed"]
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    report = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "ok": not failed and clean_tree_safe,
        "profile": normalized,
        "run_id": run_id,
        "duration_ms": duration_ms,
        "artifact_dir": relative_path(run_dir),
        "clean_tree_safe": clean_tree_safe,
        "git_status_delta": delta,
        "step_count": len(results),
        "defined_step_count": len(steps),
        "timings": {
            "total_ms": duration_ms,
            "passed_ms": round(sum(item["duration_ms"] for item in results if item["status"] == "passed"), 3),
        },
        "steps": results,
    }
    report_path = run_dir / "summary.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["summary_artifact"] = artifact_metadata(report_path)
    return report


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    compact_steps = []
    for step in report["steps"]:
        row = {
            "name": step["name"],
            "status": step["status"],
            "returncode": step["returncode"],
            "duration_ms": step["duration_ms"],
        }
        if step.get("skip_reason"):
            row["skip_reason"] = step["skip_reason"]
        if step.get("log_artifacts"):
            row["log_artifacts"] = step["log_artifacts"]
        if step.get("wheel_artifact"):
            row["wheel_artifact"] = step["wheel_artifact"]
        if step.get("smoke_artifact"):
            row["smoke_artifact"] = step["smoke_artifact"]
        if step.get("controlled_live_artifact"):
            row["controlled_live_artifact"] = step["controlled_live_artifact"]
        if step.get("stderr_tail"):
            row["stderr_tail"] = step["stderr_tail"]
        compact_steps.append(row)
    return {
        "ok": report["ok"],
        "profile": report["profile"],
        "duration_ms": report["duration_ms"],
        "clean_tree_safe": report["clean_tree_safe"],
        "git_status_delta": report["git_status_delta"],
        "artifact_dir": report["artifact_dir"],
        "summary_artifact": report["summary_artifact"],
        "steps": compact_steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run datalens-dev-mcp validation profiles with timings and artifact-backed logs.")
    parser.add_argument("--profile", choices=PROFILE_NAMES, default="standard")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    args = parser.parse_args(argv)
    report = run_profile(args.profile, artifact_root=Path(args.artifact_root))
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
