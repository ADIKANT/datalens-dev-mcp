from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPO_ROOT / "scripts" / "codex_mcp_launch.sh"


def test_failed_auth_probe_exposes_canonical_same_task_recovery_action() -> None:
    from datalens_dev_mcp.mcp.tools.runtime import dl_auth_probe

    class ReauthenticationRequiredClient:
        token_refresher = None

        def rpc(self, method: str, payload: dict[str, object]) -> dict[str, object]:
            del method, payload
            raise RuntimeError("initial_token_bootstrap_failed: yc iam create-token failed")

    with patch.dict(
        os.environ,
        {
            "DATALENS_ENV_FILE": "/tmp/synthetic-datalens-env",
            "DATALENS_ORG_ID": "org_synthetic",
            "DATALENS_ENABLE_TOKEN_REFRESH_ON_401": "1",
            "DATALENS_YC_BINARY": "/opt/homebrew/bin/yc",
        },
        clear=True,
    ):
        client = ReauthenticationRequiredClient()
        result = dl_auth_probe(client=client)

    recovery = result["credential_recovery"]
    assert result["error"]["category"] == "yc_reauthentication_required"
    assert recovery["schema_id"] == "datalens_credential_recovery/v1"
    assert recovery["state"] == "interactive_reauthentication_required"
    assert recovery["operator_action"] == {
        "required": True,
        "kind": "run_local_command",
        "command": "scripts/codex_mcp_launch.sh --recover-credentials",
        "opens_browser_when_required": True,
    }
    assert recovery["canonical_env_reload"]["automatic"] is True
    assert recovery["verification_probe"] == "dl_auth_probe"
    assert recovery["continuation"] == "same_task"
    dumped = json.dumps(result, ensure_ascii=False)
    assert "org_synthetic" not in dumped
    assert "/tmp/synthetic-datalens-env" not in dumped


def test_launcher_recovery_mode_uses_launcher_interpreter_and_canonical_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        launcher = root / "scripts" / LAUNCHER.name
        python = root / ".venv" / "bin" / "python"
        launcher.parent.mkdir(parents=True)
        python.parent.mkdir(parents=True)
        launcher.write_text(LAUNCHER.read_text(encoding="utf-8"), encoding="utf-8")
        launcher.chmod(0o755)
        python.write_text(
            "#!/bin/sh\n"
            "printf 'ARGS=%s\\n' \"$*\"\n"
            "printf 'PROJECT=%s\\n' \"$DATALENS_MCP_LAUNCHER_PROJECT_ROOT\"\n"
            "printf 'PYTHON=%s\\n' \"$DATALENS_MCP_LAUNCHER_PYTHON\"\n"
            "printf 'CWD=%s\\n' \"$DATALENS_MCP_LAUNCHER_CWD\"\n"
            "printf 'STATE=%s\\n' \"$DATALENS_MCP_LAUNCHER_STATE_ROOT\"\n"
            "printf 'SURFACE=%s\\n' \"$DATALENS_MCP_LAUNCHER_TOOL_SURFACE\"\n",
            encoding="utf-8",
        )
        python.chmod(0o755)
        result = subprocess.run(
            [str(launcher), "--recover-credentials"],
            cwd=root.parent,
            env={**os.environ, "PATH": f"{root}:{os.environ.get('PATH', '')}"},
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "ARGS=-m datalens_dev_mcp.credential_recovery --interactive" in result.stdout
    assert f"PROJECT={root.resolve()}" in result.stdout
    assert f"PYTHON={python.resolve()}" in result.stdout
    assert f"CWD={root.resolve()}" in result.stdout
    assert f"STATE={root.resolve() / '.datalens-mcp' / 'tasks'}" in result.stdout
    assert "SURFACE=autonomous-v2" in result.stdout


def test_interactive_recovery_persists_then_verifies_in_the_same_task() -> None:
    from datalens_dev_mcp.config import DataLensConfig
    from datalens_dev_mcp.credential_recovery import recover_credentials

    cfg = DataLensConfig(
        org_id="org_synthetic",
        env_file_path="/tmp/synthetic-datalens-env",
        token_refresh_enabled=True,
        yc_binary="/synthetic/yc",
    )

    persisted_tokens: list[str] = []

    class Client:
        def __init__(self, supplied: DataLensConfig) -> None:
            assert supplied is cfg

        def persist_refreshed_token(self, token: str) -> None:
            assert token == "synthetic-fresh-token"
            persisted_tokens.append(token)

    interactive_calls: list[tuple[str, ...]] = []
    with (
        patch("datalens_dev_mcp.credential_recovery.DataLensConfig.from_env", return_value=cfg),
        patch("datalens_dev_mcp.credential_recovery._resolved_yc_binary", return_value="/synthetic/yc"),
        patch(
            "datalens_dev_mcp.credential_recovery.refresh_iam_token_with_yc",
            side_effect=[RuntimeError("reauth required"), "synthetic-fresh-token"],
        ),
        patch("datalens_dev_mcp.credential_recovery.DataLensApiClient", Client),
        patch("datalens_dev_mcp.credential_recovery.dl_auth_probe", return_value={"ok": True}),
    ):
        result = recover_credentials(
            interactive=True,
            interactive_runner=lambda command: interactive_calls.append(tuple(command)) or 0,
        )

    assert result["ok"] is True
    assert result["recovery_mode"] == "interactive_reauthentication"
    assert result["canonical_env_reloaded"] is True
    assert result["continuation"] == "same_task"
    assert result["old_task_lookup_required"] is False
    assert interactive_calls == [("/synthetic/yc", "init")]
    assert persisted_tokens == ["synthetic-fresh-token"]
    assert "synthetic-fresh-token" not in json.dumps(result)


def test_runtime_status_proves_launcher_parity_across_all_required_dimensions() -> None:
    from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status

    root = REPO_ROOT.resolve()
    state_root = root / ".datalens-mcp" / "tasks"
    env = {
        "DATALENS_MCP_LAUNCHER_PROJECT_ROOT": str(root),
        "DATALENS_MCP_LAUNCHER_PYTHON": str(Path(os.sys.executable).resolve()),
        "DATALENS_MCP_LAUNCHER_CWD": str(root),
        "DATALENS_MCP_LAUNCHER_STATE_ROOT": str(state_root),
        "DATALENS_MCP_LAUNCHER_TOOL_SURFACE": "autonomous-v2",
    }
    with patch.dict(os.environ, env, clear=False), patch("os.getcwd", return_value=str(root)):
        status = dl_runtime_status(project_root=str(root))

    parity = status["launcher_parity"]
    assert parity["managed"] is True
    assert parity["all_match"] is True
    assert set(parity["dimensions"]) == {"interpreter", "package", "cwd", "state", "public_surface"}
    assert all(item["matches"] for item in parity["dimensions"].values())
    assert parity["dimensions"]["package"]["build_identity_hash"]
    assert parity["dimensions"]["public_surface"]["tool_surface_hash"]
    assert parity["dimensions"]["public_surface"]["tool_count"] > 0


def test_standard_public_inspect_projects_the_same_launcher_parity() -> None:
    from datalens_dev_mcp.mcp.tools.tasks import dl_inspect

    root = REPO_ROOT.resolve()
    env = {
        "DATALENS_MCP_LAUNCHER_PROJECT_ROOT": str(root),
        "DATALENS_MCP_LAUNCHER_PYTHON": str(Path(os.sys.executable).resolve()),
        "DATALENS_MCP_LAUNCHER_CWD": str(root),
        "DATALENS_MCP_LAUNCHER_STATE_ROOT": str(root / ".datalens-mcp" / "tasks"),
        "DATALENS_MCP_LAUNCHER_TOOL_SURFACE": "autonomous-v2",
    }
    with patch.dict(os.environ, env, clear=False), patch("os.getcwd", return_value=str(root)):
        result = dl_inspect(project_root=str(root), max_nodes=1)

    parity = result["runtime_identity"]["launcher_parity"]
    assert parity["managed"] is True
    assert parity["all_match"] is True
    assert parity["dimensions"]["public_surface"]["name"] == "autonomous-v2"


def test_launcher_parity_keeps_installed_package_root_separate_from_project_root(tmp_path: Path) -> None:
    from datalens_dev_mcp.mcp.tools.runtime import dl_runtime_status

    package_root = REPO_ROOT.resolve()
    project_root = tmp_path.resolve()
    env = {
        "DATALENS_MCP_LAUNCHER_PROJECT_ROOT": str(project_root),
        "DATALENS_MCP_LAUNCHER_PACKAGE_ROOT": str(package_root),
        "DATALENS_MCP_LAUNCHER_PYTHON": str(Path(os.sys.executable).resolve()),
        "DATALENS_MCP_LAUNCHER_CWD": str(project_root),
        "DATALENS_MCP_LAUNCHER_STATE_ROOT": str(project_root / ".datalens-mcp" / "tasks"),
        "DATALENS_MCP_LAUNCHER_TOOL_SURFACE": "autonomous-v2",
    }
    with patch.dict(os.environ, env, clear=False), patch("os.getcwd", return_value=str(project_root)):
        parity = dl_runtime_status(project_root=str(project_root))["launcher_parity"]

    assert parity["all_match"] is True
    assert parity["dimensions"]["package"]["source_root"] == str(package_root)
    assert parity["dimensions"]["package"]["project_root"] == str(project_root)
