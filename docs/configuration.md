# Local Configuration

`datalens-dev-mcp` loads config in this order:

1. Explicit `--local-config <path>` passed to the server.
2. `DATALENS_MCP_LOCAL_CONFIG`.
3. `config/datalens_mcp.local.json` when it exists in the repo root.
4. Built-in safe defaults.

`config/datalens_mcp.local.json` is gitignored. Use it for local project
workspace paths and placeholder workbook/dashboard defaults that should not be
shared in committed files.

Credential values come from a canonical env file when `DATALENS_ENV_FILE` is
set or an env-file path is passed to `DataLensConfig.from_env(...)`. For
credentials, that canonical file takes precedence over stale process env values.
Runtime reports only source location and reload state; it never reports token
values, prefixes, lengths, or token-derived metadata. On HTTP 401, the client
runs a minimal auth probe, reloads the canonical env file, and retries once.
If refresh-on-401 is explicitly enabled, the approved refresh command persists
the new token atomically to the canonical env file, reloads it, and retries
once.

Start from the example:

```bash
cp config/datalens_mcp.local.example.json config/datalens_mcp.local.json
python3 scripts/validate_schemas.py
python3 scripts/smoke_mcp_stdio.py
```

## Supported Sections

- `defaults`: project workspace path plus optional workbook, project, and
  dashboard placeholders.
- `safe_mode`: read-only/plan-only defaults. `allow_writes` must stay `false`.
- `approval_gates`: env and tool approval requirements for write and publish
  flows. Launcher defaults keep guarded write/save/publish flags off; an
  approved mutation run must enable each required gate explicitly. Then
  delivery intent still decides whether a known live implementation/fix/enhance
  target continues from saved readback to publish and published readback after
  all gates.
- `readback`: `none`, `minimal`, `full`, or `debug`. `none` requires a
  justification.
- `validation`: strictness and route/template/relation/secret scan gates.
- `safe_apply`: required approved plan path, approval flag, env write
  enablement, save-first behavior, and readback after save.
- `live_testing`: live tests are off by default and require
  `DATALENS_MCP_RUN_LIVE_TESTS=1`.
- `api_defaults`: request interval, retry count, and timeout defaults.
- `routing`: Wizard-first standard chart mapping, registered JavaScript
  capability gaps, the `wizard_map_native` compatibility alias, and
  explicit-user-request-only QL behavior.
- `style`: style guide, chart design rule, and theme token paths.
- `naming`: native dashboard title/hint metadata policy.
- `selectors`: left labels, percentage widths, 96% row width, and binding
  requirements.

## Effective Config Tool

Codex can call:

```json
{"name": "dl_get_local_config", "arguments": {}}
```

The tool returns the merged effective config and metadata about the source path.
Output is sanitized recursively for accidental token, authorization, password,
or secret keys.

## Safety Rules

- Config cannot enable writes by itself.
- Config cannot make QL automatic, add a runtime fallback between Wizard,
  JavaScript, and QL, or override fresh-read technology preservation.
- Config cannot bypass the delivery-intent state machine or runtime publish
  gates.
- Config cannot allow hidden delete/move/permission operations in normal
  workflows. Explicit removal requires a project manifest
  `retire_legacy_objects` action with object IDs, user decision provenance,
  no-reference proof, approval, execution summary, and post-retire readback.
- Config and normal env vars cannot select a user tool profile. Legacy `mcp`
  config keys and `DATALENS_MCP_TOOL_PROFILE` are ignored by normal runtime and
  reported as internal/profile diagnostics when present.
- Hidden/internal compatibility tools require both
  `DATALENS_MCP_TEST_ONLY_REGISTRY=1` and
  `DATALENS_MCP_ALLOW_HIDDEN_TOOL_CALLS=1`; the hidden-call flag alone is
  ignored.
- Safe apply still requires env enablement, Codex/tool approval, fresh read,
  revision preservation, save mode first, and readback.
- `tools/list` always returns the standard DataLens tool surface. Legacy `mcp`
  keys in ignored local configs are tolerated but ignored and are not returned
  by `dl_get_local_config`.
