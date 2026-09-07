from __future__ import annotations

import subprocess

from datalens_dev_mcp.api.errors import DataLensApiError


def refresh_iam_token_with_yc(*, yc_binary: str = "yc", timeout_sec: float = 15.0) -> str:
    try:
        result = subprocess.run(
            [yc_binary, "iam", "create-token", "--no-browser", "--no-user-output"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_sec,
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
