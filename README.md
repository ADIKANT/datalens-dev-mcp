# datalens-dev-mcp

[Русская версия](README_ru.md)

`datalens-dev-mcp` is a local Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for AI-assisted development of Yandex DataLens dashboards. It gives MCP clients a governed toolset for inspecting DataLens objects, planning dashboards and charts, validating payloads, and applying approved changes through a guarded save/readback flow.

The server uses stdio: your MCP client starts it as a subprocess on your computer. There is no hosted service, account, or telemetry endpoint in this repository. Live DataLens operations still connect from your machine to the configured DataLens API.

> This is an independent community project. It is not an official Yandex or Yandex Cloud product and is not endorsed by Yandex.

## What it does

- Reads workbooks, workbook entries, object relations, dashboards, charts, datasets, and connections through a sanitized DataLens API client.
- Builds deterministic plans for native Wizard charts and registered Advanced Editor use cases.
- Validates routes, chart roles, dashboard relations, selectors, layouts, internal names, Editor bundles, and generated SQL.
- Maintains a local project workspace for requirements, implementation plans, validation evidence, and deployment reports.
- Creates fresh snapshots before changes and preserves saved object technology and revision data.
- Keeps live writes behind explicit runtime flags, an approved safe-apply plan, save-first semantics, and readback.
- Exposes packaged DataLens reference data compiled from public documentation; source and license details are recorded in `THIRD_PARTY_NOTICES.md`.

The default DataLens runtime is read-only. Local planning tools may still create project artifacts under the directory passed as `--project-root`. You can use offline planning and validation tools without DataLens credentials.

## Requirements

- Python 3.11 or newer.
- An MCP client that can launch a local stdio server, such as Codex, Claude Code, Claude Desktop, or another MCP-compatible tool.
- For live DataLens reads: a Yandex Cloud organization ID and IAM token with access to the target objects.

## Install from source

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\datalens-dev-mcp.exe` in place of the POSIX paths above.

Use `pip install -e .` instead when developing the server itself.

## Configure credentials

Credentials are optional for offline tools. For live reads, create an env file outside the repository:

```bash
mkdir -p ~/.config/datalens-dev-mcp
touch ~/.config/datalens-dev-mcp/env
chmod 600 ~/.config/datalens-dev-mcp/env
```

Add your values without committing the file:

```dotenv
DATALENS_ORG_ID=<YOUR_ORG_ID>
DATALENS_IAM_TOKEN=<YOUR_IAM_TOKEN>
DATALENS_API_BASE_URL=https://api.datalens.tech
DATALENS_API_VERSION=auto

# Keep every mutation gate off for the first session.
DATALENS_MCP_ENABLE_WRITES=0
DATALENS_MCP_LIVE_ALLOW_SAVE=0
DATALENS_MCP_LIVE_ALLOW_PUBLISH=0
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

`YC_IAM_TOKEN` can be used instead of `DATALENS_IAM_TOKEN`. Pass the absolute path to this env file in your client config. Do not put tokens in MCP arguments, prompts, committed config, or issue reports.

## Connect an MCP client

Replace every `/absolute/path/...` value below. `--project-root` is the local directory in which the server may read project inputs and write generated project artifacts. It can be the checkout itself or a separate dashboard project.

Ready-to-copy files are available in [`examples/clients/`](examples/clients/).

### Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
```

Or register the same server from the Codex CLI:

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Restart Codex after changing the config. See [`docs/mcp/codex_connection.md`](docs/mcp/codex_connection.md) for verification and troubleshooting.

### Claude Code

Run this from the dashboard project directory:

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Use `claude mcp list` to verify the registration.

### Claude Desktop

Add the server to the `mcpServers` object in `claude_desktop_config.json`. The default location is `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS and `%APPDATA%\Claude\claude_desktop_config.json` on Windows:

```json
{
  "mcpServers": {
    "datalens-dev": {
      "command": "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp",
      "args": [
        "stdio",
        "--project-root",
        "/absolute/path/to/your/dashboard-project"
      ],
      "env": {
        "DATALENS_ENV_FILE": "/absolute/path/to/home/.config/datalens-dev-mcp/env"
      }
    }
  }
}
```

Restart Claude Desktop after saving the file.

### Other stdio clients

Use the following process definition in any client that accepts MCP stdio command, argument, and environment fields:

```json
{
  "command": "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp",
  "args": [
    "stdio",
    "--project-root",
    "/absolute/path/to/your/dashboard-project"
  ],
  "env": {
    "DATALENS_ENV_FILE": "/absolute/path/to/home/.config/datalens-dev-mcp/env"
  }
}
```

The process communicates with JSON-RPC on stdin/stdout. Clients must not expect an HTTP endpoint. Server diagnostics go to stderr; stdout is reserved for MCP messages.

## First read-only session

After the client connects, ask it to perform these calls in order:

1. Call `dl_runtime_status` and confirm `allow_writes`, `allow_save`, and `allow_publish` are all `false`.
2. Call `dl_auth_probe`. With no credentials, a sanitized blocked result is expected; with valid credentials, it performs a minimal read.
3. Call `dl_list_workbooks`, then `dl_get_workbook_entries` for a workbook you are allowed to inspect.
4. Use `dl_snapshot_dashboard` before planning any change to an existing dashboard.

Example prompt:

> Use the DataLens MCP server. First show `dl_runtime_status` and verify that all mutation gates are off. Then run `dl_auth_probe` and list the workbooks available to this account. Do not save, publish, or change anything.

The tools return structured MCP results and sanitize credential-related errors. The server must never report token values, token fragments, authorization headers, or token-derived metadata.

## Write safety

Read and plan operations are the normal starting point. Enabling `DATALENS_MCP_ENABLE_WRITES=1` only opens the first runtime gate; it does not authorize a blind write. A mutation still requires:

1. A known target and fresh saved readback.
2. A validated payload and approved safe-apply plan.
3. Revision and object-technology preservation.
4. Explicit save enablement and saved readback.
5. Separate publish enablement when publishing is part of the approved delivery intent.
6. Published readback and a deployment report after publish.

Planning, review, draft, save-only, and no-publish instructions continue to block publishing. QL is used only after a direct QL request; it is never selected automatically. Delete, move, and permission operations are not part of the normal write path.

See [`docs/local-only-safety-model.md`](docs/local-only-safety-model.md), [`docs/safe-apply.md`](docs/safe-apply.md), and [`docs/route-policy.md`](docs/route-policy.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `src/datalens_dev_mcp/` | Python package, MCP dispatcher, tools, API client, pipeline, validators, and packaged resources |
| `config/` | Versioned safe defaults, routing policy, style policy, and API metadata |
| `schemas/` | JSON Schemas used for project artifacts and validation |
| `templates/` | Parameterized Wizard, Advanced Editor, requirements, and project templates |
| `docs/` | Operator, safety, API, tool, and workflow documentation |
| `examples/` | Synthetic inputs, response contracts, and MCP client configurations |
| `scripts/` | Offline acceptance, smoke, schema, packaging, and maintenance commands |
| `tests/` | Unit and offline integration tests |

Generated outputs, credentials, virtual environments, caches, and local target configs are intentionally ignored by Git. Keep real object exports and sensitive operational evidence outside commits.

For the component flow and trust boundaries, see [`docs/architecture.md`](docs/architecture.md). For the complete tool surface, see [`docs/mcp/tools.md`](docs/mcp/tools.md) and [`docs/mcp/response_contracts.md`](docs/mcp/response_contracts.md).

## Local configuration

Built-in defaults are safe for a first run. To override project-local placeholders or display preferences, copy the example into the dashboard project and keep the copy untracked:

```bash
mkdir -p /absolute/path/to/your/dashboard-project/config
cp config/datalens_mcp.local.example.json \
  /absolute/path/to/your/dashboard-project/config/datalens_mcp.local.json
```

You can also pass `--local-config /absolute/path/to/config.json` or set `DATALENS_MCP_LOCAL_CONFIG`. Local config cannot enable writes or bypass approval, fresh-read, save-first, readback, and publish gates. See [`docs/configuration.md`](docs/configuration.md).

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
python3 scripts/run_quick_checks.py
python3 scripts/run_offline_acceptance.py
```

The acceptance suite is offline and must not require credentials. Opt-in live checks must use disposable targets and explicitly enabled gates; see [`docs/live_testing_local.md`](docs/live_testing_local.md).

Contributions are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), report vulnerabilities according to [`SECURITY.md`](SECURITY.md), and keep secrets and real customer data out of issues and pull requests.

## License and attribution

Project code and original documentation are licensed under the Apache License 2.0; see [`LICENSE`](LICENSE). Third-party notices and the terms for documentation-derived reference data are listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
