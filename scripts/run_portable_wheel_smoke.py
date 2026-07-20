#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


_ISOLATION_ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
)


def _isolated_subprocess_env() -> tuple[dict[str, str], list[str]]:
    env = dict(os.environ)
    removed = [key for key in _ISOLATION_ENV_KEYS if key in env]
    for key in _ISOLATION_ENV_KEYS:
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env, removed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_is_within(path: str, parent: Path) -> bool:
    try:
        Path(path).resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a wheel in a temporary venv and run portable runtime smoke.")
    parser.add_argument("--wheel", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cwd", default=tempfile.gettempdir())
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    out = Path(args.out).resolve()
    script = Path(__file__).with_name("smoke_portable_runtime.py").resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    isolated_env, removed_env_keys = _isolated_subprocess_env()
    wheel_sha256 = _sha256_file(wheel)
    import_probe = (
        "import datalens_dev_mcp,json,sys;"
        "print(json.dumps({'module_path':datalens_dev_mcp.__file__,'prefix':sys.prefix},sort_keys=True))"
    )
    with tempfile.TemporaryDirectory(dir=str(out.parent)) as tmp:
        venv_dir = Path(tmp) / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python_bin = venv_dir / "bin" / "python"
        install = subprocess.run(
            [
                str(python_bin),
                "-I",
                "-m",
                "pip",
                "install",
                "--force-reinstall",
                "--no-deps",
                "--no-index",
                str(wheel),
            ],
            env=isolated_env,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        verify_import = subprocess.run(
            [str(python_bin), "-I", "-c", import_probe],
            env=isolated_env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        import_details: dict[str, str] = {}
        try:
            loaded = json.loads(verify_import.stdout)
            if isinstance(loaded, dict):
                import_details = {
                    "module_path": str(loaded.get("module_path") or ""),
                    "prefix": str(loaded.get("prefix") or ""),
                }
        except Exception:
            import_details = {}
        import_inside_venv = bool(
            import_details.get("module_path")
            and _path_is_within(import_details["module_path"], venv_dir)
            and import_details.get("prefix")
            and Path(import_details["prefix"]).resolve() == venv_dir.resolve()
        )
        run = subprocess.run(
            [str(python_bin), "-I", str(script)],
            cwd=args.cwd,
            env=isolated_env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    payload = {
        "wheel": str(wheel),
        "wheel_sha256": wheel_sha256,
        "wheel_size_bytes": wheel.stat().st_size,
        "cwd": args.cwd,
        "isolation": {
            "isolated_mode": True,
            "removed_environment_keys": removed_env_keys,
            "python_no_user_site": True,
        },
        "install": {
            "returncode": install.returncode,
            "stdout_tail": install.stdout[-1000:],
            "stderr_tail": install.stderr[-1000:],
        },
        "import_verification": {
            "returncode": verify_import.returncode,
            "module_path": import_details.get("module_path", ""),
            "prefix": import_details.get("prefix", ""),
            "inside_temporary_venv": import_inside_venv,
            "stdout_tail": verify_import.stdout[-1000:],
            "stderr_tail": verify_import.stderr[-1000:],
        },
        "run": {
            "returncode": run.returncode,
            "stdout": run.stdout,
            "stderr_tail": run.stderr[-1000:],
        },
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = False
    try:
        ok = (
            install.returncode == 0
            and verify_import.returncode == 0
            and import_inside_venv
            and run.returncode == 0
            and json.loads(run.stdout).get("ok") is True
        )
    except Exception:
        ok = False
    print(
        json.dumps(
            {
                "ok": ok,
                "install": install.returncode,
                "import": verify_import.returncode,
                "import_inside_temporary_venv": import_inside_venv,
                "run": run.returncode,
                "wheel_sha256": wheel_sha256,
                "artifact": str(out),
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
