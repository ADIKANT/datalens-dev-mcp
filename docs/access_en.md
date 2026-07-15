# DataLens access

[Русский](access.md) · **English** · [Project home](../README_en.md) · [Codex setup](codex_setup_en.md)

[Quick start](../README_en.md#quick-start) · **DataLens access** · [Connect](codex_setup_en.md) · [Tools](tools_en.md) · [Workflows](usage-flow_en.md) · [Sources](sources_en.md) · [Safety](local-only-safety-model_en.md) · [Русский](access.md)

The Public API requires Yandex Cloud CLI, an organization ID, an IAM token, and access to the target workbook. The server reads these values from a separate env file and does not return them in MCP responses.

## 1. Install and initialize Yandex Cloud CLI

Install `yc` using the [official quickstart](https://yandex.cloud/ru/docs/cli/quickstart), then initialize it interactively:

```bash
yc init
yc config list
```

Run `yc iam create-token` as the user who has DataLens access. If `yc` asks you to sign in again, complete the interactive login in a terminal and retry the check.

## 2. Get the organization ID

Copy the ID from Yandex Cloud or follow [Get the organization ID](https://yandex.cloud/ru/docs/organization/operations/organization-get-id). Store it as `DATALENS_ORG_ID`.

Use the organization that owns the target DataLens workbooks. One account may have access to multiple organizations.

## 3. Check DataLens roles

[DataLens roles](https://yandex.cloud/ru/docs/datalens/security/roles) apply to the service and to individual workbooks or collections.

- `datalens.workbooks.viewer` can read workbook contents.
- `datalens.workbooks.editor` or a broader inherited role is needed to edit nested objects.
- `datalens.workbooks.admin` or an inherited collection role with equivalent permissions is needed to publish nested objects.

Grant access only to the workbooks and collections the server should use. A successful API probe proves that workbook listing works; permission for a particular mutation is checked against its target object.

## 4. Create an IAM token

Follow the official guide: [Create an IAM token for a local user](https://yandex.cloud/ru/docs/iam/operations/iam-token/create-for-local).

```bash
yc iam create-token
```

The token lifetime is at most 12 hours. Copy the result only to the protected env file. Never put it in `config.toml`, command arguments, prompts, logs, issues, or repository files.

## 5. Create a protected env file

```bash
mkdir -p ~/.config/datalens-dev-mcp
touch ~/.config/datalens-dev-mcp/env
chmod 600 ~/.config/datalens-dev-mcp/env
```

Fill `~/.config/datalens-dev-mcp/env`:

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

Pass the absolute file path to the MCP client as `DATALENS_ENV_FILE`. The [DataLens Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) uses an IAM token and organization ID; the server builds the `Authorization` and `x-dl-org-id` headers.

### Automatic token bootstrap and refresh

With `DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1`, the server runs the configured `yc iam create-token` command when:

1. `dl_auth_probe` cannot find an initial token in the canonical env file;
2. DataLens returns HTTP 401 for an expired token.

The new value is written atomically to `DATALENS_ENV_FILE`, the file mode is set to `0600`, and the original request is retried once. Updating the token in the canonical env file does not require a client restart because the server reloads that file. Restart the client after changing MCP process settings.

If `yc` is not on the MCP process `PATH`, set its absolute path in `DATALENS_YC_BINARY`. The `refresh_available` field from `dl_runtime_status` confirms that the refresh command was resolved.

For manual token management, keep refresh disabled and replace `DATALENS_IAM_TOKEN` with the output of `yc iam create-token` when it expires.

## 6. Connect the MCP client

Codex example:

```toml
[mcp_servers.datalens_dev]
command = "/absolute/path/to/datalens-dev-mcp/.venv/bin/datalens-dev-mcp"
args = ["stdio", "--project-root", "/absolute/path/to/your/dashboard-project"]
cwd = "/absolute/path/to/your/dashboard-project"
env = { DATALENS_ENV_FILE = "/absolute/path/to/home/.config/datalens-dev-mcp/env" }
default_tools_approval_mode = "approve"
```

See the [Codex setup guide](codex_setup_en.md). Claude and generic client files are under [`examples/clients/`](../examples/clients/).

## 7. Check configuration and access

Call `dl_runtime_status` first. It checks local configuration and reports:

- whether the canonical env file was found;
- whether the organization ID and token are present;
- whether write, save, and publish are available;
- whether token refresh through `yc` is available.

Then call `dl_auth_probe`. It performs a minimal `getWorkbooksList` request with page size 1.

Copyable prompt:

> Call `dl_runtime_status` and `dl_auth_probe` through the DataLens MCP server. Show credential presence without values, the write/save/publish state, token-refresh availability, and the live access-check result. Do not change anything.

## Access error categories

| Result | Cause | Action |
| --- | --- | --- |
| `missing_credentials` | No organization ID or token, and `yc` bootstrap is unavailable | Check `DATALENS_ENV_FILE`, `DATALENS_ORG_ID`, and `yc` installation and initialization |
| `expired_token` | The token expired and refresh is disabled or failed | Run `yc iam create-token` and update the env file, or enable refresh on 401 |
| `organization_access_denied` | The user or token cannot access the organization or target | Check the organization ID and [DataLens roles](https://yandex.cloud/ru/docs/datalens/security/roles) |
| `yc_reauthentication_required` | The Yandex Cloud CLI session needs an interactive login | Run `yc init` or the login command shown by the CLI in a terminal |
| `transport_failure` | `api.datalens.tech`, TLS/DNS, or the proxy prevents a connection | Check network, proxy, and API URL |
| `api_failure` | DataLens API returns a technical error after the connection succeeds | Retry after service recovery and retain the sanitized response code |

Do not publish the env-file contents when troubleshooting. The `dl_runtime_status` result, category code, and sanitized `dl_auth_probe` message are sufficient.
