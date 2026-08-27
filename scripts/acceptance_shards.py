from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def publication_tree_hash() -> tuple[str, int]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("cannot enumerate publication tree")
    digest = hashlib.sha256()
    count = 0
    for raw in sorted(item for item in result.stdout.split(b"\0") if item):
        relative = Path(raw.decode("utf-8"))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("unsafe publication path")
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            continue
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        count += 1
    return digest.hexdigest(), count


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def py(*parts: str) -> list[str]:
    return [sys.executable, *parts]


ACCEPTANCE_SURFACES = frozenset({"autonomous-v2", "legacy-v1"})
AUTONOMOUS_PROFILES = frozenset({"autonomy", "affected", "full-sharded", "public-autonomy"})


def run_acceptance(
    name: str,
    shards: list[dict[str, Any]],
    *,
    surface: str,
    output: Path | None = None,
) -> dict[str, Any]:
    declared_surface = str(surface or "").strip()
    if declared_surface not in ACCEPTANCE_SURFACES:
        raise ValueError(f"acceptance surface must be one of: {', '.join(sorted(ACCEPTANCE_SURFACES))}")
    if name in AUTONOMOUS_PROFILES and declared_surface != "autonomous-v2":
        raise ValueError(f"{name} acceptance must declare autonomous-v2")
    for shard in shards:
        shard_surface = str(shard.get("surface") or declared_surface)
        if shard_surface != declared_surface:
            raise ValueError(f"shard {shard.get('name')!r} changes the declared acceptance surface")
        leaked = str((shard.get("env") or {}).get("DATALENS_MCP_TOOL_SURFACE") or "")
        if leaked and leaked != declared_surface:
            raise ValueError(f"shard {shard.get('name')!r} overrides the declared acceptance surface")
    started = time.perf_counter()
    source_hash, file_count = publication_tree_hash()
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{os.getpid()}"
    run_dir = ROOT / "artifacts" / "autonomy" / "acceptance" / f"{name}-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    base_env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONFAULTHANDLER": "1",
        "DATALENS_MCP_TOOL_SURFACE": declared_surface,
        "DATALENS_MCP_RUN_ARTIFACT_DIR": str(run_dir / "mcp_runs"),
    }
    results: list[dict[str, Any]] = []
    for index, shard in enumerate(shards, start=1):
        shard_started = time.perf_counter()
        commands = shard.get("commands") or [shard["command"]]
        command_results = []
        status = "passed"
        for command_index, command in enumerate(commands, start=1):
            print(f"+ [{shard['name']}:{command_index}] {' '.join(command)}", file=sys.stderr, flush=True)
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env={**base_env, **(shard.get("env") or {})},
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=int(shard.get("timeout_sec") or 600),
                    check=False,
                )
                returncode = completed.returncode
                stdout = completed.stdout
                stderr = completed.stderr
            except subprocess.TimeoutExpired as exc:
                returncode = 124
                stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
                stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(errors="replace")
                stderr += "\nacceptance command timed out"
            stdout_path = run_dir / f"{index:02d}-{shard['name']}-{command_index:02d}.stdout.log"
            stderr_path = run_dir / f"{index:02d}-{shard['name']}-{command_index:02d}.stderr.log"
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            command_results.append(
                {
                    "returncode": returncode,
                    "command": command,
                    "stdout_sha256": _file_sha(stdout_path),
                    "stderr_sha256": _file_sha(stderr_path),
                }
            )
            if returncode != 0:
                status = "failed"
                diagnostic = (stderr or stdout or "acceptance command failed without output")[-12_000:]
                print(diagnostic, file=sys.stderr, flush=True)
                break
        results.append(
            {
                "name": shard["name"],
                "status": status,
                "duration_ms": round((time.perf_counter() - shard_started) * 1000, 3),
                "commands": command_results,
            }
        )
        if status == "failed":
            break
    current_hash, current_count = publication_tree_hash()
    report = {
        "schema_id": "datalens_autonomy_acceptance_receipt",
        "profile": name,
        "declared_surface": declared_surface,
        "effective_surface": declared_surface,
        "surface_consistent": True,
        "ok": len(results) == len(shards) and all(item["status"] == "passed" for item in results),
        "exact_head": git_head(),
        "source_tree_sha256": source_hash,
        "source_file_count": file_count,
        "source_unchanged": current_hash == source_hash and current_count == file_count,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "defined_shard_count": len(shards),
        "completed_shard_count": len(results),
        "shards": results,
    }
    report["ok"] = bool(report["ok"] and report["source_unchanged"])
    target = output or run_dir / "summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["receipt"] = {
        "path": _relative(target),
        "sha256": _file_sha(target),
    }
    return report


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": report["ok"],
        "profile": report["profile"],
        "declared_surface": report["declared_surface"],
        "effective_surface": report["effective_surface"],
        "surface_consistent": report["surface_consistent"],
        "exact_head": report["exact_head"],
        "source_tree_sha256": report["source_tree_sha256"],
        "source_unchanged": report["source_unchanged"],
        "duration_ms": report["duration_ms"],
        "receipt": report["receipt"],
        "shards": [
            {"name": item["name"], "status": item["status"], "duration_ms": item["duration_ms"]}
            for item in report["shards"]
        ],
    }


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)
