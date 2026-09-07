from __future__ import annotations

import os
import subprocess
from pathlib import Path

from datalens_dev_mcp.api.errors import DataLensApiError


def refresh_iam_token_with_yc(*, yc_binary: str = "yc", timeout_sec: float = 15.0) -> str:
    env = os.environ.copy()
    path_entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    binary_path = Path(yc_binary)
    if binary_path.is_absolute():
        path_entries.insert(0, str(binary_path.parent))
    for system_path in ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        if system_path not in path_entries:
            path_entries.append(system_path)
    env["PATH"] = os.pathsep.join(dict.fromkeys(path_entries))
    try:
        result = subprocess.run(
            [yc_binary, "iam", "create-token", "--no-browser", "--no-user-output"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise DataLensApiError("yc IAM token refresh timed out") from exc
    except OSError as exc:
        raise DataLensApiError("yc IAM token refresh could not start") from exc
    if result.returncode != 0:
        raise DataLensApiError("yc IAM token refresh failed; authenticate interactively and retry")
    token = result.stdout.strip()
    if not token or any(character.isspace() for character in token):
        raise DataLensApiError("yc IAM token refresh returned an invalid credential")
    return token
