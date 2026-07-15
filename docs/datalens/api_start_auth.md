# DataLens API Start And Auth

Source trace: `https://yandex.cloud/ru/docs/datalens/operations/api-start` and live OpenAPI security schemes.

- Required headers: `accept: application/json`, `content-type: application/json`, `x-dl-api-version: 2`, `x-dl-org-id: <ORG_ID>`, `Authorization: Bearer <IAM_TOKEN>`. Runtime default `DATALENS_API_VERSION=auto` selects the locally compiled version 2. `latest` and explicit v1 are read-only modes. Guarded writes are rejected before HTTP when the selected version differs from the required version in the local lock; v2 does not fall back to v1.
- Never log token values, token prefixes or token lengths.
- `dl_probe_auth` uses `getWorkbooksList` with a tiny page size as the read-only auth probe.
- Live credentials missing means `BLOCKED_LIVE_CREDENTIALS`; offline fixtures and plan generation still run.
