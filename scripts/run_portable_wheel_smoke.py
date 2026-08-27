#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
import venv
import zipfile
from pathlib import Path, PurePosixPath

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


def _install_pure_wheel(
    wheel: Path,
    *,
    python_bin: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    purelib_probe = subprocess.run(
        [
            str(python_bin),
            "-I",
            "-c",
            "import sysconfig;print(sysconfig.get_path('purelib'))",
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if purelib_probe.returncode != 0:
        return purelib_probe
    purelib = Path(purelib_probe.stdout.strip()).resolve()
    try:
        with zipfile.ZipFile(wheel) as archive:
            wheel_metadata = next(
                (
                    name
                    for name in archive.namelist()
                    if name.endswith(".dist-info/WHEEL")
                ),
                "",
            )
            metadata_text = (
                archive.read(wheel_metadata).decode("utf-8", errors="replace")
                if wheel_metadata
                else ""
            )
            if "Root-Is-Purelib: true" not in metadata_text:
                raise ValueError("portable smoke supports only purelib wheels")
            written = 0
            for info in archive.infolist():
                member = PurePosixPath(info.filename)
                if info.is_dir():
                    continue
                if member.is_absolute() or ".." in member.parts:
                    raise ValueError(f"unsafe wheel member: {info.filename}")
                parts = list(member.parts)
                data_index = next(
                    (
                        index
                        for index, part in enumerate(parts)
                        if part.endswith(".data")
                    ),
                    -1,
                )
                if data_index >= 0:
                    if data_index + 1 >= len(parts) or parts[data_index + 1] != "purelib":
                        continue
                    parts = parts[data_index + 2 :]
                if not parts:
                    continue
                destination = purelib.joinpath(*parts).resolve()
                if not _path_is_within(str(destination), purelib):
                    raise ValueError(f"unsafe wheel destination: {info.filename}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(info))
                written += 1
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return subprocess.CompletedProcess(
            args=["pure-wheel-install", str(wheel)],
            returncode=1,
            stdout="",
            stderr=str(exc),
        )
    return subprocess.CompletedProcess(
        args=["pure-wheel-install", str(wheel)],
        returncode=0,
        stdout=f"installed {written} purelib wheel files into {purelib}\n",
        stderr="",
    )


def _ensure_venv_runtime_library(venv_dir: Path) -> str:
    library_name = str(sysconfig.get_config_var("LDLIBRARY") or "").strip()
    if not library_name:
        return ""
    candidates = (
        Path(sys.base_prefix) / "lib" / library_name,
        Path(sys.executable).resolve().parent.parent / "lib" / library_name,
    )
    source = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
    if source is None:
        return ""
    destination = venv_dir / "lib" / library_name
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source)
    return str(destination)


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
        venv.EnvBuilder(with_pip=False).create(venv_dir)
        runtime_library = _ensure_venv_runtime_library(venv_dir)
        python_bin = venv_dir / "bin" / "python"
        install = _install_pure_wheel(
            wheel,
            python_bin=python_bin,
            env=isolated_env,
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
        except (json.JSONDecodeError, TypeError, ValueError):
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
    runtime_payload: dict[str, object] = {}
    try:
        loaded_runtime_payload = json.loads(run.stdout)
        if isinstance(loaded_runtime_payload, dict):
            runtime_payload = loaded_runtime_payload
    except (TypeError, ValueError):
        runtime_payload = {}
    public_tool_count = 0
    public_surface_exact = False
    for check in runtime_payload.get("checks") or []:
        if not isinstance(check, dict) or check.get("name") != "tools_list":
            continue
        metadata = check.get("metadata") if isinstance(check.get("metadata"), dict) else {}
        public_tool_count = int(metadata.get("tool_count") or 0)
        public_surface_exact = bool(check.get("ok") and public_tool_count == 8)
        break
    payload = {
        "wheel": str(wheel),
        "wheel_sha256": wheel_sha256,
        "wheel_size_bytes": wheel.stat().st_size,
        "cwd": args.cwd,
        "isolation": {
            "isolated_mode": True,
            "removed_environment_keys": removed_env_keys,
            "python_no_user_site": True,
            "runtime_library_linked": bool(runtime_library),
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
            "public_tool_count": public_tool_count,
            "public_surface_exact": public_surface_exact,
        },
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = (
        install.returncode == 0
        and verify_import.returncode == 0
        and import_inside_venv
        and run.returncode == 0
        and runtime_payload.get("ok") is True
        and public_surface_exact
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "install": install.returncode,
                "import": verify_import.returncode,
                "import_inside_temporary_venv": import_inside_venv,
                "run": run.returncode,
                "public_tool_count": public_tool_count,
                "public_surface_exact": public_surface_exact,
                "wheel_sha256": wheel_sha256,
                "artifact": str(out),
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
