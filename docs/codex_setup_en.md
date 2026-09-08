# Connect DataLens to Codex

[Русский](codex_setup.md) · [Installation](installation.md) · [Usage](usage-flow_en.md)

Python 3.11+ is required. Install the backend into a stable environment. From the repository checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
.venv/bin/python scripts/installed_smoke.py
```

The smoke script checks import from `site-packages` without `PYTHONPATH`, version identity, stdio initialization, and the closed 25-tool surface from a temporary directory. This is offline installation evidence, not live access or rendered acceptance.

Install or enable the repository plugin through the host's supported plugin installation flow. Its [manifest](../.codex-plugin/plugin.json) loads five domain skills and [.mcp.json](../.mcp.json). The bundled stdio configuration is:

```json
{
  "mcpServers": {
    "datalens": {
      "command": "datalens-dev-mcp",
      "args": ["stdio"]
    }
  }
}
```

The installed executable must be on the MCP process `PATH`. If registering stdio manually, use the absolute path to the installed executable and the single `stdio` argument. A manual server registration alone does not install the domain skills. Keep a single intended server registration to avoid accidentally using an older backend.

For live access, supply `DATALENS_ORG_ID` and `DATALENS_IAM_TOKEN` through the process environment or the protected `${XDG_CONFIG_HOME:-~/.config}/datalens-dev-mcp/credentials.env` file. Explicit `DATALENS_ENV_FILE` takes precedence. Preserve existing credentials and never paste their values into prompts or diagnostics.

After updating the backend and plugin snapshot, start a fresh ordinary task from the exact dashboard project or subproject. Verify the connected runtime with `dl_server_info`, inspect its `tools/list` schemas, and use `dl_auth_check` for a harmless live access probe. Runtime identity, successful authentication, object-specific permissions, and rendering are separate checks.

A clear scoped request authorizes its requested save/readback and publish/readback steps. A compact plan does not add another approval pause; read-only and save-only limits remain binding. Native permission events remain host-controlled. An automatic reviewer allow is not a pending human reply; do not change global approval settings or external skills to bypass a restriction. See [authorized scope](../skills/datalens-dashboard/references/authorized-scope.md).

If startup fails, check the installed executable path and process environment. If a live probe fails, report the exact authentication or access boundary without exposing credentials. If the runtime exposes a different surface, resolve the backend/plugin version mismatch before writing. Use the [current tools](tools_en.md) and [domain usage](usage-flow_en.md), with exact arguments from the installed schema.
