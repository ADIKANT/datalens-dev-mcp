# Safety model

[Русский](local-only-safety-model.md) · **English** · [Project home](../README_en.md) · [Safe Apply](safe-apply_en.md)

`datalens-dev-mcp` runs locally over stdio and inherits the permissions of the user and MCP client. It opens outbound connections only to the configured DataLens API and does not start a network listener.

## Credentials

The IAM token and organization ID live in a separate `DATALENS_ENV_FILE` with `0600` permissions. The server sanitizes responses, reports, and error messages for tokens, authorization headers, passwords, and private keys.

Do not commit `.env`, `.env.local`, `.datalens.env`, `datalens_token.env`, private keys, or exports containing private data. See [DataLens access](access_en.md) for setup.

## Operation selection

The standard mode follows the user request:

- audits, reviews, and diagnostics read data;
- plan-only prepares a plan;
- save-only saves and performs saved readback;
- create/fix/update/enhance/redesign saves, verifies saved state, publishes it, and verifies published state.

The server does not ask again before ordinary save or publish. A `0` value in a write/save/publish env switch hard-disables that capability.

## Write safeguards

Before every write request, the server:

1. checks the exact target type and ID;
2. reads current saved state again;
3. verifies revision and expected fields;
4. overlays only the requested change while preserving other fields;
5. validates the payload against object schemas and rules;
6. reads saved state after save;
7. builds publishing only from verified saved state;
8. reads published state after publish.

A revision conflict, object lock, uniqueness conflict, or unknown write outcome stops the flow for reconciliation.

## Deletion

Arbitrary whole-object deletion is unsupported. Only a project-manifest
`retire_legacy_objects` action uses separate confirmation: the first call
returns exact IDs, relations, and the plan hash, and the second passes
`confirm_delete=true` for that same plan. A changed plan must be confirmed
again. Whole-object QL deletion is unsupported.

Removing an element inside an object, such as a legend, filter, column, tab, or widget, is an update. Object moves, permission changes, and credential mutations are unsupported.

## Local files

Tools create plans, snapshots, and reports inside the selected `--project-root` or an explicitly supplied path. Give the server a dedicated workspace and restrict its filesystem permissions appropriately.

See [Safe Apply](safe-apply_en.md) for the write sequence.
