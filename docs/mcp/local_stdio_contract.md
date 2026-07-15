# Local Stdio MCP Contract

`datalens-dev-mcp` is launched by Codex as a local subprocess over stdio. It is not a hosted HTTP/SSE service and does not expose a network listener.

## Codex MCP Config

Use one local Custom MCP server:

```json
{
  "mcpServers": {
    "datalens-dev": {
      "command": "<REPO_ROOT>/scripts/codex_mcp_launch.sh",
      "args": [],
      "env": {
        "PYTHONPATH": "<REPO_ROOT>/src",
        "DATALENS_ENV_FILE": "~/.config/datalens-dev-mcp/env",
        "PYTHONDONTWRITEBYTECODE": "1"
      }
    }
  }
}
```

The env file is local-only and must not be committed.
The local MCP config is JSON. Copy `config/datalens_mcp.local.example.json` to
an untracked path when local defaults need real workbook or workspace values.

## Stdio Rules

- `stdin` accepts newline-delimited MCP JSON-RPC messages.
- `stdout` is reserved for newline-delimited MCP JSON-RPC responses only.
- Logs, debug request metadata, parse tracebacks, and diagnostics go to `stderr`.
- `initialize` returns protocol version `2025-06-18`, tool/resource/prompt
  capabilities, and server info.
- `notifications/initialized` is accepted as a notification and produces no
  stdout response.
- `tools/list`, `tools/call`, `prompts/list`, `prompts/get`,
  `resources/list`, and `resources/read` are local subprocess operations.
- `tools/list` entries include `name`, `title`, `description`, and
  `inputSchema`.
- `tools/call` returns MCP content plus `isError`. Tool failures are encoded as
  structured JSON text with `ok: false` and an `error.category`.
- Runtime startup is read-only and write/publish gates are off. Guarded writes require explicit safe-apply approval and write-mode env flags; implementation/fix/enhance delivery for known targets continues to publish only after saved readback and publish gates.

## Local Smoke

```bash
python3 scripts/smoke_mcp_stdio.py
```

The smoke harness starts the server as a subprocess, sends `initialize`,
`notifications/initialized`, `tools/list`, a safe `tools/call`,
`prompts/list`, `prompts/get`, `resources/list`, `resources/read`, an invalid
method, and malformed JSON. It fails if any stdout line is not valid JSON-RPC or
if the notification produces output.
