#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import venv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a wheel in a temporary venv and run portable runtime smoke.")
    parser.add_argument("--wheel", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cwd", default=tempfile.gettempdir())
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    out = Path(args.out)
    script = Path(__file__).with_name("smoke_portable_runtime.py").resolve()
    with tempfile.TemporaryDirectory(dir=str(out.parent)) as tmp:
        venv_dir = Path(tmp) / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python_bin = venv_dir / "bin" / "python"
        install = subprocess.run(
            [str(python_bin), "-m", "pip", "install", "--no-index", str(wheel)],
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        run = subprocess.run(
            [str(python_bin), str(script)],
            cwd=args.cwd,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    payload = {
        "wheel": str(wheel),
        "cwd": args.cwd,
        "install": {
            "returncode": install.returncode,
            "stdout_tail": install.stdout[-1000:],
            "stderr_tail": install.stderr[-1000:],
        },
        "run": {
            "returncode": run.returncode,
            "stdout": run.stdout,
            "stderr_tail": run.stderr[-1000:],
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = False
    try:
        ok = install.returncode == 0 and run.returncode == 0 and json.loads(run.stdout).get("ok") is True
    except Exception:
        ok = False
    print(json.dumps({"ok": ok, "install": install.returncode, "run": run.returncode, "artifact": str(out)}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
