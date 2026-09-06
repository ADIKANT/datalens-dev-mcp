# Installation

Build and install the wheel in a stable user environment, then install or enable the repository plugin so Codex loads `.codex-plugin/plugin.json`, the five skills, and `.mcp.json`. The `datalens-dev-mcp` executable must be on `PATH` for the bundled stdio server.

Verify from a directory outside the checkout:

```bash
datalens-dev-mcp --version
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"1"}}}' | datalens-dev-mcp stdio
```
