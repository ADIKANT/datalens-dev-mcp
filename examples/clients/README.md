# MCP client examples

These files describe the same local stdio process for different MCP clients. Replace every `/absolute/path/...` value before use.

The executable path points to a source checkout installed in its own virtual environment:

```text
/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp
```

The `--project-root` value is the local dashboard workspace used for inputs and generated artifacts. It does not identify a DataLens workbook or dashboard.

## Codex

Copy [`codex.toml`](codex.toml) into `~/.codex/config.toml`, or merge its server block with the existing file. The equivalent CLI command is:

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

## Claude Code

Run from the dashboard project directory:

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Verify with `claude mcp list`.

## Claude Desktop

Merge the `mcpServers` entry from [`claude-desktop.json`](claude-desktop.json) into `claude_desktop_config.json`, then restart the application. The default config location is `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS and `%APPDATA%\Claude\claude_desktop_config.json` on Windows.

## Other clients

Use [`generic-stdio.json`](generic-stdio.json) when a client asks separately for an executable, argument list, and environment map. It is a process definition rather than an HTTP endpoint.

## Safe first call

Keep all write flags set to `0`, restart the MCP client, and ask it to call `dl_runtime_status`. Confirm `allow_writes`, `allow_save`, and `allow_publish` are `false` before live reads.
