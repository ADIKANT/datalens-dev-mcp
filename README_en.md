# datalens-dev-mcp

[Русский](README.md) · **English**

[Quick start](#quick-start) · [DataLens access](docs/access_en.md) · [Connect](#connect-an-mcp-client) · [Tools](docs/tools_en.md) · [Interactive JS Cookbook](https://adikant.github.io/datalens-dev-mcp/?lang=en) · [Workflows](#example-tasks) · [Sources](docs/sources_en.md) · [Safety](#change-safety) · [Русский](README.md)

`datalens-dev-mcp` is a local [MCP server](https://modelcontextprotocol.io/) that connects Codex, Claude, and other MCP clients to Yandex DataLens. The user describes a task in plain language, the client calls the server's typed tools, and the server reads current objects through the DataLens Public API, checks dependencies and request schemas, prepares changes, saves them, and publishes when requested with result readback.

It is not a separate DataLens interface or a standalone AI assistant. The project gives an MCP client controlled local access to DataLens development operations and works only with the current user's permissions.

### What you get

Once connected, you can:

- find the required workbook, dashboard, chart, dataset, or connection;
- understand a dashboard's structure, objects, and dependencies;
- capture a local dependency snapshot and run a read-only audit;
- prepare a plan, create an object, or make a bounded change;
- save a draft or save and publish a validated version;
- receive saved/published readback, reports, and paths to local artifacts.

For example:

> Fix chart `<CHART_ID>` in workbook `<WORKBOOK_ID>`: `<REQUIREMENT>`. Save and publish the result, then verify the saved and published versions.

[Go to quick start](#quick-start)

> The server runs locally over stdio, opens no inbound HTTP port, and uses no separate hosted broker. This is an independent Alpha project and is not an official Yandex or Yandex Cloud product.

### How it works

```text
User
  -> Codex / Claude / another MCP client
  -> local datalens-dev-mcp
  -> Yandex DataLens Public API

project root
  <- snapshots, plans, checks, readback, and reports
```

The user states the objective, and the MCP client selects and calls the appropriate tools. The server applies checks, calls the DataLens API, and stores local artifacts inside the selected project root. The client presents the result and, when it has browser access, can additionally verify rendering in the DataLens interface.

## Capabilities

| User goal | Result |
| --- | --- |
| Find and inspect objects | Workbook contents plus reads of dashboards, charts, datasets, connections, and relations |
| Run an audit | Local dependency-graph snapshot, diagnostic findings, and reports without writes |
| Prepare a change | A plan with targets, affected fields, API methods, checks, and blockers |
| Create or update | A validated payload for a dashboard, chart, HTML page, dataset, or connection |
| Change part of a solution | A bounded dashboard-tab, dataset-model, or related-object-group update |
| Deliver the result | Save, saved readback, publish from verified saved state, and published readback |
| Work locally | Standalone HTML artifacts, project manifests, snapshots, plans, and reports inside the project root |

[Open the interactive JavaScript Visualization Cookbook →](https://adikant.github.io/datalens-dev-mcp/?lang=en)

It contains shared Tips, 34 copy-ready JavaScript visualizations, three linked
application cases, source contracts, and complete Editor tab sets.
The [Markdown catalog and source files](docs/cookbook/README_en.md) remain available in the repository.

### What the server does and what remains with the MCP client

| Server | MCP client |
| --- | --- |
| Exposes typed tools, reads the DataLens API, validates and performs permitted operations, and creates local artifacts | Interprets the plain-language request, selects the tool sequence, presents results, and controls any UI-verification capabilities available to it |

The server has no language model, chat, or user-facing web UI of its own. It does not replace the DataLens interface and cannot establish visual quality without a separate rendering check.

### How this differs from disconnected DataLens API calls

- The MCP client uses typed operations instead of assembling arbitrary HTTP requests itself.
- A change is built on the current saved version of the object.
- The exact target, revision, and payload are checked before writing.
- Unknown and untouched fields are preserved while only the declared scope changes.
- Save and publish are separate stages with separate readbacks.
- Related actions can run as one verifiable group, while plans and results remain local artifacts.

This process reduces the risk of writing to the wrong object, dropping fields, or publishing an unverified version. A conflict or uncertain result stops the cycle instead of triggering a hidden write retry.

## Example tasks

### Connection check

```text
Use the DataLens MCP server. Check local configuration and real DataLens access. Show whether reading, saving, and publishing are available. Do not change anything.
```

The client uses `dl_runtime_status`, followed by the minimal live `dl_auth_probe`.

### Read-only audit

```text
Audit dashboard <DASHBOARD_ID> in workbook <WORKBOOK_ID>. Show its structure, related objects, dependencies, and main risks. Do not save or publish anything.
```

### Plan without applying

```text
Plan a change to chart <CHART_ID>: <REQUIREMENT>. Show which fields and objects would be affected, but do not save anything.
```

### Save without publishing

```text
Update <OBJECT_TYPE> <OBJECT_ID>: <REQUIREMENT>. Save the change and verify saved state, but do not publish.
```

### Normal change

```text
Fix chart <CHART_ID> in workbook <WORKBOOK_ID>: <REQUIREMENT>. Save and publish the result, then verify the saved and published versions.
```

### Create an object

```text
Create a <OBJECT_TYPE> in workbook <WORKBOOK_ID> with these requirements: <REQUIREMENTS>. Check dependencies and request data, then save and publish the result.
```

### HTML page

```text
Create a self-contained HTML page in workbook <WORKBOOK_ID>: <REQUIREMENT>. Validate its sandbox contract, save it, read saved state, publish that revId, and verify published state.
```

### What the result looks like

This is a response outline, not the exact JSON contract:

```text
Result
- target object found
- change validated
- saved version read and matched to the plan
- published version read
- report created
- local artifact paths returned
- UI verification completed or explicitly marked unavailable
```

When an operation stops, the user receives the reason and a safe next step, such as rereading after a revision conflict or reconciling DataLens state after an uncertain result.

## Operation modes

The task wording selects the stopping point; users do not need to learn every tool name to choose a mode.

| Request | Behavior |
| --- | --- |
| Audit, review, diagnose, inspect | Reads and local reports only |
| `plan-only` | Plan and validation without writing |
| `save-only`, `no-publish`, “save without publishing” | Save and saved readback without publish |
| Create, fix, update, enhance, redesign | Save, saved readback, publish from saved state, and published readback |

An explicit `0` in a write/save/publish environment setting hard-disables that capability and overrides the request. The normal lifecycle does not delete complete objects; separate confirmation is used only for a project-manifest `retire_legacy_objects` action with exact IDs and an unchanged plan.

## Supported objects and limitations

### Supported

- listing available workbooks and their contents;
- reading relations, dashboards, Wizard/Editor/QL charts, datasets, and connections;
- creating and updating supported dashboards, charts, HTML pages, datasets, and connections through planning and Safe Apply;
- bounded dashboard-tab changes and guarded dataset-model changes;
- local snapshots of a dashboard and its dependency graph;
- local self-contained HTML artifact generation, sandbox validation, and a guarded Public API lifecycle for HTML Pages;
- declared project-manifest dry-run and apply processes;
- storing plans, snapshots, readback, and reports inside the project root.

### Wizard, Editor, and QL

- New standard KPIs, tables, lines, areas, columns, combined charts, pie charts, scatter/bubble charts, treemaps, funnels, and maps use Wizard by default.
- Updates preserve the existing chart technology and `visualization_id`.
- Editor is selected for an explicit JavaScript request or a documented Wizard capability gap.
- QL is used only on a direct request with an explicit payload or current QL version; it is never selected automatically or used as a fallback.
- Create and full redesign automatically use `standard_dashboard`, including
  role-based titles, dashboard composition, a protected Editor runtime, and final
  payload/QA attestation while the autonomous surface keeps lifecycle calls inside the server.

See the full policy in [`docs/route-policy_en.md`](docs/route-policy_en.md).

### Limitations

- The server is not a hosted service, chatbot, or DataLens user interface.
- It grants no permissions beyond the current user's permissions.
- Arbitrary whole-object deletion, including whole-object QL deletion, is unavailable.
- Object moves and changes to access rights, licenses, or credentials are unsupported.
- The local HTML generator performs no live write by itself; HTML Page create/update uses the separate guarded lifecycle, while whole-object deletion remains unavailable.
- `dl_diagnose` analyzes supplied data and does not query databases on its own.
- API readback verifies object structure; visual verification depends on the MCP client's browser capabilities.
- A snapshot covers the selected dashboard's dependency graph, not necessarily the entire organization.
- A method may exist in the API catalog while remaining unsupported for writes.

The project does not claim complete DataLens coverage and does not replace manual review of important changes.

## Quick start

Requirements: Python 3.11+, a local stdio MCP client, and, for live access, an organization ID, IAM token, and permissions on the target workbook.

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

Follow the [DataLens access guide](docs/access_en.md). A minimal protected env file:

```dotenv
DATALENS_ORG_ID=<ORGANIZATION_ID>
DATALENS_IAM_TOKEN=<IAM_TOKEN>
DATALENS_API_BASE_URL=https://api.datalens.tech
DATALENS_MCP_ENABLE_WRITES=1
DATALENS_MCP_LIVE_ALLOW_SAVE=1
DATALENS_MCP_LIVE_ALLOW_PUBLISH=1
DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1
DATALENS_MCP_ENABLE_EXPERT_RPC=0
```

Keep the file outside the repository with `0600` permissions and pass its absolute path through `DATALENS_ENV_FILE`. With a configured `yc` CLI, the server can obtain an initial IAM token and refresh an expired token once.

## Connect an MCP client

Replace `/absolute/path/...` with absolute paths. `--project-root` selects the local directory for inputs and artifacts; live DataLens object IDs are supplied separately in the task.

### Codex

Add this to `~/.codex/config.toml` or a trusted project's `.codex/config.toml`:

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

Or register the same command from the CLI:

```bash
codex mcp add datalens_dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Run `codex mcp list`, restart Codex, and inspect `/mcp`. See [Codex setup](docs/codex_setup_en.md) for details.

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

Copyable configurations: [`examples/clients/`](examples/clients/).

## First session

Start with a read-only check:

> Use the DataLens MCP server. Call `dl_runtime_status`, then `dl_auth_probe`. Show whether reading, saving, and publishing are available. Do not change anything or print credentials.

`dl_runtime_status` checks local configuration and hard-off switches. `dl_auth_probe` performs a minimal live `getWorkbooksList`. After a successful check, discover objects, read their relations, or use one of the [copyable workflows](#example-tasks).

## Change safety

Before writing, the server:

1. rereads the current saved version;
2. verifies the exact target type and ID;
3. checks the revision and expected fields;
4. applies only the requested change and preserves untouched fields;
5. validates the payload and related conditions;
6. reads and verifies saved state after save;
7. builds publish only from verified saved state;
8. reads published state after publish.

A revision conflict, lock, uniqueness violation, or uncertain write result stops the cycle. `DATALENS_MCP_ENABLE_WRITES=0`, `DATALENS_MCP_LIVE_ALLOW_SAVE=0`, and `DATALENS_MCP_LIVE_ALLOW_PUBLISH=0` override the request.

API readback verifies object structure and state. Actual rendering requires a separate browser check by the MCP client; when it is unavailable, the result should state that limitation explicitly.

See the [safety model](docs/local-only-safety-model_en.md) and [Safe Apply](docs/safe-apply_en.md).

## Documentation

| Topic | Guide |
| --- | --- |
| All documentation | [`docs/README_en.md`](docs/README_en.md) |
| Access, IAM token, and roles | [`docs/access_en.md`](docs/access_en.md) |
| Connect Codex | [`docs/codex_setup_en.md`](docs/codex_setup_en.md) |
| 8 autonomous tools and compatibility | [`docs/tools_en.md`](docs/tools_en.md) |
| Copyable workflows | [`docs/usage-flow_en.md`](docs/usage-flow_en.md) |
| Wizard, Editor, and QL | [`docs/route-policy_en.md`](docs/route-policy_en.md) |
| Safe Apply and readback | [`docs/safe-apply_en.md`](docs/safe-apply_en.md) |
| Architecture and API coverage | [`docs/architecture.md`](docs/architecture.md), [`docs/datalens/api_contract_coverage.md`](docs/datalens/api_contract_coverage.md) |

The exact schema of the active surface is available through MCP `tools/list`. The compact `autonomous-v2` profile is the default; `legacy-v1` preserves the previous 39 lifecycle tools.

## Project status

- Independent project and not an official Yandex or Yandex Cloud product.
- Python package maturity: **Alpha**.
- Use deliberately selected targets for live writes and verify the result.
- `main` contains the single current server implementation; Git history and reviewed pull requests preserve change history.
- The current installation's `tools/list` is authoritative; the default `autonomous-v2` surface contains 8 task-level tools.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
python3 scripts/check_docs_consistency.py
python3 scripts/run_quick_checks.py
python3 scripts/run_offline_acceptance.py
```

Offline acceptance uses no real DataLens credentials and performs no live writes.

## License and sources

Project code and original documentation are licensed under the [Apache License 2.0](LICENSE). Reference data adapted from Yandex Cloud documentation includes [CC BY 4.0](LICENSES/CC-BY-4.0.txt) attribution. See [`docs/sources_en.md`](docs/sources_en.md) for official sources and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for complete notices.
