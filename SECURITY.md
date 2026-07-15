# Security policy

## Supported versions

Security fixes are applied to the latest published release and to `main`. Older alpha releases may not receive backports.

## Report a vulnerability

Use GitHub private vulnerability reporting:

<https://github.com/ADIKANT/datalens-dev-mcp/security/advisories/new>

Include a minimal reproduction, affected version, impact, and suggested mitigation when known. Use synthetic values. Never attach a working IAM token, authorization header, private workbook export, customer data, or private key.

If a real credential was exposed, revoke or rotate it immediately. Removing it from a message or commit does not invalidate it.

## Runtime security model

`datalens-dev-mcp` is a local stdio server. It inherits the permissions of the local user and the MCP client. It does not provide a network listener or hosted service.

The standard runtime is ready for write, save, and publish. The user request selects the operation:

- audit, review, diagnose, and plan-only requests do not write;
- save-only and no-publish stop after saved readback;
- create, fix, update, enhance, and redesign requests continue through save, saved readback, publish from saved state, and published readback;
- deleting a complete DataLens object requires a separate confirmation with exact IDs and an unchanged plan.

Before each write, the server checks the target, reads current saved state, preserves revision and unknown fields, validates the payload, and reads the result. Publishing is built only from verified saved state. Removing content inside an object is an update; object moves, permission changes, and credential mutations are unsupported.

Set `DATALENS_MCP_ENABLE_WRITES`, `DATALENS_MCP_LIVE_ALLOW_SAVE`, or `DATALENS_MCP_LIVE_ALLOW_PUBLISH` to `0` to hard-disable that capability. Keep `DATALENS_MCP_ENABLE_EXPERT_RPC=0` in user configuration.

## Credential handling

Store IAM tokens in a separate `DATALENS_ENV_FILE` with `0600` permissions. The server sanitizes responses, artifacts, and errors for token, authorization, password, and private-key material. Debug logs and public reports must not contain token values, token prefixes, authorization headers, organization IDs, or private object payloads.

The server can use an initialized `yc` CLI to obtain or refresh an IAM token. New tokens are atomically written to the canonical env file. Restrict filesystem access to that file and grant the account only the DataLens roles it needs.

## Scope

This policy covers vulnerabilities in this repository. Account compromise, Yandex Cloud incidents, credential recovery, and DataLens product support belong to their respective upstream support channels. The project is independent of Yandex.
