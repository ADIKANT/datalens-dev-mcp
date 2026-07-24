from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
import time
from typing import Any

from datalens_dev_mcp.pipeline.project_live_workflows import (
    _tracked_source_mutation_result,
    _tracked_source_snapshot,
)
from datalens_dev_mcp.validators.redaction import (
    redact_text,
    secret_values_from_mapping,
)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _heartbeat(
    *,
    stop: Event,
    status_path: Path,
    execution_id: str,
    target_pid: int,
    started_epoch: float,
    deadline_epoch: float,
) -> None:
    while not stop.wait(2):
        _atomic_json(
            status_path,
            {
                "schema_version": "2026-07-23.project_live_worker_status.v1",
                "execution_id": execution_id,
                "status": "running",
                "target_pid": target_pid,
                "heartbeat_epoch": time.time(),
                "started_epoch": started_epoch,
                "deadline_epoch": deadline_epoch,
            },
        )


def run_worker(spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    root = Path(str(spec["project_root"])).resolve()
    execution_id = str(spec["execution_id"])
    status_path = Path(str(spec["worker_status_path"]))
    result_path = Path(str(spec["worker_result_path"]))
    stdout_path = Path(str(spec["stdout_path"]))
    stderr_path = Path(str(spec["stderr_path"]))
    timeout_sec = max(1, int(spec.get("timeout_sec") or 1))
    started_epoch = float(spec.get("started_epoch") or time.time())
    deadline_epoch = started_epoch + timeout_sec
    secrets = secret_values_from_mapping(dict(os.environ))
    mutation_before = (
        _tracked_source_snapshot(root)
        if bool(spec.get("mutation_guarded"))
        else {"available": False, "files": {}}
    )
    target: subprocess.Popen[str] | None = None
    stop = Event()
    heartbeat: Thread | None = None
    try:
        target = subprocess.Popen(
            [str(item) for item in spec["command"]],
            cwd=root,
            env=dict(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        _atomic_json(
            status_path,
            {
                "schema_version": "2026-07-23.project_live_worker_status.v1",
                "execution_id": execution_id,
                "status": "running",
                "target_pid": target.pid,
                "heartbeat_epoch": time.time(),
                "started_epoch": started_epoch,
                "deadline_epoch": deadline_epoch,
            },
        )
        heartbeat = Thread(
            target=_heartbeat,
            kwargs={
                "stop": stop,
                "status_path": status_path,
                "execution_id": execution_id,
                "target_pid": target.pid,
                "started_epoch": started_epoch,
                "deadline_epoch": deadline_epoch,
            },
            daemon=True,
        )
        heartbeat.start()
        timed_out = False
        try:
            stdout, stderr = target.communicate(timeout=max(0.1, deadline_epoch - time.time()))
        except subprocess.TimeoutExpired:
            timed_out = True
            target.terminate()
            try:
                stdout, stderr = target.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                target.kill()
                stdout, stderr = target.communicate()
        mutation_guard = _tracked_source_mutation_result(root, mutation_before)
        safe_stdout = redact_text(stdout or "", secret_values=secrets)
        safe_stderr = redact_text(stderr or "", secret_values=secrets)
        _atomic_text(stdout_path, safe_stdout[:32_000])
        _atomic_text(stderr_path, safe_stderr[:32_000])
        result = {
            "schema_version": "2026-07-23.project_live_worker_result.v1",
            "execution_id": execution_id,
            "status": "timeout" if timed_out else "completed",
            "returncode": None if timed_out else target.returncode,
            "timed_out": timed_out,
            "target_pid": target.pid,
            "started_epoch": started_epoch,
            "completed_epoch": time.time(),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "tracked_source_mutation_guard": mutation_guard,
        }
        _atomic_json(result_path, result)
        _atomic_json(
            status_path,
            {
                **result,
                "heartbeat_epoch": result["completed_epoch"],
            },
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        message = redact_text(str(exc), secret_values=secrets)[:1000]
        _atomic_text(stdout_path, "")
        _atomic_text(stderr_path, message)
        _atomic_json(
            result_path,
            {
                "schema_version": "2026-07-23.project_live_worker_result.v1",
                "execution_id": execution_id,
                "status": "worker_failed",
                "returncode": None,
                "timed_out": False,
                "target_pid": target.pid if target is not None else None,
                "started_epoch": started_epoch,
                "completed_epoch": time.time(),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "tracked_source_mutation_guard": {
                    "available": False,
                    "mutated": False,
                    "changed_paths": [],
                    "policy": "worker_failed_before_mutation_guard_completion",
                },
                "error": message or exc.__class__.__name__,
            },
        )
        return 1
    finally:
        stop.set()
        if heartbeat is not None:
            heartbeat.join(timeout=1)


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    return run_worker(Path(sys.argv[1]).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
