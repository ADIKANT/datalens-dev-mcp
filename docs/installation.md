# Installation

Build and install the wheel in a stable user environment, then install or enable the repository plugin so Codex loads `.codex-plugin/plugin.json`, the five skills, and `.mcp.json`. The `datalens-dev-mcp` executable must be on `PATH` for the bundled stdio server.

Verify from a directory outside the checkout:

```bash
datalens-dev-mcp --version
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"verify","version":"1"}}}' | datalens-dev-mcp stdio
```

Use the five domain skills from the installed plugin's current catalogue: inspect, dataset/Wizard, Editor, dashboard, maintenance. Do not retain links to a prior versioned cache directory or the retired `dl_task_*` workflow. After updating the backend wheel and local plugin snapshot, start a fresh ordinary task to load that snapshot. Keep credentials in the existing protected user configuration; a skill refresh does not require login or manual environment injection.

Call `dl_server_info` in the active MCP session after installation. It reports the
process instance/start time, active package version/content digest, capability
revision, and the separately observed installed distribution version. An existing
process can still run old code after a wheel upgrade; `pip show` alone is not an
active-process check. Build commit is explicitly unknown when it was not embedded
in the package; the server never substitutes the caller directory's Git HEAD.
The local 1.1.0 candidate keeps the SDK pinned at 0.9.0. Its operation store uses
OS file locks on macOS/Linux; lock release after a crash never permits replay of
an uncertain write. Compact terminal receipts retain operation ID bindings after
detail pruning; size limits bound retained detail, not the number of ID bindings.

For a captured tool result, `python scripts/print_tool_result.py < result.json`
prints `structuredContent` once, falling back to compatibility text, and exits
nonzero for tool/protocol errors. MCP itself retains both wire representations.

If a separately installed dashboard entrypoint still references the retired task tools, update only that entrypoint to route to the current domain skills, preserving its user rules about exact project roots, technology, target/reference identity, readback and browser acceptance. Do not remove the entire user skills directory or change unrelated plugins.
