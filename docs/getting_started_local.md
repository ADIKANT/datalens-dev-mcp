# Local quick start

`datalens-dev-mcp` is an MCP stdio subprocess. Install it once, then point Codex, Claude, or another MCP client at the virtual-environment executable.

The default is read-only for DataLens. Planning tools may still create local artifacts under the selected project root.

## Install

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

The smoke test is offline. Use `pip install -e .` only for server development.

## Optional live-read credentials

Create an untracked env file outside the checkout:

```dotenv
DATALENS_ORG_ID=<YOUR_ORG_ID>
DATALENS_IAM_TOKEN=<YOUR_IAM_TOKEN>
DATALENS_MCP_ENABLE_WRITES=0
DATALENS_MCP_LIVE_ALLOW_SAVE=0
DATALENS_MCP_LIVE_ALLOW_PUBLISH=0
```

Pass its absolute path as `DATALENS_ENV_FILE` in the client configuration. Offline planning and validation do not need credentials.

## Start command

All supported clients ultimately launch the same process:

```text
/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp
  stdio
  --project-root /absolute/path/to/your/dashboard-project
```

Use JSON-RPC over stdin/stdout. Set the process environment rather than adding credential values to command arguments.

Client-specific examples:

- [Codex TOML](../examples/clients/codex.toml)
- [Claude Desktop JSON](../examples/clients/claude-desktop.json)
- [Generic stdio JSON](../examples/clients/generic-stdio.json)
- [Claude Code CLI and client notes](../examples/clients/README.md)

## First session

1. Call `dl_runtime_status`; verify `allow_writes`, `allow_save`, and `allow_publish` are `false`.
2. Call `dl_auth_probe`; without credentials, a sanitized blocked result is expected.
3. With valid read credentials, call `dl_list_workbooks`.
4. Read entries or snapshot a dashboard before creating any change plan.

Start with this prompt:

> Inspect the DataLens MCP runtime and verify that every mutation gate is off. Probe auth and list workbooks read-only. Do not save, publish, or modify objects.

See the main [`README.md`](../README.md) for safety, repository structure, and development commands.
