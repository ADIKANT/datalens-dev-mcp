#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO_ROOT"

PYTHON_BIN=""
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "datalens-dev-mcp launcher: python3 was not found and .venv/bin/python is absent." >&2
  exit 127
fi

export PYTHONPATH="$REPO_ROOT/src"
export DATALENS_ENV_FILE="${DATALENS_ENV_FILE:-$HOME/.config/datalens-dev-mcp/env}"
export DATALENS_API_BASE_URL="${DATALENS_API_BASE_URL:-https://api.datalens.tech}"
export DATALENS_ENABLE_TOKEN_REFRESH_ON_401="${DATALENS_ENABLE_TOKEN_REFRESH_ON_401:-1}"
export DATALENS_MCP_ENABLE_WRITES="${DATALENS_MCP_ENABLE_WRITES:-1}"
export DATALENS_MCP_ENABLE_EXPERT_RPC="${DATALENS_MCP_ENABLE_EXPERT_RPC:-0}"
export DATALENS_MCP_LIVE_ALLOW_SAVE="${DATALENS_MCP_LIVE_ALLOW_SAVE:-1}"
export DATALENS_MCP_LIVE_ALLOW_PUBLISH="${DATALENS_MCP_LIVE_ALLOW_PUBLISH:-1}"
export DATALENS_MCP_TASKS_DIR="${DATALENS_MCP_TASKS_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/datalens-dev-mcp/tasks}"

case "${DATALENS_MCP_TEST_ONLY_REGISTRY:-}" in
  1|true|TRUE|yes|YES|on|ON)
    ;;
  *)
    unset DATALENS_MCP_ALLOW_HIDDEN_TOOL_CALLS
    unset DATALENS_MCP_TOOL_PROFILE
    unset DATALENS_MCP_TOOL_SURFACE
    ;;
esac

export DATALENS_MCP_LAUNCHER_PROJECT_ROOT="$REPO_ROOT"
export DATALENS_MCP_LAUNCHER_PACKAGE_ROOT="$REPO_ROOT"
export DATALENS_MCP_LAUNCHER_PYTHON="$PYTHON_BIN"
export DATALENS_MCP_LAUNCHER_CWD="$REPO_ROOT"
export DATALENS_MCP_LAUNCHER_STATE_ROOT="$DATALENS_MCP_TASKS_DIR"
export DATALENS_MCP_LAUNCHER_TOOL_SURFACE="${DATALENS_MCP_TOOL_SURFACE:-autonomous-v2}"

if [[ "${DATALENS_ENABLE_TOKEN_REFRESH_ON_401}" == "1" || "${DATALENS_ENABLE_TOKEN_REFRESH_ON_401}" == "true" ]]; then
  if [[ -n "${DATALENS_YC_BINARY:-}" ]]; then
    YC_BIN="$DATALENS_YC_BINARY"
  else
    YC_BIN="$(command -v yc || true)"
  fi
  if [[ -z "${YC_BIN:-}" ]]; then
    echo "datalens-dev-mcp launcher: yc was not found; the server will start and dl_runtime_status will report refresh unavailable." >&2
  elif [[ "$YC_BIN" == */* && ! -x "$YC_BIN" ]]; then
    echo "datalens-dev-mcp launcher: configured yc is not executable; the server will start and dl_runtime_status will report refresh unavailable." >&2
  else
    export DATALENS_YC_BINARY="$YC_BIN"
  fi
fi

if [[ "${1:-}" == "--recover-credentials" ]]; then
  if [[ "$#" -ne 1 ]]; then
    echo "datalens-dev-mcp launcher: --recover-credentials accepts no additional arguments." >&2
    exit 2
  fi
  exec "$PYTHON_BIN" -m datalens_dev_mcp.credential_recovery --interactive
fi

CONFIG_PATH="$REPO_ROOT/config/datalens_mcp.local.json"
if [[ ! -f "$CONFIG_PATH" ]]; then
  CONFIG_PATH="$REPO_ROOT/config/datalens_mcp.local.example.json"
fi

exec "$PYTHON_BIN" -m datalens_dev_mcp.server \
  --project-root "$REPO_ROOT" \
  --local-config "$CONFIG_PATH"
