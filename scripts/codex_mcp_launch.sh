#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO_ROOT"

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
export DATALENS_API_VERSION="${DATALENS_API_VERSION:-auto}"
export DATALENS_ENABLE_TOKEN_REFRESH_ON_401="${DATALENS_ENABLE_TOKEN_REFRESH_ON_401:-0}"
export DATALENS_MCP_ENABLE_WRITES="${DATALENS_MCP_ENABLE_WRITES:-0}"
export DATALENS_MCP_ENABLE_EXPERT_RPC="${DATALENS_MCP_ENABLE_EXPERT_RPC:-0}"
export DATALENS_MCP_LIVE_ALLOW_SAVE="${DATALENS_MCP_LIVE_ALLOW_SAVE:-0}"
export DATALENS_MCP_LIVE_ALLOW_PUBLISH="${DATALENS_MCP_LIVE_ALLOW_PUBLISH:-0}"

case "${DATALENS_MCP_TEST_ONLY_REGISTRY:-}" in
  1|true|TRUE|yes|YES|on|ON)
    ;;
  *)
    unset DATALENS_MCP_ALLOW_HIDDEN_TOOL_CALLS
    unset DATALENS_MCP_TOOL_PROFILE
    unset DATALENS_MCP_TOOL_SURFACE
    ;;
esac

if [[ "${DATALENS_ENABLE_TOKEN_REFRESH_ON_401}" == "1" || "${DATALENS_ENABLE_TOKEN_REFRESH_ON_401}" == "true" ]]; then
  if [[ -n "${DATALENS_YC_BINARY:-}" ]]; then
    YC_BIN="$DATALENS_YC_BINARY"
  else
    YC_BIN="$(command -v yc || true)"
  fi
  if [[ -z "${YC_BIN:-}" ]]; then
    echo "datalens-dev-mcp launcher: token refresh requested but yc was not found. Set DATALENS_YC_BINARY or disable DATALENS_ENABLE_TOKEN_REFRESH_ON_401." >&2
    exit 127
  fi
  if [[ "$YC_BIN" == */* && ! -x "$YC_BIN" ]]; then
    echo "datalens-dev-mcp launcher: yc binary is not executable at DATALENS_YC_BINARY." >&2
    exit 127
  fi
  export DATALENS_YC_BINARY="$YC_BIN"
fi

CONFIG_PATH="$REPO_ROOT/config/datalens_mcp.local.json"
if [[ ! -f "$CONFIG_PATH" ]]; then
  CONFIG_PATH="$REPO_ROOT/config/datalens_mcp.local.example.json"
fi

exec "$PYTHON_BIN" -m datalens_dev_mcp.server \
  --project-root "$REPO_ROOT" \
  --local-config "$CONFIG_PATH"
