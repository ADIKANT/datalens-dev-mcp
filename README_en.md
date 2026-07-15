# datalens-dev-mcp

[Русский](README.md) · **English**

[Install](#installation) · [Tools](docs/tools_en.md) · [Usage flow](docs/usage-flow_en.md) · [Official sources](docs/sources_en.md) · [Safety](docs/local-only-safety-model.md) · [All documentation](docs/README_en.md)

`datalens-dev-mcp` is a local Python [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for AI-assisted development of Yandex DataLens dashboards. It gives Codex, Claude, and other MCP clients a governed toolset for inspecting DataLens objects, planning changes, validating payloads, and applying approved changes safely.

The server uses stdio: the MCP client starts it as a subprocess on your computer. This repository has no hosted service, account, or telemetry endpoint. Live operations connect from your machine to the configured DataLens Public API.

> This is an independent community project. It is not an official Yandex or Yandex Cloud product and is not endorsed by Yandex.

## Capabilities

| Goal | Capability |
| --- | --- |
| Setup and diagnostics | Inspect runtime configuration, credential presence, and minimal authentication without exposing secrets |
| Read DataLens | Workbooks, entries, object relations, dashboards, charts, datasets, and connections |
| Plan changes | Wizard-first object lifecycle, Advanced Editor for an explicit request or registered capability gap, and QL only after a direct request |
| Validate | Payloads, routes, relations, selectors, layout, SQL, Editor runtime, and source availability |
| Apply changes | Guarded safe apply with fresh read, revision preservation, save, saved readback, publish-from-saved, and published readback |
| Audit | Dashboard graph snapshots, deployment reports, and explicit static/API/save/publish/browser proof levels |
| Reference | Compact source-traced records compiled from public DataLens documentation and API contracts |

Normal operation starts read-only. Local planning tools may create artifacts inside `--project-root`, but DataLens mutations are disabled by default.

- [Guide to all 38 public tools](docs/tools_en.md)
- [Complete flow from connection to runtime QA](docs/usage-flow_en.md)
- [Map of official documentation and API sources](docs/sources_en.md)
- [Technical MCP catalog and response contracts](docs/mcp/tools.md)

## Requirements

- Python 3.11 or newer.
- An MCP client that can launch a local stdio server, such as Codex, Claude Code, Claude Desktop, or another compatible client.
- For live reads: a Yandex Cloud organization ID and IAM token with access to the target objects.

## Installation

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\datalens-dev-mcp.exe`. Install with `pip install -e .` when developing the server itself.

## Credentials

Offline planning does not require credentials. For live reads, create an env file outside the repository:

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

# Keep all mutation gates off for the first session.
DATALENS_MCP_ENABLE_WRITES=0
DATALENS_MCP_LIVE_ALLOW_SAVE=0
DATALENS_MCP_LIVE_ALLOW_PUBLISH=0
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

`YC_IAM_TOKEN` can replace `DATALENS_IAM_TOKEN`. Give the MCP client only the absolute env-file path. Never put tokens in MCP arguments, prompts, tracked configuration, logs, or issue reports.

## Connect an MCP client

Replace every `/absolute/path/...`. `--project-root` is the local directory for project inputs and generated artifacts; it does not select a live workbook or dashboard.

Copyable examples are available under [`examples/clients/`](examples/clients/).

### Codex

Add this server to `~/.codex/config.toml` or a trusted project's `.codex/config.toml`:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
```

Or register it with the CLI:

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Run `codex mcp list`, restart Codex, and inspect `/mcp`. See [`docs/codex_setup_en.md`](docs/codex_setup_en.md) for the complete guide.

### Claude Code

```bash
claude mcp add --transport stdio --scope local \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  datalens-dev -- \
  /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Verify with `claude mcp list`.

### Claude Desktop and generic stdio clients

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

For a generic client, use the nested `command`, `args`, and `env` values. The process exchanges JSON-RPC over stdin/stdout; it has no HTTP endpoint. Diagnostics go to stderr.

## First read-only session

Ask the client to:

1. Run `dl_runtime_status` and confirm `allow_writes`, `allow_save`, and `allow_publish` are `false`.
2. Run `dl_auth_probe` for a minimal safe live read.
3. Run `dl_list_workbooks`, then `dl_get_workbook_entries` for the selected workbook.
4. Run `dl_snapshot_dashboard` before planning any change to an existing dashboard.

Copyable prompt:

> Use the DataLens MCP server. First show `dl_runtime_status` and confirm every mutation gate is off. Then run `dl_auth_probe` and list available workbooks. Do not save, publish, or change anything.

The [usage flow guide](docs/usage-flow_en.md) covers plan-only, save-only, and guarded publish scenarios.

## Write safety

`DATALENS_MCP_ENABLE_WRITES=1` opens only one runtime gate. A mutation still requires:

1. A known target and fresh saved readback.
2. A validated payload and approved safe-apply plan.
3. Revision, unknown-field, and object-technology preservation.
4. Save followed by a distinct saved readback.
5. Publish-from-saved only when delivery intent and the publish gate allow it.
6. Published readback, deployment report, and runtime/browser proof for visible changes.

Planning, review, draft, save-only, and no-publish instructions block publishing. QL requires a direct request. Delete, move, and permission operations are outside the normal write path.

See the [safety model](docs/local-only-safety-model.md), [safe apply](docs/safe-apply.md), and [route policy](docs/route-policy.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `src/datalens_dev_mcp/` | Python package, MCP dispatcher, tools, API client, pipeline, validators, and packaged resources |
| `config/` | Versioned safe defaults, route policy, style, and API metadata |
| `schemas/` | JSON Schemas for project artifacts and validation |
| `templates/` | Wizard, Advanced Editor, requirements, and project templates |
| `docs/` | Documentation hub, guides, safety, API, and technical contracts |
| `examples/` | Synthetic inputs and MCP client configurations |
| `scripts/` | Offline acceptance, smoke, packaging, and maintenance checks |
| `tests/` | Unit and offline integration tests |

See [`docs/architecture.md`](docs/architecture.md) for architecture and trust boundaries and [`docs/configuration.md`](docs/configuration.md) for local configuration.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
python3 scripts/run_quick_checks.py
python3 scripts/run_offline_acceptance.py
```

The acceptance suite runs offline and does not require DataLens credentials. Live checks are opt-in and must use disposable targets.

## License and attribution

Project code and original documentation are licensed under Apache License 2.0: [`LICENSE`](LICENSE). Reference records adapted from Yandex Cloud documentation are attributed under CC BY 4.0: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). See [`docs/sources_en.md`](docs/sources_en.md) for the source map.
