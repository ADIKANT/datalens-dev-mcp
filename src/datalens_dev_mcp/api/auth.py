from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from datalens_dev_mcp.api.errors import CredentialRefreshError
from datalens_dev_mcp.api.budget import current_budget


def refresh_iam_token_with_yc(
    *, yc_binary: str = "yc", allow_browser: bool = False, timeout_sec: float | None = None,
) -> str:
    # Background reads stay noninteractive. Explicit recovery lets yc complete
    # its own external-browser/SSO callback without exposing a login URL or token.
    if timeout_sec is None:
        timeout_sec = 120.0 if allow_browser else 15.0
    budget = current_budget.get()
    if budget is not None:
        timeout_sec = min(timeout_sec, budget.check())
    command = [yc_binary, "iam", "create-token"]
    if not allow_browser:
        command.append("--no-browser")
    command.append("--no-user-output")
    stage = "browser_credential_helper" if allow_browser else "credential_helper"
    env = os.environ.copy()
    path_entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    binary_path = Path(yc_binary)
    if binary_path.is_absolute():
        path_entries.insert(0, str(binary_path.parent))
    for system_path in ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        if system_path not in path_entries:
            path_entries.append(system_path)
    env["PATH"] = os.pathsep.join(dict.fromkeys(path_entries))
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise CredentialRefreshError("credential_refresh_timeout", stage=stage,
                                     elapsed_sec=round(time.monotonic() - started, 3)) from exc
    except OSError as exc:
        raise CredentialRefreshError("credential_helper_unavailable", stage="helper_launch",
                                     elapsed_sec=round(time.monotonic() - started, 3)) from exc
    if result.returncode != 0:
        # Only an explicit helper instruction establishes interactive recovery.
        # Inspect stderr locally, but never return it (or stdout) to callers.
        login_required = re.search(
            r"(?im)\b(?:please|you (?:must|need to))\s+(?:run|execute)\s+[`'\"]?yc\s+init\b",
            result.stderr or "",
        ) is not None
        raise CredentialRefreshError(
            "interactive_login_required" if login_required else "credential_refresh_failed",
            exit_status=result.returncode, stage=stage, elapsed_sec=round(time.monotonic() - started, 3),
        )
    token = result.stdout.strip()
    if not token or any(character.isspace() for character in token):
        raise CredentialRefreshError("credential_invalid", stage="credential_validation",
                                     elapsed_sec=round(time.monotonic() - started, 3))
    return token
