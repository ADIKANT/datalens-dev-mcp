# Connect `datalens-dev-mcp` to Codex

Codex can start `datalens-dev-mcp` as a local stdio MCP server. Install the server in a virtual environment before adding it to Codex:

```bash
git clone https://github.com/ADIKANT/datalens-dev-mcp.git
cd datalens-dev-mcp
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/datalens-dev-mcp --version
python3 scripts/smoke_mcp_stdio.py
```

Use absolute paths in MCP configuration. Codex does not expand repository placeholders for you.

## Option 1: `config.toml`

Add the following server to `~/.codex/config.toml`:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
```

`--project-root` selects the local workspace used for project inputs and generated artifacts. It does not select a DataLens workbook or dashboard; pass those IDs to tools when needed. The env file is optional for offline planning and required for authenticated live reads.

A copyable example is available at [`examples/clients/codex.toml`](../../examples/clients/codex.toml).

## Option 2: Codex CLI

Register the same subprocess from a terminal:

```bash
codex mcp add datalens-dev \
  --env DATALENS_ENV_FILE=/absolute/path/to/home/.config/datalens-dev-mcp/env \
  -- /absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp \
  stdio --project-root /absolute/path/to/your/dashboard-project
```

Use `codex mcp list` to inspect registered servers. Restart Codex after adding or changing a server.

## Credentials

Keep credentials outside the checkout:

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

`YC_IAM_TOKEN` is accepted as an alternative token variable. Never place real values in `config.toml`, command arguments, prompts, logs, or committed files.

## Verify the connection

Start with a read-only prompt:

> Use the DataLens MCP server. Call `dl_runtime_status` and confirm that `allow_writes`, `allow_save`, and `allow_publish` are false. Then call `dl_auth_probe`. Do not change any DataLens object.

`dl_runtime_status` should identify the selected project root and report credential presence without returning credential values. `dl_auth_probe` performs a minimal read when credentials are available and returns a sanitized blocked result otherwise.

For a deeper offline transport check, run:

```bash
cd /absolute/path/to/datalens-dev-mcp
python3 scripts/smoke_mcp_stdio.py
```

The smoke test covers MCP initialization, tools, prompts, resources, malformed input handling, and stdout cleanliness without contacting DataLens.

## Checkout launcher

`scripts/codex_mcp_launch.sh` is a POSIX convenience launcher for a source checkout. It finds the checkout virtual environment, defaults mutation gates to off, and reserves stdout for MCP. It always uses the checkout as its project root, so the installed console command shown above is preferable when your dashboard project lives elsewhere.

Launcher-based configuration:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/scripts/codex_mcp_launch.sh"
args = []
cwd = "/absolute/path/to/datalens-dev-mcp"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
```

## Troubleshooting

- **Server does not start:** run the executable's `--version`, then run `python3 scripts/smoke_mcp_stdio.py` from the checkout. Verify every configured path is absolute and exists.
- **Codex shows an old tool list:** restart Codex after reinstalling or editing `config.toml`.
- **`BLOCKED_LIVE_CREDENTIALS`:** verify `DATALENS_ENV_FILE`, file permissions, `DATALENS_ORG_ID`, and one token variable. Do not paste the token into chat for diagnosis.
- **Auth probe fails after working earlier:** IAM tokens expire. Replace the value in the external env file and restart the MCP process.
- **Unexpected write block:** first confirm the block is appropriate. The default is read-only, and write, save, publish, approval, fresh-read, and readback gates are independent.
- **Protocol parse error or stdout pollution:** run the smoke test. Application logging and diagnostics must go to stderr, never stdout.

See [`docs/codex_setup.md`](../codex_setup.md) for the full first-run sequence and [`docs/mcp/local_stdio_contract.md`](local_stdio_contract.md) for the transport contract.
