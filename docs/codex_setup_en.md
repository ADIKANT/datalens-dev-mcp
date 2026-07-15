# Codex setup

[Русский](codex_setup.md) · **English** · [Documentation](README_en.md) · [Complete flow](usage-flow_en.md)

Codex launches `datalens-dev-mcp` as a local stdio MCP server. The Codex app, CLI, and IDE extension share configuration on the same host. Official reference: [Model Context Protocol in Codex](https://learn.chatgpt.com/docs/extend/mcp).

## 1. Install the server

Python 3.11 or newer is required:

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

The smoke test runs offline, validates MCP initialization/tools/prompts/resources, and does not contact DataLens.

## 2. Choose a project root

```bash
mkdir -p /absolute/path/to/your/dashboard-project
```

`--project-root` selects the local directory for requirements, plans, validation outputs, and deployment artifacts. It does not select a live workbook or dashboard; tools receive object IDs separately.

Read-only refers to DataLens mutations. Local planners may write artifacts inside the project root.

## 3. Create an external env file

Offline tools work without credentials. For live reads:

```bash
mkdir -p ~/.config/datalens-dev-mcp
touch ~/.config/datalens-dev-mcp/env
chmod 600 ~/.config/datalens-dev-mcp/env
```

```dotenv
DATALENS_ORG_ID=<YOUR_ORG_ID>
DATALENS_IAM_TOKEN=<YOUR_IAM_TOKEN>
DATALENS_API_BASE_URL=https://api.datalens.tech
DATALENS_API_VERSION=auto

DATALENS_MCP_ENABLE_WRITES=0
DATALENS_MCP_LIVE_ALLOW_SAVE=0
DATALENS_MCP_LIVE_ALLOW_PUBLISH=0
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

`YC_IAM_TOKEN` can replace `DATALENS_IAM_TOKEN`. Keep the file outside the checkout and give Codex only its absolute path.

## 4. Register the MCP server

### In the Codex app

1. Open **Settings** → **MCP servers**.
2. Select **Add server**.
3. Choose **STDIO** and enter the command/arguments shown below.
4. Save the server and select **Restart**.

### With `config.toml`

Global configuration lives at `~/.codex/config.toml`. A trusted project can use `.codex/config.toml` in its project root.

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
startup_timeout_sec = 20
tool_timeout_sec = 120
```

Copyable template: [`examples/clients/codex.toml`](../examples/clients/codex.toml).

### With the CLI

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Inspect registration:

```bash
codex mcp list
codex mcp --help
```

Restart Codex after adding or changing the server. In the interactive composer, use `/mcp` to inspect active servers and tools.

## 5. Verify the safe runtime

Prompt:

> Call `dl_runtime_status` through the DataLens MCP server. Show the project root, API version, auth presence, and mutation gates. Confirm that `allow_writes`, `allow_save`, `allow_publish`, and `expert_rpc_enabled` are off. Do not call mutation tools.

Verify that:

- reported project root matches the selected directory;
- `allow_writes`, `allow_save`, and `allow_publish` are `false`;
- `expert_rpc_enabled` is `false`;
- credential presence is reported without a token value, prefix, or length;
- the standard tool surface contains 38 tools.

## 6. Verify live read access

Prompt:

> Run `dl_auth_probe`, then call `dl_list_workbooks`. This is a read-only check. Do not save, publish, or modify anything.

`dl_auth_probe` runs a minimal `getWorkbooksList`. If it returns `BLOCKED_LIVE_CREDENTIALS`, correct the external env file and restart the MCP process. Do not paste the token into chat for troubleshooting.

After a successful probe, use `dl_get_workbook_entries`, `dl_snapshot_dashboard`, `dl_read_object`, and `dl_get_entries_relations`.

## 7. Start real work

Recommended Codex flow for an existing dashboard:

1. runtime/auth preflight;
2. workbook inventory;
3. fresh dashboard snapshot and relation graph;
4. object/route/API planning;
5. object and project validation;
6. payload and unapproved safe-apply plan;
7. guarded save with approval and enabled gates;
8. saved readback;
9. publish-from-saved only when delivery intent permits;
10. published readback and browser/runtime QA.

Copyable read-only, plan-only, save-only, and publish prompts are in the [usage flow](usage-flow_en.md).

## 8. Update or remove registration

After updating the checkout, reinstall the package and restart Codex:

```bash
cd /absolute/path/to/datalens-dev-mcp
.venv/bin/python -m pip install .
python3 scripts/smoke_mcp_stdio.py
codex mcp list
```

Use the commands shown by `codex mcp --help` for removal and other management actions. The source of truth is the selected global or project `config.toml`.

## Troubleshooting

- **Server does not start:** check the executable's `--version`, absolute paths, and `python3 scripts/smoke_mcp_stdio.py`.
- **Codex shows an old tool list:** reinstall the package and restart the app/extension.
- **Wrong project root:** correct `args` and `cwd`, then restart.
- **Auth stopped working:** the IAM token may have expired; update only the external env file and restart the process.
- **Unexpected write block:** first verify that the block is appropriate; write/save/publish, approval, fresh read, and readback are independent gates.
- **Protocol parse error/stdout pollution:** run the smoke test; stdout is reserved for MCP JSON-RPC and diagnostics belong on stderr.

Compact technical reference: [`docs/mcp/codex_connection.md`](mcp/codex_connection.md). Transport contract: [`docs/mcp/local_stdio_contract.md`](mcp/local_stdio_contract.md).
