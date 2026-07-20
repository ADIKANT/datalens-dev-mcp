# datalens-dev-mcp

[Русский](README.md) · **English**

[Quick start](#quick-start) · [DataLens access](docs/access_en.md) · [Connect](#connect-an-mcp-client) · [Tools](docs/tools_en.md) · [Workflows](docs/usage-flow_en.md) · [Sources](docs/sources_en.md) · [Safety](docs/local-only-safety-model_en.md) · [All documentation](docs/README_en.md) · [Русский](README.md)

`datalens-dev-mcp` is a local Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for developing Yandex DataLens dashboards with Codex, Claude, and other MCP clients. It reads DataLens objects, builds and validates change plans, saves changes, and publishes the verified saved version.

The MCP client starts the server on your computer over stdio. The server reaches the [DataLens Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) with your credentials. It does not require an inbound network listener, a hosted broker, or project telemetry.

> This is an independent community project and is not an official Yandex or Yandex Cloud product.

## Capabilities

| Goal | What the server does |
| --- | --- |
| Setup | Checks local configuration and real DataLens access |
| Discovery | Lists workbooks and entries and reads object relations |
| Audit | Captures a dashboard together with related charts, datasets, and connections |
| Development | Plans dashboard, chart, dataset, and connection creation or updates |
| Validation | Checks API schemas, SQL, relations, selectors, layout, and Editor code |
| Delivery | Performs a fresh read, saves the change, verifies saved state, publishes it, and verifies the result |
| Reference | Answers bounded DataLens and API questions with source links |

Write, save, and publish capabilities are available in the standard configuration. The request determines the operation:

- “review”, “audit”, “diagnose”, and “inspect” are read-only;
- “plan” and `plan-only` stop after planning;
- “save without publishing”, `save-only`, and `no-publish` stop after saved readback;
- “create”, “fix”, “update”, “enhance”, and “redesign” continue through save, saved readback, publish from saved state, and final verification;
- arbitrary whole-object deletion is unavailable; a project-manifest
  `retire_legacy_objects` action requires separate confirmation of the
  unchanged plan and exact IDs.

The [guide to all 38 tools](docs/tools_en.md) describes the purpose, inputs, result, and operation class of every call.

## Requirements

- Python 3.11 or newer.
- Codex, Claude Code, Claude Desktop, or another MCP client that can launch a local stdio server.
- For DataLens access: Yandex Cloud CLI, an organization ID, and access to the target workbook.

## Quick start

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\datalens-dev-mcp.exe`. For server development, install with `.venv/bin/python -m pip install -e '.[test]'`.

Next, follow the [DataLens access guide](docs/access_en.md). A minimal protected env file looks like this:

```dotenv
DATALENS_ORG_ID=<ORGANIZATION_ID>
DATALENS_IAM_TOKEN=<IAM_TOKEN>
DATALENS_API_BASE_URL=https://api.datalens.tech
DATALENS_API_VERSION=auto
DATALENS_MCP_ENABLE_WRITES=1
DATALENS_MCP_LIVE_ALLOW_SAVE=1
DATALENS_MCP_LIVE_ALLOW_PUBLISH=1
DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

IAM tokens have a limited lifetime. With an initialized `yc` CLI, the server can obtain an initial token and refresh an expired one, then atomically store it in `DATALENS_ENV_FILE` with `0600` permissions.

## Connect an MCP client

Replace every `/absolute/path/...` with an absolute path. `--project-root` selects the local directory for inputs, plans, and reports. Workbook, dashboard, and other live object IDs are supplied separately in the task.

### Codex

Add this block to `~/.codex/config.toml` or a trusted project's `.codex/config.toml`:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
default_tools_approval_mode = "approve"
startup_timeout_sec = 20
tool_timeout_sec = 120
```

`default_tools_approval_mode = "approve"` lets Codex run normal calls to this MCP server without a separate client prompt before save or publish. Separate confirmation applies only to a project-manifest `retire_legacy_objects` action.

You can register the same server from the CLI:

```bash
codex mcp add datalens_dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Run `codex mcp list`, restart Codex, and inspect `/mcp`. See the [Codex setup guide](docs/codex_setup_en.md) for details.

### Claude Code

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Verify the registration with `claude mcp list`.

### Claude Desktop and other stdio clients

```json
{
  "mcpServers": {
    "datalens-dev": {
      "command": "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp",
      "args": ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"],
      "env": {
        "DATALENS_ENV_FILE": "/absolute/path/to/home/.config/datalens-dev-mcp/env"
      }
    }
  }
}
```

Copyable files are available under [`examples/clients/`](examples/clients/).

## First session

Start by checking the connection:

> Use the DataLens MCP server. Call `dl_runtime_status`, then `dl_auth_probe`. Show whether write, save, and publish are available, and list the available workbooks. Keep this step read-only and never print credentials.

`dl_runtime_status` checks local settings. `dl_auth_probe` performs a minimal live `getWorkbooksList` request. After a successful probe, use `dl_get_workbook_entries`, `dl_snapshot_dashboard`, `dl_read_object`, and `dl_get_entries_relations`.

For a change, state the objective and the target:

> Fix chart `<CHART_ID>` in workbook `<WORKBOOK_ID>`: `<CHANGE DESCRIPTION>`. Read the current saved object and its relations, validate the plan, save the change, verify saved state, publish from the saved version, and verify the published result.

The [usage workflows](docs/usage-flow_en.md) include copyable prompts for audits, plan-only work, save-only delivery, and normal changes.

## Change safety

Before writing, the server checks the exact target, current revision, request schema, and object relations. Updates preserve unknown fields and the existing chart technology. Publishing uses the verified saved version and is followed by a separate readback.

Set `DATALENS_MCP_ENABLE_WRITES`, `DATALENS_MCP_LIVE_ALLOW_SAVE`, or `DATALENS_MCP_LIVE_ALLOW_PUBLISH` to `0` to disable that capability. A hard-off value takes precedence over the request.

Removing a legend, filter, column, tab, or widget inside an object is an update.
The standard lifecycle tools do not delete complete objects; only a
project-manifest `retire_legacy_objects` action is supported, with two-step
confirmation of exact IDs and the unchanged plan. Whole-object QL deletion is
unsupported.

See the [safety model](docs/local-only-safety-model_en.md), [safe apply](docs/safe-apply_en.md), and [chart route policy](docs/route-policy_en.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `src/datalens_dev_mcp/` | Python package, MCP server, DataLens API client, planners, and validators |
| `config/` | Versioned behavior and route settings |
| `schemas/` | JSON Schema for inputs, plans, and reports |
| `templates/` | Wizard, Editor, and project templates |
| `docs/` | User guides and technical documentation |
| `examples/` | Synthetic examples and MCP client configurations |
| `scripts/` | Checks, packaging, and reference-data maintenance |
| `tests/` | Unit and offline integration tests |

See [`docs/architecture.md`](docs/architecture.md) for architecture and [`docs/configuration_en.md`](docs/configuration_en.md) for local settings.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
python3 scripts/run_quick_checks.py
python3 scripts/run_offline_acceptance.py
```

Offline acceptance does not require DataLens credentials. Use deliberately selected objects for live-write checks.

## License and sources

Project code and original documentation are licensed under the [Apache License 2.0](LICENSE). Reference data adapted from Yandex Cloud documentation includes [CC BY 4.0](LICENSES/CC-BY-4.0.txt) attribution. See [`docs/sources_en.md`](docs/sources_en.md) for the official source map and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for complete notices.
