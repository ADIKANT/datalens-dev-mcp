# MCP Configuration

Use stdio with one local Codex MCP server:

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

The env file is local-only. Do not put it in a repository. See `docs/mcp/local_stdio_contract.md` for the stdout/stderr contract.

Copy `config/datalens_mcp.local.example.json` to
`config/datalens_mcp.local.json` for local defaults, or point
`DATALENS_MCP_LOCAL_CONFIG` at another untracked JSON file.
