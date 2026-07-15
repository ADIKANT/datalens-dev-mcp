# Security policy

## Supported versions

Security fixes are applied to the latest published release and to the `main`
branch. Older releases may not receive backports while the project remains in
alpha.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting flow:

<https://github.com/ADIKANT/datalens-dev-mcp/security/advisories/new>

Do not open a public issue for a suspected vulnerability. Include a minimal
reproduction, affected version, impact, and suggested mitigation when known.
Use synthetic values only: never attach a working IAM token, authorization
header, private workbook export, customer data, or private key.

The maintainer will acknowledge reports and coordinate remediation on a
best-effort basis. Please allow time for a fix and release before public
disclosure.

If a real credential was exposed, revoke or rotate it with the credential
issuer immediately. Removing it from a message or commit does not invalidate
the credential.

## Security model

`datalens-dev-mcp` is a local stdio server. It inherits the permissions of the
local account and the MCP client that launches it. It is not a sandbox and
must not be exposed directly as a network service.

The intended defaults are:

- no hosted listener or inbound network port;
- no live DataLens calls in CI;
- write mode disabled unless `DATALENS_MCP_ENABLE_WRITES=1` is explicitly set;
- expert RPC disabled unless `DATALENS_MCP_ENABLE_EXPERT_RPC=1` is explicitly
  set;
- mutations governed by planning, fresh-read, revision, save, readback, and
  delivery-intent gates;
- secrets loaded from the local environment or an ignored environment file,
  never from tracked configuration.

Operators are responsible for restricting filesystem access to token files,
reviewing enabled tools in their MCP client, and using least-privilege Yandex
Cloud credentials. Debug logs and bug reports must not print token values,
token prefixes, authorization headers, org IDs, or private object payloads.

## Scope boundaries

This policy covers vulnerabilities in this repository. Account compromise,
Yandex Cloud service incidents, credential recovery, and DataLens product
support must be handled through the applicable upstream support channel. This
independent project is not affiliated with or supported by Yandex LLC.
