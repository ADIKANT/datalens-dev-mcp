# Local configuration

[Русский](configuration.md) · **English** · [DataLens access](access_en.md) · [Safety](local-only-safety-model_en.md)

## Load order

The server resolves local configuration in this order:

1. `--local-config`;
2. `DATALENS_MCP_LOCAL_CONFIG`;
3. `config/datalens_mcp.local.json` in the repository root;
4. settings packaged with the server.

`config/datalens_mcp.local.json` is ignored by Git. Start from the example:

```bash
cp config/datalens_mcp.local.example.json config/datalens_mcp.local.json
python3 scripts/validate_schemas.py
python3 scripts/smoke_mcp_stdio.py
```

## Execution mode

Local config v2 includes:

```json
{
  "execution": {
    "default": "follow_user_request",
    "writes": true,
    "save": true,
    "publish": true,
    "delete_requires_confirmation": true
  }
}
```

`follow_user_request` selects the action from the task:

- audits, reviews, and diagnostics are read-only;
- `plan-only` creates a plan;
- `save-only` and `no-publish` save without publishing;
- create, fix, update, enhance, and redesign continue through save and publish;
- deleting a complete object requires `confirm_delete=true` for the unchanged plan.

Older local configuration is migrated to v2 when loaded. Use `dl_get_local_config` to inspect the effective settings.

## Canonical env file

Store credentials and hard-off switches outside the repository:

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
# DATALENS_YC_BINARY=/absolute/path/to/yc
```

Pass its absolute path as `DATALENS_ENV_FILE`. The canonical file is reloaded during access checks and before write operations. For write/save/publish, a value of `0` in either the file or the process environment always takes precedence over `1`.

If `yc` is missing from the MCP process `PATH`, set `DATALENS_YC_BINARY`. `dl_runtime_status` reports `refresh_available` without exposing token paths or values.

## Hard-off switches

A value of `0` in either the canonical env file or the MCP process environment always disables the corresponding action:

| Variable | Result at `0` |
| --- | --- |
| `DATALENS_MCP_ENABLE_WRITES` | All write requests are blocked |
| `DATALENS_MCP_LIVE_ALLOW_SAVE` | Save requests are blocked |
| `DATALENS_MCP_LIVE_ALLOW_PUBLISH` | A permitted save ends as `saved_not_published` |
| `DATALENS_ENABLE_TOKEN_REFRESH_ON_401` | The user refreshes the token manually |

Changes to write/save/publish values and the IAM token in the canonical env file apply before the next RPC without restarting. Restart the MCP client to change a variable supplied directly when the process was launched.

## Configuration sections

- `defaults` — workspace and optional project, workbook, and dashboard IDs;
- `execution` — request-driven mode and write/save/publish availability;
- `safe_apply` — fresh reads, revision preservation, save-first, and readback;
- `readback` — readback breadth;
- `validation` — strictness, route, relation, template, and secret checks;
- `live_testing` — checks against deliberately selected objects;
- `api_defaults` — intervals, retries, and timeout;
- `routing` — Wizard, Editor, and QL selection;
- `style`, `naming`, `selectors` — object presentation and layout.

## Inspect effective configuration

Call:

```json
{"name": "dl_get_local_config", "arguments": {}}
```

The response contains merged settings and source metadata. Keys containing token, authorization, password, or secret are sanitized recursively.

Then use `dl_runtime_status` to inspect process capabilities. See [`access_en.md`](access_en.md) for the complete access setup.
