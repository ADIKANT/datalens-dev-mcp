# DataLens API Contract

Source trace: external docs corpus `raw/api/openapi.json`, `api_inventory.json`, `reports/content_hashes.json`, and normalized Editor docs under `raw/md/`.

## Transport

- Curated operations are `POST /rpc/<method>` JSON RPC-style calls under `https://api.datalens.tech`.
- Required request headers are `Authorization: Bearer <IAM_TOKEN>`, `x-dl-org-id: <ORG_ID>`, `x-dl-api-version: 2`, `content-type: application/json`, and `accept: application/json`.
- Runtime default API version is `auto`: the intended request goes directly to the compiled current version. No read or write request falls back to v1; explicit `DATALENS_API_VERSION=1` is a read-only compatibility mode and `latest` is read-only.
- The client sanitizes diagnostics and must not print token values, token prefixes, token lengths, auth headers, or subject tokens.

## Support Status Contract

- `EXECUTABLE_TOOL_SUPPORTED`: callable through a read-only MCP tool or `dl_rpc_readonly` without enabling writes.
- `PLAN_ONLY_SUPPORTED`: official method and schema evidence exist, but MCP returns a safe-apply plan and does not execute by default.
- `READ_ONLY_REFERENCE`: documented for import/read/reference only; not used as an executable chart creation route.
- `UNSUPPORTED_NO_VALIDATED_METHOD`: official method is outside the validated local MCP workflow or lacks a safe payload contract.

## Write Safety

- Guarded writes are plan-only until safe apply is approved, writes are explicitly enabled, a fresh read preserves revision/unknown fields, `save` semantics are chosen, and readback is recorded.
- Delete, move, rename, permission, license mutation, and QL delete are blocked from operator write routing.
- Dataset fields and calculated fields are represented through dataset payloads; no standalone official field RPC is claimed.
- Writes are never retried under a different API version.

