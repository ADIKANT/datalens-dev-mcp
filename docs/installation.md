# Installation

Build and install the wheel in a stable user environment, then install or enable the repository plugin so Codex loads `.codex-plugin/plugin.json`, the five skills, and `.mcp.json`. The `datalens-dev-mcp` executable must be on `PATH` for the bundled stdio server.

Verify from a directory outside the checkout:

```bash
datalens-dev-mcp --version
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"1"}}}' | datalens-dev-mcp stdio
```

Use the five domain skills from the installed plugin's current catalogue: inspect, dataset/Wizard, Editor, dashboard, maintenance. Do not retain links to a prior versioned cache directory or the retired `dl_task_*` workflow. After updating the backend wheel and local plugin snapshot, start a fresh ordinary task to load that snapshot. Keep credentials in the existing protected user configuration; a skill refresh does not require login or manual environment injection.

If a separately installed dashboard entrypoint still references the retired task tools, update only that entrypoint to route to the current domain skills, preserving its user rules about exact project roots, technology, target/reference identity, readback and browser acceptance. Do not remove the entire user skills directory or change unrelated plugins.
