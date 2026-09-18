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
DATALENS_MCP_ENABLE_WRITES=1
DATALENS_MCP_LIVE_ALLOW_SAVE=1
DATALENS_MCP_LIVE_ALLOW_PUBLISH=1
DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1
DATALENS_MCP_ENABLE_EXPERT_RPC=0
# DATALENS_YC_BINARY=/absolute/path/to/yc
```

Pass the absolute file path to the MCP client as `DATALENS_ENV_FILE`. The [DataLens Public API](https://yandex.cloud/ru/docs/datalens/operations/api-start) uses an IAM token and organization ID; the server builds the `Authorization` and `x-dl-org-id` headers.

### Automatic token bootstrap and refresh

With `DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1`, an initial API probe without a token and a read after HTTP 401 may run `yc iam create-token --no-browser --no-user-output` once (up to 15 seconds). A failure is retained in the current runtime so later reads do not repeat the same failed attempt.

Use `dl_auth_refresh` for token renewal. It defaults to `allow_browser=true`: the configured `yc` can open **the system external browser** for its existing profile/SSO sign-in and wait up to 120 seconds. A valid browser session may authenticate automatically; the user supplies a password or MFA only when required. `allow_browser=false` keeps the noninteractive mode. A background timeout alone does not establish a login prohibition or network failure.

The token stays in process memory, updates both API and SDK clients, and is not written to the credentials file. Successful `dl_auth_refresh` also verifies access with a harmless API read. Do not transfer tokens manually, copy callback URLs into an embedded browser, or replay an unknown write during recovery. The account, profile and permissions stay unchanged.

If `yc` is absent from the MCP process PATH, set an absolute `DATALENS_YC_BINARY`. `dl_auth_check` returns a safe configuration/access report. After one failed browser-enabled attempt, inspect pending password/MFA, helper launch and network evidence; do not keep repeating an unchanged failure.

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
- whether interpreter, package/build, cwd, state root, and public tool surface match the launching process.
- the shared API limiter settings and aggregate request, 429, retry, and cache-hit counters.

Then call `dl_auth_probe`. It performs a minimal `getWorkbooksList` request with page size 1.

Copyable prompt:

> Call `dl_runtime_status` and `dl_auth_probe` through the DataLens MCP server. Show credential presence without values, the write/save/publish state, token-refresh availability, and the live access-check result. Do not change anything.

## Access error categories

| Result | Cause | Action |
| --- | --- | --- |
| `missing_credentials` | No organization ID or token, and `yc` bootstrap is unavailable | Check `DATALENS_ENV_FILE`, `DATALENS_ORG_ID`, and `yc` installation and initialization |
| `expired_token` | The token expired and refresh is disabled or failed | Run `yc iam create-token` and update the env file, or enable refresh on 401 |
| `organization_access_denied` | The user or token cannot access the organization or target | Check the organization ID and [DataLens roles](https://yandex.cloud/ru/docs/datalens/security/roles) |
| `yc_reauthentication_required` | The Yandex Cloud CLI session needs an interactive login | Run `scripts/codex_mcp_launch.sh --recover-credentials`; it invokes `yc init` only when safe background refresh is insufficient |
| `transport_failure` | `api.datalens.tech`, TLS/DNS, or the proxy prevents a connection | Check network, proxy, and API URL |
| `api_failure` | DataLens API returns a technical error after the connection succeeds | Retry after service recovery and retain the sanitized response code |

Do not publish the env-file contents when troubleshooting. The `dl_runtime_status` result, category code, and sanitized `dl_auth_probe` message are sufficient.
