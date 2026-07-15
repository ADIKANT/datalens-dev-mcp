# Codex setup

This guide installs `datalens-dev-mcp`, connects it to Codex, and verifies a first read-only session. The MCP process stays local; authenticated tools connect from your machine to the DataLens API.

## 1. Install the server

Python 3.11 or newer is required.

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
```

Run the offline transport smoke test:

```bash
python3 scripts/smoke_mcp_stdio.py
```

The test does not need credentials and does not make live DataLens requests.

## 2. Choose a project root

Create or select a directory for the dashboard project:

```bash
mkdir -p /absolute/path/to/your/dashboard-project
```

The server receives this path through `--project-root`. Tools use it for local requirements, plans, validation outputs, and deployment artifacts. DataLens object IDs are separate inputs; the path does not imply a live target.

Read-only mode refers to DataLens mutations. Local planning tools may still write generated artifacts inside this project root.

Built-in safe defaults are enough to start. If you need project-local placeholders or display settings, create an untracked config inside the project:

```bash
mkdir -p /absolute/path/to/your/dashboard-project/config
cp config/datalens_mcp.local.example.json \
  /absolute/path/to/your/dashboard-project/config/datalens_mcp.local.json
```

Local config cannot enable live writes or bypass safety gates.

## 3. Create an external env file

Offline tools work without this file. Live read tools need an organization ID and IAM token:

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

`YC_IAM_TOKEN` can replace `DATALENS_IAM_TOKEN`. Keep the file outside Git and pass only its absolute path to Codex.

## 4. Register the server

Add this block to `~/.codex/config.toml` and replace all paths:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
```

Alternatively, use the CLI:

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Check registration with `codex mcp list`, then restart Codex.

## 5. Verify safe runtime state

Ask Codex:

> Call `dl_runtime_status` through the DataLens MCP server. Show the project root, auth presence, selected API version, and the write flags. Do not call a mutation tool.

Before any live work, verify:

- `allow_writes` is `false`;
- `allow_save` is `false`;
- `allow_publish` is `false`;
- `expert_rpc_enabled` is `false`;
- the reported project root is the directory you selected;
- auth status is reported without token values.

## 6. Verify live read access

Ask Codex:

> Run `dl_auth_probe`, then call `dl_list_workbooks`. This is a read-only check. Do not save, publish, or modify anything.

The auth probe uses a minimal workbook-list read. If it returns `BLOCKED_LIVE_CREDENTIALS`, correct the external env file and restart the MCP process. Do not share the credential value while troubleshooting.

After auth succeeds, continue with `dl_get_workbook_entries`, `dl_get_entries_relations`, or `dl_snapshot_dashboard` for objects the account may access.

## 7. Plan before changing anything

A normal existing-dashboard workflow is:

1. Read the exact target and its relations.
2. Create a fresh dashboard snapshot.
3. Build and validate the route and payload plan.
4. Create a safe-apply plan.
5. Review target IDs, affected objects, and blocked reasons.
6. Enable only the mutation gates required for the approved run.
7. Save first and verify saved readback.
8. Publish only when the requested delivery intent includes publish and the publish gate is enabled.
9. Verify published readback and create the deployment report.

Setting `DATALENS_MCP_ENABLE_WRITES=1` does not skip any of the other steps. Review, draft, plan-only, save-only, and no-publish instructions remain binding.

## Update or remove the registration

After updating the checkout, reinstall the package and restart Codex:

```bash
cd /absolute/path/to/datalens-dev-mcp
.venv/bin/python -m pip install .
python3 scripts/smoke_mcp_stdio.py
```

Use the Codex MCP management commands to inspect or remove the configured server. The exact source of truth is `~/.codex/config.toml`.

## Next documentation

- [`docs/mcp/codex_connection.md`](mcp/codex_connection.md): compact connection reference and troubleshooting.
- [`docs/configuration.md`](configuration.md): local config precedence and supported settings.
- [`docs/local-only-safety-model.md`](local-only-safety-model.md): trust boundaries and mutation gates.
- [`docs/mcp/tools.md`](mcp/tools.md): tool catalog.
- [`docs/mcp/response_contracts.md`](mcp/response_contracts.md): structured response contracts.
