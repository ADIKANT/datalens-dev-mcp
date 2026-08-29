from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.tools.runtime import dl_auth_probe

InteractiveRunner = Callable[[Sequence[str]], int]


def recover_credentials(
    *,
    interactive: bool,
    interactive_runner: InteractiveRunner | None = None,
) -> dict[str, Any]:
    """Recover the canonical IAM token without depending on another client task."""

    cfg = DataLensConfig.from_env()
    if not cfg.env_file_path:
        return _result(False, "canonical_configuration_required", "DATALENS_ENV_FILE is not configured")
    if not cfg.org_id:
        return _result(False, "canonical_configuration_required", "DATALENS_ORG_ID is not configured")
    yc_binary = _resolved_yc_binary(cfg.yc_binary)
    if not yc_binary:
        return _result(False, "yc_unavailable", "configured yc executable was not found")

    try:
        token = refresh_iam_token_with_yc(yc_binary=yc_binary, timeout_sec=cfg.token_refresh_timeout_sec)
        recovery_mode = "background_refresh"
    except Exception:  # noqa: BLE001
        if not interactive:
            return _result(False, "interactive_reauthentication_required", "interactive recovery is required")
        runner = interactive_runner or _run_yc_init
        if runner((yc_binary, "init")) != 0:
            return _result(False, "interactive_reauthentication_failed", "yc init did not complete successfully")
        try:
            token = refresh_iam_token_with_yc(yc_binary=yc_binary, timeout_sec=cfg.token_refresh_timeout_sec)
        except Exception:  # noqa: BLE001
            return _result(False, "credential_refresh_failed", "yc token creation failed after interactive login")
        recovery_mode = "interactive_reauthentication"

    client = DataLensApiClient(cfg)
    client.persist_refreshed_token(token)
    verified = dl_auth_probe()
    if not verified.get("ok"):
        return _result(False, "verification_failed", "dl_auth_probe failed after canonical env reload")
    return {
        **_result(True, "healthy", "credential recovery completed"),
        "recovery_mode": recovery_mode,
        "canonical_env_reloaded": True,
        "verification_probe": "dl_auth_probe",
        "continuation": "same_task",
    }


def _resolved_yc_binary(configured: str) -> str:
    value = str(configured or "").strip()
    if not value:
        return ""
    if "/" in value:
        path = shutil.which(value)
        return path or ""
    return shutil.which(value) or ""


def _run_yc_init(command: Sequence[str]) -> int:
    return subprocess.run(list(command), check=False).returncode


def _result(ok: bool, state: str, message: str) -> dict[str, Any]:
    return {
        "schema_id": "datalens_credential_recovery_result/v1",
        "ok": ok,
        "state": state,
        "message": message,
        "credential_values_exposed": False,
        "old_task_lookup_required": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recover DataLens credentials in the canonical env file.")
    parser.add_argument("--interactive", action="store_true", help="Allow yc init to open the login flow.")
    args = parser.parse_args(argv)
    result = recover_credentials(interactive=args.interactive)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
