# Codex setup

[Русский](codex_setup.md) · **English** · [Project home](../README_en.md)

[Quick start](../README_en.md#quick-start) · [DataLens access](access_en.md) · **Connect** · [Tools](tools_en.md) · [Workflows](usage-flow_en.md) · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md) · [Русский](codex_setup.md)

Codex starts `datalens-dev-mcp` as a local stdio server. Codex app, CLI, and IDE extension use the same `config.toml` format. Current MCP settings are documented in the [official Codex MCP guide](https://learn.chatgpt.com/docs/extend/mcp).

## 1. Install the server

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

The last command checks the MCP protocol locally without contacting DataLens.

## 2. Prepare the workspace and access

Create a directory where the server can store plans, snapshots, and reports:

```bash
mkdir -p /absolute/path/to/your/dashboard-project
```

`--project-root` selects this directory. It does not select a DataLens workbook or dashboard.

Then follow [DataLens access](access_en.md): install `yc`, get the organization ID, check roles, and create a protected env file.

## 3. Add the server to `config.toml`

The global Codex configuration is `~/.codex/config.toml`. A trusted project can use `.codex/config.toml` in its root.

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

Use absolute paths. `default_tools_approval_mode = "approve"` allows normal calls to this server without a separate Codex prompt before save or publish. The server still requires confirmation to delete a complete DataLens object.

Copyable file: [`examples/clients/codex.toml`](../examples/clients/codex.toml).

## 4. Alternative: register with the CLI

```bash
codex mcp add datalens_dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

The command creates the server entry. Then open `~/.codex/config.toml` and add these values to `[mcp_servers.datalens_dev]`:

```toml
default_tools_approval_mode = "approve"
startup_timeout_sec = 20
tool_timeout_sec = 120
```

Verify registration:

```bash
codex mcp list
```

## 5. Restart Codex

After installing the package or changing `config.toml`, restart Codex app, the CLI session, or the IDE extension. Open `/mcp` in a new task and confirm that `datalens_dev` is connected and exposes 38 tools.

## 6. Check configuration and access

Send this prompt:

> Use the DataLens MCP server. Call `dl_runtime_status` and show the selected project root, API version, organization-ID and token presence without values, and write, save, publish, and token-refresh availability. Then call `dl_auth_probe`. Do not change anything in this step.

Expected result:

- `project_root` matches the selected directory;
- write, save, and publish are available;
- the canonical env file is found;
- `dl_auth_probe` completes a minimal `getWorkbooksList` call.

A successful workbook-list probe proves general authorization. Access to a particular chart, dataset, or dashboard is checked when that object is read or changed.

## 7. Start working

Read-only audit:

> Audit dashboard `<DASHBOARD_ID>` in workbook `<WORKBOOK_ID>`. Read the current saved version, related objects, and their relations. Show issues and generated report paths. Do not save or publish anything.

Normal change:

> Fix `<OBJECT_TYPE>` `<OBJECT_ID>` in workbook `<WORKBOOK_ID>`: `<REQUIREMENT>`. Read current saved state and relations, validate the plan and request, save the change, verify saved state, publish from the saved version, and verify the published result. Do not ask for another confirmation before save or publish.

See [usage workflows](usage-flow_en.md) for more variants.

## 8. Update and troubleshoot

After updating the checkout, reinstall and restart Codex:

```bash
cd /absolute/path/to/datalens-dev-mcp
.venv/bin/python -m pip install .
python3 scripts/smoke_mcp_stdio.py
codex mcp list
```

| Problem | Check |
| --- | --- |
| Server does not start | Run `--version`, verify absolute paths, and run `scripts/smoke_mcp_stdio.py` |
| `/mcp` shows an old list | Reinstall the package and fully restart Codex |
| Wrong workspace | Fix `args` and `cwd` in `config.toml` |
| No DataLens access | Follow the error table in [DataLens access](access_en.md#access-error-categories) |
| Codex prompts for every tool | Check `default_tools_approval_mode = "approve"` in this server table and restart Codex |
| A change does not save | Use `dl_runtime_status` to confirm write and save are available, then inspect the exact blocker |
| A change saves but does not publish | Check publish in `dl_runtime_status` and remove `save-only` or `no-publish` from the task |

Transport contract: [`docs/mcp/local_stdio_contract.md`](mcp/local_stdio_contract.md).
